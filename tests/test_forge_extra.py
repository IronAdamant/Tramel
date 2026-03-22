"""Extended Forge tests: edge cases, planner internals, MCP dispatch, incremental harness."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import ExecutionHarness, explore, plan_and_execute, synthesize  # noqa: E402
from trammel.core import Planner, _default_beam_count  # noqa: E402
from trammel.mcp_server import _TOOL_SCHEMAS, dispatch_tool  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402
from trammel.utils import (  # noqa: E402
    analyze_failure,
    analyze_imports,
    cosine,
    sha256_json,
    topological_sort,
    trigram_bag_cosine,
    trigram_signature,
)


# ── Utils extras ─────────────────────────────────────────────────────────────

class TestUtilsExtra(unittest.TestCase):
    def test_sha256_stable(self) -> None:
        self.assertEqual(sha256_json({"z": 1, "a": 2}), sha256_json({"a": 2, "z": 1}))

    def test_analyze_failure_import_error(self) -> None:
        result = analyze_failure("ModuleNotFoundError: No module named 'foo'", "")
        self.assertEqual(result["error_type"], "import_error")
        self.assertIn("foo", result["message"])

    def test_analyze_failure_syntax_error(self) -> None:
        stderr = 'File "test.py", line 5\n    SyntaxError: invalid syntax'
        result = analyze_failure(stderr, "")
        self.assertEqual(result["error_type"], "syntax_error")
        self.assertEqual(result["file"], "test.py")
        self.assertEqual(result["line"], 5)

    def test_analyze_failure_unknown(self) -> None:
        result = analyze_failure("", "all good")
        self.assertEqual(result["error_type"], "unknown")

    def test_topological_sort_diamond(self) -> None:
        deps = {"d.py": ["b.py", "c.py"], "b.py": ["a.py"], "c.py": ["a.py"]}
        result = topological_sort(deps)
        self.assertLess(result.index("a.py"), result.index("b.py"))
        self.assertLess(result.index("a.py"), result.index("c.py"))
        self.assertLess(result.index("b.py"), result.index("d.py"))
        self.assertLess(result.index("c.py"), result.index("d.py"))


# ── Store extras ─────────────────────────────────────────────────────────────

class TestStoreExtra(unittest.TestCase):
    def test_recipe_success_increments(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "r.db"))
            strat = {"steps": [{"file": "x.py"}]}
            store.save_recipe("goal one", strat, True)
            store.save_recipe("goal two", strat, True)
            row = store.conn.execute(
                "SELECT successes FROM recipes WHERE sig = ?", (sha256_json(strat),)
            ).fetchone()
            self.assertEqual(row[0], 2)

    def test_recipe_failure_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "f.db"))
            strat = {"steps": [{"file": "z.py"}]}
            store.save_recipe("goal", strat, False)
            row = store.conn.execute(
                "SELECT successes, failures FROM recipes WHERE sig = ?", (sha256_json(strat),)
            ).fetchone()
            self.assertEqual(row[0], 0)
            self.assertEqual(row[1], 1)

    def test_step_update(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "s.db"))
            strat = {"steps": [{"description": "test step", "rationale": "r", "depends_on": []}]}
            pid = store.create_plan("g", strat)
            plan = store.get_plan(pid)
            step_id = plan["steps"][0]["id"]
            store.update_step(step_id, "passed", verification={"success": True})
            step = store.get_step(step_id)
            self.assertEqual(step["status"], "passed")
            self.assertTrue(step["verification"]["success"])

    def test_list_plans_filter(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "l.db"))
            store.create_plan("a", {"steps": []})
            store.create_plan("b", {"steps": []})
            pid = store.create_plan("c", {"steps": []})
            store.update_plan_status(pid, "completed")
            all_plans = store.list_plans()
            self.assertEqual(len(all_plans), 3)
            completed = store.list_plans("completed")
            self.assertEqual(len(completed), 1)

    def test_constraint_filter_by_type(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "cf.db"))
            store.add_constraint("avoid", "don't use globals")
            store.add_constraint("dependency", "A depends on B")
            avoids = store.get_active_constraints("avoid")
            self.assertEqual(len(avoids), 1)
            all_c = store.get_active_constraints()
            self.assertEqual(len(all_c), 2)


# ── Planner extras ───────────────────────────────────────────────────────────

class TestPlannerExtra(unittest.TestCase):
    def test_decompose_uses_stored_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "pl.db"))
            canned = {"steps": [{"file": "canned.py", "description": "canned"}]}
            store.save_recipe("specific goal phrase", canned, True)
            planner = Planner(store=store)
            out = planner.decompose("specific goal phrase", d)
            self.assertIn("steps", out)

    def test_decompose_produces_dependency_graph(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
            (pkg / "child.py").write_text(
                "from pkg.base import Base\nclass Child(Base):\n    pass\n",
                encoding="utf-8",
            )
            planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
            strat = planner.decompose("refactor pkg", d)
            self.assertIn("dependency_graph", strat)
            self.assertIn("steps", strat)

    def test_invalid_python_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "broken.py").write_text("this is not valid python !!!\n", encoding="utf-8")
            planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
            strat = planner.decompose("goal", d)
            self.assertTrue(any(s.get("file") == "__project__" for s in strat["steps"]))

    def test_beam_count_respects_cap(self) -> None:
        self.assertLessEqual(_default_beam_count(100), 12)
        self.assertGreaterEqual(_default_beam_count(100), 3)

    def test_beams_have_different_variants(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
            strat = planner.decompose("task", d)
            beams = planner.explore_trajectories(strat, num_beams=3)
            variants = {b["variant"] for b in beams}
            self.assertEqual(variants, {"bottom_up", "top_down", "risk_first"})


# ── Harness extras ───────────────────────────────────────────────────────────

class TestHarnessExtra(unittest.TestCase):
    def test_incremental_stops_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "tests").mkdir()
            (pathlib.Path(d) / "tests" / "test_x.py").write_text(
                "import unittest\nimport importlib\n"
                "class T(unittest.TestCase):\n"
                "    def test_check(self):\n"
                "        mod = importlib.import_module('check')\n"
                "        self.assertTrue(mod.ok)\n",
                encoding="utf-8",
            )
            h = ExecutionHarness(timeout_s=30)
            step1 = [{"path": "check.py", "content": "ok = True\n"}]
            step2 = [{"path": "check.py", "content": "ok = False\n"}]
            r = h.run_incremental([step1, step2], d)
            self.assertFalse(r["success"])
            self.assertEqual(r["steps_completed"], 1)
            self.assertEqual(r["failed_at_step"], 1)

    def test_timeout_returns_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "tests").mkdir()
            (pathlib.Path(d) / "tests" / "test_x.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_x(self):\n        pass\n",
                encoding="utf-8",
            )
            h = ExecutionHarness(timeout_s=30)

            def boom(*_a, **_k):
                raise subprocess.TimeoutExpired(cmd="python", timeout=1)

            with patch("trammel.harness.subprocess.run", side_effect=boom):
                r = h.run([], d)
            self.assertFalse(r["success"])
            self.assertEqual(r["output"], "timeout")


# ── Plan-and-execute extras ──────────────────────────────────────────────────

class TestPlanAndExecuteExtra(unittest.TestCase):
    def test_failed_when_tests_fail(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "fail.db")
            (pathlib.Path(d) / "tests").mkdir()
            (pathlib.Path(d) / "tests" / "test_bad.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_fail(self):\n        self.assertTrue(False)\n",
                encoding="utf-8",
            )
            out = plan_and_execute("fix it", d, num_beams=2, db_path=db)
            self.assertEqual(out.get("status"), "failed")
            self.assertIn("plan_id", out)


# ── MCP dispatch ─────────────────────────────────────────────────────────────

class TestMCPDispatch(unittest.TestCase):
    def test_status_tool(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            result = dispatch_tool(store, "status", {})
            self.assertEqual(result["recipes"], 0)
            self.assertEqual(result["plans_total"], 0)

    def test_create_and_get_plan(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            strat = {"steps": [{"description": "s1", "rationale": "r", "depends_on": []}]}
            result = dispatch_tool(store, "create_plan", {"goal": "test", "strategy": strat})
            plan_id = result["plan_id"]
            plan = dispatch_tool(store, "get_plan", {"plan_id": plan_id})
            self.assertEqual(plan["goal"], "test")
            self.assertEqual(len(plan["steps"]), 1)

    def test_constraint_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            dispatch_tool(store, "add_constraint", {
                "constraint_type": "avoid",
                "description": "don't mutate X",
            })
            constraints = dispatch_tool(store, "get_constraints", {})
            self.assertEqual(len(constraints), 1)

    def test_unknown_tool_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            with self.assertRaises(ValueError):
                dispatch_tool(store, "nonexistent", {})

    def test_all_schemas_have_required_fields(self) -> None:
        for name, schema in _TOOL_SCHEMAS.items():
            self.assertIn("name", schema, msg=f"{name} missing 'name'")
            self.assertIn("description", schema, msg=f"{name} missing 'description'")
            self.assertIn("parameters", schema, msg=f"{name} missing 'parameters'")
            self.assertEqual(schema["name"], name)


# ── CLI ──────────────────────────────────────────────────────────────────────

class TestCLI(unittest.TestCase):
    def test_cli_json_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "cli.db")
            tdir = pathlib.Path(d) / "tests"
            tdir.mkdir()
            (tdir / "test_ok.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_t(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT)
            proc = subprocess.run(
                [sys.executable, "-m", "trammel", "cli smoke", "--root", d,
                 "--beams", "1", "--db", db],
                cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload.get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
