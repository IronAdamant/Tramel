# Trammel — technical specification

**Version:** 1.2.0
**Language:** Python 3.10+ (stdlib only for core; `mcp` optional for MCP server)

## 1. Purpose

Trammel externalizes the planning bottleneck for LLM coding assistants. It decomposes goals into dependency-aware strategies, explores genuinely different beam orderings, runs isolated verification (full or incremental), propagates failure constraints, and persists successful strategies as reusable recipes. It does **not** call LLMs — it is a tool that LLMs use.

Part of the **Stele + Chisel + Trammel** triad:
- **Stele**: Persistent context retrieval and semantic indexing
- **Chisel**: Code analysis, churn, coupling, risk mapping
- **Trammel**: Planning discipline, verification, failure learning, recipe memory

Each works standalone. When co-installed, they cooperate through the LLM's MCP tool layer.

## 2. Non-goals

- Network calls, vector DBs, or embedding APIs beyond SQLite + trigram text similarity.
- Automatic code generation — the LLM fills `content` fields; Trammel handles structure and verification.
- Pytest as a hard dependency (tests use `unittest discover`).

## 3. Public API

| Entry | Behavior |
|-------|----------|
| `plan_and_execute(goal, project_root, num_beams=3, db_path="trammel.db")` | Decompose → plan → beams → harness each beam → log trajectories → save recipe on first passing beam |
| `explore(goal, project_root, num_beams=3, db_path="trammel.db")` | Decompose + beams only (no harness) |
| `synthesize(goal, strategy, db_path="trammel.db")` | Upsert a strategy as successful recipe (caller-verified) |
| `trammel/__version__` | Derived from `importlib.metadata` at runtime; matches `pyproject.toml` version |
| CLI `python -m trammel` | Argparse; optional JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd` |
| MCP `trammel-mcp` | 13 tools over stdio transport |

## 4. Planner (`core.py`)

- **Recipe hit**: If `retrieve_best_recipe(goal)` returns a strategy (similarity >= 0.3), use it.
- **Import analysis**: `analyze_imports()` builds a file→file dependency graph from AST `Import`/`ImportFrom` nodes, matching against project-internal modules.
- **Topological sort**: Kahn's algorithm orders files so dependencies come first. Cycles are appended at end.
- **Step generation**: Each file with symbols becomes a step with `description`, `rationale`, `depends_on` (indices of prior steps this depends on).
- **Beam strategies**: `bottom_up` (dependencies first — safest), `top_down` (API surface first), `risk_first` (most-imported files first — highest coupling impact).

## 5. Harness (`harness.py`)

- **`__init__(timeout_s=60, test_cmd=None)`**: Configure timeout and optional custom test command (e.g. `["pytest", "-x"]`). Defaults to `unittest discover`.
- **`run(edits, project_root)`**: Copy project to temp dir, apply all edits, run tests. Returns structured result.
- **`verify_step(edits, project_root, prior_edits)`**: Verify a single step in isolation. Applies prior_edits first, then current edits.
- **`run_incremental(step_edits, project_root)`**: Verify step-by-step. Stops at first failure with `failed_at_step` index and `failure_analysis`.
- **`analyze_failure(stderr, stdout)`**: Extracts error_type, message, file, line, suggestion from test output via regex patterns.

## 6. Store (`store.py`)

**SQLite tables (5)**

- `recipes(sig PK, pattern, strategy, constraints, successes, failures, created, updated)` — sig = SHA-256 of canonical JSON strategy.
- `plans(id, goal, strategy, status, current_step, total_steps, created, updated)`.
- `steps(id, plan_id FK, step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found)`.
- `constraints(id, plan_id FK, step_id FK, constraint_type, description, context, active)` — types: dependency, incompatible, requires, avoid.
- `trajectories(id, plan_id FK, beam_id, strategy_variant, steps_completed, outcome, failure_reason)`.

**Recipe retrieval**: `trigram_bag_cosine(goal, pattern)` with minimum threshold 0.3; tie-break on `successes`.

**Constraint propagation**: Active constraints are loaded during `decompose()` and included in the strategy. Constraints persist across sessions until deactivated.

## 7. MCP Server (`mcp_server.py`, `mcp_stdio.py`)

13 tools exposed via stdio JSON-RPC:

| Tool | Purpose |
|------|---------|
| `decompose` | Goal → dependency-aware strategy |
| `explore` | Goal → strategy + beam variants |
| `create_plan` | Persist a plan with tracked steps |
| `get_plan` | Retrieve full plan state |
| `verify_step` | Isolated single-step verification |
| `record_step` | Update step status/edits/verification |
| `save_recipe` | Store successful strategy |
| `get_recipe` | Retrieve best matching recipe |
| `add_constraint` | Record failure constraint |
| `get_constraints` | Query active constraints |
| `list_plans` | List plans by status |
| `history` | Trajectory history for a plan |
| `status` | Summary counts |

## 8. Utilities (`utils.py`)

- `_is_ignored_dir` — Check if a directory should be skipped (frozenset + `.egg-info` suffix).
- `analyze_imports` — AST-based project-internal import graph.
- `topological_sort` — Kahn's algorithm with cycle handling (uses `deque` for O(1) queue ops).
- `analyze_failure` — Structured error extraction from test output.
- `trigram_bag_cosine` — Shared-vocabulary trigram cosine similarity.
- `dumps_json` — Stable `sort_keys=True` JSON for hashing and persistence.
- `sha256_json` — Content-addressed recipe ID.
- `db_connect` — WAL + foreign keys.

## 9. Extension points

- Pass `test_cmd` to `ExecutionHarness` for pytest or a custom runner.
- Emit real `content` in edits from an LLM (the primary integration point).
- Add richer beam strategies beyond the current three.
- Connect to Stele/Chisel via MCP for context-aware planning and risk-aware step ordering.
