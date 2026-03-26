# Stele-Context MCP Server - Phase 7 Assessment

**Project**: RecipeLab_alt (Zero-Dependency Node.js Implementation)
**Date**: 2026-03-25
**Phase**: Feature Implementation with MCP Validation

---

## Overview

Stele-context is a semantic code understanding MCP server that provides symbol-level analysis, cross-references, semantic search, and code impact tracking. It uses embeddings and LSP-style parsing for precise code navigation.

---

## What Worked

### 1. `find_references` - Symbol Tracking
**Status**: ✅ Excellent

**Best feature of Stele-context.** Precise symbol tracking with verdict field:
- `referenced` - symbol is used elsewhere
- `unreferenced` - symbol has no usages (dead code)
- `external` - symbol is from external dependency
- `not_found` - symbol not in index

**Examples from this project**:
```json
{
  "symbol": "PluginManager",
  "verdict": "referenced",
  "definitions": [...],
  "references": [
    {
      "document_path": "src/plugins/index.js",
      "line_number": 5
    }
  ]
}
```

**Accuracy**: High - correctly identifies all import references, class definitions, and usage patterns.

### 2. `find_definition` - Jump to Definition
**Status**: ✅ Accurate

Returns full chunk content with line numbers for symbol definitions. Fast alternative to grep-based searches.

### 3. `index` - Document Indexing
**Status**: ✅ Fast and Reliable

- Indexed 152 documents across multiple projects
- 368 chunks, 171,305 total tokens
- Fast incremental updates for modified files

### 4. `map` - Project Overview
**Status**: ✅ Useful Summary

Returns document count, token totals, and chunk counts. Good for orientation.

### 5. `detect_changes` - Change Detection
**Status**: ✅ Reliable for Indexed Files

Correctly identifies modified indexed files. Shows when files were last indexed.

### 6. `coupling` (Semantic) - Relationship Analysis
**Status**: ✅ Better than Chisel's

Unlike Chisel's coupling, this provides bidirectional relationships with shared symbols:
```json
{
  "depends_on": ["fileA.js", "fileB.js"],
  "depended_on_by": ["fileC.js"],
  "bidirectional": ["sharedUtils.js"],
  "shared_symbols": ["transform", "parse"]
}
```

---

## What Didn't Work

### 1. `search` - Semantic Search
**Status**: ❌ Consistently Irrelevant Results

**Issue**: Returns highly irrelevant results for domain-specific queries. The embedding model weights structural code patterns (boilerplate, imports, exports) over semantic meaning.

**Example - Query: "allergen dietary compliance"**
- **Result #1**: `units.test.js` (test file with no dietary logic)
- **Expected**: allergenData.js, dietaryComplianceService.js

**Root Cause**:
- Embedding model trained on generic code, not domain-specific
- Test boilerplate patterns score high due to common structure
- Domain vocabulary not well represented

**Impact**: High - renders semantic search unusable for practical queries.

### 2. `impact_radius` - Blast Radius Analysis
**Status**: ❌ Output Too Large

**Issue**: Returns massive unstructured output (193K characters for a single file).

**Example**: Running on `Recipe.js` produced 193,000+ characters of output listing every transitive dependent.

**Impact**: High - output is unusable without manual parsing.

### 3. `detect_changes` Cannot Discover New Files
**Status**: ❌ Major Gap

**Issue**: Only checks already-indexed files. New files created since last index are NOT detected.

**Example**: When 4 agents created 108 new files, `detect_changes` showed 0 new files until:
1. `index` was called on each new file
2. Or `index --force-reindex` was run on entire project

**Impact**: High - requires explicit indexing after file creation.

### 4. Search Should Boost Recent Content
**Status**: ⚠️ Not Implemented

No way to filter results by indexing timestamp. Recent files don't get ranking boost.

---

## Issues Surfaced

### Issue 1: Embedding Model Domain Gap

The semantic search fails because the embedding model is not trained on recipe/cooking domain vocabulary. Generic code patterns dominate results.

**Example**:
- Query: "unit conversion calculations"
- Top result: Import-heavy route file (because imports/conversions appear in boilerplate)

### Issue 2: Symbol Index Time Lag

New symbols don't appear in `find_references` until:
1. File is indexed (via `index` or `detect_changes`)
2. Symbol graph is rebuilt (via `rebuild_symbols`)

This creates a race condition where newly created symbols appear as `not_found` until indexing completes.

### Issue 3: Stale Locks

The stats show expired locks issue:
```
"expired_locks": 152,
"active_lock_agents": 3,
"total_conflicts": 0
```

All 152 documents have expired locks, suggesting the lock cleanup isn't working properly.

### Issue 4: Low Token Budget for Results

`search` has a `max_tokens` parameter (default 4000) that limits results. For large codebases, this causes truncation.

---

## Symbol Analysis Examples

### Feature 1: Ingredient Substitution Engine

**Symbol**: `substitutionEngine` in `src/services/substitutionEngine.js`

```
verdict: not_found
```

**Issue**: The symbol wasn't found even though it exists. Likely because:
1. The file was indexed but symbol extraction failed
2. Or the symbol name differs from filename-based lookup

**Workaround**: Use `find_references` on actual exported symbols like `findSubstitutes`, `suggestSwap`.

### Feature 2: Version Control Service

**Symbol**: `versionControlService`

```
verdict: not_found
```

Same issue as above - file-based symbol lookup fails but class-method symbols work.

### Feature 3: Plugin Manager

**Symbol**: `PluginManager`

```
verdict: referenced
definitions: 1 (PluginManager.js line 1)
references: 1 (index.js line 5)
```

**Success**: Class symbol correctly tracked.

### Feature 4: Meal Plan Optimizer

**Symbol**: `mealPlanOptimizer`

```
verdict: not_found
```

Same issue as Features 1 and 2.

---

## Chunk Statistics

| Metric | Value |
|--------|-------|
| Total documents | 152 |
| Total chunks | 368 |
| Total tokens | 171,305 |
| Symbol count | 5,921 |
| Definition count | 1,896 |
| Reference count | 4,025 |
| Edge count | 1,938 |

---

## Recommendations for Stele-Context Improvement

### High Priority

1. **BM25/Keyword Fallback for Search**: When semantic similarity is low, fall back to keyword matching. This hybrid approach would fix the domain-gap issue.

2. **impact_radius Summary Mode**: Add `compact: true` option that returns file counts per depth level instead of full chunk list.

3. **New-File Filesystem Scan**: Add optional mode to scan project root for files not yet indexed.

### Medium Priority

4. **Recent Content Boost**: Allow filtering by indexing timestamp for search ranking.

5. **Better Symbol Extraction**: Improve CommonJS `module.exports` parsing for class/function symbols.

6. **Lock Cleanup**: Fix the expired locks issue - 152 expired locks with 3 active agents suggests cleanup isn't running.

---

## Conclusion

Stele-context excels at **precise symbol tracking** (`find_references`, `find_definition`) but fails at **semantic discovery** (`search`). The tool is invaluable for:
- Understanding code relationships
- Finding all usages of a symbol
- Jump-to-definition navigation

But unusable for:
- Natural language code discovery
- Large-scale impact analysis
- Cross-domain queries

**Overall Rating**: 7/10 - Excellent symbol tools, poor semantic search.
