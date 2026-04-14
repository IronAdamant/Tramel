"""Archetype regression tests — Trammel must decompose reliably on
messy real-world codebases.
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import Planner  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402

_ARCH_ROOT = ROOT / "tests" / "archetypes"


def _decompose_on(root: pathlib.Path) -> dict:
    store = RecipeStore(":memory:")
    return Planner(store=store).decompose(
        f"refactor {root.name}",
        str(root),
        suppress_creation_hints=True,
        skip_recipes=True,
    )


class TestArchetypeTestFarm(unittest.TestCase):
    def test_decompose_succeeds_and_includes_source_modules(self) -> None:
        result = _decompose_on(_ARCH_ROOT / "test_farm")
        self.assertIsNone(result.get("error"), msg=result.get("analysis_meta"))
        self.assertGreater(len(result.get("steps", [])), 0)
        files = {s.get("file") for s in result["steps"]}
        src_files = {f for f in files if f and f.startswith("src/")}
        test_files = {f for f in files if f and f.startswith("tests/")}
        self.assertTrue(
            len(src_files) >= 4,
            f"Expected source modules in steps, got {src_files}",
        )
        self.assertTrue(
            len(test_files) >= 3,
            f"Expected test files in steps, got {test_files}",
        )


class TestArchetypeFacadeService(unittest.TestCase):
    def test_decompose_succeeds_and_includes_coordinator(self) -> None:
        result = _decompose_on(_ARCH_ROOT / "facade_service")
        self.assertIsNone(result.get("error"))
        self.assertGreater(len(result.get("steps", [])), 0)
        files = {s.get("file") for s in result["steps"]}
        self.assertIn("src/coordinator.py", files)
        worker_files = {f for f in files if f and f.startswith("src/workers/")}
        self.assertTrue(len(worker_files) >= 8, f"Expected workers, got {worker_files}")


class TestArchetypeMonorepo(unittest.TestCase):
    def test_decompose_succeeds_with_cross_package_deps(self) -> None:
        result = _decompose_on(_ARCH_ROOT / "monorepo")
        self.assertIsNone(result.get("error"))
        self.assertGreater(len(result.get("steps", [])), 0)
        dep_graph = result.get("dependency_graph", {})
        # auth and api should both depend on shared_utils files
        all_deps = [d for deps in dep_graph.values() for d in deps]
        self.assertTrue(
            any("shared_utils" in d for d in all_deps),
            "shared_utils should appear as a dependency in the graph",
        )


class TestArchetypeGeneratedCode(unittest.TestCase):
    def test_decompose_succeeds_and_includes_handmade_files(self) -> None:
        result = _decompose_on(_ARCH_ROOT / "generated_code")
        self.assertIsNone(result.get("error"))
        self.assertGreater(len(result.get("steps", [])), 0)
        files = {s.get("file") for s in result["steps"]}
        self.assertIn("src/handmade/cli.py", files)
        self.assertIn("src/handmade/core.py", files)
        gen_files = {f for f in files if f and f.startswith("src/generated/")}
        self.assertTrue(len(gen_files) >= 3, f"Expected generated files, got {gen_files}")


class TestArchetypeLegacyBallOfMud(unittest.TestCase):
    def test_decompose_succeeds_despite_cycles_and_high_fanout(self) -> None:
        result = _decompose_on(_ARCH_ROOT / "legacy_ball_of_mud")
        self.assertIsNone(result.get("error"))
        self.assertGreater(len(result.get("steps", [])), 0)
        files = {s.get("file") for s in result["steps"]}
        self.assertIn("src/hub.py", files)
        self.assertIn("src/a.py", files)
        self.assertIn("src/b.py", files)
        self.assertIn("src/c.py", files)
        # circular import chain a->b->c->a should not fatal
        dep_graph = result.get("dependency_graph", {})
        # high fan-out hub should be in graph with many deps
        hub_deps = dep_graph.get("src/hub.py", [])
        self.assertTrue(len(hub_deps) >= 6, f"hub.py fan-out too low: {hub_deps}")


class TestArchetypeDashboard(unittest.TestCase):
    """Meta-test: prints a markdown table of pass/fail per archetype."""

    def test_dashboard(self) -> None:
        rows = []
        for name in (
            "test_farm",
            "facade_service",
            "monorepo",
            "generated_code",
            "legacy_ball_of_mud",
        ):
            result = _decompose_on(_ARCH_ROOT / name)
            error = result.get("error")
            step_count = len(result.get("steps", []))
            status = "✅ pass" if error is None and step_count > 0 else "❌ fail"
            rows.append(f"| {name} | {step_count} | {status} |")

        table = "\n".join([
            "| Archetype | Steps | Status |",
            "|-----------|-------|--------|",
            *rows,
        ])
        # Print for CI logs; assertion always passes so the table is visible
        print("\n" + table + "\n")
        self.assertTrue(all("pass" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
