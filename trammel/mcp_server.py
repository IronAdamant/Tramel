"""Tool schemas and dispatch for Trammel MCP servers.

Contains JSON Schema definitions for all Trammel tools and a dispatch-dict
based router used by the stdio MCP server.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .core import Planner
from .strategies import get_strategies
from .harness import ExecutionHarness
from .store import RecipeStore

_LANGUAGES = [
    "python", "typescript", "javascript", "go", "rust", "cpp", "c", "java", "kotlin",
    "csharp", "ruby", "php", "swift", "dart", "zig",
]


def _prop(type_: str, desc: str, **kw: Any) -> dict[str, Any]:
    """Build a JSON Schema property dict."""
    p: dict[str, Any] = {"type": type_, "description": desc}
    p.update(kw)
    return p


def _schema(name: str, desc: str, props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    """Build a tool schema dict."""
    return {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []}}


_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "decompose": _schema("decompose",
        "Decompose a high-level goal into a dependency-aware strategy with ordered steps. "
        "Analyzes project imports to determine file dependencies, generates steps with "
        "ordering rationale, and checks for matching cached recipes.",
        {"goal": _prop("string", "High-level goal to decompose (e.g. 'refactor auth module')."),
         "project_root": _prop("string", "Absolute path to the project root directory."),
         "scope": _prop("string", "Subdirectory to scope analysis to (monorepo support). Relative to project_root."),
         "language": _prop("string", "Project language (auto-detected if omitted).", enum=_LANGUAGES)},
        ["goal", "project_root"]),
    "explore": _schema("explore",
        "Generate beam variants for a strategy without running verification. "
        "Returns multiple execution orderings: bottom_up (safest), top_down (API-first), "
        "risk_first (highest coupling first).",
        {"goal": _prop("string", "High-level goal string."),
         "project_root": _prop("string", "Absolute path to the project root directory."),
         "scope": _prop("string", "Subdirectory to scope analysis to (monorepo support). Relative to project_root."),
         "num_beams": _prop("integer", "Number of beam variants to generate (default: 3, max: 12)."),
         "language": _prop("string", "Project language (auto-detected if omitted).", enum=_LANGUAGES)},
        ["goal", "project_root"]),
    "create_plan": _schema("create_plan",
        "Create a tracked plan from a strategy. Persists the plan and its steps "
        "in the database for incremental execution and verification.",
        {"goal": _prop("string", "Goal this plan addresses."),
         "strategy": _prop("object", "Strategy dict (from decompose) with steps, dependency_graph, etc.")},
        ["goal", "strategy"]),
    "get_plan": _schema("get_plan",
        "Retrieve full plan state including all steps, their statuses, "
        "verification results, and discovered constraints.",
        {"plan_id": _prop("integer", "ID of the plan to retrieve.")},
        ["plan_id"]),
    "verify_step": _schema("verify_step",
        "Verify a single step's edits in an isolated temp copy of the project. "
        "Runs test discovery after applying edits. Returns structured pass/fail "
        "with failure analysis (error type, file, line, suggestion) on failure.",
        {"edits": _prop("array", "Edits for this step: [{path, content}, ...].",
                        items={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}),
         "project_root": _prop("string", "Absolute path to the project root."),
         "prior_edits": _prop("array", "Edits from already-verified prior steps to apply first.", items={"type": "object"}),
         "test_cmd": _prop("array", "Custom test command (e.g. ['pytest', '-x']). Defaults to unittest discover.", items={"type": "string"}),
         "language": _prop("string", "Project language for auto-detecting test command and error patterns.", enum=_LANGUAGES)},
        ["edits", "project_root"]),
    "record_step": _schema("record_step",
        "Update a step's status, edits, and verification results in the database. "
        "Use after verify_step to persist the outcome.",
        {"step_id": _prop("integer", "Database ID of the step to update."),
         "status": _prop("string", "New status for the step.", enum=["pending", "running", "passed", "failed", "skipped"]),
         "edits": _prop("array", "Edits applied in this step.", items={"type": "object"}),
         "verification": _prop("object", "Verification result from verify_step.")},
        ["step_id", "status"]),
    "save_recipe": _schema("save_recipe",
        "Store a verified strategy as a reusable recipe. Successful recipes are "
        "retrieved by similarity when future goals match.",
        {"goal": _prop("string", "Goal pattern for future matching."),
         "strategy": _prop("object", "Strategy to persist."),
         "outcome": _prop("boolean", "True if the strategy succeeded, false if it failed.")},
        ["goal", "strategy", "outcome"]),
    "get_recipe": _schema("get_recipe",
        "Retrieve the best matching recipe for a goal. Uses blended similarity "
        "(trigram + Jaccard + substring, minimum 0.3).",
        {"goal": _prop("string", "Goal to match against stored recipes."),
         "context_files": _prop("array", "File paths in the current project for structural matching boost.", items={"type": "string"})},
        ["goal"]),
    "add_constraint": _schema("add_constraint",
        "Record a failure constraint to prevent repeating known-bad approaches. "
        "Active constraints are checked during decomposition and propagated to "
        "future planning sessions.",
        {"constraint_type": _prop("string", "Type of constraint.", enum=["dependency", "incompatible", "requires", "avoid"]),
         "description": _prop("string", "Human-readable constraint description."),
         "context": _prop("object", "Structured context (file, function, error details)."),
         "plan_id": _prop("integer", "Associated plan ID."),
         "step_id": _prop("integer", "Associated step ID.")},
        ["constraint_type", "description"]),
    "get_constraints": _schema("get_constraints",
        "Retrieve all active failure constraints, optionally filtered by type.",
        {"constraint_type": _prop("string", "Filter by constraint type.", enum=["dependency", "incompatible", "requires", "avoid"])}),
    "list_plans": _schema("list_plans",
        "List all plans, optionally filtered by status.",
        {"status": _prop("string", "Filter by plan status.", enum=["pending", "running", "completed", "failed"])}),
    "history": _schema("history",
        "Retrieve trajectory history for a plan: which beams were tried, "
        "how many steps completed, outcomes, and failure reasons.",
        {"plan_id": _prop("integer", "Plan ID to get trajectory history for.")},
        ["plan_id"]),
    "status": _schema("status",
        "Get a summary of the current Trammel state: active plans, recipe count, constraint count.",
        {}),
    "update_plan_status": _schema("update_plan_status",
        "Set a plan's status (pending/running/completed/failed). "
        "Use to close out a plan after all steps are done or after aborting.",
        {"plan_id": _prop("integer", "Plan ID to update."),
         "status": _prop("string", "New status.", enum=["pending", "running", "completed", "failed"])},
        ["plan_id", "status"]),
    "deactivate_constraint": _schema("deactivate_constraint",
        "Deactivate a constraint by ID. Use when a constraint is stale or "
        "over-conservative. The constraint remains in the database but is "
        "no longer enforced during decomposition.",
        {"constraint_id": _prop("integer", "ID of the constraint to deactivate.")},
        ["constraint_id"]),
    "list_recipes": _schema("list_recipes",
        "List stored recipes with pattern, success/failure counts, and file paths touched.",
        {"limit": _prop("integer", "Maximum recipes to return (default: 20).")}),
    "prune_recipes": _schema("prune_recipes",
        "Remove stale, low-quality recipes. Cascade-deletes associated trigram index "
        "and file entries. Returns count of pruned recipes.",
        {"max_age_days": _prop("integer", "Max age in days before a recipe is prunable (default: 90)."),
         "min_success_ratio": _prop("number", "Minimum success ratio to keep (default: 0.1).")}),
    "list_strategies": _schema("list_strategies",
        "List all registered beam strategies with their historical "
        "success/failure rates from trajectory data.",
        {}),
    "resume": _schema("resume",
        "Get plan progress for resumption. Returns prior_edits from passed steps, "
        "remaining steps, and the next step index to resume from.",
        {"plan_id": _prop("integer", "Plan ID to resume.")},
        ["plan_id"]),
    "validate_recipes": _schema("validate_recipes",
        "Check recipe file entries against the current project. Removes stale file "
        "entries and prunes recipes whose files are entirely missing.",
        {"project_root": _prop("string", "Absolute path to the project root.")},
        ["project_root"]),
    "estimate": _schema("estimate",
        "Quick file count for a project or scope without running full analysis. "
        "Use to decide whether to scope before calling decompose/explore on large repos.",
        {"project_root": _prop("string", "Absolute path to the project root."),
         "scope": _prop("string", "Subdirectory to count within (optional)."),
         "language": _prop("string", "Override language detection.", enum=_LANGUAGES)},
        ["project_root"]),
    "usage_stats": _schema("usage_stats",
        "Get usage telemetry: tool call counts, recipe hit/miss rates, "
        "strategy win rates. Data aggregated over a configurable time window.",
        {"days": _prop("integer", "Number of days to look back (default: 30).")}),
    "failure_history": _schema("failure_history",
        "Get historical failure patterns for a file or the entire project. "
        "Shows which files fail frequently, what error types occur, how many "
        "times each pattern has been seen, and what resolutions worked. "
        "Use before modifying a file to check if it has known failure patterns.",
        {"file_path": _prop("string", "Filter to a specific file path (optional)."),
         "limit": _prop("integer", "Max patterns to return (default: 20).")}),
    "resolve_failure": _schema("resolve_failure",
        "Record what fixed a known failure pattern. Call after successfully "
        "fixing a file that had a recorded failure pattern.",
        {"file_path": _prop("string", "File that was fixed."),
         "error_type": _prop("string", "Error type that was resolved."),
         "resolution": _prop("string", "What fixed it (brief description).")},
        ["file_path", "error_type", "resolution"]),
    "claim_step": _schema("claim_step",
        "Claim a plan step for an agent. Prevents other agents from working on it. "
        "Claims auto-expire after 10 minutes if not refreshed or completed.",
        {"plan_id": _prop("integer", "Plan ID."),
         "step_id": _prop("integer", "Step ID to claim."),
         "agent_id": _prop("string", "Unique identifier for the claiming agent.")},
        ["plan_id", "step_id", "agent_id"]),
    "release_step": _schema("release_step",
        "Release a step claim. Only the owning agent can release.",
        {"step_id": _prop("integer", "Step ID to release."),
         "agent_id": _prop("string", "Agent ID that owns the claim.")},
        ["step_id", "agent_id"]),
    "available_steps": _schema("available_steps",
        "Get steps ready for work: dependencies satisfied, not claimed by another agent. "
        "Use in multi-agent setups to find the next step to work on.",
        {"plan_id": _prop("integer", "Plan ID."),
         "agent_id": _prop("string", "Your agent ID (excludes steps claimed by others).")},
        ["plan_id", "agent_id"]),
}


# ── Dispatch handlers ────────────────────────────────────────────────────────

def _get_analyzer(args: dict[str, Any]) -> Any:
    """Build a language analyzer from args, or None for auto-detection."""
    from .analyzers import get_analyzer
    lang = args.get("language")
    return get_analyzer(lang) if lang else None


def _handle_decompose(store: RecipeStore, args: dict[str, Any]) -> Any:
    return Planner(store=store, analyzer=_get_analyzer(args)).decompose(
        args["goal"], args["project_root"], scope=args.get("scope"),
    )


def _handle_explore(store: RecipeStore, args: dict[str, Any]) -> Any:
    planner = Planner(store=store, analyzer=_get_analyzer(args))
    strategy = planner.decompose(args["goal"], args["project_root"], scope=args.get("scope"))
    beams = planner.explore_trajectories(strategy, num_beams=args.get("num_beams", 3))
    return {"strategy": strategy, "beams": beams}


def _handle_create_plan(store: RecipeStore, args: dict[str, Any]) -> Any:
    return {"plan_id": store.create_plan(args["goal"], args["strategy"])}


def _handle_get_plan(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_plan(args["plan_id"]) or {"error": "plan not found"}


def _handle_verify_step(_store: RecipeStore, args: dict[str, Any]) -> Any:
    harness = ExecutionHarness(test_cmd=args.get("test_cmd"), analyzer=_get_analyzer(args))
    return harness.verify_step(
        args["edits"], args["project_root"], prior_edits=args.get("prior_edits"),
    )


def _handle_record_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.update_step(
        args["step_id"], args["status"],
        edits=args.get("edits"), verification=args.get("verification"),
    )
    return {"ok": True}


def _handle_save_recipe(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.save_recipe(args["goal"], args["strategy"], args["outcome"])
    return {"ok": True}


def _handle_get_recipe(store: RecipeStore, args: dict[str, Any]) -> Any:
    ctx = set(args["context_files"]) if args.get("context_files") else None
    return store.retrieve_best_recipe(args["goal"], context_files=ctx) or {"match": None}


def _handle_list_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.list_recipes(limit=args.get("limit", 20))


def _handle_prune_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    return {
        "pruned": store.prune_recipes(
            max_age_days=args.get("max_age_days", 90),
            min_success_ratio=args.get("min_success_ratio", 0.1),
        )
    }


def _handle_add_constraint(store: RecipeStore, args: dict[str, Any]) -> Any:
    cid = store.add_constraint(
        args["constraint_type"], args["description"],
        context=args.get("context"),
        plan_id=args.get("plan_id"), step_id=args.get("step_id"),
    )
    return {"constraint_id": cid}


def _handle_get_constraints(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_active_constraints(args.get("constraint_type"))


def _handle_update_plan_status(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.update_plan_status(args["plan_id"], args["status"])
    return {"ok": True}


def _handle_deactivate_constraint(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.deactivate_constraint(args["constraint_id"])
    return {"ok": True}


def _handle_list_plans(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.list_plans(args.get("status"))


def _handle_history(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_trajectories(args["plan_id"])


def _handle_status(store: RecipeStore, _args: dict[str, Any]) -> Any:
    summary = store.get_status_summary()
    summary["tools"] = len(_TOOL_SCHEMAS)
    return summary


def _handle_list_strategies(store: RecipeStore, _args: dict[str, Any]) -> Any:
    stats = store.get_strategy_stats()
    return [
        {"name": name, "successes": stats.get(name, (0, 0))[0], "failures": stats.get(name, (0, 0))[1]}
        for name in get_strategies()
    ]


def _handle_resume(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_plan_progress(args["plan_id"]) or {"error": "plan not found"}


def _handle_validate_recipes(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.validate_recipes(args["project_root"])


def _handle_estimate(_store: RecipeStore, args: dict[str, Any]) -> Any:
    from .analyzers import detect_language
    from .utils import _collect_project_files
    scope = args.get("scope")
    analysis_root = os.path.join(args["project_root"], scope) if scope else args["project_root"]
    analyzer = _get_analyzer(args) or detect_language(analysis_root)
    files = _collect_project_files(analysis_root, analyzer.extensions)
    return {
        "language": analyzer.name,
        "scope": scope,
        "matching_files": len(files),
        "recommendation": "use scope" if len(files) > 5000 else "full analysis OK",
    }


def _handle_usage_stats(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_usage_stats(days=args.get("days", 30))


def _handle_failure_history(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_failure_history(
        file_path=args.get("file_path"), limit=args.get("limit", 20),
    )


def _handle_resolve_failure(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.resolve_failure_pattern(
        args["file_path"], args["error_type"], args["resolution"],
    )
    return {"ok": True}


def _handle_claim_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    ok = store.claim_step(args["plan_id"], args["step_id"], args["agent_id"])
    return {"claimed": ok}


def _handle_release_step(store: RecipeStore, args: dict[str, Any]) -> Any:
    store.release_step(args["step_id"], args["agent_id"])
    return {"ok": True}


def _handle_available_steps(store: RecipeStore, args: dict[str, Any]) -> Any:
    return store.get_available_steps(args["plan_id"], args["agent_id"])


# ── Dispatch table ───────────────────────────────────────────────────────────

_DISPATCH: dict[str, Callable[..., Any]] = {
    "decompose": _handle_decompose,
    "explore": _handle_explore,
    "create_plan": _handle_create_plan,
    "get_plan": _handle_get_plan,
    "verify_step": _handle_verify_step,
    "record_step": _handle_record_step,
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
}


_schema_dispatch_diff = set(_TOOL_SCHEMAS) ^ set(_DISPATCH)
if _schema_dispatch_diff:
    raise RuntimeError(f"Schema/dispatch mismatch: {_schema_dispatch_diff}")

from .analyzers import _ANALYZER_REGISTRY  # noqa: E402

_lang_analyzer_diff = set(_LANGUAGES) ^ set(_ANALYZER_REGISTRY)
if _lang_analyzer_diff:
    raise RuntimeError(f"Language/analyzer mismatch: {_lang_analyzer_diff}")


def dispatch_tool(
    store: RecipeStore, tool_name: str, arguments: dict[str, Any]
) -> Any:
    """Route an MCP tool call to the appropriate Trammel handler."""
    handler = _DISPATCH.get(tool_name)
    if handler is None:
        raise ValueError(
            f"Unknown tool: {tool_name!r}. Available: {sorted(_TOOL_SCHEMAS)}"
        )
    store.log_event("tool_call", tool_name)
    return handler(store, arguments)
