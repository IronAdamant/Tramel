"""SQLite store: recipes (strategy patterns), plans, steps, constraints, trajectories."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from .store_agents import AgentStoreMixin
from .store_recipes import RecipeStoreMixin
from .utils import DEFAULT_DB_PATH, db_connect, dumps_json, transaction

_log = logging.getLogger(__name__)


_STEP_COLUMNS = (
    "id, plan_id, step_index, description, rationale, depends_on, "
    "status, edits_json, verification, constraints_found, claimed_by, claimed_at, created"
)


def _step_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a step row to a dictionary with parsed JSON fields."""
    return {
        "id": row["id"], "plan_id": row["plan_id"],
        "step_index": row["step_index"],
        "description": row["description"], "rationale": row["rationale"],
        "depends_on": json.loads(row["depends_on"]),
        "status": row["status"], "edits": json.loads(row["edits_json"]),
        "verification": json.loads(row["verification"]) if row["verification"] else None,
        "constraints_found": json.loads(row["constraints_found"]),
        "claimed_by": row["claimed_by"], "claimed_at": row["claimed_at"],
        "created": row["created"],
    }


class RecipeStore(RecipeStoreMixin, AgentStoreMixin):
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
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
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    raise
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
            f"SELECT {_STEP_COLUMNS} FROM steps WHERE plan_id = ? ORDER BY step_index",
            (plan_id,),
        ).fetchall()
        return {
            "id": row["id"], "goal": row["goal"],
            "strategy": json.loads(row["strategy"]),
            "status": row["status"], "current_step": row["current_step"],
            "total_steps": row["total_steps"],
            "created": row["created"], "updated": row["updated"],
            "steps": [_step_to_dict(s) for s in steps],
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
                "id": r["id"], "goal": r["goal"], "status": r["status"],
                "current_step": r["current_step"], "total_steps": r["total_steps"],
                "created": r["created"], "updated": r["updated"],
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

    def update_steps_batch(
        self,
        updates: list[dict[str, Any]],
    ) -> int:
        """Batch-update multiple steps in a single transaction.

        Each entry should have: step_id, status.  Optionally: edits, verification.
        Designed for P6 single-agent workflows where per-step record_step is overhead.

        Returns count of steps updated.
        """
        if not updates:
            return 0
        count = 0
        failure_patterns: list[tuple[str, str, str]] = []
        with transaction(self.conn):
            for entry in updates:
                step_id = entry["step_id"]
                status = entry["status"]
                cols = ["status = ?"]
                params: list[Any] = [status]
                if entry.get("edits") is not None:
                    cols.append("edits_json = ?")
                    params.append(dumps_json(entry["edits"]))
                if entry.get("verification") is not None:
                    cols.append("verification = ?")
                    params.append(dumps_json(entry["verification"]))
                params.append(step_id)
                self.conn.execute(
                    f"UPDATE steps SET {', '.join(cols)} WHERE id = ?", tuple(params),
                )
                count += 1
                if status == "failed" and entry.get("verification"):
                    fa = entry["verification"].get("failure_analysis", {})
                    if fa.get("file") and fa.get("error_type"):
                        failure_patterns.append(
                            (fa["file"], fa["error_type"], fa.get("message", "")),
                        )
        for file_path, error_type, message in failure_patterns:
            self.record_failure_pattern(file_path, error_type, message)
        return count

    def get_step(self, step_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT {_STEP_COLUMNS} FROM steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        return _step_to_dict(row) if row else None

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

    # ── Compound operations ────────────────────────────────────────────────

    def complete_plan(
        self,
        plan_id: int,
        outcome: bool,
        step_status: str = "passed",
    ) -> dict[str, Any]:
        """Finalize a plan in one call: batch-update pending steps, set plan
        status, and save the strategy as a recipe.

        Designed for single-agent workflows where per-step claim/record/verify
        overhead is disproportionate.

        Args:
            plan_id: Plan to complete.
            outcome: True if the work succeeded (saves recipe as success).
            step_status: Status to assign to all still-pending steps
                         ("passed" or "skipped").  Already-recorded steps
                         are left untouched.

        Returns:
            Summary dict with counts and the recipe sig.
        """
        plan = self.get_plan(plan_id)
        if plan is None:
            return {"error": "plan not found"}

        now = time.time()
        steps_updated = 0
        with transaction(self.conn):
            for step in plan["steps"]:
                if step["status"] == "pending":
                    self.conn.execute(
                        "UPDATE steps SET status = ? WHERE id = ?",
                        (step_status, step["id"]),
                    )
                    steps_updated += 1

            plan_status = "completed" if outcome else "failed"
            self.conn.execute(
                "UPDATE plans SET status = ?, updated = ? WHERE id = ?",
                (plan_status, now, plan_id),
            )

        strategy = plan["strategy"]
        self.save_recipe(plan["goal"], strategy, outcome)

        return {
            "plan_id": plan_id,
            "plan_status": plan_status,
            "steps_updated": steps_updated,
            "recipe_saved": outcome,
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
                "id": r["id"], "plan_id": r["plan_id"], "step_id": r["step_id"],
                "type": r["constraint_type"], "description": r["description"],
                "context": json.loads(r["context"]), "created": r["created"],
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
        for r in rows:
            pair = stats.setdefault(r["strategy_variant"], [0, 0])
            try:
                success = json.loads(r["outcome"]).get("success", False)
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
                "id": r["id"], "beam_id": r["beam_id"],
                "strategy_variant": r["strategy_variant"],
                "steps_completed": r["steps_completed"],
                "outcome": json.loads(r["outcome"]),
                "failure_reason": r["failure_reason"], "created": r["created"],
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
                    (error_message[:200], now, existing["id"]),
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
        params: tuple[str | int, ...] = (limit,)
        if file_path is not None:
            query += " WHERE file_path = ?"
            params = (file_path, limit)
        rows = self.conn.execute(query + " ORDER BY occurrences DESC LIMIT ?", params).fetchall()
        return [
            {"file": r["file_path"], "error_type": r["error_type"],
             "message": r["error_message"], "test_file": r["test_file"],
             "occurrences": r["occurrences"], "last_resolution": r["last_resolution"],
             "first_seen": r["first_seen"], "last_seen": r["last_seen"]}
            for r in rows
        ]

    # ── Status summary ─────────────────────────────────────────────────────

    def get_status_summary(self) -> dict[str, Any]:
        """Return a summary of current state: recipe, plan, and constraint counts."""
        row = self.conn.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM recipes) AS recipe_count, "
            "(SELECT COUNT(*) FROM plans) AS plan_count, "
            "(SELECT COUNT(*) FROM plans WHERE status IN ('pending','running')) AS active_count, "
            "(SELECT COUNT(*) FROM constraints WHERE active = 1) AS constraint_count"
        ).fetchone()
        return {
            "recipes": row["recipe_count"],
            "plans_total": row["plan_count"],
            "plans_active": row["active_count"],
            "constraints_active": row["constraint_count"],
        }

    # ── Telemetry ───────────────────────────────────────────────────────────

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Record a usage event for telemetry."""
        try:
            with transaction(self.conn):
                self.conn.execute(
                    "INSERT INTO usage_events (event_type, detail, value, created) VALUES (?, ?, ?, ?)",
                    (event_type, detail, value, time.time()),
                )
        except sqlite3.Error:
            _log.debug("telemetry write failed", exc_info=True)

    def get_usage_stats(self, days: int = 30) -> dict[str, Any]:
        """Aggregate usage telemetry over the given window."""
        cutoff = time.time() - (days * 86400)
        rows = self.conn.execute(
            "SELECT event_type, detail, value FROM usage_events WHERE created >= ?", (cutoff,),
        ).fetchall()
        tool_calls: dict[str, int] = {}
        hits, misses, scores = 0, 0, []
        for r in rows:
            etype, detail, value = r["event_type"], r["detail"], r["value"]
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
            # Laplace-smoothed win rate: +1 in denominator avoids division by zero
            # and dampens rates for strategies with few observations
            "strategy_win_rates": {
                n: s / (s + f + 1)
                for n, (s, f) in self.get_strategy_stats().items()
            },
            "days": days, "total_events": len(rows),
        }
