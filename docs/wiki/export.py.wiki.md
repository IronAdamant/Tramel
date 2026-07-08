# trammel/export.py

Versioned plan/strategy JSON export for non-MCP external runners (`format=trammel.plan`, `format_version=1`).

## Key Functions / Classes
- `export_strategy(strategy, goal=None, path=None, metadata=None)` — serialize a planner strategy into a self-contained document with steps (`depends_on`), dependency_graph, scaffold, constraints.
- `export_plan(plan, path=None, metadata=None)` — same shape from a `RecipeStore.get_plan` dict (includes `plan_id`, status, step statuses).
- `export_plan_from_store(store, plan_id, path=None)` — load + export; returns `{"error": "plan not found", ...}` when missing.
- `EXPORT_FORMAT` / `EXPORT_FORMAT_VERSION` — document identity (`"trammel.plan"` / `1`).

## Design Notes
- Pure data serialization; no network, no MCP dependency. Optional `path` writes pretty JSON + trailing newline.
- Steps are normalized so external runners always see `step_index`, `description`, `rationale`, `depends_on`, `status`.
- Public API re-exports from `trammel` package root; MCP tool `export_plan` and CLI `--export` call these functions.

## Relationships
- Imports: stdlib only (`json`, `time`).
- Imported by: `__init__.py`, `cli.py`, `mcp_server._handle_export_plan`.
