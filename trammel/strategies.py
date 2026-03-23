"""Beam strategy registry and built-in orderings for dependency-aware exploration.

Extracted from core.py to keep each module under 500 LOC.
"""

from __future__ import annotations

import os
from typing import Any, Callable, NamedTuple

from .utils import topological_sort

StrategyFn = Callable[[list[dict[str, Any]], dict[str, list[str]]], list[dict[str, Any]]]


class StrategyEntry(NamedTuple):
    name: str
    description: str
    fn: StrategyFn


_STRATEGY_REGISTRY: dict[str, StrategyEntry] = {}


def register_strategy(name: str, description: str, fn: StrategyFn) -> None:
    """Register a beam strategy by name. Raises ValueError on duplicate."""
    if name in _STRATEGY_REGISTRY:
        raise ValueError(f"Strategy {name!r} is already registered")
    _STRATEGY_REGISTRY[name] = StrategyEntry(name, description, fn)


def get_strategies() -> list[str]:
    """Return the names of all registered beam strategies."""
    return list(_STRATEGY_REGISTRY)


def _default_beam_count(requested: int) -> int:
    cores = os.cpu_count() or 4
    cap = min(12, max(3, cores))
    return min(requested, cap)


# ── Beam strategies ──────────────────────────────────────────────────────────

def _split_active_skipped(
    steps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate active steps from skipped steps."""
    active = [s for s in steps if s.get("status") != "skipped"]
    skipped = [s for s in steps if s.get("status") == "skipped"]
    return active, skipped


def _order_bottom_up(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Dependencies first, then dependents. Stable sort by dep count ascending."""
    active, skipped = _split_active_skipped(steps)
    active.sort(key=lambda s: len(dep_graph.get(s.get("file", ""), [])))
    return active + skipped


def _order_top_down(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Entry points first (most dependencies), internals last. Skipped at end."""
    active, skipped = _split_active_skipped(steps)
    active.sort(key=lambda s: len(dep_graph.get(s.get("file", ""), [])), reverse=True)
    return active + skipped


def _order_risk_first(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Most-imported files first. Incompatible steps isolated, skipped at end."""
    import_counts: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            import_counts[d] = import_counts.get(d, 0) + 1

    active, skipped = _split_active_skipped(steps)

    isolated = [s for s in active if s.get("incompatible_with")]
    batchable = [s for s in active if not s.get("incompatible_with")]

    isolated.sort(
        key=lambda s: import_counts.get(s.get("file", ""), 0), reverse=True,
    )

    pkg_groups: dict[str, list[dict[str, Any]]] = {}
    for s in batchable:
        pkg = os.path.dirname(s.get("file", "")) or "__root__"
        pkg_groups.setdefault(pkg, []).append(s)
    sorted_groups = sorted(
        pkg_groups.values(),
        key=lambda g: max(import_counts.get(s.get("file", ""), 0) for s in g),
        reverse=True,
    )

    result: list[dict[str, Any]] = list(isolated)
    for group in sorted_groups:
        group.sort(
            key=lambda s: import_counts.get(s.get("file", ""), 0), reverse=True,
        )
        result.extend(group)
    result.extend(skipped)
    return result


def _order_critical_path(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Longest dependency chain first (fast feedback on bottlenecks). Skipped at end."""
    active, skipped = _split_active_skipped(steps)

    all_files = {s.get("file", "") for s in active}
    depth: dict[str, int] = {}

    # Iterative longest-path (avoids recursion limit on deep graphs)
    for s in active:
        start = s.get("file", "")
        if start in depth:
            continue
        stack: list[tuple[str, bool]] = [(start, False)]
        in_stack: set[str] = set()
        while stack:
            node, processed = stack.pop()
            if node in depth:
                continue
            if processed:
                in_stack.discard(node)
                children = [d for d in dep_graph.get(node, []) if d in all_files]
                depth[node] = 1 + max((depth.get(c, 0) for c in children), default=0)
                continue
            if node in in_stack:
                depth[node] = 0  # cycle: assign depth 0
                continue
            in_stack.add(node)
            stack.append((node, True))
            for c in dep_graph.get(node, []):
                if c in all_files and c not in depth:
                    stack.append((c, False))

    active.sort(key=lambda s: depth.get(s.get("file", ""), 0), reverse=True)
    return active + skipped


def _order_cohesion(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Group tightly coupled files, process each group contiguously. Skipped at end."""
    active, skipped = _split_active_skipped(steps)

    all_files = {s.get("file", "") for s in active}
    adj: dict[str, set[str]] = {f: set() for f in all_files}
    for f, deps in dep_graph.items():
        if f not in all_files:
            continue
        for d in deps:
            if d in all_files:
                adj[f].add(d)
                adj[d].add(f)

    # Flood-fill connected components
    visited: set[str] = set()
    components: list[list[str]] = []
    for f in sorted(all_files):
        if f in visited:
            continue
        component: list[str] = []
        stack = [f]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(sorted(adj.get(node, set()) - visited))
        components.append(component)

    components.sort(key=len, reverse=True)

    file_order: list[str] = []
    for comp in components:
        if len(comp) == 1:
            file_order.extend(comp)
        else:
            comp_set = set(comp)
            sub_graph = {
                f: [d for d in dep_graph.get(f, []) if d in comp_set]
                for f in comp
            }
            file_order.extend(topological_sort(sub_graph))

    file_to_step = {s.get("file", ""): s for s in active}
    ordered = [file_to_step[f] for f in file_order if f in file_to_step]
    ordered_files = {s.get("file", "") for s in ordered}
    for s in active:
        if s.get("file", "") not in ordered_files:
            ordered.append(s)
    return ordered + skipped


def _order_minimal_change(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Fewest symbols first (quick wins, catch trivial failures early). Skipped at end."""
    active, skipped = _split_active_skipped(steps)
    active.sort(key=lambda s: s.get("symbol_count", 0))
    return active + skipped


def _order_leaf_first(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Files with zero importers first (safe, isolated changes). Skipped at end."""
    active, skipped = _split_active_skipped(steps)

    importer_counts: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            importer_counts[d] = importer_counts.get(d, 0) + 1

    active.sort(key=lambda s: importer_counts.get(s.get("file", ""), 0))
    return active + skipped


def _order_hub_first(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Network hubs first (both import many and imported by many). Skipped at end."""
    active, skipped = _split_active_skipped(steps)

    importer_counts: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            importer_counts[d] = importer_counts.get(d, 0) + 1

    def hub_score(s: dict[str, Any]) -> float:
        f = s.get("file", "")
        imports_out = len(dep_graph.get(f, []))
        imports_in = importer_counts.get(f, 0)
        return imports_out * imports_in

    active.sort(key=hub_score, reverse=True)
    return active + skipped


def _order_test_adjacent(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Files with corresponding test files first (verifiable changes prioritized). Skipped at end."""
    active, skipped = _split_active_skipped(steps)

    all_files = {s.get("file", "") for s in active}

    def has_test(s: dict[str, Any]) -> int:
        f = s.get("file", "")
        base = os.path.splitext(os.path.basename(f))[0]
        test_patterns = [f"test_{base}", f"{base}_test", f"{base}_spec"]
        for af in all_files:
            af_base = os.path.splitext(os.path.basename(af))[0]
            if af_base in test_patterns:
                return 1
        return 0

    active.sort(key=has_test, reverse=True)
    return active + skipped


# ── Register built-in strategies ──────────────────────────────────────────────

register_strategy("bottom_up", "Modify dependencies first, then dependents (safest)", _order_bottom_up)
register_strategy("top_down", "Modify API surface first, then internals", _order_top_down)
register_strategy("risk_first", "Modify most-imported files first (highest impact)", _order_risk_first)
register_strategy("critical_path", "Longest dependency chain first (bottleneck feedback)", _order_critical_path)
register_strategy("cohesion", "Tightly coupled files grouped together", _order_cohesion)
register_strategy("minimal_change", "Fewest symbols first (quick wins)", _order_minimal_change)
register_strategy("leaf_first", "Files with zero importers first (safe isolated changes)", _order_leaf_first)
register_strategy("hub_first", "Network hub files first (highest connectivity risk)", _order_hub_first)
register_strategy("test_adjacent", "Files with matching test files first (verifiable changes)", _order_test_adjacent)
