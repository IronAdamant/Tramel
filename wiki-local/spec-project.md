# Trammel — technical specification

**Version:** 3.7.4
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
| CLI `python -m trammel` | Argparse; optional JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd`, `--dry-run` (runs `explore()` instead of `plan_and_execute()`), `--language`, `--scope` (monorepo support) |
| MCP `trammel-mcp` | 21 tools over stdio transport |

## 4. Language Analyzers (`analyzers.py` + `analyzers_ext.py`)

Module split: `analyzers.py` (~460 LOC) holds the protocol, Python, TypeScript, registry, and detection. `analyzers_ext.py` (~440 LOC) holds Go, Rust, C/C++, and Java/Kotlin. `analyzers_ext2.py` (~445 LOC) holds C#, Ruby, PHP, Swift, Dart, and Zig. Shared `_collect_symbols_regex` and `_collect_typed_symbols_regex` helpers live in `utils.py`. Where possible, `_*_SYMBOL_PATTERNS` are derived from `_*_TYPED_PATTERNS` to avoid regex duplication. All existing imports preserved via re-export from `analyzers.py`.

- **`LanguageAnalyzer` protocol**: Defines `collect_symbols(root) -> dict[str, list[str]]`, `analyze_imports(root) -> dict[str, list[str]]`, `test_command() -> list[str]`, `error_patterns() -> list[str]`.
- **`PythonAnalyzer`**: AST-based symbol collection and import analysis (moved from `core.py` and `utils.py`).
- **`TypeScriptAnalyzer`**: Regex-based, stdlib-only analysis for `.ts`/`.tsx`/`.js`/`.jsx`/`.mts`/`.mjs` files. Symbol detection via `_TS_SYMBOL_PATTERNS` list (interface, enum, const enum, type alias, abstract class, decorated class, function expression, namespace). `_strip_c_comments` (shared from `utils.py`) strips comments before symbol/import detection. Import detection via expanded `_TS_IMPORT_RE` (standard imports, re-exports `export { } from`, barrel exports `export * from`, type re-exports `export type { } from`, dynamic imports `import()`). `_TS_ALIAS_IMPORT_RE` detects non-relative alias imports. `_read_ts_path_aliases(root)` reads `compilerOptions.paths` + `baseUrl` from `tsconfig.json`. `_resolve_alias()` resolves alias-based import paths.
- **`GoAnalyzer`**: Regex-based analysis for `.go` files. Reads `go.mod` for module path. Resolves internal imports (imports matching the module path) to project-relative file paths.
- **`RustAnalyzer`**: Regex-based analysis for `.rs` files. Resolves `use crate::` imports and `mod` declarations to project-relative file paths.
- **`CppAnalyzer`**: Regex-based analysis for `.c/.cpp/.cc/.cxx/.h/.hpp/.hxx` files. 5-pattern symbol detection: template functions, qualified functions (static/inline/constexpr), operator overloading, constructor/destructor, macro-prefixed functions (EXPORT_API etc). `#include "..."` import resolution with comment stripping. Registered as "cpp" and "c".
- **`JavaAnalyzer`**: Regex-based analysis for `.java/.kt/.kts` files. Symbol detection for class, interface, enum, fun, object, and @interface declarations. `_detect_source_roots(project_root)` reads `build.gradle`/`build.gradle.kts`/`pom.xml` for standard source directories (`src/main/java`, `src/main/kotlin`, etc); falls back to project root. `analyze_imports` walks detected source roots instead of project root. Registered as "java" and "kotlin".
- **`CSharpAnalyzer`**: Regex-based analysis for `.cs` files in `analyzers_ext2.py`. Symbol detection for class, interface, struct, enum, record, and delegate declarations. `using` import resolution. Registered as "csharp".
- **`RubyAnalyzer`**: Regex-based analysis for `.rb` files in `analyzers_ext2.py`. Symbol detection for class, module, and def declarations. `require`/`require_relative` import resolution. Registered as "ruby".
- **`PhpAnalyzer`**: Regex-based analysis for `.php` files in `analyzers_ext2.py`. Symbol detection for class, interface, trait, enum, and function declarations. `use`/`require`/`include` import resolution. Registered as "php".
- **`SwiftAnalyzer`**: Regex-based analysis for `.swift` files in `analyzers_ext2.py`. Symbol detection for class, struct, enum, protocol, func, and actor declarations. `import` resolution. Registered as "swift".
- **`DartAnalyzer`**: Regex-based analysis for `.dart` files in `analyzers_ext2.py`. Symbol detection for class, mixin, extension, enum, and typedef declarations. `import`/`part` resolution. Registered as "dart".
- **`ZigAnalyzer`**: Regex-based analysis for `.zig` files in `analyzers_ext2.py`. Symbol detection for pub fn, const, struct, enum, and union declarations. `@import` resolution. Registered as "zig".
- **Shared `_collect_symbols_regex` and `_collect_typed_symbols_regex` helpers** (in `utils.py`): Common symbol collection logic used by all regex-based analyzers. Eliminates circular dependency workarounds (previously used `functools.cache` lazy imports).
- **`_detect_from_config(root)`**: Config-file detection (Cargo.toml → rust, go.mod → go, tsconfig.json/package.json → typescript, build.gradle/pom.xml → java, CMakeLists.txt → cpp, pyproject.toml/setup.py → python, Package.swift → swift, build.zig → zig, pubspec.yaml → dart, .csproj/.sln → csharp, Gemfile → ruby, composer.json → php). Takes priority over extension counting.
- **`detect_language(root)`**: Config-file detection first, falling back to extension counting. Counts `.py`, `.ts`/`.tsx`/`.js`/`.jsx`, `.go`, `.rs`, `.c`/`.cpp`, `.java`/`.kt`, `.cs`, `.rb`, `.php`, `.swift`, `.dart`, and `.zig` files.
- **`get_analyzer(language)`**: Factory returning the appropriate analyzer instance. Registry supports 15 languages: python, typescript, javascript, go, rust, cpp, c, java, kotlin, csharp, ruby, php, swift, dart, zig.

## 5. Planner (`core.py`) and Strategies (`strategies.py`)

`core.py` (~325 LOC) holds the `Planner`, step generation, and constraint enforcement. `strategies.py` (~280 LOC) holds the strategy registry and 9 built-in orderings (extracted from `core.py` in v3.3.1).

- **Recipe hit**: If `retrieve_best_recipe(goal, context_files)` returns a strategy (composite score >= 0.3), use it. Two-phase: text-only fast path, then structural scoring with file overlap.
- **Scope support**: `decompose(goal, project_root, scope=None)` accepts an optional `scope` subdirectory. When provided, analysis is scoped to `os.path.join(project_root, scope)` while the full project remains available for test execution. Enables monorepo workflows.
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

Module split: `store.py` (~342 LOC) holds schema init, plans, steps, constraints, trajectories, and `RecipeStore` (inherits `RecipeStoreMixin`). `store_recipes.py` (~210 LOC) holds `RecipeStoreMixin` with recipe methods: `save_recipe`, `retrieve_best_recipe`, `list_recipes`, `prune_recipes`, `_rebuild_trigram_index`, `_backfill_files`.

**SQLite tables (7)**

- `recipes(sig PK, pattern, strategy, constraints, successes, failures, created, updated)` — sig = SHA-256 of canonical JSON strategy.
- `recipe_trigrams(trigram, recipe_sig FK)` — inverted index for fast recipe retrieval. Indexed on `trigram`. Populated on `save_recipe`, auto-backfilled on schema init.
- `recipe_files(file_path, recipe_sig FK)` — file paths from strategy steps for structural matching. Indexed on both `file_path` and `recipe_sig`. Populated on `save_recipe`, auto-backfilled via `_backfill_files()`.
- `plans(id, goal, strategy, status, current_step, total_steps, created, updated)`.
- `steps(id, plan_id FK, step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found)`.
- `constraints(id, plan_id FK, step_id FK, constraint_type, description, context, active)` — types: dependency, incompatible, requires, avoid.
- `trajectories(id, plan_id FK, beam_id, strategy_variant, steps_completed, outcome, failure_reason)`.

**Recipe retrieval**: Two-phase indexed lookup — query `recipe_trigrams` for candidates sharing trigrams with normalized goal, then score via `goal_similarity` (0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring on normalized text). When `context_files` provided, composite scoring with recency weighting: text similarity (0.4) + file overlap via Jaccard (0.25) + success ratio (0.15) + recency (0.2, 30-day half-life). Without `context_files`, backward-compatible text-only scoring. Minimum threshold 0.3; tie-break on `successes`. `save_recipe` uses single parameterized query (merged duplicated SQL branches). `_rebuild_trigram_index` rebuilds all trigrams with normalized text on init (renamed from `_backfill_trigrams`).

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
