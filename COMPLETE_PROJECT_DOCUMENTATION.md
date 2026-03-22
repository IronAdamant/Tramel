# Trammel — Project documentation index

**Updated:** 2026-03-23
**Version:** 1.4.0
**Purpose:** Stdlib-only planning harness: dependency-aware decomposition, real beam branching, incremental verification, failure constraint propagation, SQLite recipe/plan/step/constraint/trajectory persistence. MCP server for LLM integration.

## Root files

| Path | Purpose |
|------|---------|
| `README.md` | Overview, quickstart, CLI, MCP setup, architecture, version notes |
| `COMPLETE_PROJECT_DOCUMENTATION.md` | This file: inventory and data flows |
| `LLM_Development.md` | Chronological change log |
| `pyproject.toml` | Package metadata (`trammel` 1.4.0), `requires-python >=3.10`, `mcp` optional dep, console scripts `trammel` + `trammel-mcp` |

## wiki-local/

| Path | Purpose |
|------|---------|
| `wiki-local/index.md` | Wiki hub; links to spec, glossary, root docs |
| `wiki-local/spec-project.md` | Technical spec: API, schema, planner/harness/store behavior |
| `wiki-local/glossary.md` | Named concepts (beam, recipe, strategy, harness, constraint, ...) |

## Package `trammel/`

| Path | Purpose | Main deps |
|------|---------|-----------|
| `trammel/__init__.py` | `__version__` (from `importlib.metadata`), `plan_and_execute`, `explore`, `synthesize`; wires Planner, ExecutionHarness, RecipeStore | `core`, `harness`, `store` |
| `trammel/__main__.py` | `python -m trammel` → `cli.main()` | `cli` |
| `trammel/cli.py` | Argparse + JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd` | `__init__` |
| `trammel/core.py` | `Planner`: import-aware dependency analysis, topological step ordering, real beam branching (bottom_up/top_down/risk_first) | `store`, `utils` |
| `trammel/harness.py` | Temp copy, `_apply_edits`, full `run()`, `verify_step()`, `run_incremental()`, configurable `test_cmd`, failure analysis | `utils` |
| `trammel/store.py` | SQLite: recipes (strategy + constraints + success/failure counts), plans (step tracking), steps, constraints, trajectories | `utils` |
| `trammel/utils.py` | Trigrams, cosine, `analyze_imports`, `topological_sort`, `analyze_failure`, `_is_ignored_dir`, `dumps_json`, `sha256_json`, `db_connect` | stdlib |
| `trammel/mcp_server.py` | MCP tool schemas (13 tools) + `match/case` `dispatch_tool` routing | `core`, `harness`, `store` |
| `trammel/mcp_stdio.py` | MCP stdio server entry point (`trammel-mcp` console script) | `mcp_server`, `store`, `mcp` (optional) |

## Tests

| Path | Purpose |
|------|---------|
| `tests/test_trammel.py` | Core: trigrams, toposort, import analysis, store, harness, plan_and_execute, explore |
| `tests/test_trammel_extra.py` | Edges: failure analysis, step updates, constraint filtering, beam variants, incremental harness, MCP dispatch, CLI |

## Data flow

1. `plan_and_execute` → `RecipeStore.retrieve_best_recipe` (goal vs stored `pattern` via trigram bag cosine, min 0.3) → optional cached strategy.
2. Else `Planner.decompose` scans `.py` AST for symbols, `analyze_imports` builds dependency graph, `topological_sort` orders files → steps with rationale + depends_on.
3. `explore_trajectories` emits beams with genuinely different strategies: `bottom_up` (dependencies first), `top_down` (API first), `risk_first` (highest coupling first).
4. `ExecutionHarness.run` copies tree, applies content edits, runs `unittest discover`. `verify_step` does single-step verification. `run_incremental` verifies step-by-step, aborting on first failure with structured `failure_analysis`.
5. Success → `save_recipe` (strategy + constraints); failure → `add_constraint` (type, description, context). Plans/steps/trajectories logged in SQLite.

## Schema (trammel.db)

| Table | Key columns |
|-------|-------------|
| `recipes` | sig (PK), pattern, strategy, constraints, successes, failures, created, updated |
| `plans` | id (PK), goal, strategy, status, current_step, total_steps, created, updated |
| `steps` | id (PK), plan_id (FK), step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found |
| `constraints` | id (PK), plan_id (FK), step_id (FK), constraint_type, description, context, active |
| `trajectories` | id (PK), plan_id (FK), beam_id, strategy_variant, steps_completed, outcome, failure_reason |

## Changelog (high level)

- **1.4.0:** Cleanup — converted `mcp_stdio.py` from absolute to relative imports for package consistency, removed unreachable `UnicodeDecodeError` from `_collect_python_symbols` except clause (files opened with `errors="replace"`), added `.chisel` to `_IGNORED_DIRS`. 45 tests.
- **1.3.0:** Cleanup — removed unused test imports (`explore`, `synthesize`, `analyze_imports`, `cosine`, `trigram_bag_cosine`, `trigram_signature`), removed dead `goal_slice` parameter from `_collect_python_symbols`, simplified `topological_sort` by removing redundant `.setdefault()`, fixed `plan_and_execute` API signature in spec docs. 45 tests.
- **1.2.0:** `__version__` from `importlib.metadata`, `dispatch_tool` to `match/case`, configurable `test_cmd` in harness/CLI/MCP, recipe retrieval early termination, `tests/__init__.py`. 45 tests.
- **1.1.0:** Cleanup — removed dead code (`advance_plan_step`, unused imports), consolidated duplicated ignored-dirs logic via `_is_ignored_dir` helper, fixed `egg-info` pattern, modernized `topological_sort` with `deque`, simplified `Planner.decompose` set construction. 45 tests.
- **1.0.0:** Full rework — dependency-aware planning (import analysis + toposort), real beam branching (3 strategies), incremental verification, structured failure analysis, constraint propagation, enriched 5-table schema, MCP server (13 tools), 45 tests.
- **0.3.0:** Min similarity threshold, async def support, filtered os.walk, dead code removal.
- **0.2.0:** Recipe similarity fix (shared-vocabulary trigram cosine), `sys.executable`, beam edits carry `path`, `foreign_keys=ON`, `dumps_json`, `__version__`/`--version`.
