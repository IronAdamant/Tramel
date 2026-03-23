"""Tool schemas and dispatch for Trammel MCP servers.

Contains JSON Schema definitions for all Trammel tools and the dispatch
function used by the stdio MCP server.
"""

from __future__ import annotations

import os
from typing import Any

from .core import Planner, get_strategies
from .harness import ExecutionHarness
from .store import RecipeStore

_LANGUAGES = ["python", "typescript", "javascript", "go", "rust", "cpp", "c", "java", "kotlin"]


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
}


def dispatch_tool(
    store: RecipeStore, tool_name: str, arguments: dict[str, Any]
) -> Any:
    """Route an MCP tool call to the appropriate Trammel logic."""
    from .analyzers import get_analyzer
    lang = arguments.get("language")
    analyzer = get_analyzer(lang) if lang else None

    scope = arguments.get("scope")

    match tool_name:
        case "decompose":
            return Planner(store=store, analyzer=analyzer).decompose(
                arguments["goal"], arguments["project_root"], scope=scope,
            )

        case "explore":
            planner = Planner(store=store, analyzer=analyzer)
            strategy = planner.decompose(arguments["goal"], arguments["project_root"], scope=scope)
            beams = planner.explore_trajectories(
                strategy, num_beams=arguments.get("num_beams", 3), store=store,
            )
            return {"strategy": strategy, "beams": beams}

        case "create_plan":
            return {"plan_id": store.create_plan(arguments["goal"], arguments["strategy"])}

        case "get_plan":
            return store.get_plan(arguments["plan_id"]) or {"error": "plan not found"}

        case "verify_step":
            harness = ExecutionHarness(test_cmd=arguments.get("test_cmd"), analyzer=analyzer)
            return harness.verify_step(
                arguments["edits"],
                arguments["project_root"],
                prior_edits=arguments.get("prior_edits"),
            )

        case "record_step":
            store.update_step(
                arguments["step_id"],
                arguments["status"],
                edits=arguments.get("edits"),
                verification=arguments.get("verification"),
            )
            return {"ok": True}

        case "save_recipe":
            store.save_recipe(
                arguments["goal"], arguments["strategy"], arguments["outcome"],
            )
            return {"ok": True}

        case "get_recipe":
            ctx = set(arguments["context_files"]) if arguments.get("context_files") else None
            return store.retrieve_best_recipe(
                arguments["goal"], context_files=ctx,
            ) or {"match": None}

        case "list_recipes":
            return store.list_recipes(limit=arguments.get("limit", 20))

        case "prune_recipes":
            return {
                "pruned": store.prune_recipes(
                    max_age_days=arguments.get("max_age_days", 90),
                    min_success_ratio=arguments.get("min_success_ratio", 0.1),
                )
            }

        case "add_constraint":
            cid = store.add_constraint(
                arguments["constraint_type"],
                arguments["description"],
                context=arguments.get("context"),
                plan_id=arguments.get("plan_id"),
                step_id=arguments.get("step_id"),
            )
            return {"constraint_id": cid}

        case "get_constraints":
            return store.get_active_constraints(arguments.get("constraint_type"))

        case "update_plan_status":
            store.update_plan_status(arguments["plan_id"], arguments["status"])
            return {"ok": True}

        case "deactivate_constraint":
            store.deactivate_constraint(arguments["constraint_id"])
            return {"ok": True}

        case "list_plans":
            return store.list_plans(arguments.get("status"))

        case "history":
            return store.get_trajectories(arguments["plan_id"])

        case "status":
            recipes = store.conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
            plans = store.conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
            active = store.conn.execute(
                "SELECT COUNT(*) FROM plans WHERE status IN ('pending','running')"
            ).fetchone()[0]
            constraints = store.conn.execute(
                "SELECT COUNT(*) FROM constraints WHERE active = 1"
            ).fetchone()[0]
            return {
                "recipes": recipes,
                "plans_total": plans,
                "plans_active": active,
                "constraints_active": constraints,
                "tools": len(_TOOL_SCHEMAS),
            }

        case "list_strategies":
            stats = store.get_strategy_stats()
            return [
                {
                    "name": name,
                    "successes": stats.get(name, (0, 0))[0],
                    "failures": stats.get(name, (0, 0))[1],
                }
                for name in get_strategies()
            ]

        case "resume":
            return store.get_plan_progress(arguments["plan_id"]) or {"error": "plan not found"}

        case "validate_recipes":
            return store.validate_recipes(arguments["project_root"])

        case "estimate":
            from .analyzers import detect_language, get_analyzer
            from .utils import _collect_project_files
            est_root = arguments["project_root"]
            est_scope = arguments.get("scope")
            analysis_root = os.path.join(est_root, est_scope) if est_scope else est_root
            if lang:
                est_analyzer = get_analyzer(lang)
            else:
                est_analyzer = detect_language(analysis_root)
            files = _collect_project_files(analysis_root, est_analyzer.extensions)
            total_files = sum(1 for _ in os.scandir(analysis_root)) if os.path.isdir(analysis_root) else 0
            return {
                "language": est_analyzer.name,
                "scope": est_scope,
                "matching_files": len(files),
                "recommendation": "use scope" if len(files) > 5000 else "full analysis OK",
            }

        case _:
            raise ValueError(
                f"Unknown tool: {tool_name!r}. Available: {sorted(_TOOL_SCHEMAS)}"
            )
