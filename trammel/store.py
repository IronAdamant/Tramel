"""SQLite store: recipes (strategy patterns), plans, steps, constraints, trajectories."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from .store_agents import AgentStoreMixin
from .store_recipes import RecipeStoreMixin
from .utils import db_connect, dumps_json, transaction


class RecipeStore(RecipeStoreMixin, AgentStoreMixin):
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

    _SCHEMA_RECIPE_TABLES = """
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
    """

    _SCHEMA_FAILURE_PATTERNS = """
        CREATE TABLE IF NOT EXISTS failure_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL DEFAULT '',
            test_file TEXT,
            occurrences INTEGER NOT NULL DEFAULT 1,
            last_resolution TEXT,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_failure_patterns_file
            ON failure_patterns(file_path);
    """

    _SCHEMA_TELEMETRY = """
        CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            value REAL,
            created REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usage_events_type
            ON usage_events(event_type);
    """

    _SCHEMA_PLAN_TABLES = """
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
    """

    def _init_schema(self) -> None:
        self.conn.executescript(
            self._SCHEMA_RECIPE_TABLES + self._SCHEMA_PLAN_TABLES
            + self._SCHEMA_FAILURE_PATTERNS + self._SCHEMA_TELEMETRY
        )
        # Add multi-agent columns (safe migration for existing DBs)
        for col, default in [("claimed_by TEXT", "NULL"), ("claimed_at REAL", "NULL")]:
            try:
                self.conn.execute(f"ALTER TABLE steps ADD COLUMN {col} DEFAULT {default}")
            except sqlite3.OperationalError:
                pass  # column already exists
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
                    (plan_id, i, step.get("description", ""), step.get("rationale", ""),
                     dumps_json(step.get("depends_on", [])), "pending", now),
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
            "edits_json, verification, constraints_found, claimed_by, claimed_at "
            "FROM steps WHERE plan_id = ? ORDER BY step_index",
            (plan_id,),
        ).fetchall()
        return {
            "id": row[0], "goal": row[1], "strategy": json.loads(row[2]),
            "status": row[3], "current_step": row[4], "total_steps": row[5],
            "created": row[6], "updated": row[7],
            "steps": [
                {"id": s[0], "step_index": s[1], "description": s[2], "rationale": s[3],
                 "depends_on": json.loads(s[4]), "status": s[5], "edits": json.loads(s[6]),
                 "verification": json.loads(s[7]) if s[7] else None,
                 "constraints_found": json.loads(s[8]),
                 "claimed_by": s[9], "claimed_at": s[10]}
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
        if status is not None:
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
        # Auto-record failure patterns when step fails with verification data
        if status == "failed" and verification:
            fa = verification.get("failure_analysis", {})
            if fa.get("file") and fa.get("error_type"):
                self.record_failure_pattern(
                    fa["file"], fa["error_type"], fa.get("message", ""),
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

    def get_plan_progress(self, plan_id: int) -> dict[str, Any] | None:
        """Get plan state with accumulated edits from passed steps for resumption."""
        plan = self.get_plan(plan_id)
        if plan is None:
            return None
        prior_edits: list[dict[str, Any]] = []
        next_step_index = 0
        for step in plan["steps"]:
            if step["status"] == "passed":
                prior_edits.extend(step.get("edits") or [])
                next_step_index = step["step_index"] + 1
            else:
                break
        remaining = [s for s in plan["steps"] if s["step_index"] >= next_step_index]
        return {
            **plan,
            "prior_edits": prior_edits,
            "next_step_index": next_step_index,
            "remaining_steps": remaining,
            "completed_count": next_step_index,
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
            try:
                success = json.loads(outcome_str).get("success", False)
            except (json.JSONDecodeError, TypeError):
                success = False
            pair[0 if success else 1] += 1
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

    # ── Failure patterns ─────────────────────────────────────────────────────

    def record_failure_pattern(
        self, file_path: str, error_type: str, error_message: str = "", test_file: str | None = None,
    ) -> None:
        now = time.time()
        with transaction(self.conn):
            existing = self.conn.execute(
                "SELECT id FROM failure_patterns WHERE file_path = ? AND error_type = ?",
                (file_path, error_type),
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE failure_patterns SET occurrences = occurrences + 1, "
                    "error_message = ?, last_seen = ? WHERE id = ?",
                    (error_message[:200], now, existing[0]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO failure_patterns "
                    "(file_path, error_type, error_message, test_file, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (file_path, error_type, error_message[:200], test_file, now, now),
                )

    def resolve_failure_pattern(self, file_path: str, error_type: str, resolution: str) -> None:
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE failure_patterns SET last_resolution = ? "
                "WHERE file_path = ? AND error_type = ?",
                (resolution[:200], file_path, error_type),
            )

    def get_failure_history(
        self, file_path: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get failure patterns, optionally filtered by file. Sorted by frequency."""
        query = ("SELECT file_path, error_type, error_message, test_file, "
                 "occurrences, last_resolution, first_seen, last_seen FROM failure_patterns")
        params: tuple[Any, ...] = (limit,)
        if file_path is not None:
            query += " WHERE file_path = ?"
            params = (file_path, limit)
        rows = self.conn.execute(query + " ORDER BY occurrences DESC LIMIT ?", params).fetchall()
        return [
            {"file": r[0], "error_type": r[1], "message": r[2], "test_file": r[3],
             "occurrences": r[4], "last_resolution": r[5], "first_seen": r[6], "last_seen": r[7]}
            for r in rows
        ]

    # ── Status summary ─────────────────────────────────────────────────────

    def get_status_summary(self) -> dict[str, Any]:
        """Return a summary of current state: recipe, plan, and constraint counts."""
        recipes = self.conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        plans = self.conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
        active = self.conn.execute(
            "SELECT COUNT(*) FROM plans WHERE status IN ('pending','running')"
        ).fetchone()[0]
        constraints = self.conn.execute(
            "SELECT COUNT(*) FROM constraints WHERE active = 1"
        ).fetchone()[0]
        return {
            "recipes": recipes,
            "plans_total": plans,
            "plans_active": active,
            "constraints_active": constraints,
        }

    # ── Telemetry ───────────────────────────────────────────────────────────

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Record a usage event for telemetry."""
        try:
            self.conn.execute(
                "INSERT INTO usage_events (event_type, detail, value, created) VALUES (?, ?, ?, ?)",
                (event_type, detail, value, time.time()),
            )
            self.conn.commit()
        except Exception:
            logging.getLogger(__name__).debug("telemetry write failed", exc_info=True)

    def get_usage_stats(self, days: int = 30) -> dict[str, Any]:
        """Aggregate usage telemetry over the given window."""
        cutoff = time.time() - (days * 86400)
        rows = self.conn.execute(
            "SELECT event_type, detail, value FROM usage_events WHERE created >= ?", (cutoff,),
        ).fetchall()
        tool_calls: dict[str, int] = {}
        hits, misses, scores = 0, 0, []
        for etype, detail, value in rows:
            if etype == "tool_call":
                tool_calls[detail] = tool_calls.get(detail, 0) + 1
            elif etype == "recipe_hit":
                hits += 1
                if value is not None:
                    scores.append(value)
            elif etype == "recipe_miss":
                misses += 1
        total = hits + misses
        return {
            "tool_calls": tool_calls, "total_tool_calls": sum(tool_calls.values()),
            "recipe_hits": hits, "recipe_misses": misses,
            "recipe_hit_rate": hits / total if total > 0 else 0.0,
            "avg_hit_score": sum(scores) / len(scores) if scores else 0.0,
            "strategy_win_rates": {
                n: s / (s + f) if (s + f) > 0 else 0.0
                for n, (s, f) in self.get_strategy_stats().items()
            },
            "days": days, "total_events": len(rows),
        }
