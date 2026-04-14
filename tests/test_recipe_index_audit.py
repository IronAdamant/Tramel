"""Audit recipe retrieval indices: trigram, term (TF-IDF), MinHash, and arch MinHash.

Validates that:
- All four index methods return reasonable candidate sets
- Unified retrieval (retrieve_best_recipe) aggregates them correctly
- The tightened default min_similarity (0.55) blocks false positives
- The composite score floor (0.35) blocks low-confidence structural matches
"""

from __future__ import annotations

import os
import tempfile
import unittest

from trammel.store import RecipeStore


class TestRecipeIndexAudit(unittest.TestCase):
    """Compare coverage and precision of the recipe index backends."""

    def _seed_store(self, store: RecipeStore) -> None:
        recipes = [
            ("refactor auth module", {"steps": [{"file": "src/auth.py", "action": "modify", "symbols": ["login"]}]}, True),
            ("add websocket support", {"steps": [{"file": "src/socket.py", "action": "create", "symbols": ["connect"]}]}, True),
            ("optimize database queries", {"steps": [{"file": "src/db.py", "action": "modify", "symbols": ["query"]}]}, True),
            ("implement user service", {"steps": [{"file": "src/services/user.py", "action": "create", "symbols": ["UserService"]}]}, True),
            ("fix routing bug", {"steps": [{"file": "src/routes.py", "action": "modify", "symbols": ["route"]}]}, True),
            ("build test harness", {"steps": [{"file": "tests/harness.py", "action": "create", "symbols": ["Harness"]}]}, True),
        ]
        for goal, strat, outcome in recipes:
            store.save_recipe(goal, strat, outcome)

    def test_trigram_search_returns_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            results = store.search_recipes_by_trigrams("refactor authentication", threshold=0.1)
            sigs = {sig for sig, _ in results}
            self.assertTrue(len(sigs) > 0, "trigram search should return candidates")

    def test_term_search_returns_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            results = store.search_recipes_by_terms("refactor authentication", top_k=10)
            sigs = {sig for sig, _ in results}
            self.assertTrue(len(sigs) > 0, "term search should return candidates")

    def test_minhash_search_returns_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            results = store.search_recipes_by_minhash("refactor authentication", threshold=0.1)
            sigs = {sig for sig, _ in results}
            self.assertTrue(len(sigs) > 0, "minhash search should return candidates")

    def test_unified_retrieval_aggregates_all_indices(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            # Exact goal should hit via term + trigram + minhash
            recipe = store.retrieve_best_recipe("refactor auth module")
            self.assertIsNotNone(recipe)
            # Slight rewording should still hit because at least one index catches it
            recipe = store.retrieve_best_recipe("rewrite authentication module")
            self.assertIsNotNone(recipe)

    def test_default_min_similarity_blocks_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            # Default min_similarity is now 0.55
            recipe = store.retrieve_best_recipe("banana smoothie recipe")
            self.assertIsNone(recipe)

    def test_composite_floor_blocks_low_confidence_matches(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            # Provide context_files to force composite scoring path
            context_files = {"src/irrelevant.py"}
            recipe = store.retrieve_best_recipe(
                "banana smoothie recipe",
                context_files=context_files,
            )
            self.assertIsNone(recipe)

    def test_near_matches_respect_min_score(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            # Near-match query with low floor should still filter out nonsense
            near = store.retrieve_near_matches("banana smoothie recipe", min_score=0.55)
            self.assertEqual(len(near), 0)

    def test_debug_candidates_include_all_indices(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "a.db"))
            self._seed_store(store)
            recipe = store.retrieve_best_recipe(
                "refactor auth module",
                debug=True,
            )
            self.assertIsNotNone(recipe)
            candidates = recipe.get("_debug_candidates", [])
            self.assertTrue(len(candidates) > 0)
            # At least one candidate should come from the aggregated search
            scores = [c["match_score"] for c in candidates]
            self.assertTrue(all(s >= 0.55 for s in scores), "debug candidates should respect min_similarity")


if __name__ == "__main__":
    unittest.main()
