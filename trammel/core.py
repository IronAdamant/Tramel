"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

import ast
import os
from typing import Any

from .store import RecipeStore
from .utils import (
    _is_ignored_dir,
    analyze_imports,
    topological_sort,
    trigram_signature,
)


def _default_beam_count(requested: int) -> int:
    cores = os.cpu_count() or 4
    cap = min(12, max(3, cores))
    return min(requested, cap)


# ── Symbol collection ────────────────────────────────────────────────────────

def _collect_python_symbols(project_root: str) -> dict[str, list[dict[str, Any]]]:
    """Collect function/class symbols grouped by relative file path."""
    symbols: dict[str, list[dict[str, Any]]] = {}
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not _is_ignored_dir(d)]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project_root)
            try:
                with open(path, encoding="utf-8", errors="replace") as fp:
                    src = fp.read()
                tree = ast.parse(src, filename=path)
            except (OSError, SyntaxError):
                continue
            file_symbols: list[dict[str, Any]] = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    file_symbols.append({
                        "file": rel,
                        "name": node.name,
                        "type": type(node).__name__,
                        "line": node.lineno,
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


# ── Constraint enforcement ────────────────────────────────────────────────────

def _apply_constraints(
    steps: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Enforce active constraints on steps.

    Returns (modified_steps, applied_constraints).
    """
    if not constraints:
        return steps, []

    applied: list[dict[str, Any]] = []
    avoid_files: set[str] = set()
    required_orderings: list[tuple[str, str]] = []
    incompatible_pairs: list[tuple[str, str]] = []
    required_files: list[str] = []

    for c in constraints:
        ctx = c.get("context", {})
        ctype = c.get("type", "")
        if ctype == "avoid" and ctx.get("file"):
            avoid_files.add(ctx["file"])
            applied.append(c)
        elif ctype == "dependency":
            before = ctx.get("before") or ctx.get("dependency")
            after = ctx.get("after") or ctx.get("dependent")
            if before and after:
                required_orderings.append((before, after))
                applied.append(c)
        elif ctype == "incompatible":
            file_a = ctx.get("file_a") or ctx.get("file")
            file_b = ctx.get("file_b") or ctx.get("other")
            if file_a and file_b:
                incompatible_pairs.append((file_a, file_b))
                applied.append(c)
        elif ctype == "requires" and (ctx.get("file") or ctx.get("prerequisite")):
            required_files.append(ctx.get("file") or ctx["prerequisite"])
            applied.append(c)

    # Mark avoided files as skipped
    filtered: list[dict[str, Any]] = []
    for step in steps:
        f = step.get("file", "")
        if f in avoid_files:
            skipped = dict(step)
            skipped["status"] = "skipped"
            skipped["skip_reason"] = f"constraint: avoid {f}"
            filtered.append(skipped)
        else:
            filtered.append(step)

    # Inject dependency orderings
    file_to_idx = {s.get("file"): i for i, s in enumerate(filtered)}
    for before, after in required_orderings:
        if before in file_to_idx and after in file_to_idx:
            after_step = filtered[file_to_idx[after]]
            deps = list(after_step.get("depends_on", []))
            before_idx = file_to_idx[before]
            if before_idx not in deps:
                after_step["depends_on"] = deps + [before_idx]

    # Record incompatible pairs as metadata
    for file_a, file_b in incompatible_pairs:
        for step in filtered:
            f = step.get("file", "")
            if f == file_a:
                step.setdefault("incompatible_with", []).append(file_b)
            elif f == file_b:
                step.setdefault("incompatible_with", []).append(file_a)

    # Ensure required prerequisite steps exist
    existing_files = {s.get("file") for s in filtered}
    for prereq in required_files:
        if prereq not in existing_files:
            filtered.append({
                "step_index": len(filtered),
                "file": prereq,
                "symbols": [],
                "symbol_count": 0,
                "description": f"Required prerequisite: {prereq}",
                "rationale": "Added by 'requires' constraint",
                "depends_on": [],
            })

    return filtered, applied


# ── Beam strategies ──────────────────────────────────────────────────────────

def _order_bottom_up(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dependencies first, then dependents. Skipped steps at end."""
    active = [s for s in steps if s.get("status") != "skipped"]
    skipped = [s for s in steps if s.get("status") == "skipped"]
    return active + skipped


def _order_top_down(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entry points and API surface first, internals last. Skipped at end."""
    active = [s for s in steps if s.get("status") != "skipped"]
    skipped = [s for s in steps if s.get("status") == "skipped"]
    return list(reversed(active)) + skipped


def _order_risk_first(
    steps: list[dict[str, Any]], dep_graph: dict[str, list[str]]
) -> list[dict[str, Any]]:
    """Most-imported files first. Incompatible steps isolated, skipped at end."""
    import_counts: dict[str, int] = {}
    for deps in dep_graph.values():
        for d in deps:
            import_counts[d] = import_counts.get(d, 0) + 1

    active = [s for s in steps if s.get("status") != "skipped"]
    skipped = [s for s in steps if s.get("status") == "skipped"]

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

        symbols = _collect_python_symbols(project_root)
        dep_graph = analyze_imports(project_root)

        all_files = set(symbols) | set(dep_graph)
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
        steps, applied = _apply_constraints(steps, active_constraints)

        return {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c["description"] for c in active_constraints],
            "constraints_applied": [c["description"] for c in applied],
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
            active = [s for s in ordered if s.get("status") != "skipped"]
            skipped = [s for s in ordered if s.get("status") == "skipped"]
            beam: dict[str, Any] = {
                "beam_id": i,
                "variant": variant_name,
                "variant_description": variant_desc,
                "steps": ordered,
                "edits": [
                    {"step_index": s.get("step_index", j), "path": s.get("file"), "task": s}
                    for j, s in enumerate(active)
                ],
                "skipped": skipped,
            }
            beams.append(beam)

        return beams
