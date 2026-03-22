"""Extended Trammel tests: edge cases, planner internals, MCP dispatch, incremental harness."""

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

from trammel import ExecutionHarness, plan_and_execute  # noqa: E402
from trammel.core import Planner, _apply_constraints, _default_beam_count  # noqa: E402
from trammel.mcp_server import _TOOL_SCHEMAS, dispatch_tool  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402
from trammel.utils import (  # noqa: E402
    analyze_failure,
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
            from trammel.utils import dumps_json
            import time as _time
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
            self.assertEqual(result["tools"], 18)

    def test_all_18_schemas_valid(self) -> None:
        from trammel.mcp_server import _TOOL_SCHEMAS
        self.assertEqual(len(_TOOL_SCHEMAS), 18)
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
            import time as _time
            old_time = _time.time() - (100 * 86400)
            store.conn.execute(
                "UPDATE recipes SET updated = ?, created = ? WHERE sig = ?",
                (old_time, old_time, sig),
            )
            store.conn.commit()
            result = dispatch_tool(store, "prune_recipes", {"max_age_days": 90})
            self.assertEqual(result["pruned"], 1)


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
            import json
            out = json.loads(result.stdout)
            self.assertIn("strategy", out)
            self.assertIn("beams", out)


if __name__ == "__main__":
    unittest.main()
