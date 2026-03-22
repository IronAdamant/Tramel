# Trammel glossary

| Term | Definition |
|------|------------|
| **Beam** | One variant in a bounded set of exploration branches. Each beam applies the same steps in a different order using a named strategy (bottom_up, top_down, risk_first). |
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
| **Trigram bag cosine** | Similarity between two strings built from overlapping 3-character windows; counts are aligned on the union of trigram types before cosine. Minimum threshold 0.3. |
| **Incremental verification** | Per-step harness runs where each step is verified in isolation (with prior edits applied). Stops at first failure with structured analysis. |
| **Bottom-up** | Beam strategy: modify dependencies first, then dependents. Safest ordering. |
| **Top-down** | Beam strategy: modify API surface and entry points first, then internals. |
| **Risk-first** | Beam strategy: modify most-imported (highest coupling) files first. |
| **Inverted trigram index** | The `recipe_trigrams` table mapping individual trigrams to recipe signatures. Enables sub-linear recipe retrieval by narrowing candidates before exact cosine computation. |
| **Transaction** | Explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` block with exponential backoff retry on `SQLITE_BUSY`. Ensures atomicity for multi-statement mutations and agent isolation. |
| **Constraint enforcement** | `_apply_constraints` in `core.py` that acts on active constraints: `avoid` skips steps, `dependency` injects ordering, `incompatible` marks conflict metadata, `requires` adds prerequisite steps. |
| **trammel.db** | Default SQLite path for recipes, recipe_trigrams, recipe_files, plans, steps, constraints, and trajectories — 7 tables (override with `db_path`/`--db`). |
| **Strategy registry** | Pluggable registry in `core.py` for beam strategies. `register_strategy(name, fn, description)` adds new strategies; `get_strategies()` returns all registered `StrategyEntry` items. Three built-in strategies auto-registered at module load. Strategy functions use unified signature `(steps, dep_graph) -> steps`. |
| **Strategy learning** | When `explore_trajectories` receives an optional `store`, it calls `get_strategy_stats()` to aggregate trajectory outcomes by strategy variant, then sorts strategies by historical success rate. Strategies that have succeeded more often are tried first. |
| **Language analyzer** | Implementation of the `LanguageAnalyzer` protocol in `analyzers.py`. Provides `collect_symbols`, `analyze_imports`, `test_command`, and `error_patterns` for a specific language. Built-in: `PythonAnalyzer` (AST-based) and `TypeScriptAnalyzer` (regex-based, stdlib-only). `detect_language()` auto-selects by file extension prevalence. |
| **Composite scoring** | Recipe retrieval scoring when `context_files` are provided. Weighted combination: text similarity (0.5) + file overlap via Jaccard index (0.3) + success ratio (0.2). Without `context_files`, falls back to text-only scoring for backward compatibility. |
| **Recipe files** | The `recipe_files` table mapping file paths to recipe signatures. Populated on `save_recipe` from strategy step file paths. Enables structural matching via Jaccard overlap during recipe retrieval. Auto-backfilled via `_backfill_files()` for existing databases. |
| **System prompt** | `SYSTEM_PROMPT.md` — a reference orchestration guide for LLM clients describing the plan-verify-store loop. Shows how an LLM should use Trammel's MCP tools to decompose goals, verify steps, store recipes, and propagate constraints. |
| **MCP server** | Trammel exposed as 17 tools via Model Context Protocol stdio transport. Works standalone; cooperates with Stele and Chisel when co-installed. |
