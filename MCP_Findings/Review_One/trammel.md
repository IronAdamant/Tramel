# Trammel MCP Server - Phase 7 Assessment

**Project**: RecipeLab_alt (Zero-Dependency Node.js Implementation)
**Date**: 2026-03-25
**Phase**: Feature Implementation with MCP Validation

---

## Overview

Trammel is a planning and recipe MCP server that decomposes high-level goals into dependency-aware implementation steps, manages plan execution tracking, and stores reusable implementation recipes.

---

## What Worked

### 1. `claim_step` - Step Ownership
**Status**: ✅ 100% Reliable (28/28 successes)

The most reliable Trammel feature. Successfully claimed steps during multi-agent execution without conflicts.

```json
{
  "plan_id": 1,
  "step_id": 5,
  "agent_id": "agent-123",
  "status": "claimed"
}
```

### 2. `complete_plan` - Batch Completion
**Status**: ✅ Excellent for Single-Agent

Single call to:
- Batch-mark steps as passed/failed
- Set plan status
- Save strategy as reusable recipe

Much better than individual claim/record/verify calls.

### 3. `decompose` with `scaffold` - Dependency-Aware Steps
**Status**: ✅ Produces Correct Dependency Graph

When scaffold parameter is provided (explicit file specs with `depends_on`), generates accurate dependency-aware steps with 226 edges.

**Example Structure**:
```json
{
  "steps": [
    {
      "id": 1,
      "file": "src/models/Recipe.js",
      "description": "Recipe model with CRUD",
      "depends_on": []
    },
    {
      "id": 2,
      "file": "src/services/recipeService.js",
      "description": "Recipe business logic",
      "depends_on": ["src/models/Recipe.js"]
    }
  ],
  "dependency_graph": {
    "edges": [["src/models/Recipe.js", "src/services/recipeService.js"]]
  }
}
```

### 4. `estimate` - Project Sizing
**Status**: ✅ Reasonable Estimates

Quick file count and language detection. Useful for deciding whether to scope before full decompose.

```
{
  "file_count": 105,
  "language": "javascript",
  "scope": "src/services/optimizer"
}
```

### 5. `get_constraints` / `add_constraint` - Failure Tracking
**Status**: ✅ Useful for Known Failure Patterns

Records failure constraints to prevent repeating bad approaches. Good for:
- "This API endpoint requires auth - don't implement without it"
- "This file has a known race condition"

### 6. `create_plan` / `get_plan` / `list_plans` - Plan Management
**Status**: ✅ Functional

Basic CRUD for plans works. Can create, retrieve, and list plans.

---

## What Didn't Work

### 1. `decompose` WITHOUT `scaffold` - New File Inference
**Status**: ❌ Returns Disconnected Steps

**Issue**: Cannot infer new files from goal description. Returns only existing-file steps, missing all new files to create.

**Example**: Goal: "Add user authentication"
- WITHOUT scaffold: Returns steps for existing files only
- WITH scaffold: Correctly generates steps for new `auth/*` files

**Evidence from Phase 3**: Returned 492 disconnected steps with zero new-file generation.

**Impact**: High - requires explicit scaffold for every new feature.

### 2. Recipe Matching - Structural Pattern Recognition
**Status**: ⚠️ Too Conservative

**Issue**: Recipe matching scores are too low (~0.2 max) and don't discriminate between structurally similar tasks.

**Example**: Running `get_recipe` for "Add plugin system" on a codebase that already has a plugin system returns weak match (~0.2).

**Root Cause**: Recipe matching uses trigram + Jaccard + substring with conservative thresholds.

**Impact**: Medium - matched recipes don't provide useful scaffolding guidance.

### 3. Relevance Scoring on Non-Scaffold Steps
**Status**: ⚠️ Near-Binary

**Issue**: Relevance scores for non-scaffold steps are 0.0–0.03 (nearly binary).

**Example**:
- Step with "recipe" in filename: 0.03
- Step with "model" in filename: 0.01
- Everything else: 0.00

**Impact**: Medium - cannot prioritize within existing files.

### 4. No Recipe → Scaffold Conversion
**Status**: ❌ Missing Workflow

**Issue**: Even when a recipe matches, there's no way to auto-convert it to scaffold entries.

**Desired**: Matched recipe → scaffold file specs → decompose with those specs

**Impact**: Medium - users must manually convert recipe patterns to scaffold.

---

## Issues Surfaced

### Issue 1: `skip_recipes` Parameter Not Well Known

The `skip_recipes: true` parameter was added to bypass false recipe matches. Without it, Phase 3 returned useless scaffolding. This parameter should be more prominent.

### Issue 2: Recipe Storage Growing Unbounded

No auto-pruning of old/low-quality recipes. After 9 phases, recipe store may contain stale patterns.

**Note**: `prune_recipes` tool exists but wasn't used.

### Issue 3: Verify Step is Slow

`verify_step` runs tests in isolation which is slow. For single-agent workflows, manual test runs are faster.

### Issue 4: Dependency Graph Requires Scaffold

Without scaffold entries, the dependency graph is empty. This makes `decompose` useless for greenfield features unless scaffold is manually provided.

---

## Plan Execution Example (4 Features)

We created 4 parallel plans for the new features:

| Plan | Feature | Steps | Status |
|------|---------|-------|--------|
| #10 | Ingredient Substitution Engine | ~15 | Completed |
| #11 | Recipe Version Control | ~20 | Completed |
| #12 | Meal Plan Optimizer | ~18 | Completed |
| #13 | Plugin System (18 Hooks) | ~22 | Completed |

### Execution Pattern Used

1. **Plan created** via `create_plan` with scaffold
2. **Steps claimed** via `claim_step` by each agent
3. **Steps recorded** via `record_steps` after completion
4. **Plan completed** via `complete_plan`

### What Worked Well

- Parallel execution via multiple agents
- Step-level tracking for progress visibility
- Dependency enforcement prevented circular imports

### What Didn't Work

- Couldn't share scaffold between plans (each agent created own)
- No way to run multiple plans in dependency order automatically

---

## Recipe Analysis

### Recipe Structure
Each recipe stores:
- `goal` - pattern description
- `strategy` - step structure
- `outcome` - success/failure
- `file_paths` - files touched

### Recipe Quality Issues

**Problem**: Recipes from failed plans get stored with `outcome: false`, but there's no clear way to distinguish between:
1. Recipe that failed due to bad approach (don't reuse)
2. Recipe that failed due to external factors (retry OK)

**Current Behavior**: All stored recipes are available for matching regardless of outcome.

---

## Statistics Summary

| Metric | Value |
|--------|-------|
| Plans tracked | 4+ |
| Steps claimed | 28 |
| Recipes stored | Multiple (from prior phases) |
| Recipes pruned | 0 (not run) |

---

## Recommendations for Trammel Improvement

### High Priority

1. **Goal-Text → Scaffold Inference**: Use NLP to extract file patterns from goal description and auto-generate scaffold entries.

2. **Structural Recipe Matching**: Extract model+service+route+test as matching features, not just text similarity.

3. **Recipe → Scaffold Conversion**: Add workflow to convert matched recipe to scaffold entries automatically.

### Medium Priority

4. **Relevance Score Granularity**: Use 0.0-1.0 continuous scale instead of near-binary 0.0-0.03.

5. **Failed Recipe Distinction**: Mark recipes that failed due to approach vs external factors.

6. **Batch Scaffold Generation**: Allow scaffold entries to be shared across multiple plans.

---

## Conclusion

Trammel is excellent at **plan execution tracking** (`claim_step`, `complete_plan`) and **dependency-aware decomposition** (with scaffold). The tool shines when:
- Multiple agents work in parallel
- Explicit file specs are provided
- Step-level progress tracking is needed

But struggles with:
- **Automated file discovery** - requires manual scaffold
- **Recipe quality** - too conservative, no structural matching
- **Scalability** - single plan focus, no cross-plan coordination

**Overall Rating**: 7/10 - Excellent execution tracker, weak automated planning.

---

## Feature-Specific Assessment

### Feature 1: Ingredient Substitution Engine (Stele-Context Challenge)
- **Planning**: Scaffold provided → dependency graph accurate
- **MCP Challenge**: Validated semantic search weakness (returns irrelevant results)
- **Result**: 3 files created, 2 tested

### Feature 2: Recipe Version Control (Trammel Challenge)
- **Planning**: Scaffold provided → 14 files with correct dependencies
- **MCP Challenge**: Validated scaffold dependency (without = useless)
- **Result**: 14 files, 58 tests passing

### Feature 3: Plugin System with 18 Hooks (Chisel Challenge)
- **Planning**: Scaffold provided → 27 files with hook dependencies
- **MCP Challenge**: Deliberate test gaps detected by coverage_gap
- **Result**: 27 files, 53 tests passing, 5 untested (as designed)

### Feature 4: Meal Plan Optimizer (All 3 MCP Servers)
- **Planning**: Scaffold provided → optimizer modules with constraints
- **MCP Challenge**: Validated all 3 servers
- **Result**: 12 files, 56 tests passing, 2 untested (as designed)
