"""Telemetry + failure-pattern mixin for RecipeStore.

Split out of :mod:`store` to keep that module under the project's 500-LOC
target. Hosts read/write for per-file failure patterns and the
``usage_events`` aggregation used by ``usage_stats``.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .utils import transaction

if TYPE_CHECKING:
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_log = logging.getLogger(__name__)


class TelemetryMixin:
    """Failure-pattern recording, status summary, and telemetry aggregation."""

    conn: sqlite3.Connection

    def record_failure_pattern(
        self, file_path: str, error_type: str, error_message: str = "", test_file: str | None = None,
    ) -> None:
        """Record (or increment occurrences of) a file/error-type failure pattern."""
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
        """Attach a resolution note to an existing failure pattern."""
        with transaction(self.conn):
            self.conn.execute(
                "UPDATE failure_patterns SET last_resolution = ? "
                "WHERE file_path = ? AND error_type = ?",
                (resolution[:200], file_path, error_type),
            )

    def get_failure_history(
        self, file_path: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return failure patterns sorted by frequency, optionally filtered by file."""
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

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Record a usage event for telemetry (fire-and-forget; never raises)."""
        try:
            with transaction(self.conn):
                self.conn.execute(
                    "INSERT INTO usage_events (event_type, detail, value, created) VALUES (?, ?, ?, ?)",
                    (event_type, detail, value, time.time()),
                )
        except sqlite3.Error:
            _log.debug("telemetry write failed", exc_info=True)

    def get_usage_stats(self, days: int = 30) -> dict[str, Any]:
        """Aggregate tool-call counts, recipe hit/miss rates, and strategy win rates."""
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
            # and dampens rates for strategies with few observations.
            "strategy_win_rates": {
                n: s / (s + f + 1)
                for n, (s, f) in self.get_strategy_stats().items()
            },
            "days": days, "total_events": len(rows),
        }
