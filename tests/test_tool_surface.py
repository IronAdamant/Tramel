"""MCP tool-surface simplification: primary vs advanced tiers."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel.mcp_server import (  # noqa: E402
    _DISPATCH,
    _PRIMARY_TOOLS,
    _TOOL_SCHEMAS,
    _schemas_for_surface,
    dispatch_tool,
)
from trammel.store import RecipeStore  # noqa: E402
from trammel.tool_schemas import (  # noqa: E402
    PRIMARY_TOOLS,
    TOOL_SCHEMAS,
    schemas_for_surface,
    tool_tier,
)


class TestToolSurface(unittest.TestCase):
    def test_primary_is_strict_subset(self) -> None:
        self.assertTrue(PRIMARY_TOOLS)
        self.assertLess(len(PRIMARY_TOOLS), len(TOOL_SCHEMAS))
        self.assertTrue(PRIMARY_TOOLS.issubset(set(TOOL_SCHEMAS)))
        # Happy-path compose tool is primary
        self.assertIn("start_plan", PRIMARY_TOOLS)
        # Power tools stay advanced (still dispatched)
        for name in ("explore", "claim_step", "prune_recipes", "merge_plans"):
            self.assertIn(name, TOOL_SCHEMAS)
            self.assertEqual(tool_tier(name), "advanced")
            self.assertNotIn(name, PRIMARY_TOOLS)

    def test_schemas_for_surface_filters(self) -> None:
        primary = schemas_for_surface("primary")
        full = schemas_for_surface("all")
        self.assertEqual(set(primary), set(PRIMARY_TOOLS))
        self.assertEqual(set(full), set(TOOL_SCHEMAS))
        self.assertEqual(len(primary), len(PRIMARY_TOOLS))
        self.assertGreater(len(full), len(primary))
        # aliases
        self.assertEqual(set(schemas_for_surface("happy")), set(primary))
        self.assertEqual(set(schemas_for_surface("full")), set(full))

    def test_every_schema_has_tier(self) -> None:
        for name, schema in TOOL_SCHEMAS.items():
            self.assertIn(schema.get("tier"), ("primary", "advanced"), name)
            self.assertEqual(schema["tier"], tool_tier(name))
            if schema["tier"] == "advanced":
                self.assertIn("[advanced]", schema["description"])

    def test_schema_dispatch_includes_start_plan(self) -> None:
        self.assertEqual(set(_TOOL_SCHEMAS), set(_DISPATCH))
        self.assertIn("start_plan", _DISPATCH)
        self.assertEqual(_PRIMARY_TOOLS, PRIMARY_TOOLS)

    def test_status_exposes_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "t.db")
            with RecipeStore(db) as store:
                summary = dispatch_tool(store, "status", {})
        self.assertEqual(summary["primary_tool_count"], len(PRIMARY_TOOLS))
        self.assertEqual(set(summary["primary_tools"]), set(PRIMARY_TOOLS))
        self.assertEqual(summary["tools"], len(TOOL_SCHEMAS))
        self.assertIn("start_plan", summary["primary_tools"])
        self.assertIn("explore", summary["advanced_tools"])
        self.assertEqual(summary["tool_surface_default"], "primary")

    def test_start_plan_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "t.db")
            root = os.path.join(tmp, "proj")
            os.makedirs(root)
            pathlib.Path(root, "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
            with RecipeStore(db) as store:
                out = dispatch_tool(
                    store,
                    "start_plan",
                    {
                        "goal": "touch a",
                        "project_root": root,
                        "scaffold": [
                            {"file": "a.py", "description": "module a"},
                        ],
                    },
                )
                self.assertEqual(out.get("workflow"), "start_plan")
                self.assertTrue(out.get("persisted"))
                self.assertIsInstance(out.get("plan_id"), int)
                self.assertIsInstance(out.get("strategy"), dict)
                plan = store.get_plan(out["plan_id"])
                self.assertIsNotNone(plan)
                self.assertEqual(plan["goal"], "touch a")

    def test_start_plan_persist_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "t.db")
            root = os.path.join(tmp, "proj")
            os.makedirs(root)
            with RecipeStore(db) as store:
                out = dispatch_tool(
                    store,
                    "start_plan",
                    {
                        "goal": "ephemeral",
                        "project_root": root,
                        "persist": False,
                        "scaffold": [{"file": "x.py", "description": "x"}],
                    },
                )
                self.assertFalse(out.get("persisted"))
                self.assertIsNone(out.get("plan_id"))
                self.assertIn("strategy", out)

    def test_advanced_still_dispatchable(self) -> None:
        """Names not in the primary listing remain callable (compat)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "t.db")
            with RecipeStore(db) as store:
                # estimate is advanced but must still work via dispatch
                self.assertEqual(tool_tier("estimate"), "advanced")
                root = os.path.join(tmp, "p")
                os.makedirs(root)
                pathlib.Path(root, "m.py").write_text("x=1\n", encoding="utf-8")
                out = dispatch_tool(
                    store, "estimate", {"project_root": root},
                )
                self.assertIn("matching_files", out)


if __name__ == "__main__":
    unittest.main()
