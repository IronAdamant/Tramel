"""Recipe mixin: save, retrieve, list, prune recipes with trigram + composite scoring."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .recipe_fingerprints import (
    _FILE_ROLE_RE,
    goal_fingerprint_from_text as _goal_fingerprint_from_text,
    goal_scaffold_fingerprint_from_text as _goal_scaffold_fingerprint_from_text,
    recipe_match_components as _recipe_match_components,
    scaffold_fingerprint as _scaffold_fingerprint,
    scaffold_structural_similarity as _scaffold_structural_similarity,
    sql_in as _sql_in,
    strategy_fingerprint as _strategy_fingerprint,
    structural_similarity as _structural_similarity,
)
from .recipe_index import RecipeIndexMixin
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

# Structural fingerprinting and scoring helpers live in
# :mod:`recipe_fingerprints`; they're imported at the top of this module
# under their legacy underscore-prefixed names to preserve call sites.


class RecipeStoreMixin(RecipeIndexMixin):
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
        """Insert file entries for a recipe (idempotent with unique index)."""
        if files:
            self.conn.executemany(
                "INSERT OR IGNORE INTO recipe_files (recipe_sig, file_path) VALUES (?, ?)",
                [(sig, f) for f in set(files)],
            )

    def search_recipes_by_trigrams(
        self, goal: str, threshold: float = 0.3, top_n: int = 20,
    ) -> list[tuple[str, float]]:
        """Trigram overlap search over indexed recipe patterns.

        Returns list of (recipe_sig, jaccard-like overlap score) sorted descending.
        """
        goal_tris = unique_trigrams(normalize_goal(goal))
        if not goal_tris:
            return []
        try:
            tri_in, tri_params = _sql_in(sorted(goal_tris))
            rows = self.conn.execute(
                f"""SELECT recipe_sig, COUNT(DISTINCT trigram) AS matches
                    FROM recipe_trigrams WHERE trigram {tri_in}
                    GROUP BY recipe_sig""",
                tri_params,
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        if not rows:
            return []
        candidates: list[tuple[str, float]] = []
        for row in rows:
            sig = row["recipe_sig"]
            matches = row["matches"]
            # Total trigrams for this recipe
            total_row = self.conn.execute(
                "SELECT COUNT(DISTINCT trigram) FROM recipe_trigrams WHERE recipe_sig = ?",
                (sig,),
            ).fetchone()
            total = total_row[0] if total_row else 0
            union = len(goal_tris) + total - matches
            score = matches / union if union > 0 else 0.0
            if score >= threshold:
                candidates.append((sig, score))
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]

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
        # Fix 4: ensure scaffold files appear as explicit create steps so
        # strategy_to_scaffold() can reconstruct them later for re-use.
        strategy = self._ensure_scaffold_create_steps(strategy)
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
            self._index_recipe_terms(sig, pattern)
            self._index_recipe_minhash(sig, pattern)
            # Architecture-shape MinHash for structural matching
            recipe_fp = _strategy_fingerprint(strategy)
            arch_text = " ".join(f"{k}:{v}" for k, v in recipe_fp.get("role_counts", {}).items())
            self._index_recipe_arch(sig, arch_text)

    def _ensure_scaffold_create_steps(self, strategy: dict[str, Any]) -> dict[str, Any]:
        """Ensure all scaffold files appear as action=create steps so the recipe
        can reconstruct the scaffold via strategy_to_scaffold() on replay."""
        steps = list(strategy.get("steps", []))
        scaffold = strategy.get("scaffold", [])

        # Files already represented as create steps
        create_files = {
            s["file"] for s in steps
            if s.get("action") == "create" and s.get("file")
        }
        # Also accept modify steps as "file already exists, don't recreate"
        existing_files = {
            s["file"] for s in steps if s.get("file")
        }

        scaffold_files = {e.get("file") for e in scaffold if e.get("file")}
        missing = scaffold_files - create_files - existing_files

        if not missing:
            return strategy

        # Build file→index map for depends_on resolution
        file_to_idx: dict[str, int] = {}
        for i, s in enumerate(steps):
            f = s.get("file")
            if f:
                file_to_idx[f] = i

        for f in sorted(missing):
            scaffold_entry = next(
                (e for e in scaffold if e.get("file") == f), {}
            )
            # Resolve depends_on to step indices
            raw_deps = scaffold_entry.get("depends_on", [])
            if isinstance(raw_deps[0], int) if raw_deps else False:
                # Already integer indices — resolve to files then back to indices
                dep_files = [
                    steps[d]["file"] for d in raw_deps
                    if d < len(steps) and steps[d].get("file")
                ]
                resolved_deps = [
                    file_to_idx[df] for df in dep_files if df in file_to_idx
                ]
            else:
                # String paths — resolve directly
                resolved_deps = [
                    file_to_idx[df] for df in raw_deps if df in file_to_idx
                ]

            steps.append({
                "step_index": len(steps),
                "file": f,
                "action": "create",
                "symbols": [],
                "symbol_count": 0,
                "description": scaffold_entry.get(
                    "description", f"Create {f}"
                ),
                "rationale": f"Scaffold file from plan: {scaffold_entry.get('description', f)}",
                "depends_on": resolved_deps,
            })
            file_to_idx[f] = len(steps) - 1

        strategy = dict(strategy, steps=steps)
        return strategy

    _W_TEXT = 0.25       # Reduced: text similarity alone shouldn't dominate
    _W_FILES = 0.15      # Reduced: file overlap matters but isn't always available
    _W_SUCCESS = 0.10    # Reduced: success rate is secondary signal
    _W_RECENCY = 0.10    # Reduced: recency is minor signal
    _W_STRUCTURAL = 0.40  # Increased: structural fingerprint is key discriminator
    _RECENCY_HALF_LIFE = 30 * 86400  # 30 days in seconds

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
            bucket = sig_files.setdefault(frow["recipe_sig"], [])
            if frow["file_path"] not in bucket:
                bucket.append(frow["file_path"])
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
            self.conn.execute(f"DELETE FROM recipe_terms WHERE recipe_sig {prune_in}", prune_params)
            self.conn.execute(f"DELETE FROM recipe_signatures WHERE recipe_sig {prune_in}", prune_params)
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
                    self.conn.execute(f"DELETE FROM recipe_terms WHERE recipe_sig {inv_in}", inv_params)
                    self.conn.execute(f"DELETE FROM recipe_signatures WHERE recipe_sig {inv_in}", inv_params)
                    self.conn.execute(f"DELETE FROM recipes WHERE sig {inv_in}", inv_params)
        return {
            "recipes_checked": len(rows),
            "files_removed": files_removed,
            "recipes_invalidated": len(invalidated),
        }
