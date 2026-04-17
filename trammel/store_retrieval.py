"""Recipe retrieval mixin: composite-scored lookup and near-match suggestions.

Split out of :mod:`store_recipes` to keep that module under the project's
500-LOC target. Retrieval uses a blended score (text similarity + file
overlap + success ratio + recency + structural fingerprint) against
candidates surfaced from the term, trigram, MinHash, and arch-MinHash
indices maintained by :class:`~.recipe_index.RecipeIndexMixin`.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from .recipe_fingerprints import (
    goal_fingerprint_from_text as _goal_fingerprint_from_text,
    recipe_match_components as _recipe_match_components,
    scaffold_fingerprint as _scaffold_fingerprint,
    sql_in as _sql_in,
)

if TYPE_CHECKING:
    from .store import RecipeStore  # noqa: F401 — documents mixin host


_MAX_LOG_GOAL_LENGTH = 100
_NEAR_PERFECT_SIMILARITY = 0.9999


class RecipeRetrievalMixin:
    """Retrieval methods mixed into RecipeStore.

    Expects the composing class to provide the recipe-index search methods
    (``search_recipes_by_terms``, ``search_recipes_by_trigrams``,
    ``search_recipes_by_minhash``, ``search_recipes_by_arch``) plus
    ``conn``, ``log_event``, and the ``_W_*`` / ``_RECENCY_HALF_LIFE``
    scoring weight constants defined in :class:`RecipeStoreMixin`.
    """

    conn: sqlite3.Connection
    _W_TEXT: float
    _W_FILES: float
    _W_SUCCESS: float
    _W_RECENCY: float
    _W_STRUCTURAL: float
    _RECENCY_HALF_LIFE: float

    def retrieve_best_recipe(
        self,
        goal: str,
        min_similarity: float = 0.55,
        context_files: set[str] | None = None,
        scaffold: list[dict[str, Any]] | None = None,
        debug: bool = False,
    ) -> dict[str, Any] | None:
        """Return the highest-scoring recipe for ``goal`` or ``None``.

        When ``context_files`` is supplied, scoring uses the full composite
        (text + file overlap + success + recency + structural); otherwise
        only text similarity is used. ``debug=True`` attaches the list of
        candidate scores to the returned strategy as ``_debug_candidates``.
        """
        term_results = self.search_recipes_by_terms(goal, top_k=50)
        trigram_results = self.search_recipes_by_trigrams(goal, threshold=0.3, top_n=50)
        minhash_results = self.search_recipes_by_minhash(goal, threshold=0.3, top_n=50)
        sig_set: set[str] = set()
        for sig, _ in term_results:
            sig_set.add(sig)
        for sig, _ in trigram_results:
            sig_set.add(sig)
        for sig, _ in minhash_results:
            sig_set.add(sig)

        goal_fp: dict[str, Any] | None = None
        if context_files is not None:
            if scaffold:
                goal_fp = _scaffold_fingerprint(scaffold)
            else:
                goal_fp = _goal_fingerprint_from_text(goal)

        if goal_fp is not None:
            arch_text = " ".join(f"{k}:{v}" for k, v in goal_fp.get("role_counts", {}).items())
            arch_results = self.search_recipes_by_arch(arch_text, threshold=0.3, top_n=50)
            for sig, _ in arch_results:
                sig_set.add(sig)

        if not sig_set:
            return None
        sig_list = sorted(sig_set)
        sig_in, sig_params = _sql_in(sig_list)
        cur = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes "
            f"WHERE sig {sig_in}",
            sig_params,
        )
        candidates = cur.fetchall()

        successful = [r for r in candidates if r["successes"] > 0]
        if successful:
            candidates = successful

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
        debug_candidates: list[dict[str, Any]] = []
        now = time.time()
        for row in candidates:
            sig, pattern = row["sig"], row["pattern"]
            strategy_str, succ, fail, updated = row["strategy"], row["successes"], row["failures"], row["updated"]
            recipe_files = sig_files.get(sig, set()) if context_files is not None else set()

            recipe_strategy: dict[str, Any] | None = None
            if goal_fp is not None:
                try:
                    recipe_strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    recipe_strategy = None

            text_sim, score, components = _recipe_match_components(
                goal, pattern, succ, fail, updated,
                context_files, recipe_files, recipe_strategy, now,
                w_text=self._W_TEXT, w_files=self._W_FILES,
                w_success=self._W_SUCCESS, w_recency=self._W_RECENCY,
                w_structural=self._W_STRUCTURAL,
                recency_half_life=self._RECENCY_HALF_LIFE,
                goal_fingerprint=goal_fp,
            )
            if text_sim < min_similarity:
                continue
            if context_files is not None and score < 0.35:
                continue

            if debug:
                debug_candidates.append({
                    "sig": sig[:12],
                    "pattern": pattern,
                    "match_score": round(score, 3),
                    "match_components": components,
                    "successes": succ,
                    "failures": fail,
                })

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
            if debug:
                best["_debug_candidates"] = sorted(debug_candidates, key=lambda c: c["match_score"], reverse=True)
        else:
            self.log_event("recipe_miss", goal[:_MAX_LOG_GOAL_LENGTH])
        return best

    def retrieve_near_matches(
        self,
        goal: str,
        n: int = 3,
        min_score: float = 0.15,
        context_files: set[str] | None = None,
        min_composite: float = 0.20,
        scaffold: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return top-N near-miss recipe candidates for reference.

        Surfaces recipes that are related but below the auto-match threshold,
        helping decompose inform the caller about potentially relevant past
        work. When ``context_files`` is set, ranking uses the same composite
        score as :meth:`retrieve_best_recipe` with ``min_composite`` as a
        floor; otherwise, text similarity alone.
        """
        term_results = self.search_recipes_by_terms(goal, top_k=50)
        trigram_results = self.search_recipes_by_trigrams(goal, threshold=0.3, top_n=50)
        minhash_results = self.search_recipes_by_minhash(goal, threshold=0.3, top_n=50)
        sig_set: set[str] = set()
        for sig, _ in term_results:
            sig_set.add(sig)
        for sig, _ in trigram_results:
            sig_set.add(sig)
        for sig, _ in minhash_results:
            sig_set.add(sig)

        goal_fp: dict[str, Any] | None = None
        if context_files is not None:
            if scaffold:
                goal_fp = _scaffold_fingerprint(scaffold)
            else:
                goal_fp = _goal_fingerprint_from_text(goal)

        if goal_fp is not None:
            arch_text = " ".join(f"{k}:{v}" for k, v in goal_fp.get("role_counts", {}).items())
            arch_results = self.search_recipes_by_arch(arch_text, threshold=0.3, top_n=50)
            for sig, _ in arch_results:
                sig_set.add(sig)

        if not sig_set:
            return []
        sig_list = sorted(sig_set)
        sig_in, sig_params = _sql_in(sig_list)
        rows = self.conn.execute(
            f"SELECT sig, pattern, strategy, successes, failures, updated FROM recipes WHERE sig {sig_in}",
            sig_params,
        ).fetchall()
        sig_files: dict[str, set[str]] = {}
        if context_files is not None and rows:
            all_sigs = [row["sig"] for row in rows]
            file_in, file_params = _sql_in(all_sigs)
            file_rows = self.conn.execute(
                f"SELECT recipe_sig, file_path FROM recipe_files WHERE recipe_sig {file_in}",
                file_params,
            ).fetchall()
            for frow in file_rows:
                sig_files.setdefault(frow["recipe_sig"], set()).add(frow["file_path"])

        now = time.time()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            sig = row["sig"]
            pattern = row["pattern"]
            strategy_str = row["strategy"]
            succ, fail, updated = row["successes"], row["failures"], row["updated"]
            recipe_files = sig_files.get(sig, set()) if context_files is not None else set()

            recipe_strategy: dict[str, Any] | None = None
            if goal_fp is not None and strategy_str:
                try:
                    recipe_strategy = json.loads(strategy_str)
                except (json.JSONDecodeError, TypeError):
                    recipe_strategy = None

            text_sim, rank_score, components = _recipe_match_components(
                goal, pattern, succ, fail, updated,
                context_files, recipe_files, recipe_strategy, now,
                w_text=self._W_TEXT, w_files=self._W_FILES,
                w_success=self._W_SUCCESS, w_recency=self._W_RECENCY,
                w_structural=self._W_STRUCTURAL,
                recency_half_life=self._RECENCY_HALF_LIFE,
                goal_fingerprint=goal_fp,
            )
            if text_sim < min_score:
                continue
            if context_files is not None and rank_score < min_composite:
                continue

            entry: dict[str, Any] = {
                "sig": sig[:12],
                "pattern": pattern,
                "score": round(text_sim, 3),
                "successes": succ,
                "failures": fail,
            }
            if context_files is not None:
                entry["match_score"] = round(rank_score, 3)
                entry["match_components"] = components
            scored.append((rank_score if context_files is not None else text_sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:n]]
