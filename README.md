# Trammel

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Pure-Python, **stdlib-only** planning and execution harness for LLM-assisted coding. Decomposes goals into dependency-aware strategies, explores bounded parallel beams with genuinely different orderings, runs incremental per-step verification in isolated temp copies, propagates failure constraints, and persists successful strategies as reusable recipes in a local SQLite database (`trammel.db`).

Trammel is a tool **for** LLMs, not a tool that calls LLMs. It provides the planning discipline, verification scaffolding, and failure memory that coding assistants need to tackle multi-step tasks reliably.

## Installation

```bash
pip install trammel            # core (stdlib only)
pip install trammel[mcp]       # with MCP server support
```

Or install from source:

```bash
git clone https://github.com/IronAdamant/Trammel.git
cd Tramel
pip install -e .               # editable install
pip install -e '.[mcp]'        # with MCP support
```

## Quickstart

Run the test suite:

```bash
python -m unittest discover -q -s tests -p 'test_*.py'
```

Use from Python:

```python
from trammel import plan_and_execute, explore, synthesize, __version__

# Full pipeline: decompose → plan → explore beams → verify → store recipe
result = plan_and_execute("your goal", "/path/to/project", num_beams=3)

# Explore only (no verification): decompose + beam variants
strategy = explore("refactor auth", "/path/to/project")

# Store a caller-verified strategy as a recipe
synthesize("refactor auth", verified_strategy)
```

Use from the CLI:

```bash
python -m trammel --version
python -m trammel "refactor X to Y" --root /path/to/project --beams 3 --db ./trammel.db
python -m trammel "fix tests" --test-cmd pytest -x -q
echo '{"goal":"fix tests"}' | python -m trammel
```

## MCP Server

Trammel exposes its capabilities as an [MCP](https://modelcontextprotocol.io/) server for integration with Claude Code, Cursor, and other MCP-aware clients.

```bash
pip install trammel[mcp]   # or: pip install mcp
trammel-mcp                # starts stdio MCP server
```

See `SYSTEM_PROMPT.md` for a reference orchestration guide that LLM clients can use to drive the plan-verify-store loop.

Configure in `.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "trammel": {
      "command": "trammel-mcp",
      "args": []
    }
  }
}
```

**MCP tools (17):** `decompose`, `explore`, `create_plan`, `get_plan`, `verify_step`, `record_step`, `save_recipe`, `get_recipe`, `add_constraint`, `get_constraints`, `list_plans`, `history`, `status`, `list_strategies`, `list_recipes`, `update_plan_status`, `deactivate_constraint`

## Architecture

Trammel treats planning as a structured search problem:

1. **Decompose** -- Analyze project imports (Python AST; TypeScript, Go, Rust regex), build dependency graph, topological sort, generate steps with ordering rationale
2. **Explore** -- Generate beam variants with genuinely different strategies (`bottom_up`, `top_down`, `risk_first`, `critical_path`, `cohesion`, `minimal_change`)
3. **Verify** -- Run edits in isolated temp copies, per-step or full-run; extract structured failure analysis on failure
4. **Constrain** -- Propagate failure reasons as persistent constraints that block repetition across sessions
5. **Remember** -- Store successful strategies as recipes, retrieved by composite scoring (text similarity + file overlap + success ratio)

## Project Layout

```
trammel/              Importable package
  __init__.py         plan_and_execute, explore, synthesize, __version__
  analyzers.py        LanguageAnalyzer protocol, PythonAnalyzer, TypeScriptAnalyzer, GoAnalyzer, RustAnalyzer, detect_language
  core.py             Planner: import analysis, toposort, beam strategies
  harness.py          ExecutionHarness: temp copy, edits, test runner
  store.py            RecipeStore: SQLite persistence (7 tables)
  utils.py            Trigrams, cosine, failure extraction, goal normalization, goal similarity
  cli.py              Argparse CLI entry point
  mcp_server.py       MCP tool schemas and dispatch (17 tools)
  mcp_stdio.py        MCP stdio server entry point
tests/                stdlib unittest (146 tests, 4 modules)
wiki-local/           Spec, glossary, and wiki index
SYSTEM_PROMPT.md      Reference orchestration guide for LLM clients
pyproject.toml        Package metadata
```

## SQLite Schema (`trammel.db`)

| Table | Purpose |
|-------|---------|
| `recipes` | Successful strategies keyed by SHA-256, with pattern, constraints, success/failure counts |
| `recipe_trigrams` | Inverted trigram index for fast recipe retrieval (trigram → recipe sig) |
| `recipe_files` | File paths associated with recipe steps, for structural matching (Jaccard overlap) |
| `plans` | Goal + strategy snapshot with step progress tracking |
| `steps` | Individual work units with dependencies, rationale, verification results |
| `constraints` | Failure records (dependency/incompatible/requires/avoid) that prevent known-bad repetition |
| `trajectories` | Harness run logs per beam: outcome, steps completed, failure reason |

## Integration with Stele and Chisel

Trammel works standalone. When co-installed with [Stele](https://github.com/IronAdamant/stele-context) (context retrieval) and [Chisel](https://github.com/IronAdamant/Chisel) (code analysis), all three MCP servers cooperate through the LLM's tool layer -- no cross-dependencies.

| Tool | Role |
|------|------|
| **Stele** | Persistent context retrieval and semantic indexing |
| **Chisel** | Code analysis, churn, coupling, risk mapping |
| **Trammel** | Planning discipline, verification, failure learning, recipe memory |

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes (core must remain stdlib-only; tests use `unittest` only)
4. Run the test suite: `python -m unittest discover -q -s tests -p 'test_*.py'`
5. Commit and push your branch
6. Open a pull request

## Changelog

### 2.5.0

- **Code cleanup**: Removed unused `import sys` from `harness.py`. Eliminated duplicate `set(symbols) | set(dep_graph)` computation in `Planner.decompose` (`core.py`). Added defensive `json.loads` error handling in `retrieve_best_recipe` (`store.py`). Made failure default explicit in `get_strategy_stats` (`store.py`). Fixed `register_strategy` parameter order in `spec-project.md` documentation.
- **146 tests** (unchanged).

### 2.4.0

- **Go and Rust support**: New `GoAnalyzer` (regex-based, reads `go.mod` for module path, resolves internal imports) and `RustAnalyzer` (regex-based, resolves `use crate::` and `mod` declarations). Shared `_collect_symbols_regex` helper for regex-based analyzers. `detect_language` expanded to count `.go`/`.rs` files. Registry now supports 5 languages.
- **TypeScript enhancements**: `_strip_js_comments` for comment stripping before symbol/import detection. Namespace pattern added to `_TS_SYMBOL_PATTERNS`.
- **Improved beam strategies**: `_order_bottom_up` stable-sorts by ascending dependency count (files with fewer deps first). `_order_top_down` stable-sorts by descending dependency count (most consumer-facing files first). Both now genuinely use the `dep_graph` parameter.
- **Better recipe matching**: New `word_substring_score(a, b)` for partial word matching. `goal_similarity` reweighted: 0.3 trigram cosine + 0.4 word Jaccard + 0.3 substring (was 0.4/0.6).
- **Store improvements**: Merged duplicated SQL branches in `save_recipe`, `list_plans`, `get_active_constraints`. Composite scoring gains recency weighting (30-day half-life). New weights: text 0.4, files 0.25, success 0.15, recency 0.2. File trimmed from 534 to 516 lines.
- **MCP server refactor**: `_schema()` and `_prop()` helpers reduce from 507 to 255 lines. Added "go" and "rust" to language enums.
- **146 tests** (17 new: 4 Go, 3 Rust, 2 TS enhancement, 2 detection, 2 strategy, 4 matching).

### 2.3.0

- **Code cleanup**: Extracted `_split_active_skipped` helper in `core.py`, shared by all 6 beam strategy functions (eliminates duplicated active/skipped split pattern). Modernized `_VERB_SYNONYMS` in `utils.py` from imperative loop to dict comprehension (eliminates leaked module-level variables `_canonical`, `_variants`, `_v`).
- **Documentation fixes**: Corrected canonical verb form examples in glossary and spec (was "refactor", now correctly "restructure"). Fixed `register_strategy` parameter order in glossary (`(name, description, fn)` not `(name, fn, description)`).
- **129 tests** (unchanged).

### 2.2.0

- **Improved recipe matching**: New `_VERB_SYNONYMS` (40+ verb variants to 9 canonical forms), `normalize_goal`, `word_jaccard`, and `goal_similarity` (0.4 trigram cosine + 0.6 word Jaccard on normalized text) in `utils.py`. `save_recipe` normalizes before trigram indexing. `retrieve_best_recipe` uses `goal_similarity`. `_backfill_trigrams` renamed to `_rebuild_trigram_index` (rebuilds with normalized text on init).
- **New beam strategies** (6 total, 3 new): `critical_path` (longest dependency chain first — bottleneck feedback), `cohesion` (flood-fill connected components, largest first, toposort within), `minimal_change` (fewest symbols first — quick wins).
- **TypeScript analyzer improvements**: `_TS_SYMBOL_PATTERNS` list replacing single regex (interface, enum, const enum, type alias, abstract class, decorated class, function expression). Expanded import detection (re-exports, barrel exports, type re-exports, dynamic imports). New `_TS_ALIAS_IMPORT_RE`, `_read_ts_path_aliases`, `_resolve_alias`. Added `.mts`/`.mjs` extensions.
- **129 tests** (34 new: 10 recipe matching, 9 strategy, 15 TypeScript).

### 2.1.0

- **Code cleanup**: Removed dead `json` import from `core.py`. Eliminated duplicated error patterns between `utils.py` and `PythonAnalyzer`. Removed duplicated `_pick_test_cmd` from `harness.py` (falls back to `PythonAnalyzer`). Removed `analyze_imports` backward-compat wrapper from `utils.py`.
- **95 tests** (1 obsolete backward-compat test removed).

### 2.0.0

- **Reference LLM integration**: New `SYSTEM_PROMPT.md` providing a reference orchestration guide for LLM clients (plan-verify-store loop).
- **New MCP tools**: `update_plan_status` (exposes existing store method), `deactivate_constraint` (exposes existing store method). `status` tool now includes `tools` count in response. Tool count 16 → 17.
- **96 tests** (4 new).

### 1.9.0

- **Structural recipe matching**: New `recipe_files` table in SQLite schema (7 tables total) with indexes on both columns. `save_recipe` populates `recipe_files` with file paths from strategy steps. `_backfill_files()` auto-migrates existing databases.
- **Composite scoring**: `retrieve_best_recipe` accepts optional `context_files` for composite scoring — text similarity (0.5), file overlap via Jaccard (0.3), success ratio (0.2). Without `context_files`, scoring is backward-compatible (text-only).
- **Planner integration**: `Planner.decompose` passes project file context to recipe retrieval (two-phase: text-only fast path, then structural).
- **New MCP tools**: `list_recipes` (limit=20), `get_recipe` gains `context_files` parameter. Tool count 14 → 16.
- **92 tests** (9 new recipe tests).

### 1.8.0

- **Multi-language support**: New `trammel/analyzers.py` with `LanguageAnalyzer` protocol, `PythonAnalyzer`, `TypeScriptAnalyzer` (regex-based, stdlib-only), `detect_language()`, `get_analyzer()`.
- **Planner integration**: `Planner` accepts optional `analyzer` parameter, auto-detects language. `ExecutionHarness` accepts optional `analyzer` for language-specific test commands and error patterns.
- **Refactored analysis**: `_collect_python_symbols` removed from `core.py` (moved to `PythonAnalyzer`). `analyze_imports` in `utils.py` now a backward-compat wrapper delegating to `PythonAnalyzer`. `ast` import removed from `utils.py`.
- **`analyze_failure`** accepts optional `error_patterns` parameter.
- **`_IGNORED_DIRS` expanded**: `.next`, `.nuxt`, `coverage`, `.turbo`, `.parcel-cache`.
- **`language` parameter** added to `plan_and_execute`, `explore`, and MCP `decompose`/`explore` tools.
- **New exports**: `PythonAnalyzer`, `TypeScriptAnalyzer`, `detect_language` from `trammel.__init__`.
- **83 tests** (13 new in `tests/test_analyzers.py`).

### 1.7.0

- **Pluggable strategy registry**: New `register_strategy()` and `get_strategies()` API in `core.py` with `StrategyFn` and `StrategyEntry` types. Three built-in strategies (`bottom_up`, `top_down`, `risk_first`) auto-registered at module load. Strategy functions use unified signature `(steps, dep_graph) -> steps`.
- **Strategy learning**: `explore_trajectories` accepts optional `store` for learning feedback. When provided, strategies sorted by historical success rate from trajectory data. `plan_and_execute` and `explore` pass store to enable learning.
- **Strategy stats**: `RecipeStore.get_strategy_stats()` aggregates trajectory outcomes by variant (success/failure counts per strategy).
- **New MCP tool**: `list_strategies` returns registered strategy names with success/failure stats. Tool count 13 → 14.
- **New exports**: `register_strategy` and `get_strategies` exported from `trammel.__init__`.
- **Test reorganization**: New `tests/test_strategies.py` with 8 strategy-focused tests. `TestBeamStrategies` moved from `test_trammel_extra.py`. Test count 62 → 70.

### 1.6.0

- **Simplified symbol collection**: `_collect_python_symbols` returns symbol name strings instead of redundant dicts; unused `file`, `type`, `line` fields removed (only `name` was consumed downstream).
- **Removed dead parameter**: `_step_rationale` no longer accepts unused `filepath` argument.
- **Inlined beam descriptions**: Removed `_BEAM_STRATEGIES` module-level constant; descriptions inlined at usage site, eliminating fragile index-based coupling.
- **Documentation fix**: Removed duplicated extension point line in `spec-project.md`.

### 1.5.0

- **Concurrent write protection**: All mutating `RecipeStore` methods wrapped in explicit `BEGIN IMMEDIATE` transactions with exponential backoff retry on `SQLITE_BUSY`. Multi-statement operations like `create_plan` are now atomic. `db_connect` sets `timeout=5.0`.
- **Recipe retrieval at scale**: Inverted trigram index (`recipe_trigrams` table with B-tree index). `retrieve_best_recipe` now queries candidate recipes by shared trigrams before computing exact cosine, avoiding full table scans. Existing databases auto-backfill on schema init.
- **Constraint propagation**: New `_apply_constraints` enforces active constraints during decomposition — `avoid` skips files, `dependency` injects ordering, `incompatible` marks conflict metadata, `requires` adds prerequisite steps. Strategy output now includes `constraints_applied`.
- **Constraint-aware beam strategies**: `_order_bottom_up` and `_order_top_down` place skipped steps at end. `_order_risk_first` isolates incompatible steps and batches by package directory. `explore_trajectories` excludes skipped steps from beam edits.
- **RecipeStore context manager**: Added `close()`, `__enter__`/`__exit__`, and `__del__` safety net. All public API functions and MCP server use `with RecipeStore(...)`.

### 1.4.0

- **Import consistency**: Converted absolute imports in `mcp_stdio.py` to relative imports, matching the rest of the package.
- **Dead exception handling**: Removed unreachable `UnicodeDecodeError` from `_collect_python_symbols` except clause (`core.py`). Files are opened with `errors="replace"`, so the exception can never be raised.
- **Ignored directories**: Added `.chisel` to `_IGNORED_DIRS` in `utils.py` (tool cache directory, same category as `.mypy_cache`, `.ruff_cache`).

### 1.3.0

- **Dead code removal**: Removed unused test imports (`explore`, `synthesize`, `analyze_imports`, `cosine`, `trigram_bag_cosine`, `trigram_signature`). Removed dead `goal_slice` parameter from `_collect_python_symbols` — computed per symbol but never consumed downstream.
- **Simplified topological sort**: Removed redundant `rev.setdefault()` call where keys are guaranteed to exist from pre-initialization.
- **Documentation fix**: `plan_and_execute` API signature in spec now includes `test_cmd` parameter.

### 1.2.0

- **Version from metadata**: `__version__` now derived from `importlib.metadata` at runtime, eliminating version duplication between `pyproject.toml` and source code.
- **Match/case dispatch**: `dispatch_tool` in `mcp_server.py` converted from 13-branch if/elif chain to Python 3.10+ `match/case`.
- **Configurable test command**: `ExecutionHarness` accepts `test_cmd` parameter for custom test runners (e.g. pytest). Propagated through `plan_and_execute`, CLI (`--test-cmd`), and MCP `verify_step` tool.
- **Recipe retrieval optimization**: `retrieve_best_recipe` short-circuits on exact match (similarity 1.0).
- **Tests package**: Added `tests/__init__.py`.

### 1.1.0

- **Dead code removal**: Removed unused `advance_plan_step` method from `RecipeStore`, unused `json`/`os` imports from `mcp_server.py`, unused `json` import from tests.
- **Consolidated ignored-dirs**: Unified hardcoded directory skip list in `harness.py` with `_IGNORED_DIRS` from `utils.py` via new `_is_ignored_dir` helper. Fixed `egg-info` pattern that could never match actual `*.egg-info` directories.
- **Performance**: `topological_sort` uses `collections.deque` instead of `list.pop(0)` for O(1) queue operations.
- **Simplified core**: Replaced verbose loop in `Planner.decompose` with set union for `all_files` construction.

### 1.0.0

- **Dependency-aware planning**: Import analysis via AST, topological sort, steps with ordering rationale and dependencies.
- **Real beam branching**: Three strategies -- `bottom_up`, `top_down`, `risk_first` -- instead of label variations.
- **Incremental verification**: Per-step harness with `verify_step()` and `run_incremental()`.
- **Failure analysis**: Structured error extraction (type, message, file, line, suggestion).
- **Constraint propagation**: Persistent failure constraints that block repetition across sessions.
- **MCP server**: 13 tools exposed via stdio transport, matching Stele/Chisel pattern (expanded to 17 by v2.0.0).
- **Enriched schema**: Recipes store strategies + constraints + failure counts. Plans track step-level status. New `steps` and `constraints` tables.

### 0.3.0

- Recipe retrieval requires minimum similarity threshold (0.3).
- `_collect_python_symbols` collects `async def` and skips ignored directories.
- Deduplicated trigram computation; removed dead code.

### 0.2.0

- Correct trigram similarity for recipe retrieval; tie-break on stored success counts.
- Test subprocess uses `sys.executable`; SQLite `foreign_keys=ON`.
- Beam `edits` include `path`; JSON serialization centralized via `dumps_json`.
- `__version__` and CLI `--version`.

## License

[MIT](LICENSE)
