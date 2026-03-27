"""In-repo validation for ``findings/trammel.md`` checklist (A–C, D product items).

Replaces manual RecipeLab runs in CI: same stdlib-only core, no third-party deps.
External HTTP checks (RecipeLab ``/api/mcp-challenge/trammel/plan-graph-metrics``) are
optional; chain DAG semantics are asserted here via ``compute_scaffold_dag_metrics``.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

from trammel.mcp_server import dispatch_tool
from trammel.store import RecipeStore
from trammel.core import Planner
from trammel.utils import compute_scaffold_dag_metrics


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestFindingsChecklistBaseline(unittest.TestCase):
    """A: estimate + list_recipes baseline."""

    def test_a1_estimate_returns_matching_files_and_recommendation(self) -> None:
        store = RecipeStore(":memory:")
        out = dispatch_tool(store, "estimate", {
            "project_root": _repo_root(),
            "language": "python",
        })
        self.assertIn("matching_files", out)
        self.assertIsInstance(out["matching_files"], int)
        self.assertGreaterEqual(out["matching_files"], 1)
        self.assertIn(out["recommendation"], ("full analysis OK", "use scope"))
        self.assertEqual(out.get("language"), "python")

    def test_a2_list_recipes_limit_50_returns_list(self) -> None:
        store = RecipeStore(":memory:")
        out = dispatch_tool(store, "list_recipes", {"limit": 50})
        self.assertIsInstance(out, list)


class TestFindingsChecklistScaffoldMatrix(unittest.TestCase):
    """B: greenfield chain, all-existing skip JSON, refactor + suppress."""

    def test_b3_greenfield_chain_three_steps_under_src(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "t.db"))
            result = Planner(store=store).decompose(
                "telemetry subsystem",
                d,
                scaffold=[
                    {"file": "src/mcpTelemetrySink.js", "depends_on": []},
                    {"file": "src/mcpTelemetryQuery.js", "depends_on": ["src/mcpTelemetrySink.js"]},
                    {"file": "src/mcpTelemetryRoutes.js", "depends_on": ["src/mcpTelemetryQuery.js"]},
                ],
            )
            self.assertEqual(len(result["steps"]), 3)
            files = [s["file"] for s in result["steps"]]
            self.assertEqual(
                set(files),
                {
                    "src/mcpTelemetrySink.js",
                    "src/mcpTelemetryQuery.js",
                    "src/mcpTelemetryRoutes.js",
                },
            )
            self.assertTrue(result["analysis_meta"].get("scaffold_only"))

    def test_b4_all_existing_scaffold_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name in ("x.js", "y.js", "z.js"):
                pathlib.Path(d, name).write_text("export {}\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "e.db"))
            result = Planner(store=store).decompose(
                "verify DAG",
                d,
                scaffold=[
                    {"file": "x.js"},
                    {"file": "y.js", "depends_on": ["x.js"]},
                    {"file": "z.js", "depends_on": ["y.js"]},
                ],
            )
            self.assertEqual(len(result["steps"]), 0)
            meta = result["analysis_meta"]
            skip = meta.get("skipped_existing_scaffold")
            self.assertIsNotNone(skip)
            self.assertEqual(skip["count"], 3)
            self.assertIn("paths", skip)
            self.assertIn("topological_order", skip)
            self.assertIn("summary", skip)
            self.assertIn("scaffold_dag_metrics", meta)

    def test_b5_refactor_goal_no_creation_hints_with_suppress(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "mcpChallengeRoutes.js").write_text("export {}\n", encoding="utf-8")
            pathlib.Path(d, "package.json").write_text('{"name":"t"}\n', encoding="utf-8")
            store = RecipeStore(os.path.join(d, "r.db"))
            result = Planner(store=store).decompose(
                "Refactor mcpChallengeRoutes to consolidate POST handlers",
                d,
                skip_recipes=True,
                relevant_only=True,
                suppress_creation_hints=True,
            )
            self.assertNotIn("creation_hints", result)


class TestFindingsChecklistPlanGraphAlignment(unittest.TestCase):
    """C: chain DAG ⇒ critical_path_length equals node count (RecipeLab convention)."""

    def test_c6_chain_critical_path_equals_three_nodes(self) -> None:
        g = {
            "src/a.js": [],
            "src/b.js": ["src/a.js"],
            "src/c.js": ["src/b.js"],
        }
        m = compute_scaffold_dag_metrics(g)
        self.assertEqual(m["node_count"], 3)
        self.assertEqual(m["critical_path_length"], 3)
        self.assertEqual(m["max_parallelism"], 1)
        self.assertEqual(m["max_dependency_depth"], 3)


if __name__ == "__main__":
    unittest.main()
