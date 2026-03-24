"""Recipe mixin: save, retrieve, list, prune recipes with trigram + composite scoring."""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any

from .utils import (
    dumps_json, goal_similarity, normalize_goal,
    sha256_json, transaction, unique_trigrams,
)

if TYPE_CHECKING:
    import sqlite3
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_MAX_PATTERN_LENGTH = 200
_MAX_LOG_GOAL_LENGTH = 100
_NEAR_PERFECT_SIMILARITY = 0.9999


def _sql_in(items: list[str] | tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Build an SQL IN clause and parameter tuple: ``'IN (?,?,?)' , (a, b, c)``.

    Raises ValueError on empty input (produces invalid SQL).
    """
    if not items:
        raise ValueError("_sql_in requires a non-empty sequence")
    ph = ",".join("?" for _ in items)
    return f"IN ({ph})", tuple(items)


class RecipeStoreMixin:
    """Recipe-related methods mixed into RecipeStore.

    Expects the composing class to provide:
        conn: sqlite3.Connection
        log_event(event_type, detail, value) -> None
    """

    conn: sqlite3.Connection

    # Fields stripped from strategy before computing the content-addressed sig.
    # These are volatile (change every run) or ephemeral (only meaningful during
    # a single session) and must not cause duplicate recipe entries.
    _VOLATILE_STRATEGY_KEYS = frozenset({"_source", "analysis_meta"})

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Provided by composing class."""
        raise NotImplementedError

    @classmethod
    def _stable_strategy_sig(cls, strategy: dict[str, Any]) -> str:
        """Compute a content-addressed sig from the stable subset of a strategy.

        Strips volatile fields (timing data, source tags) so that the same
        decomposition always produces the same sig regardless of when it ran.
        """
        stable = {k: v for k, v in strategy.items() if k not in cls._VOLATILE_STRATEGY_KEYS}
        return sha256_json(stable)

    def _insert_trigrams(self, sig: str, tris: set[str]) -> None:
        """Insert trigram index entries for a recipe."""
        if tris:
            self.conn.executemany(
                "INSERT INTO recipe_trigrams (trigram, recipe_sig) VALUES (?, ?)",
                [(t, sig) for t in tris],
            )

    @staticmethod
    def _extract_step_files(strategy: dict[str, Any]) -> set[str]:
        """Extract file paths from strategy steps."""
        return {f for s in strategy.get("steps", []) if (f := s.get("file"))}

    def _insert_file_entries(self, sig: str, files: set[str]) -> None:
        """Insert file entries for a recipe."""
        if files:
            self.conn.executemany(
                "INSERT INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                [(sig, f) for f in files],
            )

    def _rebuild_trigram_index(self) -> None:
        """Rebuild recipe_trigrams using normalized goal text for synonym-aware matching."""
        rows = self.conn.execute("SELECT sig, pattern FROM recipes").fetchall()
        if not rows:
            return
        with transaction(self.conn):
            self.conn.execute("DELETE FROM recipe_trigrams")
            for row in rows:
                self._insert_trigrams(row["sig"], unique_trigrams(normalize_goal(row["pattern"])))

    def _backfill_files(self) -> None:
        """Populate recipe_files for recipes that lack file entries."""
        orphans = self.conn.execute(
            "SELECT sig, strategy FROM recipes WHERE sig NOT IN "
            "(SELECT DISTINCT recipe_sig FROM recipe_files)"
        ).fetchall()
        if not orphans:
            return
        with transaction(self.conn):
            for row in orphans:
                sig, strategy_str = row["sig"], row["strategy"]
                try:
                    strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                self._insert_file_entries(sig, self._extract_step_files(strategy))

    # ── Recipes ──────────────────────────────────────────────────────────────

    def save_recipe(
        self,
        goal: str,
        strategy: dict[str, Any],
        outcome: bool,
        constraints: list[dict[str, Any]] | None = None,
    ) -> None:
        sig = self._stable_strategy_sig(strategy)
        pattern = goal[:_MAX_PATTERN_LENGTH]
        strat_json = dumps_json(strategy)
        const_json = dumps_json(constraints or [])
        now = time.time()
        col = "successes" if outcome else "failures"
        extra = ", constraints = excluded.constraints" if outcome else ""
        with transaction(self.conn):
            self.conn.execute(
                f"""INSERT INTO recipes (sig, pattern, strategy, constraints, {col}, created, updated)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(sig) DO UPDATE SET
                        {col} = recipes.{col} + 1,
                        pattern = excluded.pattern{extra},
                        updated = excluded.updated""",
                (sig, pattern, strat_json, const_json, now, now),
            )
            self.conn.execute(
                "DELETE FROM recipe_trigrams WHERE recipe_sig = ?", (sig,),
            )
            self._insert_trigrams(sig, unique_trigrams(normalize_goal(pattern)))
            self.conn.execute(
                "DELETE FROM recipe_files WHERE recipe_sig = ?", (sig,),
            )
            self._insert_file_entries(sig, self._extract_step_files(strategy))

    _W_TEXT = 0.4
    _W_FILES = 0.25
    _W_SUCCESS = 0.15
    _W_RECENCY = 0.2
    _RECENCY_HALF_LIFE = 30 * 86400  # 30 days in seconds

    def retrieve_best_recipe(
        self,
        goal: str,
        min_similarity: float = 0.3,
        context_files: set[str] | None = None,
    ) -> dict[str, Any] | None:
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return None
        tri_in, tri_params = _sql_in(sorted(goal_tris))
        candidate_sigs = self.conn.execute(
            f"SELECT DISTINCT recipe_sig FROM recipe_trigrams WHERE trigram {tri_in}",
            tri_params,
        ).fetchall()
        if not candidate_sigs:
            return None
        sig_list = [row["recipe_sig"] for row in candidate_sigs]
        sig_in, sig_params = _sql_in(sig_list)
        cur = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes "
            f"WHERE sig {sig_in}",
            sig_params,
        )
        # Batch-fetch file paths for all candidates to avoid N+1 queries
        candidates = cur.fetchall()
        sig_files: dict[str, set[str]] = {}
        if context_files is not None and candidates:
            all_sigs = [row["sig"] for row in candidates]
            file_in, file_params = _sql_in(all_sigs)
            file_rows = self.conn.execute(
                f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {file_in}",
                file_params,
            ).fetchall()
            for frow in file_rows:
                sig_files.setdefault(frow["recipe_sig"], set()).add(frow["file_path"])

        best: dict[str, Any] | None = None
        best_score = -1.0
        best_meta: dict[str, Any] = {}
        now = time.time()
        for row in candidates:
            sig, pattern = row["sig"], row["pattern"]
            strategy_str, succ, fail, updated = row["strategy"], row["successes"], row["failures"], row["updated"]
            text_sim = goal_similarity(goal, pattern)
            if text_sim < min_similarity:
                continue

            if context_files is not None:
                recipe_files = sig_files.get(sig, set())
                if recipe_files and context_files:
                    file_overlap = len(context_files & recipe_files) / len(context_files | recipe_files)
                else:
                    file_overlap = 0.0

                total = succ + fail
                success_ratio = succ / total if total > 0 else 0.5
                recency = 0.5 ** ((now - updated) / self._RECENCY_HALF_LIFE)

                score = (
                    self._W_TEXT * text_sim
                    + self._W_FILES * file_overlap
                    + self._W_SUCCESS * success_ratio
                    + self._W_RECENCY * recency
                )
                components = {
                    "text_similarity": round(text_sim, 3),
                    "file_overlap": round(file_overlap, 3),
                    "success_ratio": round(success_ratio, 3),
                    "recency": round(recency, 3),
                }
            else:
                score = text_sim
                components = {"text_similarity": round(text_sim, 3)}

            if score > best_score:
                try:
                    candidate = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                best_score = score
                best = candidate
                best_meta = {
                    "sig": sig[:12],
                    "pattern": pattern,
                    "match_score": round(score, 3),
                    "match_components": components,
                    "successes": succ,
                    "failures": fail,
                }
                if context_files is None and text_sim >= _NEAR_PERFECT_SIMILARITY:
                    break

        if best is not None:
            self.log_event("recipe_hit", goal[:_MAX_LOG_GOAL_LENGTH], best_score)
            best["_match"] = best_meta
        else:
            self.log_event("recipe_miss", goal[:_MAX_LOG_GOAL_LENGTH])
        return best

    def retrieve_near_matches(
        self,
        goal: str,
        n: int = 3,
        min_score: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Return top-N near-miss recipe candidates for reference.

        Surfaces recipes that are related but below the auto-match threshold,
        helping decompose inform the caller about potentially relevant past work.
        """
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return []
        tri_in, tri_params = _sql_in(sorted(goal_tris))
        candidate_sigs = self.conn.execute(
            f"SELECT DISTINCT recipe_sig FROM recipe_trigrams WHERE trigram {tri_in}",
            tri_params,
        ).fetchall()
        if not candidate_sigs:
            return []
        sig_list = [row["recipe_sig"] for row in candidate_sigs]
        sig_in, sig_params = _sql_in(sig_list)
        rows = self.conn.execute(
            f"SELECT sig, pattern, successes, failures FROM recipes WHERE sig {sig_in}",
            sig_params,
        ).fetchall()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            text_sim = goal_similarity(goal, row["pattern"])
            if text_sim < min_score:
                continue
            scored.append((text_sim, {
                "sig": row["sig"][:12],
                "pattern": row["pattern"],
                "score": round(text_sim, 3),
                "successes": row["successes"],
                "failures": row["failures"],
            }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:n]]

    def list_recipes(self, limit: int = 20) -> list[dict[str, Any]]:
        """List stored recipes with pattern, counts, and file paths."""
        rows = self.conn.execute(
            "SELECT sig, pattern, successes, failures, updated "
            "FROM recipes ORDER BY updated DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return []
        # Batch-fetch all file paths for the returned recipes
        sigs = [r["sig"] for r in rows]
        sig_in, sig_params = _sql_in(sigs)
        file_rows = self.conn.execute(
            f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {sig_in}",
            sig_params,
        ).fetchall()
        sig_files: dict[str, list[str]] = {}
        for frow in file_rows:
            sig_files.setdefault(frow["recipe_sig"], []).append(frow["file_path"])
        return [
            {
                "sig": r["sig"][:12],
                "pattern": r["pattern"],
                "successes": r["successes"],
                "failures": r["failures"],
                "files": sig_files.get(r["sig"], []),
                "updated": r["updated"],
            }
            for r in rows
        ]

    def prune_recipes(self, max_age_days: int = 90, min_success_ratio: float = 0.1) -> int:
        """Remove stale, low-quality recipes. Returns count of pruned recipes."""
        cutoff = time.time() - (max_age_days * 86400)
        pruned = [
            row["sig"] for row in self.conn.execute(
                "SELECT sig FROM recipes WHERE updated < ? AND "
                "(successes + failures = 0 OR CAST(successes AS REAL) / (successes + failures) < ?)",
                (cutoff, min_success_ratio),
            ).fetchall()
        ]
        if not pruned:
            return 0
        prune_in, prune_params = _sql_in(pruned)
        with transaction(self.conn):
            self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig {prune_in}", prune_params)
            self.conn.execute(f"DELETE FROM recipe_files WHERE recipe_sig {prune_in}", prune_params)
            self.conn.execute(f"DELETE FROM recipes WHERE sig {prune_in}", prune_params)
        return len(pruned)

    def validate_recipes(self, project_root: str) -> dict[str, Any]:
        """Check recipe file entries against current project. Remove stale entries.

        Returns {recipes_checked, files_removed, recipes_invalidated}.
        Recipes whose files are entirely missing are pruned.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT recipe_sig FROM recipe_files"
        ).fetchall()
        # Batch-fetch all file entries
        all_file_rows = self.conn.execute(
            "SELECT recipe_sig, file_path FROM recipe_files"
        ).fetchall()
        sig_files: dict[str, list[str]] = {}
        for frow in all_file_rows:
            sig_files.setdefault(frow["recipe_sig"], []).append(frow["file_path"])

        files_removed = 0
        invalidated: list[str] = []
        stale_pairs: list[tuple[str, str]] = []
        for row in rows:
            sig = row["recipe_sig"]
            file_list = sig_files.get(sig, [])
            missing = [f for f in file_list if not os.path.isfile(os.path.join(project_root, f))]
            if not missing:
                continue
            stale_pairs.extend((sig, f) for f in missing)
            files_removed += len(missing)
            if len(missing) == len(file_list):
                invalidated.append(sig)
        # Single transaction for all removals
        if stale_pairs or invalidated:
            with transaction(self.conn):
                if stale_pairs:
                    self.conn.executemany(
                        "DELETE FROM recipe_files WHERE recipe_sig = ? AND file_path = ?",
                        stale_pairs,
                    )
                if invalidated:
                    inv_in, inv_params = _sql_in(invalidated)
                    self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig {inv_in}", inv_params)
                    self.conn.execute(f"DELETE FROM recipes WHERE sig {inv_in}", inv_params)
        return {
            "recipes_checked": len(rows),
            "files_removed": files_removed,
            "recipes_invalidated": len(invalidated),
        }
