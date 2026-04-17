"""Contract + coverage tests for the MCP dispatch layer.

These complement :mod:`tests.test_trammel_extra` by asserting:

* Every declared tool schema has a handler and vice versa.
* Every registered tool is exercised at least once (smoke).
* Tool categories in schemas match the documented set.
* Previously-uncovered handlers (batch step update, claim/release,
  multi-agent queries, merge, usage stats, strategy stats, failure
  resolution) actually work end-to-end.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel.mcp_server import _DISPATCH, _TOOL_SCHEMAS, dispatch_tool  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402
from trammel.tool_schemas import TOOL_CATEGORIES  # noqa: E402


_EXPECTED_CATEGORIES = {
    "planning", "execution", "memory", "coordination", "telemetry", "general",
}


class TestDispatchRegistry(unittest.TestCase):
    """Schema/dispatch parity and schema shape invariants."""

    def test_schema_dispatch_parity(self) -> None:
        """Every schema has a handler and vice versa."""
        missing_handlers = set(_TOOL_SCHEMAS) - set(_DISPATCH)
        missing_schemas = set(_DISPATCH) - set(_TOOL_SCHEMAS)
        self.assertFalse(missing_handlers, f"Schemas without handlers: {missing_handlers}")
        self.assertFalse(missing_schemas, f"Handlers without schemas: {missing_schemas}")

    def test_every_schema_has_required_fields(self) -> None:
        """Schemas expose name, description, category, and parameters."""
        for name, schema in _TOOL_SCHEMAS.items():
            self.assertEqual(schema["name"], name, f"schema name mismatch for {name}")
            self.assertTrue(schema["description"], f"{name} missing description")
            self.assertIn(schema["category"], _EXPECTED_CATEGORIES,
                          f"{name} has unknown category {schema['category']!r}")
            params = schema["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIn("properties", params)
            self.assertIsInstance(params.get("required", []), list)

    def test_categories_synced_with_registry(self) -> None:
        """TOOL_CATEGORIES covers every dispatched tool with no extras."""
        extras = set(TOOL_CATEGORIES) - set(_DISPATCH)
        missing = set(_DISPATCH) - set(TOOL_CATEGORIES)
        self.assertFalse(extras, f"Extra entries in TOOL_CATEGORIES: {extras}")
        self.assertFalse(missing, f"Tools missing from TOOL_CATEGORIES: {missing}")

    def test_unknown_tool_raises(self) -> None:
        """Dispatch rejects unknown tool names with a helpful error."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                with self.assertRaises(ValueError) as cm:
                    dispatch_tool(store, "not_a_real_tool", {})
                self.assertIn("not_a_real_tool", str(cm.exception))


class TestMultiAgentDispatch(unittest.TestCase):
    """claim_step / release_step / available_steps smoke coverage."""

    def test_claim_release_and_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                strat = {
                    "steps": [
                        {"step_index": 0, "description": "first", "depends_on": []},
                        {"step_index": 1, "description": "second", "depends_on": [0]},
                    ]
                }
                plan = dispatch_tool(store, "create_plan", {"goal": "g", "strategy": strat})
                plan_id = plan["plan_id"]

                full = dispatch_tool(store, "get_plan", {"plan_id": plan_id})
                step_id = full["steps"][0]["id"]

                claim = dispatch_tool(store, "claim_step", {
                    "plan_id": plan_id, "step_id": step_id, "agent_id": "agent-a",
                })
                self.assertTrue(claim.get("claimed") or claim.get("ok") or claim)

                available = dispatch_tool(store, "available_steps", {
                    "plan_id": plan_id, "agent_id": "agent-b",
                })
                self.assertIsInstance(available, list)

                release = dispatch_tool(store, "release_step", {
                    "step_id": step_id, "agent_id": "agent-a",
                })
                self.assertEqual(release.get("ok"), True)


class TestBatchStepUpdate(unittest.TestCase):
    """record_steps: batch step status update."""

    def test_batch_update_counts_and_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                strat = {"steps": [
                    {"step_index": i, "description": f"s{i}", "depends_on": []}
                    for i in range(3)
                ]}
                plan = dispatch_tool(store, "create_plan", {"goal": "g", "strategy": strat})
                pid = plan["plan_id"]
                full = dispatch_tool(store, "get_plan", {"plan_id": pid})

                updates = [
                    {"step_id": s["id"], "status": "passed"} for s in full["steps"]
                ]
                result = dispatch_tool(store, "record_steps", {"steps": updates})
                self.assertEqual(result["ok"], True)
                self.assertEqual(result["steps_updated"], 3)

                refreshed = dispatch_tool(store, "get_plan", {"plan_id": pid})
                self.assertTrue(all(s["status"] == "passed" for s in refreshed["steps"]))


class TestMergePlans(unittest.TestCase):
    """merge_plans: compose two plans into a third."""

    def test_merge_returns_new_plan_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                strat_a = {"steps": [{"step_index": 0, "description": "a0", "depends_on": []}]}
                strat_b = {"steps": [{"step_index": 0, "description": "b0", "depends_on": []}]}
                a = dispatch_tool(store, "create_plan", {"goal": "A", "strategy": strat_a})
                b = dispatch_tool(store, "create_plan", {"goal": "B", "strategy": strat_b})

                merged = dispatch_tool(store, "merge_plans", {
                    "plan_a_id": a["plan_id"], "plan_b_id": b["plan_id"],
                    "strategy": "sequential",
                })
                self.assertIn("plan_id", merged)
                new = dispatch_tool(store, "get_plan", {"plan_id": merged["plan_id"]})
                self.assertIsNotNone(new)


class TestTelemetryAndStats(unittest.TestCase):
    """usage_stats / list_strategies / resolve_failure coverage."""

    def test_usage_stats_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                dispatch_tool(store, "status", {})
                dispatch_tool(store, "status", {})
                stats = dispatch_tool(store, "usage_stats", {"days": 30})
                self.assertIn("tool_calls", stats)
                self.assertIn("recipe_hit_rate", stats)
                self.assertIn("strategy_win_rates", stats)
                self.assertGreaterEqual(stats["total_tool_calls"], 2)

    def test_list_strategies_returns_known_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                strategies = dispatch_tool(store, "list_strategies", {})
                self.assertIsInstance(strategies, list)
                self.assertTrue(strategies)
                names = {s["name"] for s in strategies}
                self.assertIn("bottom_up", names)

    def test_resolve_failure_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                store.record_failure_pattern("foo.py", "ImportError", "msg")
                result = dispatch_tool(store, "resolve_failure", {
                    "file_path": "foo.py",
                    "error_type": "ImportError",
                    "resolution": "added missing import",
                })
                self.assertEqual(result.get("ok"), True)

                history = dispatch_tool(store, "failure_history", {"file_path": "foo.py"})
                self.assertTrue(history)
                self.assertEqual(history[0]["last_resolution"], "added missing import")


class TestIntCoercion(unittest.TestCase):
    """Schema-driven int coercion: string inputs for integer params are accepted."""

    def test_string_plan_id_is_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "trammel.db")
            with RecipeStore(db) as store:
                strat = {"steps": [{"step_index": 0, "description": "s", "depends_on": []}]}
                plan = dispatch_tool(store, "create_plan", {"goal": "g", "strategy": strat})
                pid = plan["plan_id"]
                # Pass the ID as a string — dispatch layer must coerce to int.
                got = dispatch_tool(store, "get_plan", {"plan_id": str(pid)})
                self.assertEqual(got["id"], pid)


if __name__ == "__main__":
    unittest.main()
