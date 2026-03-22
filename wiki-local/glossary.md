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
| **trammel.db** | Default SQLite path for recipes, plans, steps, constraints, trajectories, and recipe_trigrams (override with `db_path`/`--db`). |
| **MCP server** | Trammel exposed as 13 tools via Model Context Protocol stdio transport. Works standalone; cooperates with Stele and Chisel when co-installed. |
