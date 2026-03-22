# Trammel — technical specification

**Version:** 2.0.0
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
| `plan_and_execute(goal, project_root, num_beams=3, db_path="trammel.db", test_cmd=None, language=None)` | Decompose → plan → beams → harness each beam → log trajectories → save recipe on first passing beam |
| `explore(goal, project_root, num_beams=3, db_path="trammel.db", language=None)` | Decompose + beams only (no harness) |
| `synthesize(goal, strategy, db_path="trammel.db")` | Upsert a strategy as successful recipe (caller-verified) |
| `trammel/__version__` | Derived from `importlib.metadata` at runtime; matches `pyproject.toml` version |
| CLI `python -m trammel` | Argparse; optional JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd` |
| MCP `trammel-mcp` | 17 tools over stdio transport |

## 4. Language Analyzers (`analyzers.py`)

- **`LanguageAnalyzer` protocol**: Defines `collect_symbols(root) -> dict[str, list[str]]`, `analyze_imports(root) -> dict[str, list[str]]`, `test_command() -> list[str]`, `error_patterns() -> list[str]`.
- **`PythonAnalyzer`**: AST-based symbol collection and import analysis (moved from `core.py` and `utils.py`).
- **`TypeScriptAnalyzer`**: Regex-based, stdlib-only analysis for `.ts`/`.tsx`/`.js`/`.jsx` files.
- **`detect_language(root)`**: Heuristic detection by file extension prevalence.
- **`get_analyzer(language)`**: Factory returning the appropriate analyzer instance.

## 5. Planner (`core.py`)

- **Recipe hit**: If `retrieve_best_recipe(goal, context_files)` returns a strategy (composite score >= 0.3), use it. Two-phase: text-only fast path, then structural scoring with file overlap.
- **Import analysis**: Delegated to language-specific analyzers. `Planner` accepts optional `analyzer` and auto-detects language if not provided.
- **Topological sort**: Kahn's algorithm orders files so dependencies come first. Cycles are appended at end.
- **Step generation**: Each file with symbols becomes a step with `description`, `rationale`, `depends_on` (indices of prior steps this depends on).
- **Beam strategies**: `bottom_up` (dependencies first — safest), `top_down` (API surface first), `risk_first` (most-imported files first — highest coupling impact).
- **Strategy registry**: Pluggable via `register_strategy(name, fn, description)`. Three built-in strategies auto-registered at module load. `get_strategies()` returns all registered `StrategyEntry` items. Strategy functions have unified signature `StrategyFn = Callable[[list, dict], list]` — `(steps, dep_graph) -> steps`.
- **Strategy learning**: `explore_trajectories` accepts optional `store`. When provided, `get_strategy_stats()` aggregates trajectory outcomes by variant (success/failure counts) and strategies are sorted by historical success rate.

## 6. Harness (`harness.py`)

- **`__init__(timeout_s=60, test_cmd=None, analyzer=None)`**: Configure timeout, optional custom test command, and optional language analyzer for language-specific test commands and error patterns. Defaults to `unittest discover`.
- **`run(edits, project_root)`**: Copy project to temp dir, apply all edits, run tests. Returns structured result.
- **`verify_step(edits, project_root, prior_edits)`**: Verify a single step in isolation. Applies prior_edits first, then current edits.
- **`run_incremental(step_edits, project_root)`**: Verify step-by-step. Stops at first failure with `failed_at_step` index and `failure_analysis`.
- **`analyze_failure(stderr, stdout, error_patterns=None)`**: Extracts error_type, message, file, line, suggestion from test output via regex patterns. Accepts optional `error_patterns` for language-specific patterns.

## 7. Store (`store.py`)

**SQLite tables (7)**

- `recipes(sig PK, pattern, strategy, constraints, successes, failures, created, updated)` — sig = SHA-256 of canonical JSON strategy.
- `recipe_trigrams(trigram, recipe_sig FK)` — inverted index for fast recipe retrieval. Indexed on `trigram`. Populated on `save_recipe`, auto-backfilled on schema init.
- `recipe_files(file_path, recipe_sig FK)` — file paths from strategy steps for structural matching. Indexed on both `file_path` and `recipe_sig`. Populated on `save_recipe`, auto-backfilled via `_backfill_files()`.
- `plans(id, goal, strategy, status, current_step, total_steps, created, updated)`.
- `steps(id, plan_id FK, step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found)`.
- `constraints(id, plan_id FK, step_id FK, constraint_type, description, context, active)` — types: dependency, incompatible, requires, avoid.
- `trajectories(id, plan_id FK, beam_id, strategy_variant, steps_completed, outcome, failure_reason)`.

**Recipe retrieval**: Two-phase indexed lookup — query `recipe_trigrams` for candidates sharing trigrams with goal, then compute exact `trigram_bag_cosine` on candidates only. When `context_files` provided, composite scoring: text similarity (0.5) + file overlap via Jaccard (0.3) + success ratio (0.2). Without `context_files`, backward-compatible text-only scoring. Minimum threshold 0.3; tie-break on `successes`.

**`list_recipes(limit=20)`**: Returns recent recipes ordered by update time.

**Constraint propagation**: Active constraints enforced during `decompose()` via `_apply_constraints`:
- `avoid` + `context.file` → step marked `status: "skipped"` with `skip_reason`
- `dependency` + `context.before/after` → ordering injected into `depends_on`
- `incompatible` + `context.file_a/file_b` → `incompatible_with` metadata on steps
- `requires` + `context.file` → placeholder step added for missing prerequisite

Strategy output includes both `constraints` (all active) and `constraints_applied` (those that matched).

**Concurrency**: All mutating store methods wrapped in `BEGIN IMMEDIATE` transactions with exponential backoff retry on `SQLITE_BUSY`. `RecipeStore` implements context manager protocol (`with` blocks). `db_connect` sets `timeout=5.0`.

## 8. MCP Server (`mcp_server.py`, `mcp_stdio.py`)

17 tools exposed via stdio JSON-RPC:

| Tool | Purpose |
|------|---------|
| `decompose` | Goal → dependency-aware strategy (accepts `language` parameter) |
| `explore` | Goal → strategy + beam variants (accepts `language` parameter) |
| `create_plan` | Persist a plan with tracked steps |
| `get_plan` | Retrieve full plan state |
| `verify_step` | Isolated single-step verification |
| `record_step` | Update step status/edits/verification |
| `save_recipe` | Store successful strategy (populates `recipe_files`) |
| `get_recipe` | Retrieve best matching recipe (accepts `context_files` for composite scoring) |
| `add_constraint` | Record failure constraint |
| `get_constraints` | Query active constraints |
| `list_plans` | List plans by status |
| `history` | Trajectory history for a plan |
| `status` | Summary counts (includes `tools` count) |
| `list_strategies` | Registered strategy names with success/failure stats |
| `list_recipes` | List stored recipes (limit=20) |
| `update_plan_status` | Update plan status (exposes existing store method) |
| `deactivate_constraint` | Deactivate a constraint (exposes existing store method) |

See `SYSTEM_PROMPT.md` for a reference orchestration guide describing the plan-verify-store loop for LLM clients.

## 9. Utilities (`utils.py`)

- `_is_ignored_dir` — Check if a directory should be skipped (frozenset + `.egg-info` suffix). Expanded set includes `.next`, `.nuxt`, `coverage`, `.turbo`, `.parcel-cache`.
- `analyze_imports` — Backward-compat wrapper delegating to `PythonAnalyzer`.
- `topological_sort` — Kahn's algorithm with cycle handling (uses `deque` for O(1) queue ops).
- `analyze_failure` — Structured error extraction from test output. Accepts optional `error_patterns` for language-specific patterns.
- `unique_trigrams` — Distinct trigram set for index population and lookup.
- `trigram_bag_cosine` — Shared-vocabulary trigram cosine similarity.
- `transaction` — Context manager for explicit SQLite transactions with BUSY retry.
- `dumps_json` — Stable `sort_keys=True` JSON for hashing and persistence.
- `sha256_json` — Content-addressed recipe ID.
- `db_connect` — WAL + foreign keys + `timeout=5.0`.

## 10. Extension points

- Pass `test_cmd` to `ExecutionHarness` for pytest or a custom runner.
- Emit real `content` in edits from an LLM (the primary integration point).
- Register custom beam strategies via `register_strategy()` beyond the three built-in.
- Add constraint types beyond the four built-in (avoid/dependency/incompatible/requires).
- Implement `LanguageAnalyzer` protocol for additional languages beyond Python and TypeScript.
- Use `SYSTEM_PROMPT.md` as a reference for building LLM client orchestration loops.
- Connect to Stele/Chisel via MCP for context-aware planning and risk-aware step ordering.
