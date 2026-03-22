"""SQLite store: recipes (strategy patterns), plans, steps, constraints, trajectories."""

from __future__ import annotations

import json
import time
from typing import Any

from .utils import (
    db_connect, dumps_json, sha256_json, transaction,
    trigram_bag_cosine, unique_trigrams,
)


class RecipeStore:
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
        self._backfill_trigrams()
        self._backfill_files()

    def _backfill_trigrams(self) -> None:
        """Populate recipe_trigrams for any recipes that lack trigram entries."""
        orphans = self.conn.execute(
            "SELECT sig, pattern FROM recipes WHERE sig NOT IN "
            "(SELECT DISTINCT recipe_sig FROM recipe_trigrams)"
        ).fetchall()
        if not orphans:
            return
        with transaction(self.conn):
            for sig, pattern in orphans:
                tris = unique_trigrams(pattern)
                self.conn.executemany(
                    "INSERT INTO recipe_trigrams (trigram, recipe_sig) VALUES (?, ?)",
                    [(t, sig) for t in tris],
                )

    def _backfill_files(self) -> None:
        """Populate recipe_files for recipes that lack file entries."""
        orphans = self.conn.execute(
            "SELECT sig, strategy FROM recipes WHERE sig NOT IN "
            "(SELECT DISTINCT recipe_sig FROM recipe_files)"
        ).fetchall()
        if not orphans:
            return
        with transaction(self.conn):
            for sig, strategy_str in orphans:
                try:
                    strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                files = {s.get("file") for s in strategy.get("steps", []) if s.get("file")}
                if files:
                    self.conn.executemany(
                        "INSERT INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                        [(sig, f) for f in files],
                    )

    # ── Recipes ──────────────────────────────────────────────────────────────

    def save_recipe(
        self,
        goal: str,
        strategy: dict[str, Any],
        outcome: bool,
        constraints: list[dict[str, Any]] | None = None,
    ) -> None:
        sig = sha256_json(strategy)
        pattern = goal[:200]
        strat_json = dumps_json(strategy)
        const_json = dumps_json(constraints or [])
        now = time.time()
        with transaction(self.conn):
            if outcome:
                self.conn.execute(
                    """INSERT INTO recipes (sig, pattern, strategy, constraints, successes, created, updated)
                       VALUES (?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT(sig) DO UPDATE SET
                           successes = recipes.successes + 1,
                           pattern = excluded.pattern,
                           constraints = excluded.constraints,
                           updated = excluded.updated""",
                    (sig, pattern, strat_json, const_json, now, now),
                )
            else:
                self.conn.execute(
                    """INSERT INTO recipes (sig, pattern, strategy, constraints, failures, created, updated)
                       VALUES (?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT(sig) DO UPDATE SET
                           failures = recipes.failures + 1,
                           pattern = excluded.pattern,
                           updated = excluded.updated""",
                    (sig, pattern, strat_json, const_json, now, now),
                )
            self.conn.execute(
                "DELETE FROM recipe_trigrams WHERE recipe_sig = ?", (sig,),
            )
            tris = unique_trigrams(pattern)
            if tris:
                self.conn.executemany(
                    "INSERT INTO recipe_trigrams (trigram, recipe_sig) VALUES (?, ?)",
                    [(t, sig) for t in tris],
                )
            # Index file paths
            self.conn.execute(
                "DELETE FROM recipe_files WHERE recipe_sig = ?", (sig,),
            )
            files = {s.get("file") for s in strategy.get("steps", []) if s.get("file")}
            if files:
                self.conn.executemany(
                    "INSERT INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                    [(sig, f) for f in files],
                )

    _W_TEXT = 0.5
    _W_FILES = 0.3
    _W_SUCCESS = 0.2

    def retrieve_best_recipe(
        self,
        goal: str,
        min_similarity: float = 0.3,
        context_files: set[str] | None = None,
    ) -> dict[str, Any] | None:
        goal_tris = unique_trigrams(goal)
        if not goal_tris:
            return None
        placeholders = ",".join("?" for _ in goal_tris)
        candidate_sigs = self.conn.execute(
            f"SELECT DISTINCT recipe_sig FROM recipe_trigrams "
            f"WHERE trigram IN ({placeholders})",
            tuple(goal_tris),
        ).fetchall()
        if not candidate_sigs:
            return None
        sig_tuple = tuple(row[0] for row in candidate_sigs)
        sig_ph = ",".join("?" for _ in sig_tuple)
        cur = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures FROM recipes "
            f"WHERE sig IN ({sig_ph})",
            sig_tuple,
        )
        best: dict[str, Any] | None = None
        best_score = -1.0
        for sig, pattern, strategy_str, succ, fail in cur:
            text_sim = trigram_bag_cosine(goal, pattern)
            if text_sim < min_similarity:
                continue

            if context_files is not None:
                # Composite scoring
                recipe_file_rows = self.conn.execute(
                    "SELECT file_path FROM recipe_files WHERE recipe_sig = ?", (sig,),
                ).fetchall()
                recipe_files = {r[0] for r in recipe_file_rows}
                if recipe_files and context_files:
                    intersection = context_files & recipe_files
                    union = context_files | recipe_files
                    file_overlap = len(intersection) / len(union)
                else:
                    file_overlap = 0.0

                total = succ + fail
                success_ratio = succ / total if total > 0 else 0.5

                score = (
                    self._W_TEXT * text_sim
                    + self._W_FILES * file_overlap
                    + self._W_SUCCESS * success_ratio
                )
            else:
                # Backward-compatible text-only scoring
                score = text_sim

            if score > best_score:
                best_score = score
                best = json.loads(strategy_str)
                if context_files is None and text_sim == 1.0:
                    break
        return best

    def list_recipes(self, limit: int = 20) -> list[dict[str, Any]]:
        """List stored recipes with pattern, counts, and file paths."""
        rows = self.conn.execute(
            "SELECT sig, pattern, successes, failures, updated "
            "FROM recipes ORDER BY updated DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for sig, pattern, succ, fail, updated in rows:
            file_rows = self.conn.execute(
                "SELECT file_path FROM recipe_files WHERE recipe_sig = ?", (sig,),
            ).fetchall()
            result.append({
                "sig": sig[:12],
                "pattern": pattern,
                "successes": succ,
                "failures": fail,
                "files": [r[0] for r in file_rows],
                "updated": updated,
            })
        return result

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
        if status:
            rows = self.conn.execute(
                "SELECT id, goal, status, current_step, total_steps, created, updated "
                "FROM plans WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, goal, status, current_step, total_steps, created, updated "
                "FROM plans ORDER BY id DESC"
            ).fetchall()
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
        if constraint_type:
            rows = self.conn.execute(
                "SELECT id, plan_id, step_id, constraint_type, description, context, created "
                "FROM constraints WHERE active = 1 AND constraint_type = ?",
                (constraint_type,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, plan_id, step_id, constraint_type, description, context, created "
                "FROM constraints WHERE active = 1"
            ).fetchall()
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
            try:
                outcome = json.loads(outcome_str)
                if outcome.get("success"):
                    pair[0] += 1
                else:
                    pair[1] += 1
            except (json.JSONDecodeError, TypeError):
                pair[1] += 1
        return {k: (v[0], v[1]) for k, v in stats.items()}

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
