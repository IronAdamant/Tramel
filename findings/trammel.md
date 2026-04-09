# Trammel MCP Findings — Review Eight

## Review Context

**Date:** 2026-04-09
**Phase:** Review Eight — 6 new MCP challenge features
**Challenge Feature:** `ConditionalWorkflowPlanner` (Trammel-targeted), plus `CrossCuttingConcernDetector` and `ModuleContractValidator` (all-system)
**Files Created:** 18 new files (6 services, 6 routes, 6 tests)

## Tools Used During This Review

| Tool | Invocations | Status |
|------|------------|--------|
| `estimate` | 1 | PASS |
| `list_recipes` | 1 | PASS |
| `decompose` | 1 (with scaffold) | PASS |
| `create_plan` | 2 | FAIL (schema bug) |
| `complete_plan` | 0 (blocked by create_plan) | BLOCKED |
| `claim_step` | 0 (blocked) | BLOCKED |
| `record_steps` | 0 (blocked) | BLOCKED |

## Detailed Findings

### 1. `estimate` — Project Size Estimation

**Result:**
- Language: JavaScript (correct auto-detection)
- Matching files: 243
- Recommendation: "full analysis OK"

**Verdict:** Fast, accurate, reliable. Consistent across all 8 review phases.

### 2. `list_recipes` — Recipe Retrieval

**Result:** 1 recipe found:
- Signature: `b0aad850a943`
- Pattern: "Refactor database layer - convert FileStore JSON-based storage to better-sqlite3 SQLite implementation"
- Successes: 1, Failures: 0
- Files: 5 (fileStore.js, sqlite.js, migrations.js, schema.js, index.js)

**Observations:**
- Only 1 recipe stored despite 7+ completed phases. Previous phase recipes were either not saved or the database was reset.
- The stored recipe is from the Phase 7 SQLite migration, which was later reverted to FileStore. The recipe still records the successful execution even though the work was undone.
- Recipe matching did not trigger during decompose (skip_recipes was set to true).

**Verdict:** Recipe storage works but is underutilized. The recipe inventory should be richer given the project history.

### 3. `decompose` — Strategy Decomposition (STRONG PASS)

**Input:** Goal with 18-file scaffold, all 6 feature files with explicit `depends_on` declarations.

**Result:**
- 18 steps generated, all at relevance 1.0 (scaffold-only mode)
- 16 dependency edges correctly derived from scaffold
- 3-layer DAG:
  - Layer 0 (width 4): 4 independent core services
  - Layer 1 (width 10): routes + tests + 2 dependent services
  - Layer 2 (width 4): routes + tests for dependent services
- Critical path length: 3
- Max parallelism: 10
- Timing: 0.003 seconds

**Scaffold DAG Metrics:**
```
node_count: 18
edge_count: 16
max_dependency_depth: 3
critical_path_length: 3
max_parallelism: 10
layer_widths: [4, 10, 4]
```

**Assessment:** This is Trammel's best decomposition result across all review phases. The scaffold-only mode (`scaffold_applied: 18`, `expand_repo: false`) produced exactly the right steps with zero noise. No disconnected steps, no irrelevant files, no missing dependencies.

**Key Improvements from Prior Phases:**
- Phase 3: decompose without scaffold returned 492 disconnected steps. Phase 8 (this review) with scaffold: 18 precise steps.
- The `scaffold` parameter has matured from "recommended" to "essential for greenfield work."
- The `depends_on` declaration in scaffold entries correctly generated the dependency graph edges.

**What decompose got right:**
1. Topological ordering respects dependencies — services before routes, services before tests.
2. Independent services (no deps) correctly placed in Layer 0 for parallel execution.
3. Cross-feature dependencies (CrossCuttingConcernDetector depends on both ContextualSymbolResolver AND IncrementalBuildGraph) correctly modeled.
4. Action classification: all steps correctly marked as `action: "create"`.

### 4. `create_plan` — Plan Creation (CRITICAL FAILURE)

**Attempt 1:** Called with `goal`, `strategy`, and `scaffold` parameters.
**Error:** `"Error: table plans has no column named scaffold"`

**Attempt 2:** Called with only `goal` and `strategy` (omitting scaffold).
**Error:** Same error — `"Error: table plans has no column named scaffold"`

**Root Cause Analysis:**
The `create_plan` tool's function signature accepts a `scaffold` parameter (documented in the schema), but the underlying SQLite database table `plans` does not have a corresponding `scaffold` column. This is a **schema migration bug** — the tool interface was updated to accept scaffold data, but the database migration to add the column was never applied.

Even when the `scaffold` parameter is omitted from the API call, the tool appears to unconditionally attempt to insert scaffold data (possibly from the strategy object which contains scaffold references), causing the same error.

**Impact:** This bug completely blocks the plan creation → claim_step → record_steps → complete_plan workflow. Without a plan ID, no steps can be tracked, claimed, or completed. This means:
- `claim_step` — BLOCKED (requires plan_id)
- `record_steps` — BLOCKED (requires step_id from plan)
- `complete_plan` — BLOCKED (requires plan_id)
- `save_recipe` via complete_plan — BLOCKED

**Severity:** CRITICAL. The full Trammel workflow is broken for any decomposition that uses scaffold (which is the recommended approach for all greenfield work).

**Previous Phase Comparison:** In Phase 7, `create_plan` worked correctly for a 5-step database refactor plan. The scaffold column issue must have been introduced between Phase 7 and now (possibly during a Trammel server update).

**Recommended Fix:** Add an ALTER TABLE migration:
```sql
ALTER TABLE plans ADD COLUMN scaffold TEXT;
```
Or handle the scaffold data in a separate table with a foreign key to plans.

### 5. Blocked Tools (Due to create_plan Failure)

The following tools could not be tested because create_plan failed:

- **`claim_step`** — Previously 100% reliable (28/28 successes in Phase 7). Cannot validate this phase.
- **`record_steps`** — Batch step updates. Cannot test.
- **`complete_plan`** — Single-agent workflow completion. Cannot test.
- **`save_recipe`** — Automatic recipe saving via complete_plan. Cannot test.
- **`verify_step`** — Step verification. Cannot test.

This means **60% of Trammel's workflow tools are untestable** in this review due to a single database schema bug.

## Summary Scorecard

| Capability | Score (1-5) | Notes |
|-----------|-------------|-------|
| `estimate` | 5/5 | Reliable, fast, accurate |
| `list_recipes` | 3/5 | Works but inventory is thin |
| `decompose` | 5/5 | Best result ever — scaffold mode is excellent |
| `create_plan` | 0/5 | BROKEN — schema migration bug |
| `claim_step` | N/A | Blocked by create_plan |
| `record_steps` | N/A | Blocked by create_plan |
| `complete_plan` | N/A | Blocked by create_plan |

## Challenge Assessment: Did the Features Challenge Trammel?

**ConditionalWorkflowPlanner** specifically challenged Trammel by:
1. **Creating a service that does what Trammel does** — conditional workflow planning with step dependencies, parallel execution groups, and join semantics. This mirrors Trammel's own decompose + plan + execute model.
2. **Non-linear step dependencies** — The ConditionalWorkflowPlanner supports conditions (`if X then branch A else branch B`), which Trammel's decompose cannot express (decompose only supports linear dependencies via `depends_on`).
3. **Rollback semantics** — ConditionalWorkflowPlanner has explicit rollback support; Trammel has no equivalent (failed plans stay failed with no undo).
4. **Join modes** — The planner supports ALL/ANY/MAJORITY join modes; Trammel only supports ALL (all dependencies must be met).

**The irony:** The ConditionalWorkflowPlanner feature WOULD have been the perfect test case for Trammel's full workflow (decompose → plan → claim → record → complete), but the create_plan bug prevented this validation. The feature that was designed to challenge Trammel's planning capabilities exposed a more fundamental bug in Trammel's infrastructure instead.

**CrossCuttingConcernDetector** and **ModuleContractValidator** challenged Trammel by:
1. **Multi-dependency scaffold entries** — Both depend on two other scaffold entries, creating a diamond dependency pattern. Decompose handled this correctly.
2. **18-file scaffold** — The largest scaffold used in any phase. Trammel processed it in 0.003 seconds with correct topology.

## Critical Bugs Found

1. **`create_plan` broken** — `"table plans has no column named scaffold"`. This is a database schema migration that was not applied. Blocks 60% of Trammel's workflow.
2. **Recipe inventory decay** — Only 1 recipe stored despite 7+ phases of work. Either recipes aren't being saved or the database is being reset between sessions.

## Key Takeaways

1. **`decompose` with scaffold is Trammel's masterpiece** — 18 files, 16 edges, 3 layers, 0.003 seconds, zero noise. This is the gold standard for greenfield planning.
2. **`create_plan` has a critical schema bug** that blocks the entire plan execution workflow. This must be fixed before Trammel can be used for tracked plan execution.
3. **Trammel's planning model lacks conditional branching** — decompose can only express linear `depends_on` chains, not if/else or join semantics. The ConditionalWorkflowPlanner feature demonstrates what Trammel should eventually support.
4. **The gap between decompose (excellent) and plan execution (broken) is Trammel's most pressing issue.** The planning intelligence is there, but the execution infrastructure has a blocking bug.

## Follow-Up Required

**Status: RESOLVED (item 1) — 2026-04-09. Remaining items scheduled for dedicated follow-up session.**

The `create_plan` schema bug (`table plans has no column named scaffold`) blocked 60% of Trammel's workflow tools from being tested. The following items require a dedicated session to resolve and validate:

1. ~~**Fix the `create_plan` schema bug**~~ — **FIXED (v3.10.1).** Root cause: migration at `store.py:193` added `scaffold` column to `steps` table instead of `plans` table. Fixed by separating the migration targets. Live DB migrated successfully.
2. **Re-run full plan execution workflow** — Once create_plan works: create_plan → claim_step → record_steps → complete_plan → verify recipe saved. This was 100% reliable in Phase 7 (28/28 claim_step successes) and needs re-validation.
3. **Test recipe matching** — With multiple recipes stored, test whether decompose's `near_match_recipes` scoring has improved from the conservative ~0.2 max observed in prior phases.
4. **Validate scaffold persistence** — Confirm that scaffold data is correctly stored with the plan and available for recipe matching on future similar goals.
5. **Test conditional workflow decomposition** — Attempt to decompose the ConditionalWorkflowPlanner's own workflow patterns (branching, joins) to see how Trammel handles non-linear goals.

This follow-up session should focus exclusively on Trammel to get a complete assessment.
