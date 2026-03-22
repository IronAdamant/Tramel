"""Core tests for Trammel: utils, store, harness, planner, public API."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import ExecutionHarness, explore, plan_and_execute, synthesize  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402
from trammel.utils import (  # noqa: E402
    analyze_imports,
    cosine,
    topological_sort,
    trigram_bag_cosine,
    trigram_signature,
)


class TestTrigrams(unittest.TestCase):
    def test_signature_self_similarity(self) -> None:
        a = trigram_signature("hello world")
        b = trigram_signature("hello world")
        self.assertAlmostEqual(cosine(a, b), 1.0, places=5)

    def test_signature_short_string(self) -> None:
        self.assertEqual(trigram_signature(""), [1.0])
        self.assertEqual(trigram_signature("ab"), [1.0])

    def test_bag_cosine_symmetric(self) -> None:
        self.assertAlmostEqual(trigram_bag_cosine("hello world", "hello world"), 1.0, places=5)
        self.assertGreaterEqual(trigram_bag_cosine("aaa", "bbb"), 0.0)

    def test_cosine_empty(self) -> None:
        self.assertEqual(cosine([], [1.0, 2.0]), 0.0)
        self.assertEqual(cosine([1.0], []), 0.0)


class TestTopologicalSort(unittest.TestCase):
    def test_linear_chain(self) -> None:
        deps = {"c.py": ["b.py"], "b.py": ["a.py"]}
        result = topological_sort(deps)
        self.assertLess(result.index("a.py"), result.index("b.py"))
        self.assertLess(result.index("b.py"), result.index("c.py"))

    def test_no_deps(self) -> None:
        deps = {"a.py": [], "b.py": []}
        result = topological_sort(deps)
        self.assertEqual(len(result), 2)

    def test_cycle_handled(self) -> None:
        deps = {"a.py": ["b.py"], "b.py": ["a.py"]}
        result = topological_sort(deps)
        self.assertEqual(set(result), {"a.py", "b.py"})


class TestImportAnalysis(unittest.TestCase):
    def test_detects_internal_import(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "a.py").write_text("X = 1\n", encoding="utf-8")
            (pkg / "b.py").write_text("from pkg.a import X\n", encoding="utf-8")
            graph = analyze_imports(d)
            b_deps = graph.get(os.path.join("pkg", "b.py"), [])
            self.assertIn(os.path.join("pkg", "a.py"), b_deps)

    def test_ignores_external_imports(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.py").write_text("import os\nimport json\n", encoding="utf-8")
            graph = analyze_imports(d)
            self.assertEqual(graph.get("mod.py", []), [])


class TestStore(unittest.TestCase):
    def test_recipe_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            store = RecipeStore(db)
            strat = {"steps": [{"file": "a.py", "description": "modify a"}]}
            store.save_recipe("refactor auth module", strat, True)
            got = store.retrieve_best_recipe("refactor authentication")
            self.assertIsNotNone(got)

    def test_retrieve_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "e.db"))
            self.assertIsNone(store.retrieve_best_recipe("anything"))

    def test_min_similarity_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "t.db"))
            strat = {"steps": []}
            store.save_recipe("refactor auth module", strat, True)
            self.assertIsNone(store.retrieve_best_recipe("completely unrelated xyz topic"))

    def test_plan_and_steps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "p.db"))
            strat = {
                "steps": [
                    {"description": "step 1", "rationale": "first", "depends_on": []},
                    {"description": "step 2", "rationale": "second", "depends_on": [0]},
                ],
            }
            pid = store.create_plan("goal", strat)
            plan = store.get_plan(pid)
            self.assertIsNotNone(plan)
            self.assertEqual(plan["total_steps"], 2)
            self.assertEqual(len(plan["steps"]), 2)
            self.assertEqual(plan["steps"][1]["depends_on"], [0])

    def test_constraint_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "c.db"))
            cid = store.add_constraint("avoid", "don't use global state", {"file": "a.py"})
            active = store.get_active_constraints()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["description"], "don't use global state")
            store.deactivate_constraint(cid)
            self.assertEqual(len(store.get_active_constraints()), 0)

    def test_trajectory_logging(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "t.db"))
            strat = {"steps": []}
            pid = store.create_plan("g", strat)
            store.log_trajectory(pid, 0, "bottom_up", 3, {"success": True}, None)
            trajs = store.get_trajectories(pid)
            self.assertEqual(len(trajs), 1)
            self.assertEqual(trajs[0]["strategy_variant"], "bottom_up")


class TestHarness(unittest.TestCase):
    def test_runs_passing_project(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            tdir = pathlib.Path(d) / "tests"
            tdir.mkdir()
            (tdir / "test_mod.py").write_text(
                "import unittest\nfrom pkg import mod\n"
                "class T(unittest.TestCase):\n"
                "    def test_f(self):\n        self.assertEqual(mod.f(), 1)\n",
                encoding="utf-8",
            )
            h = ExecutionHarness(timeout_s=30)
            r = h.run([], d)
            self.assertTrue(r["success"], msg=r.get("trace"))

    def test_verify_step_with_prior(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tdir = pathlib.Path(d) / "tests"
            tdir.mkdir()
            (tdir / "test_x.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_t(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            h = ExecutionHarness(timeout_s=30)
            r = h.verify_step([], d, prior_edits=[])
            self.assertTrue(r["success"])

    def test_failure_includes_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tdir = pathlib.Path(d) / "tests"
            tdir.mkdir()
            (tdir / "test_bad.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_f(self):\n        self.assertTrue(False)\n",
                encoding="utf-8",
            )
            h = ExecutionHarness(timeout_s=30)
            r = h.run([], d)
            self.assertFalse(r["success"])
            self.assertIn("failure_analysis", r)


class TestPlanAndExecute(unittest.TestCase):
    def test_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "f.db")
            pkg = pathlib.Path(d) / "demo"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            tdir = pathlib.Path(d) / "tests"
            tdir.mkdir()
            (tdir / "test_x.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_t(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            out = plan_and_execute("make tests pass", d, num_beams=2, db_path=db)
            self.assertEqual(out.get("status"), "ok")

    def test_explore_returns_beams(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            ex = explore("add logging", d, num_beams=3, db_path=os.path.join(d, "e.db"))
            self.assertIn("beams", ex)
            self.assertIn("strategy", ex)
            variants = [b["variant"] for b in ex["beams"]]
            self.assertIn("bottom_up", variants)
            self.assertIn("top_down", variants)
            self.assertIn("risk_first", variants)

    def test_synthesize_then_retrieve(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "s.db")
            strat = {"steps": [{"file": "x.py", "description": "crafted"}]}
            synthesize("integration goal", strat, db_path=db)
            ex = explore("integration goal similar", d, num_beams=1, db_path=db)
            self.assertIn("steps", ex["strategy"])


if __name__ == "__main__":
    unittest.main()
