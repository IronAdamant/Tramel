# Trammel — technical specification

**Version:** 3.11.0
**Language:** Python 3.10+ (stdlib only for core; `mcp` optional for MCP server)

## 1. Purpose

Trammel externalizes the planning bottleneck for LLM coding assistants. It decomposes goals into dependency-aware strategies, explores genuinely different beam orderings, runs isolated verification (full or incremental), propagates failure constraints, and persists successful strategies as reusable recipes. It does **not** call LLMs — it is a tool that LLMs use.

Part of the **Stele + Chisel + Trammel** triad:
- **Stele**: Persistent context retrieval and semantic indexing
- **Chisel**: Code analysis, churn, coupling, risk mapping
- **Trammel**: Planning discipline, verification, failure learning, recipe memory

Each works standalone. When co-installed, they cooperate through the LLM's MCP tool layer **where the host exposes MCP**.

### 1.1 Integration surfaces (MCP optional)

The **authoritative artifacts** are **not** MCP-specific. They are:

- **`trammel.db` (SQLite):** plans, steps (`status`, `claimed_by`, `depends_on`), constraints, recipes, trajectories.
- **Python API:** `Planner.decompose`, `explore`, `plan_and_execute`, `RecipeStore`, `ExecutionHarness`.
- **CLI:** `python -m trammel`, JSON on stdin.

**MCP** (`trammel-mcp`) is a convenience for **MCP-capable** hosts (Cursor, Claude Code, etc.). **Sub-agents** in shells, CI, or secondary models often **do not** use MCP; they should consume **the same plan and store** (exported JSON, shared DB, or wrapper scripts). Trammel is designed for this split: **orchestrator** may use MCP; **workers** follow the persisted plan.

### 1.2 Roadmap and design notes (directional)

- **Worth adding:** versioned **plan/strategy export** for external runners; **apply `test_cmd` from project config** to harness defaults; optional **hooks / structured logging**; orchestrator **checklists** in docs.
- **Worth changing carefully:** `relevant_only` **re-sorts** steps by relevance—**execution order** remains `depends_on`; **document** or later split **priority** vs **execution** order; **`max_files`** truncation can weaken the graph—document tradeoffs; **consolidate** `.trammel.json` parsing so language and project config stay one evolving dialect.

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
| CLI `python -m trammel` | Argparse; optional JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd`, `--dry-run` (runs `explore()` instead of `plan_and_execute()`), `--language`, `--scope` (monorepo support) |
| MCP `trammel-mcp` | Many tools over stdio transport; use MCP `status` for current count and names |

## 4. Language Analyzers (`analyzers.py` + `analyzer_engine.py`)

Architecture: `analyzers.py` (~460 LOC) holds the `LanguageAnalyzer` protocol, `PythonAnalyzer` (AST-based), `TypeScriptAnalyzer` (regex-based), registry, and detection. All 13 other regex-based analyzers are now driven by a single declarative engine.

- **`LanguageAnalyzer` protocol**: Defines `collect_symbols(root) -> dict[str, list[str]]`, `collect_typed_symbols(root) -> dict[str, list[tuple[str, str]]]`, `analyze_imports(root) -> dict[str, list[str]]`, `pick_test_cmd(root) -> list[str]`, `error_patterns() -> list[tuple[str, str, str]]`.
- **`PythonAnalyzer`**: AST-based symbol collection and import analysis.
- **`TypeScriptAnalyzer`**: Regex-based, stdlib-only analysis for `.ts`/`.tsx`/`.js`/`.jsx`/`.mts`/`.mjs` files. Symbol detection via `_TS_SYMBOL_PATTERNS` list (interface, enum, const enum, type alias, abstract class, decorated class, function expression, namespace). `_strip_c_comments` strips comments before symbol/import detection. Import detection via expanded `_TS_IMPORT_RE` (standard imports, re-exports, barrel exports, type re-exports, dynamic imports). `_TS_ALIAS_IMPORT_RE` detects non-relative alias imports. `_read_ts_path_aliases(root)` reads `compilerOptions.paths` + `baseUrl` from `tsconfig.json`. `_resolve_alias()` resolves alias-based import paths.
- **`analyzer_specs.py`**: Declarative specs for 13 regex-based analyzers (Go, Rust, C/C++, Java/Kotlin, C#, Ruby, PHP, Swift, Dart, Zig). Each `AnalyzerSpec` bundles `symbol_patterns`, `typed_patterns`, a `strip_comments` key (`c`/`hash`/`php`), `test_cmd`, `error_patterns`, and an optional `ImportSpec` (strategy name + regex patterns).
- **`analyzer_engine.py`**: `RegexAnalyzerEngine` backed by `AnalyzerSpec`. Implements generic `collect_symbols`, `collect_typed_symbols`, `analyze_imports`, `pick_test_cmd`, and `error_patterns`. Import resolution is dispatched by strategy name to dedicated resolvers: `go_mod`, `rust_crate`, `cpp_include`, `java_namespace`, `csharp_namespace`, `ruby_require`, `php_namespace`, `swift_module`, `dart_package`, `zig_import`. Backward-compatible class shims (`GoAnalyzer`, `RustAnalyzer`, `CppAnalyzer`, `JavaAnalyzer`, `CSharpAnalyzer`, `RubyAnalyzer`, `PhpAnalyzer`, `SwiftAnalyzer`, `DartAnalyzer`, `ZigAnalyzer`) preserve all existing imports.
- **`analyzers_ext.py` / `analyzers_ext2.py`**: Backward-compatibility shims that re-export the engine-backed analyzer classes. Previously held standalone analyzer implementations; now deprecated stubs.
- **Shared helpers in `utils.py`**: `_collect_symbols_regex`, `_collect_typed_symbols_regex`, `_walk_project_sources`, `_collect_project_files`, `_walk_and_map_namespaces`, `_resolve_namespace_import`, `_strip_c_comments`, `_strip_hash_comments`, `_strip_php_comments`.
- **`_detect_from_config(root)`**: Config-file detection (Cargo.toml → rust, go.mod → go, tsconfig.json/package.json → typescript, build.gradle/pom.xml → java, CMakeLists.txt → cpp, pyproject.toml/setup.py → python, Package.swift → swift, build.zig → zig, pubspec.yaml → dart, .csproj/.sln → csharp, Gemfile → ruby, composer.json → php). Takes priority over extension counting.
- **`detect_language(root)`**: Config-file detection first, falling back to extension counting.
- **`get_analyzer(language)`**: Factory returning the appropriate analyzer instance. Registry supports 15 languages: python, typescript, javascript, go, rust, cpp, c, java, kotlin, csharp, ruby, php, swift, dart, zig.

## 5. Planner (`core.py`) and Strategies (`strategies.py`)

`core.py` (~570 LOC) is the thin orchestrator: `Planner.decompose()` and `explore_trajectories()`. Step generation, scoring, scaffold logic, goal NLP, and constraint propagation were extracted into `scoring.py`, `scaffold_logic.py`, `goal_nlp.py`, and `constraints.py` in v3.11.0. `strategies.py` (~280 LOC) holds the strategy registry and 9 built-in orderings.

- **Recipe hit**: If `retrieve_best_recipe(goal, context_files)` returns a strategy (composite score >= 0.3), use it. Two-phase: text-only fast path, then structural scoring with file overlap.
- **Scope support**: `decompose(goal, project_root, scope=None)` accepts an optional `scope` subdirectory. When provided, analysis is scoped to `os.path.join(project_root, scope)` while the full project remains available for test execution. Enables monorepo workflows.
- **Plan fidelity (v3.8+):** With a non-empty `scaffold`, decomposition defaults to **scaffold-only** (no full-repo scan) unless `expand_repo=true`. **`strict_greenfield`** rejects under-specified greenfield goals. Results include **`plan_fidelity`** metadata. Optional **`focus_keywords`**, **`focus_globs`**, **`max_files`**; merged **`[tool.trammel]`** + **`.trammel.json`** via **`project_config.py`**. Steps may expose **`relevance_keyword`**, **`relevance_graph`**, composite **`relevance`**, **`relevance_tier`**. With **`relevant_only`**, steps are re-sorted by relevance—**execution order** for work remains **`depends_on`**.
- **Scaffold DAG metrics**: When scaffold entries are provided, `decompose` returns `scaffold_dag_metrics` in `analysis_meta` containing `node_count`, `edge_count`, `max_dependency_depth`, `critical_path_length`, `max_parallelism` (widest layer — peak concurrent files), and `layer_widths` (array of file counts per topological layer). Use `layer_widths` to dispatch agents in rounds; `max_parallelism` sizes the agent pool. Validated at scale: 40 nodes, 59 edges, 6 layers, 12-file peak parallelism (Review Ten).
- **Import analysis**: Delegated to language-specific analyzers. `Planner` accepts optional `analyzer` and auto-detects language if not provided.
- **Topological sort**: Kahn's algorithm orders files so dependencies come first. Cycles are appended at end.
- **Step generation**: Each file with symbols becomes a step with `description`, `rationale`, `depends_on` (indices of prior steps this depends on).
- **Beam strategies (9 built-in)**: `bottom_up` (dependencies first), `top_down` (API surface first), `risk_first` (most-imported files first), `critical_path` (longest dependency chain first, iterative DFS with cycle detection), `cohesion` (flood-fill connected components, toposort within), `minimal_change` (fewest symbols first), `leaf_first` (zero importers first), `hub_first` (network hub files first), `test_adjacent` (files with matching test files first).
- **Strategy registry**: Pluggable via `register_strategy(name, description, fn)`. Nine built-in strategies auto-registered at module load. `get_strategies()` returns all registered `StrategyEntry` items. Strategy functions have unified signature `StrategyFn = Callable[[list, dict], list]` — `(steps, dep_graph) -> steps`.
- **Strategy learning**: `explore_trajectories` accepts optional `store`. When provided, `get_strategy_stats()` aggregates trajectory outcomes by variant (success/failure counts) and strategies are sorted by historical success rate.

## 6. Harness (`harness.py`)

- **`__init__(timeout_s=60, test_cmd=None, analyzer=None)`**: Configure timeout, optional custom test command, and optional language analyzer for language-specific test commands and error patterns. Defaults to `unittest discover`.
- **`run(edits, project_root)`**: Copy project to temp dir, apply all edits, run tests. Returns structured result.
- **`prepare_base(project_root)`**: Create one filtered base copy of the project (applies ignored-dir filtering once). Returns the base directory path.
- **`run_from_base(edits, base_dir)`**: Copy from an existing base directory, apply edits, run tests. Avoids re-filtering ignored dirs per beam.
- **`verify_step(edits, project_root, prior_edits)`**: Verify a single step in isolation. Applies prior_edits first, then current edits.
- **`run_incremental(step_edits, project_root)`**: Verify step-by-step. Stops at first failure with `failed_at_step` index and `failure_analysis`.
- **`analyze_failure(stderr, stdout, error_patterns=None)`**: Extracts error_type, message, file, line, suggestion from test output via regex patterns. Accepts optional `error_patterns` for language-specific patterns.

## 7. Store (`store.py` + `store_recipes.py`)

Module split: `store.py` (~342 LOC) holds schema init, plans, steps, constraints, trajectories, and `RecipeStore` (inherits `RecipeStoreMixin`). `store_recipes.py` (~210 LOC) holds `RecipeStoreMixin` with recipe methods. `recipe_index.py` provides the zero-dep word index + MinHash LSH used by recipe retrieval.

**SQLite tables (7)**

- `recipes(sig PK, pattern, strategy, constraints, successes, failures, created, updated)` — sig = SHA-256 of canonical JSON strategy.
- `recipe_trigrams(trigram, recipe_sig FK)` — inverted trigram index (legacy; retained for transition safety)
- `recipe_terms(term, recipe_sig, count)` — inverted word index for TF-IDF candidate lookup
- `recipe_signatures(recipe_sig PK, signature)` — MinHash LSH signature for deduplication / ANN
- `recipe_files(file_path, recipe_sig FK)` — file paths from strategy steps for structural matching. Indexed on both `file_path` and `recipe_sig`. Populated on `save_recipe`, auto-backfilled via `_backfill_files()`.
- `plans(id, goal, strategy, scaffold, status, current_step, total_steps, created, updated)`.
- `steps(id, plan_id FK, step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found)`.
- `constraints(id, plan_id FK, step_id FK, constraint_type, description, context, active)` — types: dependency, incompatible, requires, avoid.
- `trajectories(id, plan_id FK, beam_id, strategy_variant, steps_completed, outcome, failure_reason)`.

**Recipe retrieval**: Two-phase indexed lookup — query `recipe_terms` (inverted word index, TF-IDF) for candidates sharing vocabulary with the goal, then score via `goal_similarity` (0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring on normalized text). `recipe_signatures` stores MinHash LSH signatures for deduplication / approximate nearest neighbors. When `context_files` provided, composite scoring with recency weighting: text similarity (0.4) + file overlap via Jaccard (0.25) + success ratio (0.15) + recency (0.2, 30-day half-life). Without `context_files`, backward-compatible text-only scoring. Minimum threshold 0.3; tie-break on `successes`. Legacy `recipe_trigrams` table retained for transition safety.

**`list_recipes(limit=20)`**: Returns recent recipes ordered by update time.

**`prune_recipes(max_age_days=90, min_success_ratio=0.1)`**: Removes stale, low-quality recipes. Cascade deletes to `recipe_trigrams` and `recipe_files`.

**`validate_recipes(project_root)`**: Checks recipe file entries against current project. Removes stale file entries. Recipes whose files are entirely missing are cascade-pruned. Returns `{recipes_checked, files_removed, recipes_invalidated}`.

**`get_plan_progress(plan_id)`**: Returns plan state with accumulated `prior_edits` from passed steps, `remaining_steps`, `next_step_index`, and `completed_count` for plan resumption.

**Constraint propagation**: Active constraints enforced during `decompose()` via decomposed constraint functions (`_parse_constraints` -> `_mark_avoided` -> `_inject_orderings` -> `_mark_incompatible` -> `_add_prerequisites`):
- `avoid` + `context.file` → step marked `status: "skipped"` with `skip_reason`
- `dependency` + `context.before/after` → ordering injected into `depends_on`
- `incompatible` + `context.file_a/file_b` → `incompatible_with` metadata on steps
- `requires` + `context.file` → placeholder step added for missing prerequisite

Strategy output includes both `constraints` (all active) and `constraints_applied` (those that matched).

**Concurrency**: All mutating store methods wrapped in `BEGIN IMMEDIATE` transactions with exponential backoff retry on `SQLITE_BUSY`. `RecipeStore` implements context manager protocol (`with` blocks). `db_connect` sets `timeout=5.0`.

## 8. MCP Server (`mcp_server.py`, `mcp_stdio.py`)

22 tools exposed via stdio JSON-RPC:

| Tool | Purpose |
|------|---------|
| `decompose` | Goal → dependency-aware strategy (accepts `language` and `scope` parameters) |
| `explore` | Goal → strategy + beam variants (accepts `language` and `scope` parameters) |
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
| `prune_recipes` | Remove stale/low-quality recipes (`max_age_days`, `min_success_ratio` parameters) |
| `resume` | Get plan progress with prior_edits from passed steps for resumption |
| `validate_recipes` | Check recipe files against project, remove stale entries, prune fully-stale recipes |
| `estimate` | Quick file count for a project or scope without full analysis; returns `language`, `matching_files`, `recommendation` |
| `usage_stats` | Aggregated usage telemetry: tool call counts, recipe hit/miss rates, strategy win rates |

See `SYSTEM_PROMPT.md` for a reference orchestration guide describing the plan-verify-store loop for LLM clients.

## 9. Utilities (`utils.py`, ~370 LOC)

- `_is_ignored_dir` — Check if a directory should be skipped (frozenset + `.egg-info` suffix). Expanded set includes `.next`, `.nuxt`, `coverage`, `.turbo`, `.parcel-cache`.
- `topological_sort` — Kahn's algorithm with cycle handling (uses `deque` for O(1) queue ops).
- `analyze_failure` — Structured error extraction from test output. Accepts optional `error_patterns` for language-specific patterns.
- `unique_trigrams` — Distinct trigram set for index population and lookup.
- `trigram_bag_cosine` — Shared-vocabulary trigram cosine similarity.
- `_VERB_SYNONYMS` — Dict comprehension mapping 40+ verb variants to 9 canonical forms (e.g., "refactor"/"rewrite"/"reorganize" all map to "restructure").
- `_ABBREVIATIONS` — Dict of ~40 common coding abbreviations (gc→garbage collector, db→database, auth→authentication, api→application programming interface, etc.).
- `normalize_goal(text)` — Lowercase + abbreviation expansion + verb synonym replacement for goal text normalization. Abbreviation expansion enables recipe matching across abbreviated goals (e.g., "optimize GC" matches "optimize garbage collector" at 0.86+ similarity).
- `word_jaccard(a, b)` — Word-level Jaccard similarity between two strings.
- `word_substring_score(a, b)` — Partial word matching: checks for substring overlap between the word sets of two strings. Rewards partial matches that pure Jaccard misses.
- `goal_similarity(a, b)` — Blended similarity: 0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring on normalized text.
- `transaction` — Context manager for explicit SQLite transactions with BUSY retry.
- `dumps_json` — Stable `sort_keys=True` JSON for hashing and persistence.
- `sha256_json` — Content-addressed recipe ID.
- `db_connect` — WAL + foreign keys + `timeout=5.0`.

## 10. Extension points

- Pass `test_cmd` to `ExecutionHarness` for pytest or a custom runner.
- Emit real `content` in edits from an LLM (the primary integration point).
- Register custom beam strategies via `register_strategy()` beyond the nine built-in.
- Add constraint types beyond the four built-in (avoid/dependency/incompatible/requires).
- Implement `LanguageAnalyzer` protocol for additional languages beyond the 15 built-in (Python, TypeScript, JavaScript, Go, Rust, C/C++, Java, Kotlin, C#, Ruby, PHP, Swift, Dart, Zig).
- Use `SYSTEM_PROMPT.md` as a reference for building LLM client orchestration loops.
- Connect to Stele/Chisel via MCP for context-aware planning and risk-aware step ordering.
