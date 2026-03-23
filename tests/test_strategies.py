"""Tests for beam strategy registry, learning feedback, and MCP tool."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trammel import Planner  # noqa: E402
from trammel.strategies import (  # noqa: E402
    _STRATEGY_REGISTRY,
    _order_bottom_up,
    _order_cohesion,
    _order_critical_path,
    _order_hub_first,
    _order_leaf_first,
    _order_minimal_change,
    _order_risk_first,
    _order_test_adjacent,
    _order_top_down,
    get_strategies,
    register_strategy,
)
from trammel.mcp_server import dispatch_tool  # noqa: E402
from trammel.store import RecipeStore  # noqa: E402


class TestBeamStrategies(unittest.TestCase):
    def test_skipped_excluded_from_edits(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            pathlib.Path(d, "b.py").write_text("def bar():\n    pass\n", encoding="utf-8")
            store = RecipeStore(os.path.join(d, "bs.db"))
            store.add_constraint("avoid", "skip b", context={"file": "b.py"})
            planner = Planner(store=store)
            strat = planner.decompose("task", d)
            beams = planner.explore_trajectories(strat, num_beams=3)
            for beam in beams:
                edit_paths = [e.get("path") for e in beam["edits"]]
                self.assertNotIn("b.py", edit_paths)
                self.assertIn("skipped", beam)

    def test_bottom_up_skipped_at_end(self) -> None:
        steps = [
            {"file": "a.py", "status": "skipped"},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        ordered = _order_bottom_up(steps, {})
        self.assertEqual(ordered[-1]["file"], "a.py")
        self.assertEqual(ordered[-1].get("status"), "skipped")

    def test_risk_first_isolates_incompatible(self) -> None:
        steps = [
            {"file": "a.py", "incompatible_with": ["c.py"]},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        dep_graph = {"b.py": ["a.py"], "c.py": ["a.py"]}
        ordered = _order_risk_first(steps, dep_graph)
        active_files = [s["file"] for s in ordered if s.get("status") != "skipped"]
        a_idx = active_files.index("a.py")
        self.assertEqual(a_idx, 0)


# ── Registry tests ───────────────────────────────────────────────────────────

class TestStrategyRegistry(unittest.TestCase):
    def test_builtins_registered(self) -> None:
        names = get_strategies()
        for expected in ("bottom_up", "top_down", "risk_first", "critical_path",
                         "cohesion", "minimal_change", "leaf_first", "hub_first", "test_adjacent"):
            self.assertIn(expected, names)
        self.assertEqual(len(names), 9)

    def test_register_custom(self) -> None:
        name = "_test_custom_strat"
        try:
            def noop(steps, dep_graph):
                return steps
            register_strategy(name, "test strategy", noop)
            self.assertIn(name, get_strategies())
        finally:
            _STRATEGY_REGISTRY.pop(name, None)

    def test_duplicate_raises(self) -> None:
        with self.assertRaises(ValueError):
            register_strategy("bottom_up", "duplicate", lambda s, d: s)

    @patch("trammel.core.os.cpu_count", return_value=12)
    def test_custom_used_in_beams(self, _mock_cpu: object) -> None:
        name = "_test_beam_strat"
        try:
            def reverse_strat(steps, dep_graph):
                return list(reversed(steps))
            register_strategy(name, "reverse ordering", reverse_strat)

            with tempfile.TemporaryDirectory() as d:
                pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
                planner = Planner(store=RecipeStore(os.path.join(d, "x.db")))
                strat = planner.decompose("task", d)
                beams = planner.explore_trajectories(strat, num_beams=10)
                variants = {b["variant"] for b in beams}
                self.assertIn(name, variants)
        finally:
            _STRATEGY_REGISTRY.pop(name, None)


# ── Strategy stats & learning ────────────────────────────────────────────────

class TestStrategyStats(unittest.TestCase):
    def test_stats_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "s.db"))
            stats = store.get_strategy_stats()
            self.assertEqual(stats, {})

    def test_stats_from_trajectories(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "s.db"))
            pid = store.create_plan("g", {"steps": []})
            store.log_trajectory(pid, 0, "bottom_up", 1, {"success": True})
            store.log_trajectory(pid, 1, "bottom_up", 1, {"success": True})
            store.log_trajectory(pid, 2, "top_down", 0, {"success": False})
            stats = store.get_strategy_stats()
            self.assertEqual(stats["bottom_up"], (2, 0))
            self.assertEqual(stats["top_down"], (0, 1))

    def test_learning_biases_order(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "l.db"))
            pid = store.create_plan("g", {"steps": []})
            # Log many successes for risk_first
            for _ in range(10):
                store.log_trajectory(pid, 0, "risk_first", 1, {"success": True})
            # Log failures for bottom_up
            for _ in range(10):
                store.log_trajectory(pid, 0, "bottom_up", 0, {"success": False})

            pathlib.Path(d, "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
            planner = Planner(store=store)
            strat = planner.decompose("task", d)
            beams = planner.explore_trajectories(strat, num_beams=3)
            # risk_first should come first (highest success rate)
            self.assertEqual(beams[0]["variant"], "risk_first")


# ── New strategy ordering tests ─────────────────────────────────────────────

class TestNewStrategies(unittest.TestCase):
    def test_critical_path_deepest_first(self) -> None:
        # Steps for a.py, b.py, c.py, d.py
        # dep_graph: d->c->b->a chain. d has depth 3, should come first.
        steps = [
            {"file": "a.py", "symbol_count": 1},
            {"file": "b.py", "symbol_count": 1},
            {"file": "c.py", "symbol_count": 1},
            {"file": "d.py", "symbol_count": 1},
        ]
        dep_graph = {"d.py": ["c.py"], "c.py": ["b.py"], "b.py": ["a.py"]}
        ordered = _order_critical_path(steps, dep_graph)
        files = [s["file"] for s in ordered]
        self.assertEqual(files[0], "d.py")  # deepest chain

    def test_critical_path_skipped_at_end(self) -> None:
        steps = [
            {"file": "a.py", "status": "skipped"},
            {"file": "b.py"},
        ]
        ordered = _order_critical_path(steps, {})
        self.assertEqual(ordered[-1]["file"], "a.py")
        self.assertEqual(ordered[-1].get("status"), "skipped")

    def test_critical_path_handles_cycle(self) -> None:
        steps = [{"file": "a.py"}, {"file": "b.py"}]
        dep_graph = {"a.py": ["b.py"], "b.py": ["a.py"]}
        ordered = _order_critical_path(steps, dep_graph)
        self.assertEqual(len(ordered), 2)

    def test_cohesion_groups_connected(self) -> None:
        # Two disconnected components: {a,b} and {c,d}
        steps = [
            {"file": "a.py"}, {"file": "b.py"},
            {"file": "c.py"}, {"file": "d.py"},
        ]
        dep_graph = {"b.py": ["a.py"], "d.py": ["c.py"]}
        ordered = _order_cohesion(steps, dep_graph)
        files = [s["file"] for s in ordered]
        # a and b should be adjacent, c and d should be adjacent
        a_idx, b_idx = files.index("a.py"), files.index("b.py")
        c_idx, d_idx = files.index("c.py"), files.index("d.py")
        self.assertEqual(abs(a_idx - b_idx), 1)
        self.assertEqual(abs(c_idx - d_idx), 1)

    def test_cohesion_largest_component_first(self) -> None:
        steps = [
            {"file": "a.py"}, {"file": "b.py"}, {"file": "c.py"},
            {"file": "d.py"},
        ]
        dep_graph = {"b.py": ["a.py"], "c.py": ["a.py"]}
        ordered = _order_cohesion(steps, dep_graph)
        files = [s["file"] for s in ordered]
        # Component {a,b,c} is size 3, {d} is size 1
        # a/b/c should come before d
        d_idx = files.index("d.py")
        self.assertGreater(d_idx, files.index("a.py"))

    def test_cohesion_skipped_at_end(self) -> None:
        steps = [
            {"file": "a.py", "status": "skipped"},
            {"file": "b.py"},
        ]
        ordered = _order_cohesion(steps, {})
        self.assertEqual(ordered[-1]["file"], "a.py")

    def test_minimal_change_ascending_symbols(self) -> None:
        steps = [
            {"file": "a.py", "symbol_count": 5},
            {"file": "b.py", "symbol_count": 1},
            {"file": "c.py", "symbol_count": 3},
        ]
        ordered = _order_minimal_change(steps, {})
        counts = [s["symbol_count"] for s in ordered]
        self.assertEqual(counts, [1, 3, 5])

    def test_minimal_change_skipped_at_end(self) -> None:
        steps = [
            {"file": "a.py", "symbol_count": 1, "status": "skipped"},
            {"file": "b.py", "symbol_count": 2},
        ]
        ordered = _order_minimal_change(steps, {})
        self.assertEqual(ordered[-1]["file"], "a.py")

    def test_minimal_change_zero_symbols(self) -> None:
        steps = [
            {"file": "a.py", "symbol_count": 3},
            {"file": "b.py", "symbol_count": 0},
        ]
        ordered = _order_minimal_change(steps, {})
        self.assertEqual(ordered[0]["file"], "b.py")


# ── MCP tool ─────────────────────────────────────────────────────────────────

class TestListStrategiesMCP(unittest.TestCase):
    def test_list_strategies_tool(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(os.path.join(d, "m.db"))
            result = dispatch_tool(store, "list_strategies", {})
            names = [r["name"] for r in result]
            self.assertIn("bottom_up", names)
            self.assertIn("critical_path", names)
            self.assertEqual(len(result), 9)
            self.assertIn("successes", result[0])
            self.assertIn("failures", result[0])


class TestEnhancedStrategies(unittest.TestCase):
    def test_bottom_up_sorts_by_deps(self) -> None:
        steps = [
            {"file": "a.py"},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        dep_graph = {"b.py": ["a.py", "c.py"], "c.py": ["a.py"]}
        ordered = _order_bottom_up(steps, dep_graph)
        files = [s["file"] for s in ordered if s.get("status") != "skipped"]
        self.assertEqual(files, ["a.py", "c.py", "b.py"])

    def test_top_down_sorts_by_deps(self) -> None:
        steps = [
            {"file": "a.py"},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        dep_graph = {"b.py": ["a.py", "c.py"], "c.py": ["a.py"]}
        ordered = _order_top_down(steps, dep_graph)
        files = [s["file"] for s in ordered if s.get("status") != "skipped"]
        self.assertEqual(files, ["b.py", "c.py", "a.py"])


class TestLeafFirstStrategy(unittest.TestCase):
    def test_leaf_files_first(self) -> None:
        steps = [
            {"file": "a.py"},
            {"file": "b.py"},
            {"file": "c.py"},
        ]
        dep_graph = {"b.py": ["a.py"], "c.py": ["a.py"]}
        ordered = _order_leaf_first(steps, dep_graph)
        files = [s["file"] for s in ordered]
        # b.py and c.py have 0 importers; a.py is imported by 2
        self.assertEqual(files[-1], "a.py")

    def test_leaf_first_skipped_at_end(self) -> None:
        steps = [{"file": "a.py", "status": "skipped"}, {"file": "b.py"}]
        ordered = _order_leaf_first(steps, {})
        self.assertEqual(ordered[-1].get("status"), "skipped")


class TestHubFirstStrategy(unittest.TestCase):
    def test_hub_comes_first(self) -> None:
        steps = [
            {"file": "a.py"},
            {"file": "hub.py"},
            {"file": "c.py"},
        ]
        # hub.py imports a.py AND is imported by c.py → hub score = 1*1 = 1
        dep_graph = {"hub.py": ["a.py"], "c.py": ["hub.py"]}
        ordered = _order_hub_first(steps, dep_graph)
        files = [s["file"] for s in ordered]
        self.assertEqual(files[0], "hub.py")

    def test_hub_first_skipped_at_end(self) -> None:
        steps = [{"file": "a.py", "status": "skipped"}, {"file": "b.py"}]
        ordered = _order_hub_first(steps, {})
        self.assertEqual(ordered[-1].get("status"), "skipped")


class TestTestAdjacentStrategy(unittest.TestCase):
    def test_files_with_tests_come_first(self) -> None:
        steps = [
            {"file": "utils.py"},
            {"file": "test_auth.py"},
            {"file": "auth.py"},
        ]
        ordered = _order_test_adjacent(steps, {})
        files = [s["file"] for s in ordered]
        # auth.py has a corresponding test_auth.py, so it should come first
        self.assertEqual(files[0], "auth.py")

    def test_test_adjacent_skipped_at_end(self) -> None:
        steps = [{"file": "a.py", "status": "skipped"}, {"file": "b.py"}]
        ordered = _order_test_adjacent(steps, {})
        self.assertEqual(ordered[-1].get("status"), "skipped")


if __name__ == "__main__":
    unittest.main()
