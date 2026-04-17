"""Helpers for :class:`~.core.Planner` — scaffold-only decomposition,
beam-variant generation, and strategy recommendation.

Split out of :mod:`core` to keep that module under the project's 500-LOC
target. The first two take a ``Planner`` instance as their first argument
(bound by thin methods on Planner); the third is a pure function.
"""

from __future__ import annotations

import os
import time as _time
from typing import TYPE_CHECKING, Any

from .constraints import _apply_constraints
from .goal_nlp import _compute_ambiguity_score, _extract_paths_from_goal
from .scaffold_logic import (
    _declared_scaffold_graph,
    _existing_paths_for_scaffold,
    _scaffold_steps,
    _scaffold_target_paths,
    compute_scaffold_dag_metrics,
)
from .strategies import _STRATEGY_REGISTRY, StrategyEntry, _split_active_skipped
from .utils import sha256_json

if TYPE_CHECKING:
    from .core import Planner


def _get_analyzer_registry() -> dict[str, type]:
    """Lazy import to avoid circular dependency."""
    from .analyzers import _ANALYZER_REGISTRY
    return _ANALYZER_REGISTRY


def decompose_scaffold_only(
    planner: Planner,
    goal: str,
    project_root: str,
    scope: str | None,
    scaffold: list[dict[str, Any]] | None,
    skip_recipes: bool,
    matched_recipe: dict[str, Any] | None,
    active_constraints: list[dict[str, Any]],
    t0: float,
    scaffold_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dependency steps derived only from scaffold + goal path inference (no repo-wide scan)."""
    analysis_root = os.path.join(project_root, scope) if scope else project_root
    analyzer = planner._get_analyzer(analysis_root)
    lang_name = getattr(analyzer, "name", "unknown")

    scaffold_list = list(scaffold) if scaffold else []
    user_files = {e.get("file") for e in scaffold_list if e.get("file")}
    base_existing = _existing_paths_for_scaffold(analysis_root, scaffold_list)
    inferred_entries = [
        {"file": p, "description": f"Inferred from goal text: {p}"}
        for p in _extract_paths_from_goal(goal)
        if p not in base_existing
    ]
    extra = [e for e in inferred_entries if e["file"] not in user_files]
    effective_scaffold = scaffold_list + extra

    all_files = _existing_paths_for_scaffold(analysis_root, effective_scaffold)

    scaffold_steps, scaffold_graph = _scaffold_steps(
        effective_scaffold, start_index=0, existing_files=all_files,
    )
    steps: list[dict[str, Any]] = list(scaffold_steps)
    relevant_graph: dict[str, list[str]] = {}
    for f, deps in scaffold_graph.items():
        relevant_graph.setdefault(f, []).extend(deps)

    steps, applied = _apply_constraints(steps, active_constraints)

    near_matches: list[dict[str, Any]] = []
    if not skip_recipes:
        ctx_files = {e.get("file") for e in effective_scaffold if e.get("file")}
        near_matches = planner.store.retrieve_near_matches(
            goal, n=3, context_files=ctx_files, scaffold=effective_scaffold,
        )

    t4 = _time.monotonic()

    declared_graph = _declared_scaffold_graph(effective_scaffold)
    dag_metrics = compute_scaffold_dag_metrics(declared_graph)

    analysis_meta: dict[str, Any] = {
        "language": lang_name,
        "scope": scope,
        "files_analyzed": 0,
        "dep_files": len(relevant_graph),
        "dep_edges": sum(len(v) for v in relevant_graph.values()),
        "timing_s": {
            "symbols": 0.0,
            "imports": 0.0,
            "total": round(t4 - t0, 3),
        },
        "scaffold_only": True,
        "scaffold_dag_metrics": dag_metrics,
        "ambiguity": _compute_ambiguity_score(goal),
    }
    scaffold_targets = _scaffold_target_paths(effective_scaffold)
    if scaffold_targets and not steps:
        norm_targets = [p.replace("\\", "/") for p in scaffold_targets]
        existing_targets = [
            p for p in norm_targets
            if os.path.isfile(
                os.path.normpath(os.path.join(analysis_root, *p.split("/"))),
            )
        ]
        if len(existing_targets) == len(norm_targets):
            target_set = set(norm_targets)
            from .utils import topological_sort
            topo_all = topological_sort(declared_graph)
            topo_order = [p for p in topo_all if p in target_set]
            analysis_meta["skipped_existing_scaffold"] = {
                "count": len(existing_targets),
                "paths": norm_targets,
                "topological_order": topo_order,
                "summary": (
                    f"All {len(existing_targets)} scaffold file(s) already exist; "
                    "no create steps emitted. Use expand_repo or a refactor goal for full-repo steps."
                ),
            }
    if scaffold_validation is not None:
        analysis_meta["scaffold_validation"] = scaffold_validation
    if lang_name not in _get_analyzer_registry():
        analysis_meta["warning"] = (
            f"Language '{lang_name}' may not have a native analyzer; results may be approximate"
        )

    result: dict[str, Any] = {
        "goal": goal,
        "steps": steps,
        "dependency_graph": relevant_graph,
        "constraints": [c.get("description", "") for c in active_constraints],
        "constraints_applied": [c.get("description", "") for c in applied],
        "goal_fingerprint": sha256_json(goal)[:16],
        "analysis_meta": analysis_meta,
        "expand_repo": False,
    }
    if near_matches:
        result["near_match_recipes"] = near_matches
    if matched_recipe is not None:
        result["recipe"] = matched_recipe.get("_source")
        if matched_recipe.get("_match"):
            result["recipe_match"] = matched_recipe["_match"]
    result["scaffold_applied"] = len([s for s in steps if s.get("action") == "create"])
    if inferred_entries:
        result["goal_paths_inferred"] = len(inferred_entries)
    if effective_scaffold:
        result["scaffold"] = effective_scaffold
    return result


def explore_trajectories(planner: Planner, strategy: dict[str, Any], num_beams: int = 3) -> list[dict[str, Any]]:
    """Generate up to ``num_beams`` beam variants, ranked by historical success."""
    cores = os.cpu_count() or 4
    cap = max(3, min(12, cores))
    n = min(num_beams, cap)
    steps = strategy.get("steps", [])
    dep_graph = strategy.get("dependency_graph", {})

    entries = list(_STRATEGY_REGISTRY.values())

    stats = planner.store.get_strategy_stats()
    def _success_rate(entry: StrategyEntry) -> float:
        pair = stats.get(entry.name)
        if pair is None:
            return -1.0
        succ, fail = pair
        return succ / (succ + fail + 1)
    entries = sorted(entries, key=_success_rate, reverse=True)

    ordered_variants = [
        (e.name, e.description, e.fn(steps, dep_graph)) for e in entries
    ]
    if not ordered_variants:
        return []

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


def suggest_strategy(store: Any, goal: str, language: str) -> dict[str, Any] | None:
    """Return a strategy recommendation from trajectory data, falling back to cold-start heuristics."""
    stats = store.get_strategy_stats()
    if stats:
        best_variant: str | None = None
        best_rate = -1.0
        for name, (succ, fail) in stats.items():
            rate = succ / (succ + fail + 1)
            if rate > best_rate:
                best_rate = rate
                best_variant = name
        if best_variant is not None and best_rate > 0:
            return {
                "strategy": best_variant,
                "reason": "highest_success_rate_from_trajectories",
                "success_rate": round(best_rate, 3),
                "data_source": "trajectories",
            }

    goal_lower = goal.lower()
    api_keywords = {"api", "endpoint", "route", "handler", "controller", "service"}
    if any(k in goal_lower for k in api_keywords):
        return {
            "strategy": "top_down",
            "reason": "cold_start_api_first_heuristic",
            "data_source": "heuristic",
        }
    return {
        "strategy": "bottom_up",
        "reason": "cold_start_safe_default",
        "data_source": "heuristic",
    }
