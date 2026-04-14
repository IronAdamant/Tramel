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


class TestFindingsChecklistAdversarialScaffold(unittest.TestCase):
    """D: adversarial scaffold validation (cycles, empty, update mode, etc.)."""

    def test_d1_circular_dependency_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "c.db"))
            result = Planner(store=store).decompose(
                "create adversarial test",
                d,
                scaffold=[
                    {"file": "src/adv/A.js", "depends_on": ["src/adv/B.js"]},
                    {"file": "src/adv/B.js", "depends_on": ["src/adv/C.js"]},
                    {"file": "src/adv/C.js", "depends_on": ["src/adv/A.js"]},
                ],
            )
            self.assertEqual(result.get("error"), "circular_dependency")
            self.assertIn("scaffold_validation", result["analysis_meta"])
            self.assertEqual(
                result["analysis_meta"]["scaffold_validation"]["cycle"],
                ["src/adv/A.js", "src/adv/B.js", "src/adv/C.js", "src/adv/A.js"],
            )

    def test_d2_missing_dependencies_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            result = Planner(store=store).decompose(
                "create service",
                d,
                scaffold=[
                    {"file": "src/x.js", "depends_on": ["src/nonexistent.js"]},
                ],
            )
            self.assertEqual(result.get("error"), "missing_dependencies")
            missing = result["analysis_meta"]["scaffold_validation"]["missing_deps"]
            self.assertEqual(missing[0]["missing"], "src/nonexistent.js")

    def test_d3_empty_scaffold_creation_intent_returns_warning(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "app.py").write_text("pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "z.db"))
            result = Planner(store=store).decompose(
                "create new plugin system",
                d,
                scaffold=[],
            )
            self.assertEqual(result.get("error"), "empty_scaffold")
            self.assertIn("warning", result["analysis_meta"])
            self.assertEqual(result["steps"], [])

    def test_d4_over_constrained_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "o.db"))
            result = Planner(store=store).decompose(
                "create over constrained",
                d,
                scaffold=[
                    {
                        "file": "src/over.js",
                        "depends_on": ["a.js", "b.js", "c.js", "d.js", "e.js"],
                    },
                ],
            )
            self.assertEqual(result.get("error"), "over_constrained")

    def test_d5_self_referential_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "s.db"))
            result = Planner(store=store).decompose(
                "create self ref",
                d,
                scaffold=[
                    {"file": "src/self.js", "depends_on": ["src/self.js"]},
                ],
            )
            self.assertEqual(result.get("error"), "self_referential")

    def test_d6_diamond_dependency_produces_four_steps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "dia.db"))
            result = Planner(store=store).decompose(
                "create diamond",
                d,
                scaffold=[
                    {"file": "src/A.js"},
                    {"file": "src/B.js", "depends_on": ["src/A.js"]},
                    {"file": "src/C.js", "depends_on": ["src/A.js"]},
                    {"file": "src/D.js", "depends_on": ["src/B.js", "src/C.js"]},
                ],
            )
            self.assertEqual(len(result["steps"]), 4)
            files = {s["file"] for s in result["steps"]}
            self.assertEqual(files, {"src/A.js", "src/B.js", "src/C.js", "src/D.js"})
            metrics = result["analysis_meta"]["scaffold_dag_metrics"]
            self.assertEqual(metrics["node_count"], 4)

    def test_d7_deep_nesting_produces_twenty_steps(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            scaffold = []
            for i in range(20):
                file = f"src/mod{i}.js"
                deps = [f"src/mod{i-1}.js"] if i > 0 else []
                scaffold.append({"file": file, "depends_on": deps})
            store = RecipeStore(os.path.join(d, "deep.db"))
            result = Planner(store=store).decompose(
                "create deep chain",
                d,
                scaffold=scaffold,
            )
            self.assertEqual(len(result["steps"]), 20)
            metrics = result["analysis_meta"]["scaffold_dag_metrics"]
            self.assertEqual(metrics["critical_path_length"], 20)

    def test_d8_duplicate_files_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "dup.db"))
            result = Planner(store=store).decompose(
                "create duplicate",
                d,
                scaffold=[
                    {"file": "src/dup.js"},
                    {"file": "src/dup.js", "depends_on": []},
                ],
            )
            self.assertEqual(result.get("error"), "duplicate_files")

    def test_d9_scaffold_update_action_emits_update_step(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "existing.js").write_text("export {}\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "u.db"))
            result = Planner(store=store).decompose(
                "update existing module",
                d,
                scaffold=[
                    {"file": "existing.js", "action": "update", "description": "Add new handler"},
                ],
            )
            self.assertEqual(len(result["steps"]), 1)
            self.assertEqual(result["steps"][0]["action"], "update")
            self.assertIn("Add new handler", result["steps"][0]["description"])


if __name__ == "__main__":
    unittest.main()
