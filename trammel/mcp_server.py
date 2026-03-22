"""Tool schemas and dispatch for Trammel MCP servers.

Contains JSON Schema definitions for all Trammel tools and the dispatch
function used by the stdio MCP server.
"""

from __future__ import annotations

from typing import Any

from .core import Planner, get_strategies
from .harness import ExecutionHarness
from .store import RecipeStore

_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "decompose": {
        "name": "decompose",
        "description": (
            "Decompose a high-level goal into a dependency-aware strategy with ordered steps. "
            "Analyzes project imports to determine file dependencies, generates steps with "
            "ordering rationale, and checks for matching cached recipes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "High-level goal to decompose (e.g. 'refactor auth module').",
                },
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project root directory.",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "typescript", "javascript"],
                    "description": "Project language (auto-detected if omitted).",
                },
            },
            "required": ["goal", "project_root"],
        },
    },
    "explore": {
        "name": "explore",
        "description": (
            "Generate beam variants for a strategy without running verification. "
            "Returns multiple execution orderings: bottom_up (safest), top_down (API-first), "
            "risk_first (highest coupling first)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "High-level goal string.",
                },
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project root directory.",
                },
                "num_beams": {
                    "type": "integer",
                    "description": "Number of beam variants to generate (default: 3, max: 12).",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "typescript", "javascript"],
                    "description": "Project language (auto-detected if omitted).",
                },
            },
            "required": ["goal", "project_root"],
        },
    },
    "create_plan": {
        "name": "create_plan",
        "description": (
            "Create a tracked plan from a strategy. Persists the plan and its steps "
            "in the database for incremental execution and verification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Goal this plan addresses.",
                },
                "strategy": {
                    "type": "object",
                    "description": "Strategy dict (from decompose) with steps, dependency_graph, etc.",
                },
            },
            "required": ["goal", "strategy"],
        },
    },
    "get_plan": {
        "name": "get_plan",
        "description": (
            "Retrieve full plan state including all steps, their statuses, "
            "verification results, and discovered constraints."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "integer",
                    "description": "ID of the plan to retrieve.",
                },
            },
            "required": ["plan_id"],
        },
    },
    "verify_step": {
        "name": "verify_step",
        "description": (
            "Verify a single step's edits in an isolated temp copy of the project. "
            "Runs unittest discovery after applying edits. Returns structured pass/fail "
            "with failure analysis (error type, file, line, suggestion) on failure."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                    "description": "Edits for this step: [{path, content}, ...].",
                },
                "project_root": {
                    "type": "string",
                    "description": "Absolute path to the project root.",
                },
                "prior_edits": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Edits from already-verified prior steps to apply first.",
                },
                "test_cmd": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Custom test command (e.g. ['pytest', '-x']). Defaults to unittest discover.",
                },
            },
            "required": ["edits", "project_root"],
        },
    },
    "record_step": {
        "name": "record_step",
        "description": (
            "Update a step's status, edits, and verification results in the database. "
            "Use after verify_step to persist the outcome."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "step_id": {
                    "type": "integer",
                    "description": "Database ID of the step to update.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "passed", "failed", "skipped"],
                    "description": "New status for the step.",
                },
                "edits": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Edits applied in this step.",
                },
                "verification": {
                    "type": "object",
                    "description": "Verification result from verify_step.",
                },
            },
            "required": ["step_id", "status"],
        },
    },
    "save_recipe": {
        "name": "save_recipe",
        "description": (
            "Store a verified strategy as a reusable recipe. Successful recipes are "
            "retrieved by trigram similarity when future goals match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Goal pattern for future matching.",
                },
                "strategy": {
                    "type": "object",
                    "description": "Strategy to persist.",
                },
                "outcome": {
                    "type": "boolean",
                    "description": "True if the strategy succeeded, false if it failed.",
                },
            },
            "required": ["goal", "strategy", "outcome"],
        },
    },
    "get_recipe": {
        "name": "get_recipe",
        "description": (
            "Retrieve the best matching recipe for a goal. Uses trigram cosine "
            "similarity (minimum 0.3) with tie-breaking on success count."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "Goal to match against stored recipes.",
                },
                "context_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths in the current project for structural matching boost.",
                },
            },
            "required": ["goal"],
        },
    },
    "add_constraint": {
        "name": "add_constraint",
        "description": (
            "Record a failure constraint to prevent repeating known-bad approaches. "
            "Active constraints are checked during decomposition and propagated to "
            "future planning sessions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "constraint_type": {
                    "type": "string",
                    "enum": ["dependency", "incompatible", "requires", "avoid"],
                    "description": "Type of constraint.",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable constraint description.",
                },
                "context": {
                    "type": "object",
                    "description": "Structured context (file, function, error details).",
                },
                "plan_id": {"type": "integer", "description": "Associated plan ID."},
                "step_id": {"type": "integer", "description": "Associated step ID."},
            },
            "required": ["constraint_type", "description"],
        },
    },
    "get_constraints": {
        "name": "get_constraints",
        "description": "Retrieve all active failure constraints, optionally filtered by type.",
        "parameters": {
            "type": "object",
            "properties": {
                "constraint_type": {
                    "type": "string",
                    "enum": ["dependency", "incompatible", "requires", "avoid"],
                    "description": "Filter by constraint type.",
                },
            },
            "required": [],
        },
    },
    "list_plans": {
        "name": "list_plans",
        "description": "List all plans, optionally filtered by status.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed"],
                    "description": "Filter by plan status.",
                },
            },
            "required": [],
        },
    },
    "history": {
        "name": "history",
        "description": (
            "Retrieve trajectory history for a plan: which beams were tried, "
            "how many steps completed, outcomes, and failure reasons."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "integer",
                    "description": "Plan ID to get trajectory history for.",
                },
            },
            "required": ["plan_id"],
        },
    },
    "status": {
        "name": "status",
        "description": (
            "Get a summary of the current Trammel state: active plans, "
            "recipe count, constraint count."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "update_plan_status": {
        "name": "update_plan_status",
        "description": (
            "Set a plan's status (pending/running/completed/failed). "
            "Use to close out a plan after all steps are done or after aborting."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "integer",
                    "description": "Plan ID to update.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed"],
                    "description": "New status.",
                },
            },
            "required": ["plan_id", "status"],
        },
    },
    "deactivate_constraint": {
        "name": "deactivate_constraint",
        "description": (
            "Deactivate a constraint by ID. Use when a constraint is stale or "
            "over-conservative. The constraint remains in the database but is "
            "no longer enforced during decomposition."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "constraint_id": {
                    "type": "integer",
                    "description": "ID of the constraint to deactivate.",
                },
            },
            "required": ["constraint_id"],
        },
    },
    "list_recipes": {
        "name": "list_recipes",
        "description": (
            "List stored recipes with pattern, success/failure counts, "
            "and file paths touched."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum recipes to return (default: 20).",
                },
            },
            "required": [],
        },
    },
    "list_strategies": {
        "name": "list_strategies",
        "description": (
            "List all registered beam strategies with their historical "
            "success/failure rates from trajectory data."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


def dispatch_tool(
    store: RecipeStore, tool_name: str, arguments: dict[str, Any]
) -> Any:
    """Route an MCP tool call to the appropriate Trammel logic."""
    from .analyzers import get_analyzer
    lang = arguments.get("language")
    analyzer = get_analyzer(lang) if lang else None

    match tool_name:
        case "decompose":
            return Planner(store=store, analyzer=analyzer).decompose(
                arguments["goal"], arguments["project_root"],
            )

        case "explore":
            planner = Planner(store=store, analyzer=analyzer)
            strategy = planner.decompose(arguments["goal"], arguments["project_root"])
            beams = planner.explore_trajectories(
                strategy, num_beams=arguments.get("num_beams", 3), store=store,
            )
            return {"strategy": strategy, "beams": beams}

        case "create_plan":
            return {"plan_id": store.create_plan(arguments["goal"], arguments["strategy"])}

        case "get_plan":
            return store.get_plan(arguments["plan_id"]) or {"error": "plan not found"}

        case "verify_step":
            harness = ExecutionHarness(test_cmd=arguments.get("test_cmd"))
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

        case _:
            raise ValueError(
                f"Unknown tool: {tool_name!r}. Available: {sorted(_TOOL_SCHEMAS)}"
            )
