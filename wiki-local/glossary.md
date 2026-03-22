# Trammel glossary

| Term | Definition |
|------|------------|
| **Beam** | One variant in a bounded set of exploration branches. Each beam applies the same steps in a different order using a named strategy (bottom_up, top_down, risk_first, critical_path, cohesion, minimal_change). |
| **Strategy** | JSON-serializable plan: `steps` (ordered work units with dependencies), `dependency_graph`, `constraints`, `goal_fingerprint`. May come from import analysis or from a stored recipe. |
| **Step** | Atomic work unit within a strategy: `{file, symbols, description, rationale, depends_on}`. Steps are ordered by dependency graph and executed/verified individually or in sequence. |
| **Dependency graph** | Map of file → [files it imports from], built by AST analysis of `Import`/`ImportFrom` statements. Used for topological ordering of steps. |
| **Harness** | `ExecutionHarness`: temp copy of the project, optional file writes from edits, subprocess test run. Supports full run, single-step verification, and incremental verification. |
| **Edit** | Dict consumed by the harness: `path` or `file` plus `content` to write; may also carry `step_index` and `task` for planner metadata. Without `content`, no file is changed. |
| **Recipe** | Successful strategy associated with a goal pattern; stored by SHA-256 of canonical JSON (`sig`). Tracks `successes` and `failures` counts for quality signal. |
| **Pattern** | Truncated goal string stored next to a recipe for retrieval similarity (not the full strategy). |
| **Plan** | Row in `plans`: goal, strategy snapshot, status (`pending`/`running`/`completed`/`failed`), step progress tracking. |
| **Constraint** | Persistent failure record: type (`dependency`/`incompatible`/`requires`/`avoid`), description, context. Active constraints are loaded during decomposition to prevent repeating known-bad approaches. |
| **Trajectory** | One harness run for a beam: plan_id, beam_id, strategy_variant, steps_completed, outcome, failure_reason. |
| **Failure analysis** | Structured extraction from test output: error_type, message, file, line, suggestion. Used to create constraints. |
| **Trigram bag cosine** | Similarity between two strings built from overlapping 3-character windows; counts are aligned on the union of trigram types before cosine. Used as one component of `goal_similarity`. Minimum threshold 0.3. |
| **Incremental verification** | Per-step harness runs where each step is verified in isolation (with prior edits applied). Stops at first failure with structured analysis. |
| **Bottom-up** | Beam strategy: modify dependencies first, then dependents. Safest ordering. |
| **Top-down** | Beam strategy: modify API surface and entry points first, then internals. |
| **Risk-first** | Beam strategy: modify most-imported (highest coupling) files first. |
| **Critical-path** | Beam strategy: longest dependency chain first. Recursive depth computation identifies bottleneck files; feedback prioritizes them. |
| **Cohesion** | Beam strategy: flood-fill connected components in the dependency graph, process tightly coupled groups contiguously (largest component first), topological sort within each component. |
| **Minimal-change** | Beam strategy: fewest symbols first. Quick wins that catch trivial failures early. |
| **Goal normalization** | Preprocessing step for recipe matching: lowercase + verb synonym replacement via `_VERB_SYNONYMS` (40+ verb variants mapped to 9 canonical forms). Applied before trigram indexing and similarity scoring. |
| **Goal similarity** | Blended similarity function: 0.3 trigram cosine + 0.4 word Jaccard + 0.3 word substring on normalized text. Used by `retrieve_best_recipe` for scoring and replaces raw `trigram_bag_cosine` for recipe matching. |
| **Word Jaccard** | Word-level Jaccard similarity: `|intersection| / |union|` on the word sets of two strings. Used as a component (0.4 weight) in `goal_similarity`. |
| **Verb synonyms** | `_VERB_SYNONYMS` dict in `utils.py` mapping 40+ verb variants to 9 canonical forms (e.g., refactor/rewrite/reorganize all map to "restructure"). Enables recipe matching across paraphrased goals. |
| **Path aliases** | TypeScript `compilerOptions.paths` + `baseUrl` from `tsconfig.json`. Read by `_read_ts_path_aliases(root)` and resolved by `_resolve_alias()` in `TypeScriptAnalyzer` for non-relative alias imports. |
| **Inverted trigram index** | The `recipe_trigrams` table mapping individual trigrams to recipe signatures. Enables sub-linear recipe retrieval by narrowing candidates before exact cosine computation. |
| **Transaction** | Explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` block with exponential backoff retry on `SQLITE_BUSY`. Ensures atomicity for multi-statement mutations and agent isolation. |
| **Constraint enforcement** | `_apply_constraints` in `core.py` that acts on active constraints: `avoid` skips steps, `dependency` injects ordering, `incompatible` marks conflict metadata, `requires` adds prerequisite steps. |
| **trammel.db** | Default SQLite path for recipes, recipe_trigrams, recipe_files, plans, steps, constraints, and trajectories — 7 tables (override with `db_path`/`--db`). |
| **Strategy registry** | Pluggable registry in `core.py` for beam strategies. `register_strategy(name, description, fn)` adds new strategies; `get_strategies()` returns all registered `StrategyEntry` items. Six built-in strategies auto-registered at module load. Strategy functions use unified signature `(steps, dep_graph) -> steps`. |
| **Strategy learning** | When `explore_trajectories` receives an optional `store`, it calls `get_strategy_stats()` to aggregate trajectory outcomes by strategy variant, then sorts strategies by historical success rate. Strategies that have succeeded more often are tried first. |
| **Language analyzer** | Implementation of the `LanguageAnalyzer` protocol in `analyzers.py`. Provides `collect_symbols`, `analyze_imports`, `test_command`, and `error_patterns` for a specific language. Built-in: `PythonAnalyzer` (AST-based), `TypeScriptAnalyzer` (regex-based, stdlib-only), `GoAnalyzer` (regex-based, reads `go.mod`), `RustAnalyzer` (regex-based, `use crate::`/`mod`). `detect_language()` auto-selects by file extension prevalence (counts `.py`, `.ts`/`.tsx`/`.js`/`.jsx`, `.go`, `.rs`). |
| **Composite scoring** | Recipe retrieval scoring when `context_files` are provided. Weighted combination with recency: text similarity (0.4) + file overlap via Jaccard index (0.25) + success ratio (0.15) + recency (0.2, 30-day half-life). Without `context_files`, falls back to text-only scoring for backward compatibility. |
| **Recipe files** | The `recipe_files` table mapping file paths to recipe signatures. Populated on `save_recipe` from strategy step file paths. Enables structural matching via Jaccard overlap during recipe retrieval. Auto-backfilled via `_backfill_files()` for existing databases. |
| **System prompt** | `SYSTEM_PROMPT.md` — a reference orchestration guide for LLM clients describing the plan-verify-store loop. Shows how an LLM should use Trammel's MCP tools to decompose goals, verify steps, store recipes, and propagate constraints. |
| **Rebuild trigram index** | `_rebuild_trigram_index` in `store.py` (renamed from `_backfill_trigrams`). Rebuilds all trigrams with normalized text on init, ensuring the inverted index reflects current normalization rules. |
| **GoAnalyzer** | Regex-based `LanguageAnalyzer` for Go projects. Reads `go.mod` for the module path. Resolves internal imports (imports matching the module path) to project-relative file paths. Uses shared `_collect_symbols_regex` helper for symbol collection. |
| **RustAnalyzer** | Regex-based `LanguageAnalyzer` for Rust projects. Resolves `use crate::` imports and `mod` declarations to project-relative file paths. Uses shared `_collect_symbols_regex` helper for symbol collection. |
| **Word substring score** | `word_substring_score(a, b)` in `utils.py`. Partial word matching function that checks for substring overlap between the word sets of two strings. Rewards partial matches that pure Jaccard misses. Used as a component (0.3 weight) in `goal_similarity`. |
| **Recency weighting** | Time-based decay factor in composite recipe scoring. Uses a 30-day half-life: recently updated recipes score higher than stale ones. Weight 0.2 in composite scoring (text 0.4, files 0.25, success 0.15, recency 0.2). |
| **Comment stripping** | `_strip_js_comments` in `analyzers.py`. Removes single-line (`//`) and multi-line (`/* */`) comments from TypeScript/JavaScript source before symbol and import detection, preventing false matches in commented-out code. |
| **MCP server** | Trammel exposed as 17 tools via Model Context Protocol stdio transport. Works standalone; cooperates with Stele and Chisel when co-installed. |
