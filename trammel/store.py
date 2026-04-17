"""SQLite store: recipes (strategy patterns), plans, steps, constraints, trajectories."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any

from .store_agents import AgentStoreMixin
from .store_plans import PlanStoreMixin
from .store_recipes import RecipeStoreMixin
from .store_retrieval import RecipeRetrievalMixin
from .store_scaffolds import ScaffoldRecipeMixin
from .store_telemetry import TelemetryMixin
from .utils import DEFAULT_DB_PATH, db_connect, dumps_json, transaction

_log = logging.getLogger(__name__)


class RecipeStore(
    RecipeStoreMixin,
    RecipeRetrievalMixin,
    ScaffoldRecipeMixin,
    PlanStoreMixin,
    TelemetryMixin,
    AgentStoreMixin,
):
    """SQLite-backed store for plans, recipes, scaffolds, constraints, and telemetry.

    Composes mixins for each concern: recipe CRUD + retrieval, scaffold
    recipes, plan/step management, agent step-claiming, and telemetry.
    Use as a context manager (``with RecipeStore() as store:``) so the
    connection is closed even on errors.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        """Open (or create) the SQLite database at ``db_path`` and apply migrations."""
        self.db_path = db_path
        self.conn = db_connect(db_path)
        self._init_schema()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self) -> RecipeStore:
        """Return self; supports ``with RecipeStore() as store:`` usage."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Close the database connection on context-manager exit."""
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
        CREATE TABLE IF NOT EXISTS scaffold_recipes (
            sig TEXT PRIMARY KEY,
            pattern TEXT NOT NULL,
            scaffold TEXT NOT NULL,
            domain_kw TEXT NOT NULL DEFAULT '',
            role_counts TEXT NOT NULL DEFAULT '{}',
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL,
            updated REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scaffold_trigrams (
            trigram TEXT NOT NULL,
            scaffold_sig TEXT NOT NULL,
            FOREIGN KEY (scaffold_sig) REFERENCES scaffold_recipes(sig)
        );
        CREATE INDEX IF NOT EXISTS idx_scaffold_trigrams_tri
            ON scaffold_trigrams(trigram);
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
            scaffold TEXT NOT NULL DEFAULT '[]',
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
        for col, default in [
            ("claimed_by TEXT", "NULL"),
            ("claimed_at REAL", "NULL"),
        ]:
            try:
                self.conn.execute(f"ALTER TABLE steps ADD COLUMN {col} DEFAULT {default}")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e):
                    raise
        # Add scaffold column to plans table (migration for pre-scaffold DBs)
        try:
            self.conn.execute("ALTER TABLE plans ADD COLUMN scaffold TEXT NOT NULL DEFAULT '[]'")
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e):
                raise
        self.conn.commit()
        self._rebuild_trigram_index()
        self._backfill_files()
        self._init_scaffold_schema()
        self._init_recipe_index_schema()
        self.backfill_recipe_index()


    # ── Constraints ──────────────────────────────────────────────────────────

    def add_constraint(
        self,
        constraint_type: str,
        description: str,
        context: dict[str, Any] | None = None,
        plan_id: int | None = None,
        step_id: int | None = None,
    ) -> int:
        """Record a failure constraint and return its new ID.

        Constraints are checked during decomposition and propagated to
        future sessions so the same bad approach is not retried.
        """
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
        """Return active constraints, optionally filtered by ``constraint_type``."""
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
        """Mark a constraint inactive so it no longer influences planning."""
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
        """Persist a beam's execution trajectory for later strategy-stat aggregation."""
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

