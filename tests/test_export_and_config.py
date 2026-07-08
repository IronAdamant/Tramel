"""Real-path tests for config-driven test_cmd and versioned plan export (v3.14)."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import (  # noqa: E402
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    ExecutionHarness,
    RecipeStore,
    export_plan,
    export_plan_from_store,
    export_strategy,
    resolve_test_cmd,
)
from trammel.mcp_server import dispatch_tool  # noqa: E402
from trammel.project_config import load_project_config  # noqa: E402


class TestResolveTestCmd(unittest.TestCase):
    """Project config test_cmd precedence via the shipped resolver."""

    def test_config_used_when_explicit_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": ["python", "-c", "pass"]}),
                encoding="utf-8",
            )
            cmd = resolve_test_cmd(None, d)
            self.assertEqual(cmd, ["python", "-c", "pass"])
            # load_project_config also surfaces the key for orchestrators
            self.assertEqual(load_project_config(d)["test_cmd"], ["python", "-c", "pass"])

    def test_explicit_overrides_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": ["from-config"]}),
                encoding="utf-8",
            )
            cmd = resolve_test_cmd(["from-caller", "-x"], d)
            self.assertEqual(cmd, ["from-caller", "-x"])

    def test_no_config_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(resolve_test_cmd(None, d))

    def test_empty_list_in_config_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": []}),
                encoding="utf-8",
            )
            # empty list is not a useful command; resolver requires non-empty
            self.assertIsNone(resolve_test_cmd(None, d))


class TestHarnessConfigTestCmd(unittest.TestCase):
    """ExecutionHarness honor project config when constructor test_cmd is omitted."""

    def test_effective_cmd_from_trammel_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": ["custom-runner", "--flag"]}),
                encoding="utf-8",
            )
            h = ExecutionHarness()  # no explicit test_cmd
            self.assertEqual(h._effective_test_cmd(d), ["custom-runner", "--flag"])

    def test_constructor_override_beats_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": ["from-config"]}),
                encoding="utf-8",
            )
            h = ExecutionHarness(test_cmd=["override"])
            self.assertEqual(h._effective_test_cmd(d), ["override"])

    def test_verify_step_runs_config_test_cmd(self) -> None:
        """End-to-end: omitted test_cmd + project config runs that command successfully."""
        with tempfile.TemporaryDirectory() as d:
            # Always-pass test command via python -c (stdlib, no pytest needed)
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": [sys.executable, "-c", "raise SystemExit(0)"]}),
                encoding="utf-8",
            )
            pathlib.Path(d, "mod.py").write_text("x = 1\n", encoding="utf-8")
            h = ExecutionHarness(timeout_s=15)
            result = h.verify_step([], d)
            self.assertTrue(
                result.get("success"),
                f"expected config test_cmd to pass; got {result!r}",
            )

    def test_verify_step_explicit_override_ignores_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".trammel.json").write_text(
                json.dumps({"test_cmd": [sys.executable, "-c", "raise SystemExit(0)"]}),
                encoding="utf-8",
            )
            pathlib.Path(d, "mod.py").write_text("x = 1\n", encoding="utf-8")
            # Explicit failing command must win over config success
            h = ExecutionHarness(
                timeout_s=15,
                test_cmd=[sys.executable, "-c", "raise SystemExit(1)"],
            )
            result = h.verify_step([], d)
            self.assertFalse(result.get("success"))


class TestExportStrategyAndPlan(unittest.TestCase):
    """Versioned export documents for external (non-MCP) runners."""

    def _sample_strategy(self) -> dict:
        return {
            "steps": [
                {
                    "file": "a.py",
                    "description": "edit a",
                    "rationale": "leaf",
                    "depends_on": [],
                    "symbols": ["A"],
                },
                {
                    "file": "b.py",
                    "description": "edit b",
                    "rationale": "depends on a",
                    "depends_on": [0],
                    "symbols": ["B"],
                },
            ],
            "dependency_graph": {"b.py": ["a.py"], "a.py": []},
            "constraints": [],
            "goal_fingerprint": "demo",
        }

    def test_export_strategy_has_version_and_steps(self) -> None:
        strategy = self._sample_strategy()
        doc = export_strategy(strategy, goal="refactor demo")
        self.assertEqual(doc["format"], EXPORT_FORMAT)
        self.assertEqual(doc["format"], "trammel.plan")
        self.assertEqual(doc["format_version"], EXPORT_FORMAT_VERSION)
        self.assertEqual(doc["format_version"], 1)
        self.assertEqual(doc["goal"], "refactor demo")
        self.assertEqual(doc["status"], "strategy")
        self.assertIsNone(doc["plan_id"])
        self.assertEqual(len(doc["steps"]), 2)
        self.assertEqual(doc["steps"][0]["file"], "a.py")
        self.assertEqual(doc["steps"][1]["depends_on"], [0])
        self.assertEqual(doc["dependency_graph"]["b.py"], ["a.py"])
        self.assertIs(doc["strategy"], strategy)
        self.assertIn("exported_at", doc)
        self.assertIsInstance(doc["exported_at"], float)

    def test_export_strategy_writes_file(self) -> None:
        strategy = self._sample_strategy()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plan.json")
            doc = export_strategy(strategy, goal="g", path=path)
            self.assertTrue(os.path.isfile(path))
            on_disk = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            self.assertEqual(on_disk["format"], "trammel.plan")
            self.assertEqual(on_disk["format_version"], 1)
            self.assertEqual(on_disk["goal"], "g")
            self.assertEqual(len(on_disk["steps"]), 2)
            self.assertEqual(on_disk["steps"][1]["depends_on"], [0])
            # Returned doc matches file (except we re-read JSON so floats match)
            self.assertEqual(doc["goal"], on_disk["goal"])

    def test_export_plan_from_store(self) -> None:
        strategy = self._sample_strategy()
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            out_path = os.path.join(d, "export.json")
            with RecipeStore(db) as store:
                plan_id = store.create_plan("ship export", strategy)
                doc = export_plan_from_store(store, plan_id, path=out_path)
            self.assertNotIn("error", doc)
            self.assertEqual(doc["format"], "trammel.plan")
            self.assertEqual(doc["format_version"], 1)
            self.assertEqual(doc["goal"], "ship export")
            self.assertEqual(doc["plan_id"], plan_id)
            self.assertEqual(doc["status"], "pending")
            self.assertEqual(len(doc["steps"]), 2)
            # Steps from store include depends_on for external runners
            self.assertEqual(doc["steps"][1]["depends_on"], [0])
            self.assertTrue(os.path.isfile(out_path))
            loaded = json.loads(pathlib.Path(out_path).read_text(encoding="utf-8"))
            self.assertEqual(loaded["plan_id"], plan_id)
            self.assertEqual(loaded["steps"][0]["description"], "edit a")

    def test_export_plan_dict_direct(self) -> None:
        plan = {
            "id": 7,
            "goal": "g",
            "status": "running",
            "strategy": self._sample_strategy(),
            "steps": [
                {
                    "id": 1,
                    "step_index": 0,
                    "description": "s0",
                    "rationale": "r0",
                    "depends_on": [],
                    "status": "passed",
                },
                {
                    "id": 2,
                    "step_index": 1,
                    "description": "s1",
                    "rationale": "r1",
                    "depends_on": [0],
                    "status": "pending",
                },
            ],
            "current_step": 1,
            "total_steps": 2,
            "created": 1.0,
            "updated": 2.0,
        }
        doc = export_plan(plan)
        self.assertEqual(doc["plan_id"], 7)
        self.assertEqual(doc["status"], "running")
        self.assertEqual(doc["steps"][1]["depends_on"], [0])
        self.assertEqual(doc["metadata"]["current_step"], 1)

    def test_export_plan_missing_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            with RecipeStore(db) as store:
                doc = export_plan_from_store(store, 99999)
            self.assertEqual(doc["error"], "plan not found")
            self.assertEqual(doc["format"], "trammel.plan")


class TestExportPlanMcp(unittest.TestCase):
    def test_dispatch_export_plan(self) -> None:
        strategy = {
            "steps": [
                {"description": "one", "rationale": "r", "depends_on": []},
                {"description": "two", "rationale": "r", "depends_on": [0]},
            ],
            "dependency_graph": {},
        }
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            path = os.path.join(d, "out.json")
            with RecipeStore(db) as store:
                plan_id = store.create_plan("mcp export", strategy)
                result = dispatch_tool(
                    store, "export_plan", {"plan_id": plan_id, "path": path},
                )
            self.assertEqual(result["format"], "trammel.plan")
            self.assertEqual(result["format_version"], 1)
            self.assertEqual(result["goal"], "mcp export")
            self.assertEqual(result["steps"][1]["depends_on"], [0])
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
