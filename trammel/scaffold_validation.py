"""Scaffold DAG metrics and pre-flight validation.

Split out of :mod:`utils` to keep that module under the project's 500-LOC
target. Re-exported through :mod:`utils` so existing call sites keep
working.
"""

from __future__ import annotations

from typing import Any


def compute_scaffold_dag_metrics(graph: dict[str, list[str]]) -> dict[str, Any]:
    """Compute metrics for a scaffold DAG (node = file id; edges = depends_on).

    Aligns with common plan-graph summaries: longest chain length (nodes),
    per-level widths, and max width (parallelism). Uses the same
    dependency convention as :func:`topological_sort`: each node lists the
    files it depends on. Handles cycles gracefully by falling back to
    longest-path DP with safe defaults.
    """
    g: dict[str, list[str]] = {k: list(v) for k, v in graph.items()}
    all_nodes: set[str] = set(g.keys())
    for targets in g.values():
        all_nodes.update(targets)
    for n in all_nodes:
        g.setdefault(n, [])
    if not all_nodes:
        return {
            "node_count": 0,
            "edge_count": 0,
            "max_dependency_depth": 0,
            "critical_path_length": 0,
            "max_parallelism": 0,
            "layer_widths": [],
        }
    # Lazy import to break circularity (utils re-exports this module's API).
    from .utils import topological_sort
    order = topological_sort(g)
    longest_path: dict[str, int] = {}
    for n in order:
        deps = g.get(n, [])
        longest_path[n] = 1 + max((longest_path.get(d, 0) for d in deps), default=0)
    critical_path_length = max(longest_path.values()) if longest_path else 0
    level: dict[str, int] = {}
    for n in order:
        deps = g.get(n, [])
        level[n] = max((level.get(d, -1) for d in deps), default=-1) + 1
    max_level = max(level.values()) if level else -1
    layer_widths = [0] * (max_level + 1) if max_level >= 0 else []
    for n in all_nodes:
        layer_widths[level[n]] += 1
    max_parallelism = max(layer_widths) if layer_widths else 0
    edge_count = sum(len(v) for v in g.values())
    return {
        "node_count": len(all_nodes),
        "edge_count": edge_count,
        "max_dependency_depth": max_level + 1 if max_level >= 0 else 0,
        "critical_path_length": critical_path_length,
        "max_parallelism": max_parallelism,
        "layer_widths": layer_widths,
    }


def validate_scaffold(
    entries: list[dict[str, Any]],
    existing_files: set[str] | None = None,
) -> dict[str, Any]:
    """Pre-flight validation for scaffold entries.

    Detects cycles, duplicate files, self-referential entries,
    over-constrained nodes (>4 deps), and missing dependencies.
    ``over_constrained`` is surfaced as a warning and does not invalidate
    the scaffold, because test files and facades commonly have 5+ deps.
    Returns a dict with ``valid`` bool and diagnostic details.
    """
    result: dict[str, Any] = {
        "valid": True,
        "error": None,
        "cycle": None,
        "duplicates": [],
        "missing_deps": [],
        "over_constrained": [],
        "self_referential": [],
    }

    files = [e.get("file") for e in entries if e.get("file")]
    file_set = set(files)

    seen: set[str] = set()
    for f in files:
        if f in seen:
            result["duplicates"].append(f)
        seen.add(f)
    if result["duplicates"]:
        result["valid"] = False
        result["error"] = "duplicate_files"

    graph: dict[str, list[str]] = {}
    for e in entries:
        f = e.get("file")
        if f:
            graph[f] = [d for d in (e.get("depends_on") or []) if d]

    for f, deps in graph.items():
        if f in deps:
            result["self_referential"].append(f)
    if result["self_referential"] and result["valid"]:
        result["valid"] = False
        result["error"] = "self_referential"

    for f, deps in graph.items():
        if len(deps) > 4:
            result["over_constrained"].append({"file": f, "deps": deps})

    if existing_files is not None:
        all_known = file_set | existing_files
        for f, deps in graph.items():
            for d in deps:
                if d not in all_known:
                    result["missing_deps"].append({"file": f, "missing": d})
        if result["missing_deps"] and result["valid"]:
            result["valid"] = False
            result["error"] = "missing_dependencies"

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {f: WHITE for f in graph}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        color[node] = GRAY
        for neighbor in graph.get(node, []):
            if neighbor not in graph:
                continue
            ncolor = color.get(neighbor, WHITE)
            if ncolor == GRAY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if ncolor == WHITE:
                cycle = dfs(neighbor, path + [neighbor])
                if cycle:
                    return cycle
        color[node] = BLACK
        return None

    if result["valid"]:
        for f in graph:
            if color[f] == WHITE:
                cycle = dfs(f, [f])
                if cycle:
                    result["cycle"] = cycle
                    result["valid"] = False
                    result["error"] = "circular_dependency"
                    break

    return result
