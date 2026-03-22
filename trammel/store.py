"""SQLite store: recipes (strategy patterns), plans, steps, constraints, trajectories."""

from __future__ import annotations

import json
import time
from typing import Any

from .store_recipes import RecipeStoreMixin
from .utils import db_connect, dumps_json, transaction


class RecipeStore(RecipeStoreMixin):
    def __init__(self, db_path: str = "trammel.db") -> None:
        self.db_path = db_path
        self.conn = db_connect(db_path)
        self._init_schema()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self) -> RecipeStore:
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipes (
                sig TEXT PRIMARY KEY,
                pattern TEXT NOT NULL,
                strategy TEXT NOT NULL,
                constraints TEXT NOT NULL DEFAULT '[]',
                successes INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL,
                updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                strategy TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                current_step INTEGER NOT NULL DEFAULT 0,
                total_steps INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL,
                updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                description TEXT NOT NULL,
                rationale TEXT NOT NULL DEFAULT '',
                depends_on TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'pending',
                edits_json TEXT NOT NULL DEFAULT '[]',
                verification TEXT,
                constraints_found TEXT NOT NULL DEFAULT '[]',
                created REAL NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            );
            CREATE TABLE IF NOT EXISTS constraints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                step_id INTEGER,
                constraint_type TEXT NOT NULL,
                description TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created REAL NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id),
                FOREIGN KEY (step_id) REFERENCES steps(id)
            );
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                beam_id INTEGER NOT NULL,
                strategy_variant TEXT NOT NULL,
                steps_completed INTEGER NOT NULL DEFAULT 0,
                outcome TEXT NOT NULL,
                failure_reason TEXT,
                created REAL NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            );
            CREATE TABLE IF NOT EXISTS recipe_trigrams (
                trigram TEXT NOT NULL,
                recipe_sig TEXT NOT NULL,
                FOREIGN KEY (recipe_sig) REFERENCES recipes(sig)
            );
            CREATE INDEX IF NOT EXISTS idx_recipe_trigrams_tri
                ON recipe_trigrams(trigram);
            CREATE TABLE IF NOT EXISTS recipe_files (
                recipe_sig TEXT NOT NULL,
                file_path TEXT NOT NULL,
                FOREIGN KEY (recipe_sig) REFERENCES recipes(sig)
            );
            CREATE INDEX IF NOT EXISTS idx_recipe_files_sig
                ON recipe_files(recipe_sig);
            CREATE INDEX IF NOT EXISTS idx_recipe_files_path
                ON recipe_files(file_path);
        """)
        self.conn.commit()
        self._rebuild_trigram_index()
        self._backfill_files()

    # ── Plans ────────────────────────────────────────────────────────────────

    def create_plan(self, goal: str, strategy: dict[str, Any]) -> int:
        now = time.time()
        plan_steps = strategy.get("steps", [])
        with transaction(self.conn):
            cur = self.conn.execute(
                "INSERT INTO plans (goal, strategy, status, current_step, total_steps, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (goal, dumps_json(strategy), "pending", 0, len(plan_steps), now, now),
            )
            plan_id = int(cur.lastrowid)
            for i, step in enumerate(plan_steps):
                self.conn.execute(
                    "INSERT INTO steps (plan_id, step_index, description, rationale, depends_on, status, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        plan_id,
                        i,
                        step.get("description", ""),
                        step.get("rationale", ""),
                        dumps_json(step.get("depends_on", [])),
                        "pending",
                        now,
                    ),
                )
        return plan_id

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, goal, strategy, status, current_step, total_steps, created, updated "
            "FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        if not row:
            return None
        steps = self.conn.execute(
            "SELECT id, step_index, description, rationale, depends_on, status, "
            "edits_json, verification, constraints_found "
            "FROM steps WHERE plan_id = ? ORDER BY step_index",
            (plan_id,),
        ).fetchall()
        return {
            "id": row[0],
            "goal": row[1],
            "strategy": json.loads(row[2]),
            "status": row[3],
            "current_step": row[4],
            "total_steps": row[5],
            "created": row[6],
            "updated": row[7],
            "steps": [
                {
                    "id": s[0],
                    "step_index": s[1],
                    "description": s[2],
                    "rationale": s[3],
                    "depends_on": json.loads(s[4]),
                    "status": s[5],
                    "edits": json.loads(s[6]),
                    "verification": json.loads(s[7]) if s[7] else None,
                    "constraints_found": json.loads(s[8]),
                }
                for s in steps
            ],
        }

    def update_plan_status(self, plan_id: int, status: str) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE plans SET status = ?, updated = ? WHERE id = ?",
                (status, time.time(), plan_id),
            )

    def list_plans(self, status: str | None = None) -> list[dict[str, Any]]:
        query = ("SELECT id, goal, status, current_step, total_steps, created, updated "
                 "FROM plans")
        params: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        rows = self.conn.execute(query + " ORDER BY id DESC", params).fetchall()
        return [
            {
                "id": r[0], "goal": r[1], "status": r[2],
                "current_step": r[3], "total_steps": r[4],
                "created": r[5], "updated": r[6],
            }
            for r in rows
        ]

    # ── Steps ────────────────────────────────────────────────────────────────

    def update_step(
        self,
        step_id: int,
        status: str,
        edits: list[dict[str, Any]] | None = None,
        verification: dict[str, Any] | None = None,
        constraints_found: list[dict[str, Any]] | None = None,
    ) -> None:
        updates = ["status = ?"]
        params: list[Any] = [status]
        if edits is not None:
            updates.append("edits_json = ?")
            params.append(dumps_json(edits))
        if verification is not None:
            updates.append("verification = ?")
            params.append(dumps_json(verification))
        if constraints_found is not None:
            updates.append("constraints_found = ?")
            params.append(dumps_json(constraints_found))
        params.append(step_id)
        with transaction(self.conn):
            self.conn.execute(
                f"UPDATE steps SET {', '.join(updates)} WHERE id = ?", tuple(params)
            )

    def get_step(self, step_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT id, plan_id, step_index, description, rationale, depends_on, "
            "status, edits_json, verification, constraints_found "
            "FROM steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "plan_id": row[1], "step_index": row[2],
            "description": row[3], "rationale": row[4],
            "depends_on": json.loads(row[5]), "status": row[6],
            "edits": json.loads(row[7]),
            "verification": json.loads(row[8]) if row[8] else None,
            "constraints_found": json.loads(row[9]),
        }

    # ── Constraints ──────────────────────────────────────────────────────────

    def add_constraint(
        self,
        constraint_type: str,
        description: str,
        context: dict[str, Any] | None = None,
        plan_id: int | None = None,
        step_id: int | None = None,
    ) -> int:
        with transaction(self.conn):
            cur = self.conn.execute(
                "INSERT INTO constraints (plan_id, step_id, constraint_type, description, context, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (plan_id, step_id, constraint_type, description, dumps_json(context or {}), time.time()),
            )
        return int(cur.lastrowid)

    def get_active_constraints(
        self, constraint_type: str | None = None
    ) -> list[dict[str, Any]]:
        query = ("SELECT id, plan_id, step_id, constraint_type, description, context, created "
                 "FROM constraints WHERE active = 1")
        params: tuple[str, ...] = ()
        if constraint_type:
            query += " AND constraint_type = ?"
            params = (constraint_type,)
        rows = self.conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0], "plan_id": r[1], "step_id": r[2], "type": r[3],
                "description": r[4], "context": json.loads(r[5]), "created": r[6],
            }
            for r in rows
        ]

    def deactivate_constraint(self, constraint_id: int) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE constraints SET active = 0 WHERE id = ?", (constraint_id,)
            )

    # ── Trajectories ─────────────────────────────────────────────────────────

    def log_trajectory(
        self,
        plan_id: int,
        beam_id: int,
        strategy_variant: str,
        steps_completed: int,
        outcome: dict[str, Any],
        failure_reason: str | None = None,
    ) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "INSERT INTO trajectories "
                "(plan_id, beam_id, strategy_variant, steps_completed, outcome, failure_reason, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (plan_id, beam_id, strategy_variant, steps_completed,
                 dumps_json(outcome), failure_reason, time.time()),
            )

    def get_strategy_stats(self) -> dict[str, tuple[int, int]]:
        """Return {variant_name: (successes, failures)} aggregated from all trajectories."""
        rows = self.conn.execute(
            "SELECT strategy_variant, outcome FROM trajectories"
        ).fetchall()
        stats: dict[str, list[int]] = {}
        for variant, outcome_str in rows:
            pair = stats.setdefault(variant, [0, 0])
            success = False
            try:
                success = json.loads(outcome_str).get("success", False)
            except (json.JSONDecodeError, TypeError):
                success = False
            pair[0 if success else 1] += 1
        return {k: tuple(v) for k, v in stats.items()}

    def get_trajectories(self, plan_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, beam_id, strategy_variant, steps_completed, outcome, failure_reason, created "
            "FROM trajectories WHERE plan_id = ? ORDER BY id",
            (plan_id,),
        ).fetchall()
        return [
            {
                "id": r[0], "beam_id": r[1], "strategy_variant": r[2],
                "steps_completed": r[3], "outcome": json.loads(r[4]),
                "failure_reason": r[5], "created": r[6],
            }
            for r in rows
        ]
