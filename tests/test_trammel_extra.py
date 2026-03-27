"""Extended Trammel tests: edge cases, planner internals, MCP dispatch, incremental harness."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time as _time
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import ExecutionHarness, plan_and_execute  # noqa: E402
from trammel.core import (  # noqa: E402
    Planner,
    _apply_constraints,
    _extract_paths_from_goal,
    _generate_steps,
    strategy_to_scaffold,
)
from trammel.mcp_server import _TOOL_SCHEMAS, dispatch_tool  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402
from trammel.analyzers import detect_language  # noqa: E402
from trammel.utils import (  # noqa: E402
    analyze_failure,
    dumps_json,
    sha256_json,
    topological_sort,
    transaction,
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

    def test_near_matches_composite_ordering(self) -> None:
        """Structural overlap changes ranking when context_files is set."""
        with tempfile.TemporaryDirectory() as tmp:
            store = RecipeStore(os.path.join(tmp, "near.db"))
            base = "implement add services routes tests for nutrition module"
            strat_a = {"steps": [{"file": "foo/services/foo.js"}]}
            strat_b = {"steps": [{"file": "bar/models/bar.js"}]}
            store.save_recipe(base + " variant a", strat_a, True)
            store.save_recipe(base + " variant b", strat_b, True)
            goal = "implement add services routes tests for nutrition module today"
            ctx = {"foo/services/foo.js", "app.js"}
            ranked = store.retrieve_near_matches(goal, n=3, context_files=ctx)
            self.assertGreaterEqual(len(ranked), 2)
            patterns = [r["pattern"] for r in ranked]
            self.assertLess(patterns.index(base + " variant a"), patterns.index(base + " variant b"))
            for r in ranked:
                self.assertIn("match_score", r)
                self.assertIn("match_components", r)


# ── Planner extras ───────────────────────────────────────────────────────────

class TestPlannerExtra(unittest.TestCase):
    def test_extract_paths_from_goal(self) -> None:
        g = 'Implement `src/new/mod.py` and `"lib/helper.ts"` plus src/extra/file.js'
        paths = _extract_paths_from_goal(g)
        self.assertIn("src/new/mod.py", paths)
        self.assertIn("lib/helper.ts", paths)
        self.assertIn("src/extra/file.js", paths)

    def test_decompose_infers_scaffold_from_goal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "gp.db"))
            result = Planner(store=store).decompose(
                "Add feature in `src/new/feature.py`", d,
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            files = {s["file"] for s in create_steps}
            self.assertIn("src/new/feature.py", files)
            self.assertGreaterEqual(result.get("goal_paths_inferred", 0), 1)

    def test_relevance_graph_boost_for_import_hub(self) -> None:
        """Hub file with no keyword match still gets higher relevance than a leaf."""
        symbols = {
            "hub.py": ["Thing"],
            "leaf.py": ["Leaf"],
        }
        dep_graph = {
            "leaf.py": ["hub.py"],
        }
        file_order = ["hub.py", "leaf.py"]
        goal_keywords = {"zzz", "qqq"}
        steps = _generate_steps(
            file_order, symbols, dep_graph, "refactor zzz qqq",
            goal_keywords=goal_keywords, relevant_only=False,
        )
        by_file = {s["file"]: s["relevance"] for s in steps}
        self.assertGreater(by_file["hub.py"], by_file["leaf.py"])

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

    @patch("trammel.core.os.cpu_count", return_value=4)
    def test_beam_count_respects_cap(self, _mock_cpu: object) -> None:
        """Beam count is capped between 3 and 12 regardless of input."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
            strat = planner.decompose("task", d)
            beams = planner.explore_trajectories(strat, num_beams=100)
            self.assertLessEqual(len(beams), 12)
            self.assertGreaterEqual(len(beams), 3)

    @patch("trammel.core.os.cpu_count", return_value=12)
    def test_beams_have_different_variants(self, _mock_cpu: object) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
            strat = planner.decompose("task", d)
            beams = planner.explore_trajectories(strat, num_beams=6)
            variants = {b["variant"] for b in beams}
            self.assertEqual(len(variants), 6)


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
                r = h.verify_step([], d)
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


# ── Context manager ──────────────────────────────────────────────────────────

class TestStoreContextManager(unittest.TestCase):
    def test_context_manager_closes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with RecipeStore(os.path.join(d, "cm.db")) as store:
                store.add_constraint("avoid", "test")
            with self.assertRaises(Exception):
                store.conn.execute("SELECT 1")

    def test_close_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ci.db"))
            store.close()
            store.close()

    def test_del_safety(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ds.db"))
            store.close()
            del store


# ── Transactions ─────────────────────────────────────────────────────────────

class TestTransactions(unittest.TestCase):
    def test_create_plan_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "at.db"))
            strat = {
                "steps": [
                    {"description": "s1", "rationale": "r1", "depends_on": []},
                    {"description": "s2", "rationale": "r2", "depends_on": [0]},
                ],
            }
            pid = store.create_plan("atomic goal", strat)
            plan = store.get_plan(pid)
            self.assertEqual(len(plan["steps"]), 2)

    def test_transaction_rollback_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "rb.db"))
            try:
                with transaction(store.conn):
                    store.conn.execute(
                        "INSERT INTO constraints "
                        "(plan_id, step_id, constraint_type, description, context, active, created) "
                        "VALUES (NULL, NULL, 'avoid', 'rollback test', '{}', 1, 0)",
                    )
                    raise ValueError("force rollback")
            except ValueError:
                pass
            rows = store.conn.execute("SELECT COUNT(*) FROM constraints").fetchone()
            self.assertEqual(rows[0], 0)

    def test_transaction_commits_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "tc.db"))
            with transaction(store.conn):
                store.conn.execute(
                    "INSERT INTO constraints "
                    "(plan_id, step_id, constraint_type, description, context, active, created) "
                    "VALUES (NULL, NULL, 'avoid', 'commit test', '{}', 1, 0)",
                )
            rows = store.conn.execute("SELECT COUNT(*) FROM constraints").fetchone()
            self.assertEqual(rows[0], 1)


# ── Constraint propagation ──────────────────────────────────────────────────

class TestConstraintPropagation(unittest.TestCase):
    def _make_steps(self) -> list[dict]:
        return [
            {"step_index": 0, "file": "a.py", "symbols": ["foo"], "depends_on": []},
            {"step_index": 1, "file": "b.py", "symbols": ["bar"], "depends_on": [0]},
            {"step_index": 2, "file": "c.py", "symbols": ["baz"], "depends_on": []},
        ]

    def test_avoid_skips_file(self) -> None:
        constraints = [{"type": "avoid", "description": "skip b", "context": {"file": "b.py"}}]
        result, applied = _apply_constraints(self._make_steps(), constraints)
        b_step = next(s for s in result if s["file"] == "b.py")
        self.assertEqual(b_step["status"], "skipped")
        self.assertEqual(len(applied), 1)

    def test_dependency_adds_ordering(self) -> None:
        constraints = [{"type": "dependency", "description": "c before a",
                        "context": {"before": "c.py", "after": "a.py"}}]
        result, applied = _apply_constraints(self._make_steps(), constraints)
        a_step = next(s for s in result if s["file"] == "a.py")
        c_idx = next(i for i, s in enumerate(result) if s["file"] == "c.py")
        self.assertIn(c_idx, a_step["depends_on"])
        self.assertEqual(len(applied), 1)

    def test_requires_adds_step(self) -> None:
        constraints = [{"type": "requires", "description": "need d",
                        "context": {"file": "d.py"}}]
        result, applied = _apply_constraints(self._make_steps(), constraints)
        files = [s["file"] for s in result]
        self.assertIn("d.py", files)
        self.assertEqual(len(applied), 1)

    def test_incompatible_metadata(self) -> None:
        constraints = [{"type": "incompatible", "description": "a and c clash",
                        "context": {"file_a": "a.py", "file_b": "c.py"}}]
        result, applied = _apply_constraints(self._make_steps(), constraints)
        a_step = next(s for s in result if s["file"] == "a.py")
        self.assertIn("c.py", a_step.get("incompatible_with", []))
        self.assertEqual(len(applied), 1)

    def test_constraints_applied_in_decompose(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "cp.db"))
            store.add_constraint("avoid", "skip a", context={"file": "a.py"})
            planner = Planner(store=store)
            strat = planner.decompose("task", d)
            self.assertIn("constraints_applied", strat)


# ── Recipe files & composite scoring ─────────────────────────────────────────

class TestRecipeFiles(unittest.TestCase):
    def test_files_populated_on_save(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "rf.db"))
            strat = {"steps": [{"file": "a.py"}, {"file": "b.py"}]}
            store.save_recipe("goal", strat, True)
            sig = sha256_json(strat)
            rows = store.conn.execute(
                "SELECT file_path FROM recipe_files WHERE recipe_sig = ?", (sig,),
            ).fetchall()
            self.assertEqual(sorted(r[0] for r in rows), ["a.py", "b.py"])

    def test_files_updated_on_resave(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "rf.db"))
            strat = {"steps": [{"file": "a.py"}]}
            store.save_recipe("goal", strat, True)
            store.save_recipe("goal", strat, True)
            sig = sha256_json(strat)
            rows = store.conn.execute(
                "SELECT file_path FROM recipe_files WHERE recipe_sig = ?", (sig,),
            ).fetchall()
            self.assertEqual(len(rows), 1)

    def test_backfill_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "bf.db"))
            sig = sha256_json({"steps": [{"file": "x.py"}]})
            now = _time.time()
            store.conn.execute(
                "INSERT INTO recipes (sig, pattern, strategy, constraints, successes, created, updated) "
                "VALUES (?, ?, ?, ?, 1, ?, ?)",
                (sig, "backfill test", dumps_json({"steps": [{"file": "x.py"}]}), "[]", now, now),
            )
            store.conn.commit()
            store._backfill_files()
            rows = store.conn.execute(
                "SELECT file_path FROM recipe_files WHERE recipe_sig = ?", (sig,),
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], "x.py")

    def test_text_only_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ts.db"))
            strat = {"steps": [{"file": "auth.py"}]}
            store.save_recipe("refactor auth module", strat, True)
            got = store.retrieve_best_recipe("refactor authentication")
            self.assertIsNotNone(got)

    def test_file_boost(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "fb.db"))
            strat_a = {"steps": [{"file": "utils.py"}], "id": "a"}
            strat_b = {"steps": [{"file": "auth.py"}], "id": "b"}
            store.save_recipe("refactor auth module", strat_a, True)
            store.save_recipe("refactor auth module", strat_b, True)
            # With context_files matching auth.py, strat_b should win
            got = store.retrieve_best_recipe(
                "refactor auth module", context_files={"auth.py", "login.py"},
            )
            self.assertIsNotNone(got)
            self.assertEqual(got.get("id"), "b")

    def test_success_boost(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "sb.db"))
            strat_a = {"steps": [{"file": "x.py"}], "id": "a"}
            strat_b = {"steps": [{"file": "x.py"}], "id": "b"}
            store.save_recipe("refactor auth module", strat_a, True)
            # strat_b has lower success rate
            store.save_recipe("refactor auth module", strat_b, False)
            got = store.retrieve_best_recipe(
                "refactor auth module", context_files={"x.py"},
            )
            self.assertIsNotNone(got)
            self.assertEqual(got.get("id"), "a")

    def test_list_recipes_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "le.db"))
            self.assertEqual(store.list_recipes(), [])

    def test_list_recipes_populated(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "lp.db"))
            store.save_recipe("goal a", {"steps": [{"file": "a.py"}]}, True)
            store.save_recipe("goal b", {"steps": [{"file": "b.py"}]}, True)
            recipes = store.list_recipes()
            self.assertEqual(len(recipes), 2)
            self.assertIn("files", recipes[0])

    def test_list_recipes_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "lm.db"))
            store.save_recipe("goal", {"steps": [{"file": "z.py"}]}, True)
            result = dispatch_tool(store, "list_recipes", {})
            self.assertEqual(len(result), 1)
            self.assertIn("z.py", result[0]["files"])


# ── MCP tools: update_plan_status, deactivate_constraint ─────────────────────

class TestNewMCPTools(unittest.TestCase):
    def test_update_plan_status_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ups.db"))
            pid = store.create_plan("goal", {"steps": []})
            result = dispatch_tool(store, "update_plan_status", {
                "plan_id": pid, "status": "completed",
            })
            self.assertTrue(result["ok"])
            plan = store.get_plan(pid)
            self.assertEqual(plan["status"], "completed")

    def test_deactivate_constraint_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "dc.db"))
            cid = store.add_constraint("avoid", "test constraint")
            self.assertEqual(len(store.get_active_constraints()), 1)
            result = dispatch_tool(store, "deactivate_constraint", {
                "constraint_id": cid,
            })
            self.assertTrue(result["ok"])
            self.assertEqual(len(store.get_active_constraints()), 0)

    def test_status_includes_tool_count(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "st.db"))
            result = dispatch_tool(store, "status", {})
            self.assertIn("tools", result)
            self.assertEqual(result["tools"], len(_TOOL_SCHEMAS))

    def test_all_schemas_valid(self) -> None:
        self.assertGreaterEqual(len(_TOOL_SCHEMAS), 1)
        for name, schema in _TOOL_SCHEMAS.items():
            self.assertIn("name", schema)
            self.assertIn("description", schema)
            self.assertIn("parameters", schema)
            self.assertEqual(schema["name"], name)


# ── MCP prune_recipes ────────────────────────────────────────────────────────

class TestPruneRecipesMCP(unittest.TestCase):
    def test_prune_recipes_mcp_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "pr.db"))
            result = dispatch_tool(store, "prune_recipes", {})
            self.assertEqual(result["pruned"], 0)

    def test_prune_recipes_mcp_with_stale(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "pr2.db"))
            strat = {"steps": [{"file": "old.py"}]}
            store.save_recipe("old goal", strat, False)
            sig = sha256_json(strat)
            old_time = _time.time() - (100 * 86400)
            store.conn.execute(
                "UPDATE recipes SET updated = ?, created = ? WHERE sig = ?",
                (old_time, old_time, sig),
            )
            store.conn.commit()
            result = dispatch_tool(store, "prune_recipes", {"max_age_days": 90})
            self.assertEqual(result["pruned"], 1)


# ── MCP dispatch coverage for remaining tools ─────────────────────────────────

class TestMCPDispatchCoverage(unittest.TestCase):
    def test_decompose_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "dc.db"))
            result = dispatch_tool(store, "decompose", {
                "goal": "refactor a", "project_root": d,
            })
            self.assertIn("steps", result)
            self.assertIn("dependency_graph", result)

    def test_explore_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "ex.db"))
            result = dispatch_tool(store, "explore", {
                "goal": "refactor a", "project_root": d, "num_beams": 2,
            })
            self.assertIn("strategy", result)
            self.assertIn("beams", result)
            self.assertEqual(len(result["beams"]), 2)

    def test_save_and_get_recipe_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "sr.db"))
            strat = {"steps": [{"file": "auth.py"}]}
            result = dispatch_tool(store, "save_recipe", {
                "goal": "refactor auth module", "strategy": strat, "outcome": True,
            })
            self.assertTrue(result["ok"])
            got = dispatch_tool(store, "get_recipe", {
                "goal": "refactor auth module",
            })
            self.assertIn("strategy", got)
            self.assertIn("steps", got["strategy"])
            self.assertIn("match_score", got)
            self.assertIn("match_components", got)

    def test_get_recipe_include_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "sr2.db"))
            strat = {
                "steps": [
                    {
                        "step_index": 0, "file": "a.js", "action": "create",
                        "depends_on": [], "symbol_count": 0, "symbols": [],
                        "description": "first",
                    },
                    {
                        "step_index": 1, "file": "b.js", "action": "create",
                        "depends_on": [0], "symbol_count": 0, "symbols": [],
                    },
                ],
            }
            goal = "refactor auth module with scaffold export"
            store.save_recipe(goal, strat, True)
            got = dispatch_tool(store, "get_recipe", {
                "goal": goal,
                "include_scaffold": True,
            })
            self.assertIn("scaffold", got)
            self.assertEqual(len(got["scaffold"]), 2)
            self.assertEqual(got["scaffold"][1].get("depends_on"), ["a.js"])

    def test_strategy_to_scaffold_skips_symbolic_modify_steps(self) -> None:
        strat = {
            "steps": [
                {"step_index": 0, "file": "lib.py", "symbol_count": 2, "symbols": ["a", "b"]},
                {"step_index": 1, "file": "new.py", "action": "create", "depends_on": [], "symbol_count": 0},
            ],
        }
        sc = strategy_to_scaffold(strat)
        self.assertEqual([e["file"] for e in sc], ["new.py"])

    def test_get_recipe_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "nm.db"))
            result = dispatch_tool(store, "get_recipe", {"goal": "xyz"})
            self.assertIn("match", result)
            self.assertIsNone(result["match"])

    def test_record_step_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "rs.db"))
            strat = {"steps": [{"description": "s1", "rationale": "r", "depends_on": []}]}
            pid = store.create_plan("g", strat)
            step_id = store.get_plan(pid)["steps"][0]["id"]
            result = dispatch_tool(store, "record_step", {
                "step_id": step_id, "status": "passed",
                "edits": [{"path": "a.py", "content": "x"}],
                "verification": {"success": True},
            })
            self.assertTrue(result["ok"])
            step = store.get_step(step_id)
            self.assertEqual(step["status"], "passed")

    def test_verify_step_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "tests").mkdir()
            (pathlib.Path(d) / "tests" / "test_ok.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_t(self):\n        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            store = RecipeStore(os.path.join(d, "vs.db"))
            result = dispatch_tool(store, "verify_step", {
                "edits": [], "project_root": d,
            })
            self.assertTrue(result["success"])

    def test_list_plans_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "lp.db"))
            store.create_plan("a", {"steps": []})
            store.create_plan("b", {"steps": []})
            result = dispatch_tool(store, "list_plans", {})
            self.assertEqual(len(result), 2)

    def test_history_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "h.db"))
            pid = store.create_plan("g", {"steps": []})
            store.log_trajectory(pid, 0, "bottom_up", 1, {"success": True})
            result = dispatch_tool(store, "history", {"plan_id": pid})
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["strategy_variant"], "bottom_up")


# ── Plan resumption ──────────────────────────────────────────────────────────

class TestPlanResumption(unittest.TestCase):
    def test_resume_no_progress(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "res.db"))
            strat = {"steps": [
                {"description": "s0", "rationale": "r", "depends_on": []},
                {"description": "s1", "rationale": "r", "depends_on": [0]},
            ]}
            pid = store.create_plan("g", strat)
            prog = store.get_plan_progress(pid)
            self.assertEqual(prog["next_step_index"], 0)
            self.assertEqual(prog["prior_edits"], [])
            self.assertEqual(len(prog["remaining_steps"]), 2)

    def test_resume_partial_progress(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "res2.db"))
            strat = {"steps": [
                {"description": "s0", "rationale": "r", "depends_on": []},
                {"description": "s1", "rationale": "r", "depends_on": [0]},
            ]}
            pid = store.create_plan("g", strat)
            plan = store.get_plan(pid)
            step_id = plan["steps"][0]["id"]
            store.update_step(step_id, "passed", edits=[{"path": "a.py", "content": "x"}])
            prog = store.get_plan_progress(pid)
            self.assertEqual(prog["next_step_index"], 1)
            self.assertEqual(len(prog["prior_edits"]), 1)
            self.assertEqual(prog["prior_edits"][0]["path"], "a.py")
            self.assertEqual(len(prog["remaining_steps"]), 1)

    def test_resume_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "res3.db"))
            self.assertIsNone(store.get_plan_progress(999))

    def test_resume_mcp_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "res4.db"))
            pid = store.create_plan("g", {"steps": [
                {"description": "s0", "rationale": "r", "depends_on": []},
            ]})
            result = dispatch_tool(store, "resume", {"plan_id": pid})
            self.assertIn("remaining_steps", result)
            self.assertIn("prior_edits", result)

    def test_resume_mcp_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "res5.db"))
            result = dispatch_tool(store, "resume", {"plan_id": 999})
            self.assertIn("error", result)


# ── Recipe validation ─────────────────────────────────────────────────────────

class TestRecipeValidation(unittest.TestCase):
    def test_validate_no_recipes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "val.db"))
            result = store.validate_recipes(d)
            self.assertEqual(result["recipes_checked"], 0)
            self.assertEqual(result["files_removed"], 0)

    def test_validate_removes_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "exists.py").write_text("x = 1\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "val2.db"))
            strat = {"steps": [{"file": "exists.py"}, {"file": "gone.py"}]}
            store.save_recipe("goal", strat, True)
            result = store.validate_recipes(d)
            self.assertEqual(result["files_removed"], 1)
            self.assertEqual(result["recipes_invalidated"], 0)

    def test_validate_prunes_fully_stale(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "val3.db"))
            strat = {"steps": [{"file": "gone_a.py"}, {"file": "gone_b.py"}]}
            store.save_recipe("goal", strat, True)
            result = store.validate_recipes(d)
            self.assertEqual(result["recipes_invalidated"], 1)
            self.assertEqual(store.list_recipes(), [])

    def test_validate_mcp_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "val4.db"))
            result = dispatch_tool(store, "validate_recipes", {"project_root": d})
            self.assertIn("recipes_checked", result)


# ── Config-file language detection ────────────────────────────────────────────

class TestConfigDetection(unittest.TestCase):
    def test_detect_from_cargo_toml(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "rust")

    def test_detect_from_go_mod(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "go.mod").write_text("module example\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "go")

    def test_detect_from_tsconfig(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "tsconfig.json").write_text("{}\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "typescript")

    def test_detect_from_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "package.json").write_text("{}\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "javascript")

    def test_detect_from_gradle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "build.gradle").write_text("apply plugin: 'java'\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "java")

    def test_detect_from_cmake(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "CMakeLists.txt").write_text("cmake_minimum_required()\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "cpp")

    def test_detect_fallback_to_extension_count(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("x = 1\n", encoding="utf-8")
            pathlib.Path(d, "b.py").write_text("y = 2\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "python")

    def test_detect_config_takes_priority(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            # Many .py files but Cargo.toml present → rust wins
            for i in range(10):
                pathlib.Path(d, f"mod{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
            pathlib.Path(d, "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "rust")

    def test_detect_pyproject_over_package_json(self) -> None:
        """Python projects with npm tooling should detect as Python, not TypeScript."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
            pathlib.Path(d, "package.json").write_text('{"name": "x"}\n', encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "python")

    def test_detect_sconstruct_as_cpp(self) -> None:
        """SConstruct (SCons build system) should detect as C++, not Python."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "SConstruct").write_text("env = Environment()\n", encoding="utf-8")
            pathlib.Path(d, "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "cpp")

    def test_estimate_tool(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("x = 1\n", encoding="utf-8")
            pathlib.Path(d, "b.py").write_text("y = 2\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "est.db"))
            result = dispatch_tool(store, "estimate", {"project_root": d})
            self.assertEqual(result["language"], "python")
            self.assertEqual(result["matching_files"], 2)
            self.assertEqual(result["recommendation"], "full analysis OK")

    def test_analysis_meta_in_decompose(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "am.db"))
            planner = Planner(store=store)
            strat = planner.decompose("task", d)
            self.assertIn("analysis_meta", strat)
            meta = strat["analysis_meta"]
            self.assertEqual(meta["language"], "python")
            self.assertIn("timing_s", meta)
            self.assertIn("total", meta["timing_s"])
            self.assertGreater(meta["files_analyzed"], 0)

    def test_detect_pyproject_without_project_section(self) -> None:
        """pyproject.toml with only tool config should not trigger Python detection."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pyproject.toml").write_text("[tool.ruff]\nline-length=100\n", encoding="utf-8")
            pathlib.Path(d, "main.go").write_text("package main\n", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "go")


# ── CLI dry-run ──────────────────────────────────────────────────────────────

class TestCLIDryRun(unittest.TestCase):
    def test_dry_run_returns_explore_output(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            db = os.path.join(d, "dr.db")
            result = subprocess.run(
                [sys.executable, "-m", "trammel", "test goal",
                 "--root", d, "--db", db, "--dry-run"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            out = json.loads(result.stdout)
            self.assertIn("strategy", out)
            self.assertIn("beams", out)


# ── Concurrent write safety ──────────────────────────────────────────────────

class TestConcurrentWrites(unittest.TestCase):
    def _make_db(self, d: str, name: str) -> str:
        """Pre-initialize DB schema before concurrent access."""
        db_path = os.path.join(d, name)
        RecipeStore(db_path).close()
        return db_path

    def test_concurrent_plan_creation(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db_path = self._make_db(d, "conc.db")
            errors: list[Exception] = []

            def create_plans(thread_id: int) -> None:
                try:
                    from trammel.utils import db_connect
                    conn = db_connect(db_path)
                    store = RecipeStore.__new__(RecipeStore)
                    store.db_path = db_path
                    store.conn = conn
                    for i in range(5):
                        store.create_plan(f"goal-{thread_id}-{i}", {"steps": []})
                    store.close()
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=create_plans, args=(t,)) for t in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [], msg=f"Errors: {errors}")
            store = RecipeStore(db_path)
            plans = store.list_plans()
            self.assertEqual(len(plans), 20)
            store.close()

    def test_concurrent_recipe_saves(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db_path = self._make_db(d, "conc2.db")
            errors: list[Exception] = []

            def save_recipes(thread_id: int) -> None:
                try:
                    from trammel.utils import db_connect
                    conn = db_connect(db_path)
                    store = RecipeStore.__new__(RecipeStore)
                    store.db_path = db_path
                    store.conn = conn
                    for i in range(5):
                        strat = {"steps": [{"file": f"t{thread_id}_f{i}.py"}], "tid": thread_id, "i": i}
                        store.save_recipe(f"goal {thread_id} {i}", strat, True)
                    store.close()
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=save_recipes, args=(t,)) for t in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [], msg=f"Errors: {errors}")
            store = RecipeStore(db_path)
            recipes = store.list_recipes(limit=100)
            self.assertEqual(len(recipes), 20)
            store.close()

    def test_concurrent_constraint_adds(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db_path = self._make_db(d, "conc3.db")
            errors: list[Exception] = []

            def add_constraints(thread_id: int) -> None:
                try:
                    from trammel.utils import db_connect
                    conn = db_connect(db_path)
                    store = RecipeStore.__new__(RecipeStore)
                    store.db_path = db_path
                    store.conn = conn
                    for i in range(5):
                        store.add_constraint("avoid", f"t{thread_id}-c{i}")
                    store.close()
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=add_constraints, args=(t,)) for t in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [], msg=f"Errors: {errors}")
            store = RecipeStore(db_path)
            constraints = store.get_active_constraints()
            self.assertEqual(len(constraints), 20)
            store.close()


# ── Monorepo scope ───────────────────────────────────────────────────────────

class TestMonorepoScope(unittest.TestCase):
    def test_decompose_with_scope(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sub = pathlib.Path(d) / "services" / "auth"
            sub.mkdir(parents=True)
            (sub / "handler.py").write_text("def login():\n    pass\n", encoding="utf-8")
            # Root-level file should NOT appear in scoped analysis
            pathlib.Path(d, "root_mod.py").write_text("def root_fn():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sc.db"))
            planner = Planner(store=store)
            strat = planner.decompose("fix auth", d, scope="services/auth")
            step_files = [s.get("file") for s in strat.get("steps", [])]
            self.assertTrue(
                any("handler.py" in (f or "") for f in step_files)
                or strat["steps"][0].get("file") == "__project__",
            )
            # root_mod.py should not appear
            for f in step_files:
                self.assertNotIn("root_mod", f or "")

    def test_explore_with_scope_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sub = pathlib.Path(d) / "pkg"
            sub.mkdir()
            (sub / "mod.py").write_text("class Foo:\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sc2.db"))
            result = dispatch_tool(store, "explore", {
                "goal": "refactor pkg", "project_root": d,
                "scope": "pkg", "num_beams": 2,
            })
            self.assertIn("beams", result)

    def test_scope_cli_flag(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sub = pathlib.Path(d) / "lib"
            sub.mkdir()
            (sub / "util.py").write_text("def helper():\n    pass\n", encoding="utf-8")
            db = os.path.join(d, "sc3.db")
            result = subprocess.run(
                [sys.executable, "-m", "trammel", "fix lib", "--root", d,
                 "--scope", "lib", "--db", db, "--dry-run"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            out = json.loads(result.stdout)
            self.assertIn("strategy", out)


# ── Integer type coercion ────────────────────────────────────────────────────

class TestIntegerCoercion(unittest.TestCase):
    """dispatch_tool must coerce string→int for schema-declared integer params."""

    def test_update_plan_status_string_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic.db"))
            pid = store.create_plan("g", {"steps": []})
            # Pass plan_id as string (simulates MCP JSON)
            result = dispatch_tool(store, "update_plan_status", {
                "plan_id": str(pid), "status": "completed",
            })
            self.assertTrue(result["ok"])
            self.assertEqual(store.get_plan(pid)["status"], "completed")

    def test_get_plan_string_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic2.db"))
            pid = store.create_plan("g", {"steps": []})
            plan = dispatch_tool(store, "get_plan", {"plan_id": str(pid)})
            self.assertEqual(plan["goal"], "g")

    def test_deactivate_constraint_string_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic3.db"))
            cid = store.add_constraint("avoid", "test")
            result = dispatch_tool(store, "deactivate_constraint", {
                "constraint_id": str(cid),
            })
            self.assertTrue(result["ok"])
            self.assertEqual(len(store.get_active_constraints()), 0)

    def test_history_string_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic4.db"))
            pid = store.create_plan("g", {"steps": []})
            result = dispatch_tool(store, "history", {"plan_id": str(pid)})
            self.assertEqual(result, [])

    def test_record_step_string_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic5.db"))
            strat = {"steps": [{"description": "s", "rationale": "r", "depends_on": []}]}
            pid = store.create_plan("g", strat)
            step_id = store.get_plan(pid)["steps"][0]["id"]
            result = dispatch_tool(store, "record_step", {
                "step_id": str(step_id), "status": "passed",
            })
            self.assertTrue(result["ok"])

    def test_invalid_string_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic6.db"))
            with self.assertRaises((ValueError, TypeError)):
                dispatch_tool(store, "get_plan", {"plan_id": "not_a_number"})

    def test_coercion_preserves_native_ints(self) -> None:
        """Native int values must pass through unchanged."""
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "ic7.db"))
            pid = store.create_plan("g", {"steps": []})
            plan = dispatch_tool(store, "get_plan", {"plan_id": pid})
            self.assertEqual(plan["goal"], "g")


# ── Decompose output filtering ──────────────────────────────────────────────

class TestDecomposeFiltering(unittest.TestCase):
    def _make_project(self, d: str) -> None:
        for name in ("a.py", "b.py", "c.py", "d.py", "e.py"):
            pathlib.Path(d, name).write_text(
                f"def {name[0]}():\n    pass\n", encoding="utf-8",
            )

    def test_summary_only_compact(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self._make_project(d)
            store = RecipeStore(os.path.join(d, "sf.db"))
            result = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d, "summary_only": True,
            })
            # Must have compact keys, NOT full steps or dependency_graph
            self.assertIn("step_count", result)
            self.assertIn("files", result)
            self.assertIn("analysis_meta", result)
            self.assertIn("goal_fingerprint", result)
            self.assertNotIn("steps", result)
            self.assertNotIn("dependency_graph", result)
            self.assertGreater(result["step_count"], 0)

    def test_max_steps_truncates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self._make_project(d)
            store = RecipeStore(os.path.join(d, "ms.db"))
            full = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d,
            })
            total = len(full["steps"])
            self.assertGreater(total, 2, "need >2 steps for truncation test")

            capped = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d, "max_steps": 2,
            })
            self.assertEqual(len(capped["steps"]), 2)
            self.assertEqual(capped["total_steps"], total)

    def test_max_steps_trims_dep_graph(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self._make_project(d)
            store = RecipeStore(os.path.join(d, "dg.db"))
            capped = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d, "max_steps": 2,
            })
            kept_files = {s["file"] for s in capped["steps"]}
            for f, deps in capped["dependency_graph"].items():
                self.assertIn(f, kept_files)
                for dep in deps:
                    self.assertIn(dep, kept_files)

    def test_no_filtering_unchanged(self) -> None:
        """Without max_steps or summary_only, output is unchanged."""
        with tempfile.TemporaryDirectory() as d:
            self._make_project(d)
            store = RecipeStore(os.path.join(d, "nf.db"))
            result = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d,
            })
            self.assertIn("steps", result)
            self.assertIn("dependency_graph", result)
            self.assertNotIn("total_steps", result)

    def test_max_steps_string_coerced(self) -> None:
        """max_steps as string is coerced to int by dispatch_tool."""
        with tempfile.TemporaryDirectory() as d:
            self._make_project(d)
            store = RecipeStore(os.path.join(d, "msc.db"))
            result = dispatch_tool(store, "decompose", {
                "goal": "refactor", "project_root": d, "max_steps": "1",
            })
            self.assertEqual(len(result["steps"]), 1)


class TestCreationSteps(unittest.TestCase):
    """P1: decompose generates actual 'Create' steps for new-file goals."""

    def test_creation_steps_for_new_service(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            svc = os.path.join(d, "src", "services")
            os.makedirs(svc)
            pathlib.Path(svc, "authService.js").write_text(
                "function auth() {}\nmodule.exports = { auth };\n", encoding="utf-8",
            )
            pathlib.Path(svc, "userService.js").write_text(
                "function user() {}\nmodule.exports = { user };\n", encoding="utf-8",
            )
            pathlib.Path(d, "package.json").write_text('{"name":"t"}\n', encoding="utf-8")
            store = RecipeStore(os.path.join(d, "cs.db"))
            result = Planner(store=store).decompose("add search service", d)

            self.assertIn("creation_hints", result)
            hints = result["creation_hints"]
            self.assertTrue(hints["creation_intent"])
            self.assertGreater(len(hints["suggested_files"]), 0)

            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertGreater(len(create_steps), 0)
            # Naming should follow sibling pattern: <keyword>Service.js
            found = any("search" in s["file"].lower() for s in create_steps)
            self.assertTrue(found, f"Expected search-related create step, got: {[s['file'] for s in create_steps]}")

    def test_no_creation_steps_without_intent(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mod.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "nc.db"))
            result = Planner(store=store).decompose("refactor the module", d)
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertEqual(len(create_steps), 0)
            self.assertNotIn("creation_hints", result)

    def test_no_duplicate_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            svc = os.path.join(d, "src", "services")
            os.makedirs(svc)
            pathlib.Path(svc, "authService.js").write_text("function auth() {}\n", encoding="utf-8")
            pathlib.Path(svc, "searchService.js").write_text("function search() {}\n", encoding="utf-8")
            pathlib.Path(d, "package.json").write_text('{"name":"t"}\n', encoding="utf-8")
            store = RecipeStore(os.path.join(d, "nd.db"))
            result = Planner(store=store).decompose("add search service", d)
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            for s in create_steps:
                self.assertNotIn("searchService", s["file"])

    def test_creation_step_fields(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            svc = os.path.join(d, "src", "services")
            os.makedirs(svc)
            pathlib.Path(svc, "authService.js").write_text("function auth() {}\n", encoding="utf-8")
            pathlib.Path(svc, "userService.js").write_text("function user() {}\n", encoding="utf-8")
            pathlib.Path(d, "package.json").write_text('{"name":"t"}\n', encoding="utf-8")
            store = RecipeStore(os.path.join(d, "cf.db"))
            result = Planner(store=store).decompose("add search service", d)
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertGreater(len(create_steps), 0)
            step = create_steps[0]
            self.assertEqual(step["action"], "create")
            self.assertEqual(step["symbols"], [])
            self.assertEqual(step["depends_on"], [])
            self.assertEqual(step["relevance"], 1.0)
            self.assertTrue(step["description"].startswith("Create "))

    def test_snake_case_naming(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            svc = os.path.join(d, "services")
            os.makedirs(svc)
            pathlib.Path(svc, "auth_service.py").write_text("def auth(): pass\n", encoding="utf-8")
            pathlib.Path(svc, "user_service.py").write_text("def user(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sn.db"))
            result = Planner(store=store).decompose("add search service", d)
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            # Should follow snake_case: search_service.py
            found = any("search_service" in s["file"] for s in create_steps)
            self.assertTrue(found, f"Expected snake_case name, got: {[s['file'] for s in create_steps]}")


class TestScaffoldSteps(unittest.TestCase):
    """Scaffold mode: explicit file specs for greenfield work."""

    def test_scaffold_basic(self) -> None:
        """Scaffold entries produce create-action steps."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sc.db"))
            result = Planner(store=store).decompose(
                "build web UI", d,
                scaffold=[
                    {"file": "public/index.html", "description": "Main dashboard"},
                    {"file": "public/css/style.css", "description": "Global stylesheet"},
                    {"file": "public/js/app.js", "description": "Frontend entry point"},
                ],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertEqual(len(create_steps), 3)
            files = {s["file"] for s in create_steps}
            self.assertEqual(files, {"public/index.html", "public/css/style.css", "public/js/app.js"})
            self.assertEqual(result["scaffold_applied"], 3)
            self.assertNotIn("creation_hints", result)

    def test_scaffold_dependency_ordering(self) -> None:
        """Scaffold steps respect declared depends_on for topological ordering."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "so.db"))
            result = Planner(store=store).decompose(
                "build web UI", d,
                scaffold=[
                    {"file": "public/index.html", "depends_on": ["public/css/style.css", "public/js/app.js"]},
                    {"file": "public/css/style.css"},
                    {"file": "public/js/app.js", "depends_on": ["public/js/api.js"]},
                    {"file": "public/js/api.js"},
                ],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            files_ordered = [s["file"] for s in create_steps]
            # api.js must come before app.js (app.js depends on api.js)
            self.assertLess(files_ordered.index("public/js/api.js"), files_ordered.index("public/js/app.js"))
            # style.css and app.js must come before index.html
            self.assertLess(files_ordered.index("public/css/style.css"), files_ordered.index("public/index.html"))
            self.assertLess(files_ordered.index("public/js/app.js"), files_ordered.index("public/index.html"))

    def test_scaffold_depends_on_generates_step_indices(self) -> None:
        """depends_on in scaffold maps to numeric step indices in output."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "si.db"))
            result = Planner(store=store).decompose(
                "build frontend", d,
                scaffold=[
                    {"file": "b.js", "depends_on": ["a.js"]},
                    {"file": "a.js"},
                ],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            step_a = next(s for s in create_steps if s["file"] == "a.js")
            step_b = next(s for s in create_steps if s["file"] == "b.js")
            self.assertEqual(step_a["depends_on"], [])
            self.assertIn(step_a["step_index"], step_b["depends_on"])

    def test_scaffold_skips_existing_files(self) -> None:
        """Files that already exist in the project are not duplicated as scaffold steps."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "existing.py").write_text("def foo(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "se.db"))
            result = Planner(store=store).decompose(
                "add new module", d,
                scaffold=[
                    {"file": "existing.py", "description": "Already exists"},
                    {"file": "new_module.py", "description": "Brand new"},
                ],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertEqual(len(create_steps), 1)
            self.assertEqual(create_steps[0]["file"], "new_module.py")

    def test_scaffold_empty_list(self) -> None:
        """Empty scaffold list falls through to no creation steps."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "em.db"))
            result = Planner(store=store).decompose("refactor", d, scaffold=[])
            self.assertEqual(result.get("scaffold_applied"), 0)

    def test_scaffold_description_in_step(self) -> None:
        """Custom descriptions appear in step output."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "ds.db"))
            result = Planner(store=store).decompose(
                "build API", d,
                scaffold=[{"file": "api/routes.py", "description": "REST route handlers"}],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertEqual(len(create_steps), 1)
            self.assertIn("REST route handlers", create_steps[0]["description"])

    def test_scaffold_merges_into_dependency_graph(self) -> None:
        """Scaffold dependency edges appear in the result dependency_graph."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "mg.db"))
            result = Planner(store=store).decompose(
                "build frontend", d,
                scaffold=[
                    {"file": "page.js", "depends_on": ["api.js"]},
                    {"file": "api.js"},
                ],
            )
            graph = result["dependency_graph"]
            self.assertIn("page.js", graph)
            self.assertIn("api.js", graph["page.js"])

    def test_scaffold_step_fields(self) -> None:
        """Scaffold steps have correct field structure."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sf.db"))
            result = Planner(store=store).decompose(
                "add module", d,
                scaffold=[{"file": "mod.py"}],
            )
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            step = create_steps[0]
            self.assertEqual(step["action"], "create")
            self.assertEqual(step["symbols"], [])
            self.assertEqual(step["symbol_count"], 0)
            self.assertEqual(step["relevance"], 1.0)
            self.assertIn("scaffold", step["rationale"])

    def test_scaffold_dispatch(self) -> None:
        """Scaffold works through MCP dispatch."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "sd.db"))
            result = dispatch_tool(store, "decompose", {
                "goal": "build web UI",
                "project_root": d,
                "scaffold": [
                    {"file": "public/index.html", "description": "Dashboard"},
                    {"file": "public/app.js", "depends_on": ["public/api.js"]},
                    {"file": "public/api.js"},
                ],
            })
            self.assertIn("steps", result)
            create_steps = [s for s in result["steps"] if s.get("action") == "create"]
            self.assertEqual(len(create_steps), 3)
            self.assertEqual(result["scaffold_applied"], 3)

    def test_scaffold_only_skips_full_repo_steps(self) -> None:
        """Non-empty scaffold defaults to scaffold-only: no steps from existing files."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "so2.db"))
            result = Planner(store=store).decompose(
                "build web UI", d,
                scaffold=[
                    {"file": "public/index.html"},
                    {"file": "public/app.js"},
                ],
            )
            self.assertTrue(result["analysis_meta"].get("scaffold_only"))
            self.assertEqual(result["analysis_meta"]["files_analyzed"], 0)
            self.assertIs(result.get("expand_repo"), False)
            self.assertEqual(len(result["steps"]), 2)
            self.assertEqual({s["file"] for s in result["steps"]}, {"public/index.html", "public/app.js"})

    def test_expand_repo_true_merges_full_decomposition(self) -> None:
        """expand_repo=true restores full-repo scan plus scaffold create steps."""
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "er.db"))
            result = Planner(store=store).decompose(
                "build web UI", d,
                scaffold=[{"file": "public/x.html"}],
                expand_repo=True,
            )
            self.assertNotIn("scaffold_only", result["analysis_meta"])
            self.assertIs(result.get("expand_repo"), True)
            self.assertGreaterEqual(result["analysis_meta"]["files_analyzed"], 1)
            files = {s["file"] for s in result["steps"]}
            self.assertIn("app.py", files)
            self.assertIn("public/x.html", files)

    def test_strict_greenfield_rejects_under_specified(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "strict.db"))
            with self.assertRaises(ValueError) as ctx:
                Planner(store=store).decompose(
                    "add a new microservice module",
                    d,
                    skip_recipes=True,
                    strict_greenfield=True,
                )
            self.assertIn("strict_greenfield", str(ctx.exception).lower())

    def test_strict_greenfield_allows_explicit_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "st2.db"))
            Planner(store=store).decompose(
                "add feature in `src/mod.py`",
                d,
                skip_recipes=True,
                strict_greenfield=True,
            )

    def test_relevance_components_on_modify_steps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "auth_service.py").write_text("def auth(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "rel.db"))
            r = Planner(store=store).decompose(
                "refactor authentication",
                d,
                skip_recipes=True,
            )
            step = next(s for s in r["steps"] if s.get("file") == "auth_service.py")
            self.assertIn("relevance_keyword", step)
            self.assertIn("relevance_graph", step)
            self.assertIn("relevance_tier", step)

    def test_plan_fidelity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "x.py").write_text("def f(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "pf.db"))
            r = Planner(store=store).decompose("task", d, skip_recipes=True)
            self.assertIn("plan_fidelity", r)
            self.assertIn("strict_greenfield", r["plan_fidelity"])

    def test_mcp_decompose_strict_error_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main(): pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "mcp.db"))
            out = dispatch_tool(store, "decompose", {
                "goal": "create a new plugin from scratch",
                "project_root": d,
                "skip_recipes": True,
                "strict_greenfield": True,
            })
            self.assertEqual(out.get("error"), "decompose_rejected")
            self.assertIn("message", out)


class TestProjectConfigMerge(unittest.TestCase):
    def test_load_project_config_json(self) -> None:
        from trammel.project_config import load_project_config

        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                '{"default_scope": "lib", "focus_keywords": ["cache"], "max_files": 99}\n',
                encoding="utf-8",
            )
            cfg = load_project_config(d)
            self.assertEqual(cfg.get("default_scope"), "lib")
            self.assertEqual(cfg.get("max_files"), 99)
            self.assertEqual(cfg.get("focus_keywords"), ["cache"])

    @unittest.skipUnless(sys.version_info >= (3, 11), "tomllib available in 3.11+")
    def test_pyproject_trammel_merged_with_json(self) -> None:
        from trammel.project_config import load_project_config

        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "pyproject.toml").write_text(
                '[tool.trammel]\ndefault_scope = "from_toml"\n',
                encoding="utf-8",
            )
            pathlib.Path(d, ".trammel.json").write_text(
                '{"focus_keywords": ["api"]}\n',
                encoding="utf-8",
            )
            cfg = load_project_config(d)
            self.assertEqual(cfg.get("default_scope"), "from_toml")
            self.assertEqual(cfg.get("focus_keywords"), ["api"])


class TestTrammelConfig(unittest.TestCase):
    """P5: .trammel.json provides explicit language override."""

    def test_trammel_json_overrides_detection(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            pathlib.Path(d, ".trammel.json").write_text(
                '{"language": "python"}\n', encoding="utf-8",
            )
            a = detect_language(d)
            self.assertEqual(a.name, "python")

    def test_trammel_json_invalid_language_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            pathlib.Path(d, ".trammel.json").write_text(
                '{"language": "brainfuck"}\n', encoding="utf-8",
            )
            a = detect_language(d)
            self.assertEqual(a.name, "rust")

    def test_trammel_json_malformed_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "go.mod").write_text("module test\n", encoding="utf-8")
            pathlib.Path(d, ".trammel.json").write_text("not json", encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "go")

    def test_trammel_json_missing_falls_through(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "package.json").write_text('{"name":"t"}\n', encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "javascript")

    def test_trammel_json_no_language_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "Cargo.toml").write_text("[package]\n", encoding="utf-8")
            pathlib.Path(d, ".trammel.json").write_text('{"other": 1}\n', encoding="utf-8")
            a = detect_language(d)
            self.assertEqual(a.name, "rust")


if __name__ == "__main__":
    unittest.main()
