# Chisel MCP Server - Phase 7 Assessment

**Project**: RecipeLab_alt (Zero-Dependency Node.js Implementation)
**Date**: 2026-03-25
**Phase**: Feature Implementation with MCP Validation

---

## Overview

Chisel is a code intelligence MCP server that provides metrics around test coverage, risk, churn, coupling, and impact analysis. It analyzes git history and import graphs to identify code quality issues.

---

## What Worked

### 1. `analyze` - Code Scanning
**Status**: ✅ Fully Functional

- Scanned 129 code files
- Found 410 code units
- Identified 18 test files with 276 test units
- Built 2,915 test edges (import-based dependency graph)
- Parsed 2 commits

```
{
  "code_files_scanned": 129,
  "code_units_found": 410,
  "test_files_found": 18,
  "test_units_found": 276,
  "test_edges_built": 2915,
  "commits_parsed": 2
}
```

### 2. `test_gaps` - Untested Code Identification
**Status**: ✅ Works with Limitations

Successfully identified untested files:
- `src/services/optimizer/varietyScorer.js` (VarietyScorer class)
- `src/plugins/plugins/ratingPredictor.js` (predictRating function)
- `src/plugins/plugins/seasonalRecommender.js` (getCurrentSeason function)

**Limitation**: The tool only returns gaps for files that are part of the import graph from existing test files. Files not connected to tested code via imports are not reported.

### 3. `risk_map` - Risk Scoring
**Status**: ✅ Functional

Generated risk scores for 111 files. Top risk files correctly identified:
- `src/api/app.js` (risk: 0.6198) - coverage_gap: 1.0
- `src/cli/index.js` (risk: 0.6198) - coverage_gap: 1.0
- `src/plugins/index.js` (risk: 0.6198) - coverage_gap: 1.0

Risk breakdown correctly shows:
- `coverage_gap` = 1.0 for untested files
- `churn` scores based on commit frequency
- `import_coupling` computed from import relationships

### 4. `diff_impact` - Impact Analysis
**Status**: ✅ Reliable for Change Impact

Used after making code changes to identify which tests would be affected. Traces import chains transitively to find downstream test files.

### 5. `suggest_tests` - Test Recommendations
**Status**: ✅ Works When Test Edges Exist

For files with existing test coverage via import graph:
- Returns ranked test files that cover the target
- Works well for committed files with git history

**Limitation**: Returns empty for files without test edges (new/untracked files).

### 6. `churn` - Change Frequency
**Status**: ✅ Reliable

File change frequency metric worked consistently. All new files show churn_score: 0.997843 (high churn for new files with 1 commit).

### 7. `triage` - Combined Overview
**Status**: ✅ Excellent Summary

Combines risk_map + test_gaps + stale_tests in one call. Provides:
- Top risk files with full breakdown
- Test gaps with churn scores
- Actionable next steps

---

## What Didn't Work

### 1. `coupling` - Co-change Analysis
**Status**: ❌ Completely Broken

**Issue**: Returns 0.0 for ALL files regardless of threshold or min_count.

**Root Cause**: Requires multi-author co-change history. Single-author bulk commits produce zero signal. The coupling algorithm depends on git blame patterns across multiple collaborators.

**Evidence**:
```json
{
  "coupling_partners": [],
  "breakdown": {
    "cochange_coupling": 0.0,
    "cochange_global": 0.0,
    "cochange_branch": 0.0
  }
}
```

**Impact**: High - coupling is a major risk factor that always shows 0.0, making risk scores less accurate.

### 2. `coverage_gap` - Binary Scoring
**Status**: ⚠️ Binary Only

**Issue**: Returns only 0.0 (tested) or 1.0 (untested). No partial coverage scoring.

**Example**: If a file has 10 functions and 8 have tests, it still shows 1.0 (untested).

**Impact**: Medium - cannot distinguish between 90% coverage and 0% coverage.

### 3. `suggest_tests` on New Files
**Status**: ❌ Returns Empty

**Issue**: Cannot recommend tests for files not yet committed to git.

**Example**: `substitutionEngine.js` was created by agent but `suggest_tests` returns empty until committed.

**Impact**: Medium - forces waiting for git commit before test guidance.

### 4. Untracked Files Invisible to Analysis
**Status**: ❌ Major Gap

**Issue**: `risk_map`, `test_gaps`, `suggest_tests`, and `coupling` cannot see uncommitted working-tree files.

**Example**: The meal plan optimizer files existed but weren't visible until:
1. Agent completed
2. Files were committed to git
3. New `analyze --force` run executed

**Impact**: High - significant delay between code creation and tool visibility.

---

## Issues Surfaced

### Issue 1: Import Graph-Based Coverage (Not True Coverage)

Chisel's `coverage_gap` measures whether a file is connected to test files via imports, NOT whether the code itself is actually tested. A file can be:
- 100% import-connected to test files → coverage_gap = 0.0 (looks "tested")
- But actually have 0% of its functions tested

**Example from this project**:
- `mealPlanOptimizer.js` has coverage_gap = 0.0 because tests import from it
- But `paretoFrontier.js` and `varietyScorer.js` have coverage_gap = 1.0 despite being in the same module

### Issue 2: Test Instability Always 0.0

```json
"uniform_components": {
  "test_instability": {
    "value": 0.0,
    "reason": "no test results recorded; use record_result after running tests"
  }
}
```

The `record_result` tool must be called after each test run for instability tracking, but this wasn't done during the feature implementation phase.

### Issue 3: Commit-Based Analysis Requires Commits

All churn and coupling metrics depend on git commits. New files show maximum churn (0.997843) simply because they have 1 commit, not because they're changing frequently.

### Issue 4: Risk Score Uniformity

When 3+ components have uniform values (e.g., coverage_gap, author_concentration), the composite risk score becomes misleading. No warning is issued when this occurs.

---

## Deliberate Test Gaps (Validation Test)

As designed, the following files have NO tests (for Chisel validation):

| File | Type | Purpose |
|------|------|---------|
| `src/services/optimizer/paretoFrontier.js` | Pareto optimization | Deliberate gap |
| `src/services/optimizer/varietyScorer.js` | Variety scoring | Deliberate gap |
| `src/plugins/plugins/priceTagger.js` | Price estimation | Deliberate gap |
| `src/plugins/plugins/seasonalRecommender.js` | Seasonal recommendations | Deliberate gap |
| `src/plugins/plugins/ratingPredictor.js` | Rating prediction | Deliberate gap |

**Chisel Detection Results**:
- `varietyScorer.js`: ✅ Detected (VarietyScorer class)
- `ratingPredictor.js`: ✅ Detected (predictRating function)
- `seasonalRecommender.js`: ✅ Detected (getCurrentSeason function)
- `paretoFrontier.js`: ❌ NOT detected (0 test gaps returned)
- `priceTagger.js`: ❌ NOT detected (0 test gaps returned)

**Analysis**: The optimizer directory triage missed 2 of 5 deliberate gaps because `paretoFrontier.js` is only imported by `mealPlanOptimizer.js` which IS tested, so it appears "covered" from the test graph perspective.

---

## Statistics Summary

| Metric | Value |
|--------|-------|
| Code files scanned | 129 |
| Code units found | 410 |
| Test files found | 18 |
| Test units found | 276 |
| Test edges built | 2,915 |
| Commits parsed | 2 |
| Files with coverage_gap=1.0 | ~30 |

---

## Recommendations for Chisel Improvement

### High Priority

1. **Add import-graph coupling**: Replace co-change coupling with static import analysis
2. **Working-tree awareness**: Include uncommitted files in risk_map and test_gaps
3. **Graduated coverage_gap**: Add 0.25/0.5/0.75/1.0 levels for partial coverage

### Medium Priority

4. **Warn when uniform_components**: Alert when 3+ components have identical values
5. **Better new-file handling**: Default suggest_tests to "all test files" for untracked files
6. **Test instability tracking**: Make record_result easier to use in CI pipelines

---

## Conclusion

Chisel provides excellent **structural analysis** (import graphs, test edges, code scanning) but suffers from **git-dependence** for its most valuable metrics (coupling, churn). The tool works best for established projects with rich git history and struggles with:
- New greenfield code
- Single-author projects
- Uncommitted working-tree files

**Overall Rating**: 7/10 - Valuable structural insights, limited by git-history dependency.
