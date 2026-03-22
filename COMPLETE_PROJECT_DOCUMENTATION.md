# Trammel — Project documentation index

**Updated:** 2026-03-23
**Version:** 2.4.0
**Purpose:** Stdlib-only planning harness: dependency-aware decomposition (Python, TypeScript, Go, Rust), real beam branching, incremental verification, failure constraint propagation, structural recipe matching, SQLite recipe/plan/step/constraint/trajectory persistence. MCP server (17 tools) for LLM integration with reference system prompt.

## Root files

| Path | Purpose |
|------|---------|
| `README.md` | Overview, quickstart, CLI, MCP setup, architecture, version notes |
| `COMPLETE_PROJECT_DOCUMENTATION.md` | This file: inventory and data flows |
| `LLM_Development.md` | Chronological change log |
| `pyproject.toml` | Package metadata (`trammel` 2.4.0), `requires-python >=3.10`, `mcp` optional dep, console scripts `trammel` + `trammel-mcp` |
| `SYSTEM_PROMPT.md` | Reference orchestration guide for LLM clients: plan-verify-store loop |

## wiki-local/

| Path | Purpose |
|------|---------|
| `wiki-local/index.md` | Wiki hub; links to spec, glossary, root docs |
| `wiki-local/spec-project.md` | Technical spec: API, schema, planner/harness/store behavior |
| `wiki-local/glossary.md` | Named concepts (beam, recipe, strategy, harness, constraint, ...) |

## Package `trammel/`

| Path | Purpose | Main deps |
|------|---------|-----------|
| `trammel/__init__.py` | `__version__` (from `importlib.metadata`), `plan_and_execute`, `explore`, `synthesize`; exports `PythonAnalyzer`, `TypeScriptAnalyzer`, `GoAnalyzer`, `RustAnalyzer`, `detect_language`; wires Planner, ExecutionHarness, RecipeStore | `core`, `harness`, `store`, `analyzers` |
| `trammel/__main__.py` | `python -m trammel` → `cli.main()` | `cli` |
| `trammel/analyzers.py` | `LanguageAnalyzer` protocol, `PythonAnalyzer` (AST-based), `TypeScriptAnalyzer` (regex-based: `_TS_SYMBOL_PATTERNS` list, expanded import/re-export detection, `_TS_ALIAS_IMPORT_RE`, `_read_ts_path_aliases`, `_resolve_alias`, `.mts`/`.mjs` extensions, `_strip_js_comments` for comment stripping before symbol/import detection, namespace pattern in `_TS_SYMBOL_PATTERNS`), `GoAnalyzer` (regex-based, reads `go.mod` for module path, resolves internal imports), `RustAnalyzer` (regex-based, resolves `use crate::` and `mod` declarations), shared `_collect_symbols_regex` helper for regex-based analyzers, `detect_language()` (counts `.go`/`.rs` files), `get_analyzer()` — registry supports 5 languages | stdlib |
| `trammel/cli.py` | Argparse + JSON stdin; `--version`, `--root`, `--beams`, `--db`, `--test-cmd` | `__init__` |
| `trammel/core.py` | `Planner`: import-aware dependency analysis (delegates to language analyzers), topological step ordering, real beam branching (bottom_up/top_down/risk_first/critical_path/cohesion/minimal_change), constraint propagation via `_apply_constraints`. Pluggable strategy registry (`register_strategy`/`get_strategies`/`StrategyFn`/`StrategyEntry`); 6 built-in strategies auto-registered; `_split_active_skipped` helper shared by all strategies. `_order_bottom_up` stable-sorts by ascending dependency count; `_order_top_down` stable-sorts by descending dependency count; both now genuinely use the `dep_graph` parameter. `explore_trajectories` supports strategy learning via optional `store`. | `store`, `utils`, `analyzers` |
| `trammel/harness.py` | Temp copy, `_apply_edits`, full `run()`, `verify_step()`, `run_incremental()`, configurable `test_cmd`, failure analysis. Accepts optional `analyzer` for language-specific test commands and error patterns. Falls back to `PythonAnalyzer` for default test command. | `utils`, `analyzers` |
| `trammel/store.py` | SQLite: recipes, recipe_trigrams, recipe_files (structural matching), plans, steps, constraints, trajectories (7 tables). Context manager. Transaction wrapping. Composite scoring with recency weighting (text 0.4, files 0.25, success 0.15, recency 0.2; 30-day half-life). `list_recipes(limit=20)`. `save_recipe` uses single parameterized query (merged duplicated SQL branches). Merged `list_plans` and `get_active_constraints` query branches. Simplified `get_strategy_stats`. `retrieve_best_recipe` uses `goal_similarity` scoring and normalizes goals for trigram queries. `_rebuild_trigram_index` rebuilds all trigrams with normalized text on init. 516 lines (trimmed from 534). | `utils` |
| `trammel/utils.py` | Trigrams, cosine, `unique_trigrams`, `transaction`, `topological_sort`, `analyze_failure` (accepts optional `error_patterns`), `_is_ignored_dir`, `_ERROR_PATTERNS`, `dumps_json`, `sha256_json`, `db_connect`, `_VERB_SYNONYMS` (dict comprehension, 40+ verb variants → 9 canonical forms), `normalize_goal`, `word_jaccard`, `word_substring_score(a, b)` (partial word matching), `goal_similarity` (0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring) | stdlib |
| `trammel/mcp_server.py` | MCP tool schemas (17 tools) + `match/case` `dispatch_tool` routing. Refactored with `_schema()` and `_prop()` helpers (255 lines, down from 507). Language enums include "go" and "rust" (5 languages). | `core`, `harness`, `store` |
| `trammel/mcp_stdio.py` | MCP stdio server entry point (`trammel-mcp` console script) | `mcp_server`, `store`, `mcp` (optional) |

## Tests

| Path | Purpose |
|------|---------|
| `tests/test_trammel.py` | Core: trigrams, toposort, import analysis, store (incl. trigram index), harness, plan_and_execute, explore |
| `tests/test_trammel_extra.py` | Edges: failure analysis, step updates, constraint filtering/propagation, transactions, context manager, incremental harness, MCP dispatch, CLI |
| `tests/test_strategies.py` | Strategy registry, strategy learning, strategy stats, beam strategies incl. critical_path/cohesion/minimal_change (TestBeamStrategies moved from test_trammel_extra.py) |
| `tests/test_analyzers.py` | Language analyzers: PythonAnalyzer, TypeScriptAnalyzer (symbols, imports, tsconfig, graceful fallbacks, comment stripping), GoAnalyzer, RustAnalyzer, detect_language (38 tests) |

## Data flow

1. `plan_and_execute` → `RecipeStore.retrieve_best_recipe` with optional `context_files` (two-phase: text-only fast path, then composite scoring with file overlap). Scoring uses `goal_similarity` (0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring on normalized text). Composite weights: text 0.4, file overlap (Jaccard) 0.25, success ratio 0.15, recency 0.2 (30-day half-life). Min threshold 0.3 → optional cached strategy.
2. Else `Planner.decompose` detects language (or uses provided `analyzer`), scans symbols via `LanguageAnalyzer` (Python AST or TypeScript regex), builds dependency graph, `topological_sort` orders files → steps with rationale + depends_on. Active constraints enforced via `_apply_constraints` (avoid/dependency/incompatible/requires). Passes project file context to recipe retrieval for structural matching.
3. `explore_trajectories` emits beams from the strategy registry (pluggable via `register_strategy`). When `store` provided, strategies sorted by historical success rate via `get_strategy_stats()`. Constraint-aware strategies: `bottom_up` (dependencies first, skipped at end), `top_down` (API first, skipped at end), `risk_first` (highest coupling first, incompatible isolated, package batching), `critical_path` (longest dependency chain first), `cohesion` (flood-fill connected components, largest first, toposort within), `minimal_change` (fewest symbols first). Skipped steps excluded from beam edits.
4. `ExecutionHarness.run` copies tree, applies content edits, runs language-appropriate test command. `verify_step` does single-step verification. `run_incremental` verifies step-by-step, aborting on first failure with structured `failure_analysis` (accepts language-specific `error_patterns`).
5. Success → `save_recipe` (strategy + constraints + normalized trigram index + file paths in `recipe_files`); failure → `add_constraint` (type, description, context). All mutations wrapped in `BEGIN IMMEDIATE` transactions with BUSY retry. Plans/steps/trajectories logged in SQLite.

## Schema (trammel.db)

| Table | Key columns |
|-------|-------------|
| `recipes` | sig (PK), pattern, strategy, constraints, successes, failures, created, updated |
| `recipe_trigrams` | trigram, recipe_sig (FK) — indexed on trigram for fast candidate lookup |
| `recipe_files` | file_path, recipe_sig (FK) — indexed on both columns for structural matching (Jaccard overlap) |
| `plans` | id (PK), goal, strategy, status, current_step, total_steps, created, updated |
| `steps` | id (PK), plan_id (FK), step_index, description, rationale, depends_on, status, edits_json, verification, constraints_found |
| `constraints` | id (PK), plan_id (FK), step_id (FK), constraint_type, description, context, active |
| `trajectories` | id (PK), plan_id (FK), beam_id, strategy_variant, steps_completed, outcome, failure_reason |

## Changelog (high level)

- **2.4.0:** Two new language analyzers + scoring improvements. New `GoAnalyzer` (regex-based, reads `go.mod` for module path, resolves internal imports) and `RustAnalyzer` (regex-based, resolves `use crate::` and `mod` declarations) in `analyzers.py`; shared `_collect_symbols_regex` helper for regex-based analyzers; `_strip_js_comments` for TS comment stripping before symbol/import detection; namespace pattern added to `_TS_SYMBOL_PATTERNS`. `detect_language` expanded to count `.go`/`.rs` files; registry now supports 5 languages. `_order_bottom_up` now stable-sorts by ascending dependency count; `_order_top_down` by descending; both genuinely use `dep_graph`. New `word_substring_score(a, b)` in `utils.py`; `goal_similarity` reweighted to 0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring. `store.py` merged duplicated SQL branches, added recency weighting (30-day half-life); composite weights: text 0.4, files 0.25, success 0.15, recency 0.2; trimmed from 534 to 516 lines. `mcp_server.py` refactored with `_schema()`/`_prop()` helpers (507 → 255 lines), added "go" and "rust" to language enums. `GoAnalyzer`, `RustAnalyzer` exported from `__init__`. 146 tests (17 new: 4 Go, 3 Rust, 2 TS enhancement, 2 detection, 2 strategy, 4 matching).
- **2.3.0:** Cleanup. Extracted `_split_active_skipped` helper in `core.py` (shared by all 6 strategy functions, eliminating duplicated active/skipped split). Modernized `_VERB_SYNONYMS` in `utils.py` from imperative loop to dict comprehension (eliminates leaked module-level variables). Fixed documentation errors: corrected canonical verb form examples (was "refactor", now correctly "restructure") and `register_strategy` parameter order in glossary and spec. 129 tests (unchanged).
- **2.2.0:** Three features. (1) Improved recipe matching — `_VERB_SYNONYMS` dict (40+ verb variants → 9 canonical forms), `normalize_goal`, `word_jaccard`, `goal_similarity` (0.4 trigram cosine + 0.6 word Jaccard on normalized text) in `utils.py`; `save_recipe` normalizes before trigram indexing; `retrieve_best_recipe` uses `goal_similarity`; `_backfill_trigrams` renamed to `_rebuild_trigram_index` (rebuilds all trigrams with normalized text on init). (2) New beam strategies (6 total, 3 new) — `critical_path` (longest dependency chain first), `cohesion` (flood-fill connected components, largest first, toposort within), `minimal_change` (fewest symbols first). (3) TypeScript analyzer improvements — `_TS_SYMBOL_PATTERNS` list replacing single regex (interface, enum, const enum, type alias, abstract class, decorated class, function expression), expanded `_TS_IMPORT_RE` (re-exports, barrel exports, type re-exports, dynamic imports), `_TS_ALIAS_IMPORT_RE`, `_read_ts_path_aliases`, `_resolve_alias`, `.mts`/`.mjs` extensions. 129 tests (34 new).
- **2.1.0:** Cleanup — removed dead `json` import from `core.py`, eliminated duplicated error patterns between `utils.py` and `PythonAnalyzer` (`PythonAnalyzer.error_patterns()` now returns shared `_ERROR_PATTERNS`), removed duplicated `_pick_test_cmd` from `harness.py` (falls back to `PythonAnalyzer.pick_test_cmd`), removed `analyze_imports` backward-compat wrapper from `utils.py` (callers use `PythonAnalyzer` directly). 95 tests (1 obsolete backward-compat test removed).
- **2.0.0:** Reference LLM integration. New `SYSTEM_PROMPT.md` orchestration guide. New MCP tools: `update_plan_status`, `deactivate_constraint`. `status` tool includes `tools` count. 17 MCP tools total. 4 new tests; 96 total.
- **1.9.0:** Structural recipe matching. New `recipe_files` table (7 tables total) with indexes. `save_recipe` populates file paths. `_backfill_files()` auto-migrates. `retrieve_best_recipe` accepts `context_files` for composite scoring (text 0.5, file overlap Jaccard 0.3, success ratio 0.2). Two-phase retrieval in `Planner.decompose`. New `list_recipes` MCP tool; `get_recipe` gains `context_files`. 16 MCP tools. 9 new tests; 92 total.
- **1.8.0:** Multi-language support. New `trammel/analyzers.py`: `LanguageAnalyzer` protocol, `PythonAnalyzer`, `TypeScriptAnalyzer` (regex-based, stdlib-only), `detect_language()`, `get_analyzer()`. `Planner`/`ExecutionHarness` accept `analyzer`. `_collect_python_symbols` moved from `core.py` to `PythonAnalyzer`. `analyze_imports` wrapper in `utils.py`. `language` parameter on `plan_and_execute`/`explore`/MCP tools. `_IGNORED_DIRS` expanded. New `tests/test_analyzers.py` (13 tests). 83 total.
- **1.7.0:** Pluggable strategy registry — `register_strategy()`/`get_strategies()`/`StrategyFn`/`StrategyEntry` in `core.py`, 3 built-in strategies auto-registered, unified signature `(steps, dep_graph) -> steps`. Strategy learning — `explore_trajectories` accepts optional `store`, strategies sorted by historical success rate. `get_strategy_stats()` on `RecipeStore`. New `list_strategies` MCP tool (14 total). `register_strategy`/`get_strategies` exported from `__init__`. New `tests/test_strategies.py` (8 tests, `TestBeamStrategies` moved from `test_trammel_extra.py`). 70 tests.
- **1.6.0:** Cleanup — simplified `_collect_python_symbols` to return name strings (removed unused dict fields), removed dead `filepath` parameter from `_step_rationale`, inlined `_BEAM_STRATEGIES` descriptions (eliminated fragile index coupling), fixed duplicated line in spec-project.md. 62 tests.
- **1.5.0:** Concurrent write protection (explicit transactions with BUSY retry), inverted trigram index for recipe retrieval at scale, constraint propagation (`_apply_constraints` enforcing avoid/dependency/incompatible/requires), constraint-aware beam strategies (skip/isolate/batch), RecipeStore context manager. 6 tables. 62 tests.
- **1.4.0:** Cleanup — converted `mcp_stdio.py` from absolute to relative imports for package consistency, removed unreachable `UnicodeDecodeError` from `_collect_python_symbols` except clause (files opened with `errors="replace"`), added `.chisel` to `_IGNORED_DIRS`. 45 tests.
- **1.3.0:** Cleanup — removed unused test imports (`explore`, `synthesize`, `analyze_imports`, `cosine`, `trigram_bag_cosine`, `trigram_signature`), removed dead `goal_slice` parameter from `_collect_python_symbols`, simplified `topological_sort` by removing redundant `.setdefault()`, fixed `plan_and_execute` API signature in spec docs. 45 tests.
- **1.2.0:** `__version__` from `importlib.metadata`, `dispatch_tool` to `match/case`, configurable `test_cmd` in harness/CLI/MCP, recipe retrieval early termination, `tests/__init__.py`. 45 tests.
- **1.1.0:** Cleanup — removed dead code (`advance_plan_step`, unused imports), consolidated duplicated ignored-dirs logic via `_is_ignored_dir` helper, fixed `egg-info` pattern, modernized `topological_sort` with `deque`, simplified `Planner.decompose` set construction. 45 tests.
- **1.0.0:** Full rework — dependency-aware planning (import analysis + toposort), real beam branching (3 strategies), incremental verification, structured failure analysis, constraint propagation, enriched 5-table schema, MCP server (13 tools), 45 tests.
- **0.3.0:** Min similarity threshold, async def support, filtered os.walk, dead code removal.
- **0.2.0:** Recipe similarity fix (shared-vocabulary trigram cosine), `sys.executable`, beam edits carry `path`, `foreign_keys=ON`, `dumps_json`, `__version__`/`--version`.
