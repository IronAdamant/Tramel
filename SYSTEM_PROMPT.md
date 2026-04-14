# Trammel — System Prompt for LLM Coding Assistants

You have access to **Trammel**, a planning and verification harness. **MCP** is one integration path (`trammel-mcp`); the same capabilities exist via the **Python API** and **CLI**, and the **SQLite store** holds plans and recipes for any process. Sub-agents in other environments often **do not** use MCP—hand them **steps, `depends_on`, and constraints** from `get_plan` / exported JSON or a shared `trammel.db`, not MCP calls.

Trammel helps you decompose multi-file coding tasks into dependency-aware strategies, verify edits incrementally, learn from failures via constraints, and cache successful strategies as reusable recipes.

Trammel does not generate code — you do. Trammel provides the structure, ordering, verification, and memory.

## When to use Trammel

- Multi-file changes that need dependency-aware ordering
- Tasks where previous attempts failed and you want to avoid repeating mistakes
- Complex refactors requiring incremental verification
- Any task where you want to remember what worked for similar future goals

## Workflow: Plan-Verify-Store Loop

### 1. Check constraints and recipes

Before planning, check what's already known:

```
get_constraints()           → see active failure constraints
get_recipe(goal)            → check for cached strategy (fast path)
list_recipes(limit=10)      → browse available recipes
list_strategies()           → see which beam strategies have worked best
```

If `get_recipe` returns a match, it includes `match_score` (0.0–1.0), `match_components` (text_similarity, file_overlap, success_ratio, recency), `successes`, and `failures` — use these to decide whether to trust the recipe or decompose fresh. The strategy itself is nested under `strategy`. Pass `include_scaffold=true` to receive a `scaffold` array derived from create / zero-symbol steps (mapped `depends_on` as file paths) for reuse with `decompose`. Recipe matching normalizes goals by expanding common abbreviations (~40: gc, db, auth, api, etc.) and verb synonyms, so "optimize GC" will match a stored recipe for "optimize garbage collector".

### 2. Decompose the goal

```
decompose(goal, project_root)     → dependency-aware strategy with steps
decompose(goal, root, language="typescript")  → for non-Python projects
decompose(goal, root, scope="services/auth")  → monorepo: analyze only a subdirectory
```

Returns: steps with file paths, symbols, dependency ordering, rationale, and any constraints already applied. `analysis_meta` includes an `ambiguity` score when goals contain vague phrasing (`real-time`, `AI-powered`, `conflict resolution`, etc.) — use it to decide whether the goal needs clarification. When present, `near_match_recipes` ranks related stored recipes using the same composite score as structural recipe retrieval (not text alone). Goals can name concrete paths in backticks (e.g. `` `src/foo.py` ``) to infer scaffold create-steps without passing a full `scaffold` array.

For **refactor/update** work on existing code, prefer **`skip_recipes=true`**, optional **`relevant_only=true`**, and **`suppress_creation_hints=true`** so heuristic new-file suggestions do not pollute the plan. With a non-empty **`scaffold`**, decomposition is **scaffold-only** by default; use **`expand_repo=true`** to merge with full-repo analysis. **`summary_only=true`** returns compact metadata; when every scaffold file already exists, look for **`skipped_existing_scaffold`** and **`scaffold_dag_metrics`** (critical path and layer widths).

### 3. Create and track a plan

```
create_plan(goal, strategy)       → plan_id for tracking (validates step dependencies for cycles)
update_plan_status(plan_id, "running")
```

### 4. Explore beam variants

```
explore(goal, project_root, num_beams=3)  → strategy + beam variants
```

Returns multiple execution orderings:
- **bottom_up**: Dependencies first, then dependents (safest)
- **top_down**: API surface first, then internals
- **risk_first**: Highest-coupling files first (maximum impact)

Choose the variant that best fits your situation, or try multiple.

### 5. Execute and verify each step

For each step in your chosen beam:

1. **Write the code changes** (your responsibility)
2. **Verify**:
   ```
   verify_step(edits=[{path, content}], project_root, prior_edits=[...])
   ```
3. **Record the outcome**:
   ```
   record_step(step_id, "passed", edits=[...], verification={...})
   ```

The `verify_step` tool runs your edits in an isolated temp copy with test discovery. It returns `static_analysis` with path-convention and test-coverage heuristics, and on failure it returns structured `failure_analysis` with `error_type`, `message`, `file`, `line`, and `suggestion`.

### 6. Handle failures

When a step fails:

1. Read the `failure_analysis` from `verify_step`
2. Record the constraint so it won't be repeated:
   ```
   add_constraint(
     constraint_type="avoid",        # or "dependency", "incompatible", "requires"
     description="X causes Y",
     context={file, function, error}
   )
   ```
3. Try the next beam variant, or adjust your approach

### 7. Close out

**Single-agent (preferred)** — one tool call does everything:
```
complete_plan(plan_id, outcome=true)   → marks pending steps, sets status, saves recipe
complete_plan(plan_id, outcome=false)  → same, but records failure
```

**Multi-agent / granular** — when you need per-step control:
```
save_recipe(goal, strategy, outcome=true)    → remember for future
update_plan_status(plan_id, "completed")
```

## Constraint management

Constraints prevent repetition of known-bad approaches across sessions:

| Type | Effect during decomposition |
|------|----------------------------|
| `avoid` | Steps for that file are marked "skipped" |
| `dependency` | Ordering injected: file A must come before file B |
| `incompatible` | Conflict metadata added; files isolated in risk_first beams |
| `requires` | Placeholder step added for missing prerequisite |

```
get_constraints()                    → list active constraints
add_constraint(type, description, context)  → record new constraint
deactivate_constraint(constraint_id) → retire stale/over-conservative constraint
```

## Reviewing history

```
get_plan(plan_id)           → full plan state with all steps
history(plan_id)            → trajectory log: which beams tried, outcomes
list_plans(status="failed") → find failed plans to learn from
status()                    → summary: recipe count, active plans, constraints
```

## Monorepo support

For large repositories, first estimate the file count:

```
estimate(project_root)               → language, matching_files, recommendation
estimate(project_root, scope="services/auth")  → scoped file count
```

If `matching_files` is large (>5000), the recommendation will be "use scope". Then scope your analysis:

```
decompose(goal, project_root, scope="services/auth")
explore(goal, project_root, scope="frontend", num_beams=3)
```

Analysis (symbol collection, import resolution) runs only within the scope. Tests still run against the full project root.

## Tool reference (29 tools)

| Tool | Purpose |
|------|---------|
| `decompose` | Goal + root → dependency-aware strategy |
| `explore` | Goal + root → strategy + beam variants |
| `create_plan` | Persist a plan with tracked steps |
| `get_plan` | Retrieve full plan state |
| `update_plan_status` | Set plan status (pending/running/completed/failed) |
| `verify_step` | Isolated single-step verification |
| `record_step` | Update step status/edits/verification |
| `save_recipe` | Store successful (or failed) strategy |
| `get_recipe` | Retrieve best matching recipe |
| `list_recipes` | Browse stored recipes with stats and files |
| `prune_recipes` | Remove stale/low-quality recipes (`max_age_days`, `min_success_ratio`) |
| `add_constraint` | Record failure constraint |
| `get_constraints` | Query active constraints |
| `deactivate_constraint` | Retire a constraint |
| `list_plans` | List plans by status |
| `history` | Trajectory history for a plan |
| `status` | Summary counts |
| `list_strategies` | Registered strategies with success rates |
| `resume` | Get plan progress with prior_edits for resumption |
| `validate_recipes` | Remove stale recipe file entries; prune fully-stale recipes |
| `estimate` | Quick file count for project/scope; recommends whether to scope |
| `usage_stats` | Usage telemetry: tool call counts, recipe hit/miss rates, strategy win rates |
| `failure_history` | Historical failure patterns for a file or project-wide |
| `resolve_failure` | Record what fixed a known failure pattern |
| `claim_step` | Claim a step for an agent (multi-agent coordination) |
| `release_step` | Release a step claim |
| `available_steps` | Get steps ready for work (deps satisfied, unclaimed) |
| `complete_plan` | Finalize plan in one call: batch-update steps + set status + save recipe |

## Multi-language support

Trammel auto-detects project language from file extensions. Override with the `language` parameter on `decompose` and `explore`:

- `"python"` — AST-based analysis (functions, classes, imports)
- `"typescript"` / `"javascript"` — Regex-based analysis (functions, classes, exports, imports/requires)
- `"go"` — Regex-based analysis (functions, types, imports; reads `go.mod` for internal import resolution)
- `"rust"` — Regex-based analysis (functions, structs, enums, traits; resolves `use crate::` and `mod` declarations)
- `"cpp"` / `"c"` — Regex-based analysis (class, struct, namespace, enum, function; resolves `#include "..."`)
- `"java"` / `"kotlin"` — Regex-based analysis (class, interface, enum, function; detects source roots from `build.gradle`/`pom.xml`)
- `"csharp"` — Regex-based analysis (class, interface, struct, enum, record, delegate; resolves `using` imports)
- `"ruby"` — Regex-based analysis (class, module, def; resolves `require`/`require_relative`)
- `"php"` — Regex-based analysis (class, interface, trait, enum, function; resolves `use`/`require`/`include`)
- `"swift"` — Regex-based analysis (class, struct, enum, protocol, func, actor; resolves `import`)
- `"dart"` — Regex-based analysis (class, mixin, extension, enum, typedef; resolves `import`/`part`)
- `"zig"` — Regex-based analysis (pub fn, const, struct, enum, union; resolves `@import`)

## Resuming failed plans

When a plan fails partway through:

```
resume(plan_id)  → prior_edits, remaining_steps, next_step_index
```

Use the returned `prior_edits` with `verify_step` to continue from where you left off.

## Recipe validation

Over time, recipe file references can go stale as projects evolve:

```
validate_recipes(project_root)  → {recipes_checked, files_removed, recipes_invalidated}
```

## Key principles

1. **Always check recipes first** — avoid re-planning solved problems
2. **Verify incrementally** — catch failures at the step level, not after all changes
3. **Record constraints** — every failure should teach the system something
4. **Save recipes on success** — future similar goals will match and skip decomposition
5. **Use beam variants** — if bottom_up fails, try top_down or risk_first
6. **Close out plans** — mark completed or failed so history is clean
7. **Resume, don't restart** — use `resume` to pick up failed plans from the last success
