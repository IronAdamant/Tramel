"""Recipe mixin: save, retrieve, list, prune recipes with trigram + composite scoring."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .utils import (
    dumps_json, goal_similarity, normalize_goal,
    sha256_json, transaction, unique_trigrams,
)

if TYPE_CHECKING:
    pass  # conn and log_event provided by composing class (RecipeStore)


class RecipeStoreMixin:
    """Recipe-related methods mixed into RecipeStore.

    Expects the composing class to provide:
        conn: sqlite3.Connection
        log_event(event_type, detail, value) -> None
    """

    conn: sqlite3.Connection

    def log_event(self, event_type: str, detail: str = "", value: float | None = None) -> None:
        """Provided by composing class."""
        ...

    def _rebuild_trigram_index(self) -> None:
        """Rebuild recipe_trigrams using normalized goal text for synonym-aware matching."""
        rows = self.conn.execute("SELECT sig, pattern FROM recipes").fetchall()
        if not rows:
            return
        with transaction(self.conn):
            self.conn.execute("DELETE FROM recipe_trigrams")
            for sig, pattern in rows:
                tris = unique_trigrams(normalize_goal(pattern))
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
            tris = unique_trigrams(normalize_goal(pattern))
            if tris:
                self.conn.executemany(
                    "INSERT INTO recipe_trigrams (trigram, recipe_sig) VALUES (?, ?)",
                    [(t, sig) for t in tris],
                )
            self.conn.execute(
                "DELETE FROM recipe_files WHERE recipe_sig = ?", (sig,),
            )
            files = {s.get("file") for s in strategy.get("steps", []) if s.get("file")}
            if files:
                self.conn.executemany(
                    "INSERT INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                    [(sig, f) for f in files],
                )

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
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes "
            f"WHERE sig IN ({sig_ph})",
            sig_tuple,
        )
        # Batch-fetch file paths for all candidates to avoid N+1 queries
        candidates = cur.fetchall()
        sig_files: dict[str, set[str]] = {}
        if context_files is not None and candidates:
            all_sigs = tuple(row[0] for row in candidates)
            file_ph = ",".join("?" for _ in all_sigs)
            file_rows = self.conn.execute(
                f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig IN ({file_ph})",
                all_sigs,
            ).fetchall()
            for fsig, fpath in file_rows:
                sig_files.setdefault(fsig, set()).add(fpath)

        best: dict[str, Any] | None = None
        best_score = -1.0
        now = time.time()
        for sig, pattern, strategy_str, succ, fail, updated in candidates:
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
            else:
                score = text_sim

            if score > best_score:
                try:
                    candidate = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    continue
                best_score = score
                best = candidate
                if context_files is None and text_sim >= 0.9999:
                    break

        if best is not None:
            self.log_event("recipe_hit", goal[:100], best_score)
        else:
            self.log_event("recipe_miss", goal[:100])
        return best

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
        sigs = [r[0] for r in rows]
        ph = ",".join("?" for _ in sigs)
        file_rows = self.conn.execute(
            f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig IN ({ph})",
            tuple(sigs),
        ).fetchall()
        sig_files: dict[str, list[str]] = {}
        for sig, fpath in file_rows:
            sig_files.setdefault(sig, []).append(fpath)
        return [
            {
                "sig": sig[:12],
                "pattern": pattern,
                "successes": succ,
                "failures": fail,
                "files": sig_files.get(sig, []),
                "updated": updated,
            }
            for sig, pattern, succ, fail, updated in rows
        ]

    def prune_recipes(self, max_age_days: int = 90, min_success_ratio: float = 0.1) -> int:
        """Remove stale, low-quality recipes. Returns count of pruned recipes."""
        cutoff = time.time() - (max_age_days * 86400)
        pruned = [
            row[0] for row in self.conn.execute(
                "SELECT sig FROM recipes WHERE updated < ? AND "
                "(successes + failures = 0 OR CAST(successes AS REAL) / (successes + failures) < ?)",
                (cutoff, min_success_ratio),
            ).fetchall()
        ]
        if not pruned:
            return 0
        ph = ",".join("?" for _ in pruned)
        with transaction(self.conn):
            self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig IN ({ph})", tuple(pruned))
            self.conn.execute(f"DELETE FROM recipe_files WHERE recipe_sig IN ({ph})", tuple(pruned))
            self.conn.execute(f"DELETE FROM recipes WHERE sig IN ({ph})", tuple(pruned))
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
        for sig, fpath in all_file_rows:
            sig_files.setdefault(sig, []).append(fpath)

        files_removed = 0
        invalidated: list[str] = []
        stale_pairs: list[tuple[str, str]] = []
        for (sig,) in rows:
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
                    ph = ",".join("?" for _ in invalidated)
                    self.conn.execute(f"DELETE FROM recipe_trigrams WHERE recipe_sig IN ({ph})", tuple(invalidated))
                    self.conn.execute(f"DELETE FROM recipes WHERE sig IN ({ph})", tuple(invalidated))
        return {
            "recipes_checked": len(rows),
            "files_removed": files_removed,
            "recipes_invalidated": len(invalidated),
        }
