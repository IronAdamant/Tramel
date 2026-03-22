"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

import ast
import os
from typing import Any

from .store import RecipeStore
from .utils import (
    _IGNORED_DIRS,
    analyze_imports,
    topological_sort,
    trigram_signature,
)


def _default_beam_count(requested: int) -> int:
    cores = os.cpu_count() or 4
    cap = min(12, max(3, cores))
    return min(requested, cap)


# ── Symbol collection ────────────────────────────────────────────────────────

def _collect_python_symbols(
    project_root: str, goal_slice: str
) -> dict[str, list[dict[str, Any]]]:
    """Collect function/class symbols grouped by relative file path."""
    symbols: dict[str, list[dict[str, Any]]] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project_root)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
                tree = ast.parse(src, filename=path)
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            file_symbols: list[dict[str, Any]] = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    file_symbols.append({
                        "file": rel,
                        "name": node.name,
                        "type": type(node).__name__,
                        "line": node.lineno,
                        "goal_slice": goal_slice[:100],
                    })
            if file_symbols:
                symbols[rel] = file_symbols
    return symbols


# ── Step generation ──────────────────────────────────────────────────────────

def _generate_steps(
    file_order: list[str],
    symbols: dict[str, list[dict[str, Any]]],
    dep_graph: dict[str, list[str]],
    goal: str,
) -> list[dict[str, Any]]:
    """Generate plan steps from ordered files, their symbols, and dependency info."""
    steps: list[dict[str, Any]] = []
    file_to_step: dict[str, int] = {}

    for filepath in file_order:
        file_syms = symbols.get(filepath, [])
        if not file_syms:
            continue
        sym_names = [s["name"] for s in file_syms]
        step_idx = len(steps)
        file_to_step[filepath] = step_idx

        dep_files = dep_graph.get(filepath, [])
        depends_on = [file_to_step[d] for d in dep_files if d in file_to_step]

        steps.append({
            "step_index": step_idx,
            "file": filepath,
            "symbols": sym_names,
            "symbol_count": len(sym_names),
            "description": f"Modify {filepath}: {', '.join(sym_names[:5])}"
                           + (f" (+{len(sym_names)-5} more)" if len(sym_names) > 5 else ""),
            "rationale": _step_rationale(filepath, dep_files, sym_names),
            "depends_on": depends_on,
        })

    if not steps:
        steps = [{
            "step_index": 0,
            "file": "__project__",
            "symbols": ["root"],
            "symbol_count": 1,
            "description": goal[:100],
            "rationale": "No Python symbols found; treating as whole-project task",
            "depends_on": [],
        }]

    return steps


def _step_rationale(filepath: str, dep_files: list[str], sym_names: list[str]) -> str:
    parts: list[str] = []
    if dep_files:
        parts.append(f"imports from {', '.join(dep_files[:3])}")
    parts.append(f"contains {len(sym_names)} symbol(s)")
    return "; ".join(parts)


# ── Beam strategies ──────────────────────────────────────────────────────────

def _order_bottom_up(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dependencies first, then dependents. This is the default topological order."""
    return list(steps)


def _order_top_down(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entry points and API surface first, internals last."""
    return list(reversed(steps))


def _order_risk_first(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Most-imported (highest coupling) files first."""
    import_counts: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            import_counts[d] = import_counts.get(d, 0) + 1
    return sorted(
        steps,
        key=lambda s: import_counts.get(s.get("file", ""), 0),
        reverse=True,
    )


_BEAM_STRATEGIES: list[tuple[str, str]] = [
    ("bottom_up", "Modify dependencies first, then dependents (safest)"),
    ("top_down", "Modify API surface first, then internals"),
    ("risk_first", "Modify most-imported files first (highest impact)"),
]


# ── Planner ──────────────────────────────────────────────────────────────────

class Planner:
    def __init__(self, store: RecipeStore | None = None) -> None:
        self.store = store or RecipeStore()

    def decompose(self, goal: str, project_root: str) -> dict[str, Any]:
        recipe = self.store.retrieve_best_recipe(goal)
        if recipe:
            return recipe

        active_constraints = self.store.get_active_constraints()

        symbols = _collect_python_symbols(project_root, goal)
        dep_graph = analyze_imports(project_root)

        all_files = set(symbols.keys())
        for f in list(dep_graph.keys()):
            if f not in all_files:
                all_files.add(f)
        relevant_graph = {
            f: [d for d in deps if d in all_files]
            for f, deps in dep_graph.items()
            if f in all_files
        }

        file_order = topological_sort(relevant_graph)
        file_order = [f for f in file_order if f in symbols]

        for f in sorted(symbols.keys()):
            if f not in file_order:
                file_order.append(f)

        steps = _generate_steps(file_order, symbols, relevant_graph, goal)

        return {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c["description"] for c in active_constraints],
            "goal_fingerprint": trigram_signature(goal)[:8],
        }

    def explore_trajectories(
        self, strategy: dict[str, Any], num_beams: int = 3
    ) -> list[dict[str, Any]]:
        n = _default_beam_count(num_beams)
        steps = strategy.get("steps", [])
        dep_graph = strategy.get("dependency_graph", {})

        ordered_variants: list[tuple[str, str, list[dict[str, Any]]]] = [
            ("bottom_up", _BEAM_STRATEGIES[0][1], _order_bottom_up(steps)),
            ("top_down", _BEAM_STRATEGIES[1][1], _order_top_down(steps)),
            ("risk_first", _BEAM_STRATEGIES[2][1], _order_risk_first(steps, dep_graph)),
        ]

        beams: list[dict[str, Any]] = []
        for i in range(n):
            variant_name, variant_desc, ordered = ordered_variants[i % len(ordered_variants)]
            beam: dict[str, Any] = {
                "beam_id": i,
                "variant": variant_name,
                "variant_description": variant_desc,
                "steps": ordered,
                "edits": [
                    {"step_index": s.get("step_index", j), "path": s.get("file"), "task": s}
                    for j, s in enumerate(ordered)
                ],
            }
            beams.append(beam)

        return beams
