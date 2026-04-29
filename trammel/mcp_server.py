"""Dispatch for Trammel MCP servers.

Handlers for each MCP tool plus a dispatch-dict based router used by the
stdio MCP server. Tool JSON schemas live in :mod:`trammel.tool_schemas`;
they are re-exported here as ``_TOOL_SCHEMAS`` for backward compatibility.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .core import Planner
from .strategies import get_strategies
from .harness import ExecutionHarness
from .store import RecipeStore
from .tool_schemas import (
    LANGUAGES as _LANGUAGES,
    TOOL_CATEGORIES as _TOOL_CATEGORIES,
    TOOL_SCHEMAS as _TOOL_SCHEMAS,
    coerce_int_params as _coerce_int_params,
)
from .utils import _collect_project_files

__all__ = ["dispatch_tool", "_TOOL_SCHEMAS", "_LANGUAGES", "_TOOL_CATEGORIES"]


# ── Dispatch handlers ────────────────────────────────────────────────────────

def _get_analyzer(args: dict[str, Any]) -> Any:
    """Build a language analyzer from args, or None for auto-detection."""
    from .analyzers import get_analyzer
    lang = args.get("language")
    return get_analyzer(lang) if lang else None


def _detect_language(project_root: str) -> Any:
    """Lazy wrapper to avoid circular import at module load."""
    from .analyzers import detect_language
    return detect_language(project_root)


def _handle_decompose(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Run :meth:`Planner.decompose` with MCP-surface options."""
    try:
        result = Planner(store=store, analyzer=_get_analyzer(args)).decompose(
            args["goal"], args["project_root"],
            scope=args.get("scope"),
            relevant_only=args.get("relevant_only", False),
            skip_recipes=args.get("skip_recipes", False),
            min_relevance=args.get("min_relevance", 0.0),
            scaffold=args.get("scaffold"),
            expand_repo=args.get("expand_repo"),
            focus_keywords=args.get("focus_keywords"),
            focus_globs=args.get("focus_globs"),
            max_files=args.get("max_files"),
            strict_greenfield=args.get("strict_greenfield", False),
            apply_project_config=args.get("apply_project_config", True),
            suppress_creation_hints=args.get("suppress_creation_hints", False),
        )
    except ValueError as exc:
        return {"error": "decompose_rejected", "message": str(exc)}

    if args.get("summary_only"):
        steps = result.get("steps", [])
        meta = result.get("analysis_meta") or {}
        summary: dict[str, Any] = {
            "goal": result["goal"],
            "step_count": len(steps),
            "files": [s.get("file") for s in steps],
            "goal_fingerprint": result.get("goal_fingerprint"),
            "analysis_meta": meta,
            "constraints": result.get("constraints"),
            "constraints_applied": result.get("constraints_applied"),
        }
        skip = meta.get("skipped_existing_scaffold")
        if skip:
            summary["skipped_existing_scaffold"] = skip
        sdm = meta.get("scaffold_dag_metrics")
        if sdm:
            summary["scaffold_dag_metrics"] = sdm
        if "near_match_recipes" in result:
            summary["near_match_recipes"] = result["near_match_recipes"]
        if "creation_hints" in result:
            summary["creation_hints"] = result["creation_hints"]
        return summary

    max_steps = args.get("max_steps")
    if max_steps is not None:
        all_steps = result["steps"]
        result["steps"] = all_steps[:max_steps]
        result["total_steps"] = len(all_steps)
        kept_files = {s.get("file") for s in result["steps"]}
        result["dependency_graph"] = {
            f: [d for d in deps if d in kept_files]
            for f, deps in result.get("dependency_graph", {}).items()
            if f in kept_files
        }

    return result


def _handle_explore(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Decompose and generate beam variants; retry with scaffold-only fallback on failure."""
    planner = Planner(store=store, analyzer=_get_analyzer(args))
    goal = args["goal"]
    project_root = args["project_root"]
    scope = args.get("scope")

    strategy = planner.decompose(goal, project_root, scope=scope)
    if strategy.get("error") or not strategy.get("steps"):
        strategy = planner.decompose(
            goal, project_root, scope=scope,
            suppress_creation_hints=True,
            expand_repo=False,
        )

    beams = planner.explore_trajectories(strategy, num_beams=args.get("num_beams", 3))
    return {"strategy": strategy, "beams": beams}


def _handle_create_plan(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Persist a strategy as a plan and return its ID."""
    return {"plan_id": store.create_plan(
        args["goal"], args["strategy"], scaffold=args.get("scaffold")
    )}


def _handle_get_plan(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Retrieve a plan with all its steps and verifications."""
    return store.get_plan(args["plan_id"]) or {"error": "plan not found"}


def _handle_verify_step(_store: RecipeStore, args: dict[str, Any]) -> Any:
    """Run edits in an isolated copy and return structured pass/fail info."""
    harness = ExecutionHarness(test_cmd=args.get("test_cmd"), analyzer=_get_analyzer(args))
    return harness.verify_step(
        args["edits"], args["project_root"], prior_edits=args.get("prior_edits"),
    )


def _handle_record_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Persist a single step outcome (status + edits + verification)."""
    store.update_step(
        args["step_id"], args["status"],
        edits=args.get("edits"), verification=args.get("verification"),
    )
    return {"ok": True}


def _handle_record_steps(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Batch-update multiple steps in one transaction."""
    count = store.update_steps_batch(args["steps"])
    return {"ok": True, "steps_updated": count}


def _handle_save_recipe(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Persist a strategy (and optional scaffold) as a recipe."""
    outcome = bool(args["outcome"])
    store.save_recipe(args["goal"], args["strategy"], outcome)
    scaffold = args.get("scaffold")
    if outcome and scaffold:
        store.save_scaffold_recipe(args["goal"], scaffold, outcome)
    return {"ok": True}


def _handle_get_recipe(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Retrieve best-matching recipe; surface match metadata at top level."""
    context_files = set(files) if (files := args.get("context_files")) else None
    recipe = store.retrieve_best_recipe(
        args["goal"],
        context_files=context_files,
        debug=args.get("debug", False),
    )
    if recipe is None:
        # Fall back to near matches so callers see what *almost* matched —
        # otherwise get_recipe and explore.near_match_recipes report a
        # different verdict for the same goal.  Same retrieval path, same
        # ranking; only the auto-pick threshold gates the "match" verdict.
        near = store.retrieve_near_matches(args["goal"], n=3, context_files=context_files)
        return {"match": None, "near_match_recipes": near}
    meta = recipe.pop("_match", {})
    debug_candidates = recipe.pop("_debug_candidates", None)
    out: dict[str, Any] = {**meta, "strategy": recipe}
    if debug_candidates is not None:
        out["debug_candidates"] = debug_candidates
    if args.get("include_scaffold"):
        from .core import strategy_to_scaffold
        out["scaffold"] = strategy_to_scaffold(recipe)
    return out


def _handle_list_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    """List stored recipes with counts and file paths."""
    return store.list_recipes(limit=args.get("limit", 20))


def _handle_prune_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Delete stale or low-quality recipes; return count pruned."""
    return {
        "pruned": store.prune_recipes(
            max_age_days=args.get("max_age_days", 90),
            min_success_ratio=args.get("min_success_ratio", 0.1),
        )
    }


def _handle_add_constraint(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Record a failure constraint; return its new ID."""
    cid = store.add_constraint(
        args["constraint_type"], args["description"],
        context=args.get("context"),
        plan_id=args.get("plan_id"), step_id=args.get("step_id"),
    )
    return {"constraint_id": cid}


def _handle_get_constraints(store: RecipeStore, args: dict[str, Any]) -> Any:
    """List active constraints, optionally filtered by type."""
    return store.get_active_constraints(args.get("constraint_type"))


def _handle_update_plan_status(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Set a plan's status (pending/running/completed/failed)."""
    store.update_plan_status(args["plan_id"], args["status"])
    return {"ok": True}


def _handle_deactivate_constraint(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Mark a constraint inactive so it no longer influences planning."""
    store.deactivate_constraint(args["constraint_id"])
    return {"ok": True}


def _handle_list_plans(store: RecipeStore, args: dict[str, Any]) -> Any:
    """List all plans, optionally filtered by status."""
    return store.list_plans(args.get("status"))


def _handle_history(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Return trajectory history (beams tried, outcomes) for a plan."""
    return store.get_trajectories(args["plan_id"])


def _handle_status(store: RecipeStore, _args: dict[str, Any]) -> Any:
    """Return a summary of Trammel state plus tools grouped by category."""
    summary = store.get_status_summary()
    summary["tools"] = len(_TOOL_SCHEMAS)
    categories: dict[str, list[str]] = {}
    for name, schema in _TOOL_SCHEMAS.items():
        categories.setdefault(schema.get("category", "general"), []).append(name)
    summary["tools_by_category"] = {k: sorted(v) for k, v in categories.items()}
    return summary


def _handle_list_strategies(store: RecipeStore, _args: dict[str, Any]) -> Any:
    """List registered beam strategies with their historical win/loss counts."""
    stats = store.get_strategy_stats()
    result = []
    for name in get_strategies():
        s, f = stats.get(name, (0, 0))
        result.append({"name": name, "successes": s, "failures": f})
    return result


def _handle_resume(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Return prior_edits, remaining steps, and next-step index for a plan."""
    return store.get_plan_progress(args["plan_id"]) or {"error": "plan not found"}


def _handle_validate_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Remove recipe entries whose files no longer exist in the project."""
    return store.validate_recipes(args["project_root"])


def _handle_estimate(_store: RecipeStore, args: dict[str, Any]) -> Any:
    """Quickly count analyzable files for a project or scope."""
    scope = args.get("scope")
    analysis_root = os.path.join(args["project_root"], scope) if scope else args["project_root"]
    analyzer = _get_analyzer(args) or _detect_language(analysis_root)
    files = _collect_project_files(analysis_root, analyzer.extensions)
    return {
        "language": analyzer.name,
        "scope": scope,
        "matching_files": len(files),
        "recommendation": "use scope" if len(files) > 5000 else "full analysis OK",
    }


def _handle_usage_stats(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Return tool-call counts, recipe hit/miss rates, and strategy win rates."""
    return store.get_usage_stats(days=args.get("days", 30))


def _handle_failure_history(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Return historical failure patterns for a file or project-wide."""
    return store.get_failure_history(
        file_path=args.get("file_path"), limit=args.get("limit", 20),
    )


def _handle_resolve_failure(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Record the resolution of a known failure pattern."""
    store.resolve_failure_pattern(
        args["file_path"], args["error_type"], args["resolution"],
    )
    return {"ok": True}


def _handle_claim_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Claim a step for an agent; prevents other agents from taking it."""
    return store.claim_step(args["plan_id"], args["step_id"], args["agent_id"])


def _handle_release_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Release an agent's claim on a step."""
    store.release_step(args["step_id"], args["agent_id"])
    return {"ok": True}


def _handle_available_steps(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Return steps ready to work on (deps satisfied, not claimed)."""
    return store.get_available_steps(args["plan_id"], args["agent_id"])


def _handle_merge_plans(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Merge two plans into a unified strategy with conflict detection."""
    return store.merge_plans(
        args["plan_a_id"], args["plan_b_id"],
        strategy=args.get("strategy", "sequential"),
    )


def _handle_complete_plan(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Finalize a plan in one call (marks pending steps, sets status, saves recipe)."""
    return store.complete_plan(
        args["plan_id"], args["outcome"],
        step_status=args.get("step_status", "passed"),
    )


def _handle_prune_plans(store: RecipeStore, args: dict[str, Any]) -> Any:
    """Delete stale or stuck plans; return count pruned."""
    return {
        "pruned": store.prune_plans(
            max_age_days=args.get("max_age_days", 7),
            status=args.get("status", "pending"),
        )
    }


# ── Dispatch table ───────────────────────────────────────────────────────────

_DISPATCH: dict[str, Callable[..., Any]] = {
    "decompose": _handle_decompose,
    "explore": _handle_explore,
    "create_plan": _handle_create_plan,
    "get_plan": _handle_get_plan,
    "verify_step": _handle_verify_step,
    "record_step": _handle_record_step,
    "record_steps": _handle_record_steps,
    "save_recipe": _handle_save_recipe,
    "get_recipe": _handle_get_recipe,
    "list_recipes": _handle_list_recipes,
    "prune_recipes": _handle_prune_recipes,
    "add_constraint": _handle_add_constraint,
    "get_constraints": _handle_get_constraints,
    "update_plan_status": _handle_update_plan_status,
    "deactivate_constraint": _handle_deactivate_constraint,
    "list_plans": _handle_list_plans,
    "history": _handle_history,
    "status": _handle_status,
    "list_strategies": _handle_list_strategies,
    "resume": _handle_resume,
    "validate_recipes": _handle_validate_recipes,
    "estimate": _handle_estimate,
    "usage_stats": _handle_usage_stats,
    "failure_history": _handle_failure_history,
    "resolve_failure": _handle_resolve_failure,
    "claim_step": _handle_claim_step,
    "release_step": _handle_release_step,
    "available_steps": _handle_available_steps,
    "merge_plans": _handle_merge_plans,
    "complete_plan": _handle_complete_plan,
    "prune_plans": _handle_prune_plans,
}


_schema_dispatch_diff = set(_TOOL_SCHEMAS) ^ set(_DISPATCH)
if _schema_dispatch_diff:
    raise RuntimeError(f"Schema/dispatch mismatch: {_schema_dispatch_diff}")


def _validate_registries() -> None:
    """Verify _LANGUAGES stays in sync with the analyzer registry."""
    from .analyzers import _ANALYZER_REGISTRY
    diff = set(_LANGUAGES) ^ set(_ANALYZER_REGISTRY)
    if diff:
        raise RuntimeError(f"Language/analyzer mismatch: {diff}")


_validate_registries()


def dispatch_tool(
    store: RecipeStore, tool_name: str, arguments: dict[str, Any]
) -> Any:
    """Route an MCP tool call to the appropriate Trammel handler."""
    handler = _DISPATCH.get(tool_name)
    if handler is None:
        raise ValueError(
            f"Unknown tool: {tool_name!r}. Available: {sorted(_TOOL_SCHEMAS)}"
        )
    arguments = _coerce_int_params(tool_name, arguments)
    store.log_event("tool_call", tool_name)
    return handler(store, arguments)
