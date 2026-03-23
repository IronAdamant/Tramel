"""Dependency-aware decomposition and bounded beam exploration with real strategy branching."""

from __future__ import annotations

import os
import time as _time
from typing import TYPE_CHECKING, Any

from .store import RecipeStore
from .strategies import (
    StrategyEntry, _STRATEGY_REGISTRY, _default_beam_count, _split_active_skipped,
)
from .utils import topological_sort, trigram_signature

if TYPE_CHECKING:
    from .analyzers import LanguageAnalyzer

_SUPPORTED_LANGUAGES = frozenset({
    "python", "typescript", "go", "rust", "cpp", "java",
    "csharp", "ruby", "php", "swift", "dart", "zig",
})


# ── Step generation ──────────────────────────────────────────────────────────

def _generate_steps(
    file_order: list[str],
    symbols: dict[str, list[str]],
    dep_graph: dict[str, list[str]],
    goal: str,
) -> list[dict[str, Any]]:
    """Generate plan steps from ordered files, their symbols, and dependency info."""
    steps: list[dict[str, Any]] = []
    file_to_step: dict[str, int] = {}

    for filepath in file_order:
        sym_names = symbols.get(filepath, [])
        if not sym_names:
            continue
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
            "rationale": _step_rationale(dep_files, sym_names),
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


def _step_rationale(dep_files: list[str], sym_names: list[str]) -> str:
    parts: list[str] = []
    if dep_files:
        parts.append(f"imports from {', '.join(dep_files[:3])}")
    parts.append(f"contains {len(sym_names)} symbol(s)")
    return "; ".join(parts)


# ── Constraint enforcement ────────────────────────────────────────────────────

def _parse_constraints(
    constraints: list[dict[str, Any]],
) -> tuple[set[str], list[tuple[str, str]], list[tuple[str, str]], list[str], list[dict[str, Any]]]:
    """Categorize constraints by type.

    Returns (avoid_files, required_orderings, incompatible_pairs, required_files, applied).
    """
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

    return avoid_files, required_orderings, incompatible_pairs, required_files, applied


def _mark_avoided(steps: list[dict[str, Any]], avoid_files: set[str]) -> list[dict[str, Any]]:
    """Mark steps targeting avoided files as skipped."""
    result: list[dict[str, Any]] = []
    for step in steps:
        f = step.get("file", "")
        if f in avoid_files:
            skipped = dict(step)
            skipped["status"] = "skipped"
            skipped["skip_reason"] = f"constraint: avoid {f}"
            result.append(skipped)
        else:
            result.append(step)
    return result


def _inject_orderings(steps: list[dict[str, Any]], orderings: list[tuple[str, str]]) -> None:
    """Inject dependency edges from ordering constraints (mutates steps in place)."""
    file_to_idx = {s.get("file"): i for i, s in enumerate(steps)}
    for before, after in orderings:
        if before in file_to_idx and after in file_to_idx:
            after_step = steps[file_to_idx[after]]
            deps = list(after_step.get("depends_on", []))
            before_idx = file_to_idx[before]
            if before_idx not in deps:
                after_step["depends_on"] = deps + [before_idx]


def _mark_incompatible(steps: list[dict[str, Any]], pairs: list[tuple[str, str]]) -> None:
    """Record incompatible-pair metadata on steps (mutates steps in place)."""
    for file_a, file_b in pairs:
        for step in steps:
            f = step.get("file", "")
            if f == file_a:
                step.setdefault("incompatible_with", []).append(file_b)
            elif f == file_b:
                step.setdefault("incompatible_with", []).append(file_a)


def _add_prerequisites(steps: list[dict[str, Any]], required_files: list[str]) -> None:
    """Append placeholder steps for missing prerequisite files (mutates list)."""
    existing = {s.get("file") for s in steps}
    for prereq in required_files:
        if prereq not in existing:
            steps.append({
                "step_index": len(steps),
                "file": prereq,
                "symbols": [],
                "symbol_count": 0,
                "description": f"Required prerequisite: {prereq}",
                "rationale": "Added by 'requires' constraint",
                "depends_on": [],
            })


def _apply_constraints(
    steps: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Enforce active constraints on steps.

    Returns (modified_steps, applied_constraints).
    """
    if not constraints:
        return steps, []

    avoid_files, orderings, incompat, prereqs, applied = _parse_constraints(constraints)
    filtered = _mark_avoided(steps, avoid_files)
    _inject_orderings(filtered, orderings)
    _mark_incompatible(filtered, incompat)
    _add_prerequisites(filtered, prereqs)
    return filtered, applied


# ── Planner ──────────────────────────────────────────────────────────────────

class Planner:
    def __init__(
        self,
        store: RecipeStore | None = None,
        analyzer: LanguageAnalyzer | None = None,
    ) -> None:
        self.store = store or RecipeStore()
        self._analyzer = analyzer

    def _get_analyzer(self, project_root: str) -> LanguageAnalyzer:
        if self._analyzer is not None:
            return self._analyzer
        from .analyzers import detect_language
        return detect_language(project_root)

    def decompose(self, goal: str, project_root: str, scope: str | None = None) -> dict[str, Any]:
        t0 = _time.monotonic()

        # Fast path: exact text match without project scan
        recipe = self.store.retrieve_best_recipe(goal)
        if recipe:
            recipe.setdefault("_source", "recipe_exact")
            return recipe

        active_constraints = self.store.get_active_constraints()

        analysis_root = os.path.join(project_root, scope) if scope else project_root
        analyzer = self._get_analyzer(analysis_root)

        t1 = _time.monotonic()
        symbols = analyzer.collect_symbols(analysis_root)
        t2 = _time.monotonic()
        dep_graph = analyzer.analyze_imports(analysis_root)
        t3 = _time.monotonic()

        # Structural recipe match: try again with file context
        all_files = set(symbols) | set(dep_graph)
        recipe = self.store.retrieve_best_recipe(goal, context_files=all_files)
        if recipe:
            recipe.setdefault("_source", "recipe_structural")
            return recipe
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
        t4 = _time.monotonic()

        lang_name = getattr(analyzer, "name", "unknown")
        warning = None
        if lang_name not in _SUPPORTED_LANGUAGES:
            warning = f"Language '{lang_name}' may not have a native analyzer; results may be approximate"

        return {
            "goal": goal,
            "steps": steps,
            "dependency_graph": relevant_graph,
            "constraints": [c["description"] for c in active_constraints],
            "constraints_applied": [c["description"] for c in applied],
            "goal_fingerprint": trigram_signature(goal)[:8],
            "analysis_meta": {
                "language": lang_name,
                "scope": scope,
                "files_analyzed": len(symbols),
                "dep_files": len(relevant_graph),
                "dep_edges": sum(len(v) for v in relevant_graph.values()),
                "timing_s": {
                    "symbols": round(t2 - t1, 3),
                    "imports": round(t3 - t2, 3),
                    "total": round(t4 - t0, 3),
                },
                "warning": warning,
            },
        }

    def explore_trajectories(
        self,
        strategy: dict[str, Any],
        num_beams: int = 3,
        store: RecipeStore | None = None,
    ) -> list[dict[str, Any]]:
        n = _default_beam_count(num_beams)
        steps = strategy.get("steps", [])
        dep_graph = strategy.get("dependency_graph", {})

        # Build ordered variants from registry
        entries = list(_STRATEGY_REGISTRY.values())

        # If store available, sort strategies by historical success rate
        if store is not None:
            stats = store.get_strategy_stats()
            def _success_rate(entry: StrategyEntry) -> float:
                pair = stats.get(entry.name)
                if pair is None:
                    return -1.0  # no history: keep registration order
                succ, fail = pair
                return succ / (succ + fail + 1)
            entries = sorted(entries, key=_success_rate, reverse=True)

        ordered_variants = [
            (e.name, e.description, e.fn(steps, dep_graph)) for e in entries
        ]

        beams: list[dict[str, Any]] = []
        for i in range(n):
            variant_name, variant_desc, ordered = ordered_variants[i % len(ordered_variants)]
            active, skipped = _split_active_skipped(ordered)
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
