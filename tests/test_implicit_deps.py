"""Tests for implicit dependency inference engine."""

import unittest
from trammel.implicit_deps import (
    NamingConventionEngine,
    SharedStateDetector,
    PatternLearner,
    ImplicitDependencyGraphEngine,
    _extract_base_name,
    _extract_suffix,
)


class TestExtractSuffix(unittest.TestCase):
    def test_camelcase_suffix(self):
        self.assertEqual(_extract_suffix("RecipeService.js"), "Service")
        self.assertEqual(_extract_suffix("OrderController.ts"), "Controller")
        self.assertEqual(_extract_suffix("UserRoute.py"), "Route")

    def test_snake_case_suffix(self):
        self.assertEqual(_extract_suffix("recipe_service.js"), "service")
        self.assertEqual(_extract_suffix("order_model.py"), "model")

    def test_kebab_case_suffix(self):
        self.assertEqual(_extract_suffix("recipe-service.js"), "service")

    def test_single_part_filename(self):
        # Single part filenames return the whole thing as suffix (for CamelCase)
        self.assertEqual(_extract_suffix("Recipe.js"), "Recipe")
        # utils has no separator and no CamelCase, so returns None
        self.assertIsNone(_extract_suffix("utils.js"))


class TestExtractBaseName(unittest.TestCase):
    def test_camelcase_base(self):
        self.assertEqual(_extract_base_name("RecipeService.js"), "Recipe")
        self.assertEqual(_extract_base_name("OrderController.ts"), "Order")

    def test_snake_case_base(self):
        # Snake case with no capitalization returns the full base
        self.assertEqual(_extract_base_name("recipe_service.js"), "recipe_service")

    def test_with_numbers(self):
        # Numbers attached to words are included in the base
        self.assertEqual(_extract_base_name("Recipe2Service.js"), "Recipe")


class TestNamingConventionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = NamingConventionEngine()
        self.existing_files = {
            "RecipeModel.js",
            "RecipeService.js",
            "RecipeRoute.js",
            "OrderController.js",
            "OrderService.js",
            "OrderModel.js",
            "fileStore.js",
            "utils.js",
        }

    def test_service_infers_model(self):
        deps = self.engine.infer_dependencies("RecipeService.js", self.existing_files)
        targets = {d["target"] for d in deps}
        self.assertIn("RecipeModel.js", targets)

    def test_service_infers_route(self):
        deps = self.engine.infer_dependencies("RecipeService.js", self.existing_files)
        targets = {d["target"] for d in deps}
        self.assertIn("RecipeRoute.js", targets)

    def test_route_infers_service(self):
        deps = self.engine.infer_dependencies("RecipeRoute.js", self.existing_files)
        targets = {d["target"] for d in deps}
        self.assertIn("RecipeService.js", targets)

    def test_controller_infers_service_and_model(self):
        deps = self.engine.infer_dependencies("OrderController.js", self.existing_files)
        targets = {d["target"] for d in deps}
        self.assertIn("OrderService.js", targets)
        self.assertIn("OrderModel.js", targets)

    def test_infrastructure_pattern(self):
        # Test with a file that contains infrastructure keyword
        deps = self.engine.infer_dependencies("store.js", {"store.js", "RecipeService.js"})
        infra_deps = [d for d in deps if d["type"] == "infrastructure"]
        self.assertTrue(len(infra_deps) > 0)

    def test_confidence_scores(self):
        deps = self.engine.infer_dependencies("RecipeService.js", self.existing_files)
        deps_by_target = {d["target"]: d for d in deps}
        self.assertGreaterEqual(deps_by_target["RecipeModel.js"]["confidence"], 0.85)
        self.assertGreaterEqual(deps_by_target["RecipeRoute.js"]["confidence"], 0.8)


class TestSharedStateDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SharedStateDetector()

    def test_find_coupled_modules(self):
        # Simulate file access
        self.detector._file_access_map["data/recipes.json"] = {"RecipeStore", "NutritionCalculator"}
        self.detector._file_access_map["data/orders.json"] = {"OrderService"}

        coupled = self.detector.find_coupled_modules("data/recipes.json")
        self.assertIn("RecipeStore", coupled)
        self.assertIn("NutritionCalculator", coupled)

    def test_infer_shared_state_dependencies(self):
        self.detector._module_access_map["RecipeService"] = {"data/recipes.json", "data/other.json"}
        self.detector._file_access_map["data/recipes.json"] = {"RecipeService", "NutritionCalculator"}
        self.detector._file_access_map["data/other.json"] = {"RecipeService"}

        inferred = self.detector.infer_shared_state_dependencies(
            "RecipeService", {"RecipeService", "NutritionCalculator", "OrderService"}
        )
        # Should infer coupling to NutritionCalculator via shared_state
        nutrition_deps = [d for d in inferred if d["target"] == "NutritionCalculator"]
        self.assertEqual(len(nutrition_deps), 1)
        self.assertEqual(nutrition_deps[0]["type"], "shared_state")

    def test_get_shared_state_graph(self):
        self.detector._file_access_map["data/recipes.json"] = {"RecipeStore", "NutritionCalculator"}
        self.detector._file_access_map["data/orders.json"] = {"OrderService", "OrderRoute"}

        graph = self.detector.get_shared_state_graph()

        self.assertIn("RecipeStore", graph)
        self.assertIn("NutritionCalculator", graph["RecipeStore"])


class TestPatternLearner(unittest.TestCase):
    def setUp(self):
        self.learner = PatternLearner()

    def test_learn_from_import_graph(self):
        dep_graph = {
            "A.js": ["B.js", "C.js"],
            "B.js": ["C.js"],
            "C.js": [],
        }
        existing_files = {"A.js", "B.js", "C.js", "D.js"}
        self.learner.learn_from_import_graph(dep_graph, existing_files)

        patterns = self.learner.get_common_patterns(min_frequency=1)
        self.assertTrue(len(patterns) > 0)

    def test_infer_pattern_dependencies(self):
        # Set up: A.js depends on B.js (3 times), and B.js co-occurs with C.js (2 times)
        self.learner._direct_deps["A.js"]["B.js"] = 3
        self.learner._dep_pair_cooccurrence["B.js"]["C.js"] = 2

        inferred = self.learner.infer_pattern_dependencies("A.js", {"A.js", "B.js", "C.js"})
        inferred_by_target = {d["target"]: d for d in inferred}

        self.assertIn("C.js", inferred_by_target)
        self.assertGreaterEqual(inferred_by_target["C.js"]["confidence"], 0.6)


class TestImplicitDependencyGraphEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ImplicitDependencyGraphEngine()
        self.existing_files = {
            "RecipeModel.js",
            "RecipeService.js",
            "RecipeRoute.js",
            "OrderController.js",
            "fileStore.js",
            "utils.js",
        }
        self.dep_graph = {
            "RecipeModel.js": [],
            "RecipeService.js": ["RecipeModel.js"],
            "RecipeRoute.js": ["RecipeService.js"],
        }

    def test_analyze_project(self):
        self.engine.analyze_project("/fake", {f: f for f in self.existing_files}, self.dep_graph)
        self.assertEqual(len(self.engine._existing_files), len(self.existing_files))

    def test_get_implicit_dependencies(self):
        self.engine.analyze_project("/fake", {f: f for f in self.existing_files}, self.dep_graph)
        deps = self.engine.get_implicit_dependencies("RecipeService.js")
        self.assertTrue(len(deps) > 0)

    def test_get_hybrid_dependency_graph(self):
        self.engine.analyze_project("/fake", {f: f for f in self.existing_files}, self.dep_graph)
        hybrid = self.engine.get_hybrid_dependency_graph(self.dep_graph)

        # Should have the explicit deps plus inferred
        self.assertIn("RecipeService.js", hybrid)
        # RecipeService should now have RecipeRoute via inference (route->service inverse)
        recipe_service_deps = hybrid["RecipeService.js"]
        # Original explicit deps + any inferred (order may vary)

    def test_gap_analysis(self):
        self.engine.analyze_project("/fake", {f: f for f in self.existing_files}, self.dep_graph)
        gap = self.engine.get_gap_analysis(self.dep_graph)

        self.assertIn("summary", gap)
        self.assertIn("trammelBlindSpots", gap)

    def test_suggest_dependencies_for_new_module(self):
        self.engine.analyze_project("/fake", {f: f for f in self.existing_files}, self.dep_graph)
        suggestion = self.engine.suggest_dependencies_for_new_module("MealPlanService.js")

        self.assertIn("must_have", suggestion)
        self.assertIn("likely_have", suggestion)
        self.assertIn("may_have", suggestion)


if __name__ == "__main__":
    unittest.main()
