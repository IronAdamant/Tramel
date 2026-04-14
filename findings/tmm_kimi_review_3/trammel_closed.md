# trammel MCP Detailed Report — Phase 14

## Executive Summary

trammel was challenged through the construction of `SelfAdaptiveRecipePipeline` — a recipe transformation pipeline that decomposes complex goals into steps, executes them adaptively with retry, validates each step, and caches successful patterns. trammel's `decompose`, `explore`, `get_recipe`, and plan management tools were used to plan the feature and to evaluate trammel's ability to handle complex, multi-step JavaScript development goals.

## Feature Built: SelfAdaptiveRecipePipeline

**Location:** `src/services/challengeFeatures/SelfAdaptiveRecipePipeline.js` (663 lines)  
**Tests:** `tests/challenge/SelfAdaptiveRecipePipeline.test.js` (18 tests, all passing)

The pipeline takes goals like "make this recipe vegan, reduce cost by 20%, and ensure it cooks in under 30 minutes" and decomposes them into steps: `ingredient_substitution`, `portion_adjustment`, `time_optimization`, `cost_optimization`, and `dietary_validation`. Each step has real transformation logic, validation, and adaptive retry with alternative strategies. Successful patterns are cached to disk.

## MCP Tools Used & Observations

### 1. `decompose` on Recipe Pipeline Goal — Over-Constrained Failure

**Invocation:** Decomposed the goal "Build a self-adaptive recipe transformation pipeline..." with `relevant_only: true`, `max_steps: 15`.  
**Result:** `{"error": "over_constrained", "total_steps": 0}`

**Finding:** trammel's dependency analyzer determined that the existing project scaffold is **over-constrained**. Specifically, it flagged these files as having too many dependencies:
- `tests/services/recipeQL.test.js` → depends on 5 recipeQL modules
- `tests/services/recipeDSL.test.js` → depends on 6 DSL modules
- `src/services/parallelEnrichment/EnrichmentCoordinator.js` → depends on 5 enrichers
- `tests/services/parallelEnrichment.test.js` → depends on 6 enrichment modules
- `tests/services/eventSourcing.test.js` → depends on 6 event sourcing modules
- `tests/services/recipeOptPipeline.test.js` → depends on 6 pipeline modules

**Analysis:** The "over_constrained" error occurs when trammel's scaffold validator detects that too many files have fan-out counts exceeding internal thresholds. In this project, test files naturally depend on many source modules, and coordinator files depend on many workers. trammel treats this as an error condition rather than a normal pattern for test suites and facades.

**Implication:** For projects with comprehensive test coverage or service facades, `decompose` may fail unless `strict_greenfield: false` and `suppress_creation_hints: true` are used aggressively. The agent had to fall back to `explore` and manual planning.

### 2. `explore` on Same Goal — Also Over-Constrained

**Invocation:** `explore` with `num_beams: 4`.  
**Result:** All 4 beam variants (bottom_up, top_down, risk_first, critical_path) returned empty step lists with `"error": "over_constrained"`.

**Finding:** `explore` uses the same decomposition engine as `decompose`, so it inherited the same failure mode. None of the beam strategies could produce a plan because the dependency graph was rejected at the scaffold validation stage.

**Implication:** When `decompose` hits an over-constrained error, `explore` is not a viable fallback. The agent must either:
- Simplify the goal,
- Provide an explicit scaffold with `depends_on` carefully curated, or
- Use `skip_recipes: true` to bypass cached recipe matching.

### 3. `get_recipe` — Recipe Cache Retrieval Works Well

**Invocation:** `get_recipe` on "recipe transformation pipeline" with `include_scaffold: true`.  
**Result:** Retrieved a cached recipe from a previous phase with match score 0.456.

**Finding:** trammel returned a full 46-step scaffold from a prior successful build (likely Phase 6 or similar). The scaffold included:
- EventBus, EventStore, AllergenEnricher, CostEnricher, etc.
- API routes for enrichment, DSL, optimization pipeline, recipeQL, tiered cache
- Test files for each subsystem
- Proper dependency ordering (e.g., `AggregateRoot` depends on `EventStore` + `EventBus`)

**Observation:** The recipe cache is effective for similar goals. The retrieved scaffold was well-structured and would have been directly usable if the goal had been to build those exact features. However, for the current goal (a single adaptive pipeline), the cached recipe was too broad.

### 4. `list_strategies` — Empty Trajectory Data

**Invocation:** `list_strategies`.  
**Result:** All 9 strategies (bottom_up, top_down, risk_first, critical_path, cohesion, minimal_change, leaf_first, hub_first, test_adjacent) reported 0 successes and 0 failures.

**Finding:** No historical trajectory data has been accumulated for this project. This means trammel's strategy recommendation engine has no empirical basis to prefer one beam variant over another.

**Implication:** Strategy selection is currently arbitrary for this codebase. Agents should manually choose `bottom_up` for safe refactors or `top_down` for API-first work.

### 5. `create_plan`, `verify_step`, `save_recipe` — Not Directly Used

These tools were not invoked during this phase because `decompose` and `explore` failed to produce steps, and there was no prior plan to verify. The feature was built through manual planning informed by the `get_recipe` scaffold and codebase exploration.

However, the `SelfAdaptiveRecipePipeline` feature itself **emulates** trammel's core logic:
- `decomposeGoal()` mirrors `decompose`
- `executePipeline()` with adaptive retry mirrors `verify_step` with fallback
- `cachePattern()` mirrors `save_recipe`
- `findCachedPattern()` mirrors `get_recipe`

This meta-circular design was intentional — the feature challenges trammel by implementing its own planning and caching loop.

## Strengths

1. **`get_recipe` retrieval is powerful:** The cached scaffold from a prior phase was complete, well-ordered, and immediately actionable.
2. **Dependency graph transparency:** When `decompose` fails, it reports exactly which files were over-constrained, helping the agent diagnose the issue.
3. **Scaffold validation prevents broken plans:** The over-constrained check, while overly strict for test files, does prevent plans with unbuildable dependency DAGs.

## Weaknesses & Limitations

1. **Over-constrained failure on normal patterns:** Test files and facades with 5+ dependencies are common in real projects. trammel treats them as fatal errors rather than manageable complexity.
2. **No fallback decomposition mode:** When `decompose` fails, there is no "best effort" mode that returns a partial plan. The agent gets zero steps.
3. **Empty strategy trajectories:** Without historical build data, strategy recommendations are not data-driven.
4. **`explore` does not provide independent value:** It is a thin wrapper over `decompose` that suffers from the same validation failures.

## Recommendations

- **For test-heavy projects, use `suppress_creation_hints: true`** and provide an explicit `scaffold` to avoid over-constrained errors.
- **Use `get_recipe` early** to check if a similar goal has already been solved in this codebase.
- **When `decompose` fails, do not try `explore`** — instead, simplify the goal or manually curate the scaffold.
- **Run successful plans through `create_plan` + `save_recipe`** to build up trajectory data for future `list_strategies` recommendations.


---

## Post-Evaluation Action Items

Based on the Phase 14 findings, the following fixes and improvements are recommended for trammel:

### Critical
1. **Fix `over_constrained` logic for test-heavy projects** — `decompose` and `explore` both failed with `over_constrained` because test files and facades naturally have 5+ dependencies. This is normal architecture, not an error. Investigate whether:
   - The dependency threshold is too low,
   - It should be a warning instead of a fatal error,
   - There should be a "best effort" or "degraded" mode that returns a partial plan when the full graph exceeds thresholds.
2. **Give `explore` independent fallback value** — Currently a thin wrapper over `decompose`, inheriting the same failures. When `decompose` is over-constrained, `explore` should offer a fallback strategy (e.g., scaffold-only decomposition without full-repo dependency analysis) rather than also returning zero steps.

### High Priority
3. **Build strategy trajectory data** — `list_strategies` shows 0 successes and 0 failures across all 9 strategies. This means trammel has no empirical basis for recommending one beam variant over another. Either:
   - Start auto-persisting successful plans to feed trajectory data, or
   - Reconsider surfacing `list_strategies` until enough data exists to make it meaningful.
4. **Improve documentation for `strict_greenfield` and `suppress_creation_hints`** — These flags are the difference between `decompose` working and failing on normal projects. They should be more prominently documented in the tool descriptions or returned as hints when `over_constrained` is triggered.

### Medium Priority
5. **Add partial-plan recovery** — When `decompose` fails for any reason, the agent currently receives zero steps. Returning whatever steps could be inferred from the scaffold (even if dependency analysis was aborted) would be far more useful than a complete blank.
