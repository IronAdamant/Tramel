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
git clone https://github.com/IronAdamant/Tramel.git
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

**MCP tools (13):** `decompose`, `explore`, `create_plan`, `get_plan`, `verify_step`, `record_step`, `save_recipe`, `get_recipe`, `add_constraint`, `get_constraints`, `list_plans`, `history`, `status`

## Architecture

Trammel treats planning as a structured search problem:

1. **Decompose** -- Analyze project imports via AST, build dependency graph, topological sort, generate steps with ordering rationale
2. **Explore** -- Generate beam variants with genuinely different strategies (`bottom_up`, `top_down`, `risk_first`)
3. **Verify** -- Run edits in isolated temp copies, per-step or full-run; extract structured failure analysis on failure
4. **Constrain** -- Propagate failure reasons as persistent constraints that block repetition across sessions
5. **Remember** -- Store successful strategies as recipes, retrieved by trigram cosine similarity (min threshold 0.3)

## Project Layout

```
trammel/              Importable package
  __init__.py         plan_and_execute, explore, synthesize, __version__
  core.py             Planner: import analysis, toposort, beam strategies
  harness.py          ExecutionHarness: temp copy, edits, test runner
  store.py            RecipeStore: SQLite persistence (5 tables)
  utils.py            Trigrams, cosine, AST analysis, failure extraction
  cli.py              Argparse CLI entry point
  mcp_server.py       MCP tool schemas and dispatch
  mcp_stdio.py        MCP stdio server entry point
tests/                stdlib unittest (45 tests)
wiki-local/           Spec, glossary, and wiki index
pyproject.toml        Package metadata
```

## SQLite Schema (`trammel.db`)

| Table | Purpose |
|-------|---------|
| `recipes` | Successful strategies keyed by SHA-256, with pattern, constraints, success/failure counts |
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
- **MCP server**: 13 tools exposed via stdio transport, matching Stele/Chisel pattern.
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
