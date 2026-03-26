# Stele-Context MCP Phase 7 Validation Report

**Context**: This MCP will need sorting out - there are known issues that require attention.

---

## Executive Summary

This report documents Stele-Context MCP's performance against Phase 7 challenge features. Two features specifically challenge Stele-Context, with significant findings around dynamic symbol tracking, semantic search precision, and impact radius output volume.

**Known Issues Requiring Attention**:
1. `impact_radius` produces unusable output (147K+ chars)
2. `search` returns noisy results for domain queries
3. Dynamic symbol relationships invisible to static analysis
4. New files not discoverable without explicit re-indexing

---

## Phase 7 Full MCP Integration Run

During this session, ALL THREE MCPs were used simultaneously for the database refactoring task:

### MCP Usage Summary

| MCP | Used For | Status |
|-----|----------|--------|
| **Chisel** | `risk_map`, `test_gaps`, `diff_impact`, `churn` | ✓ Worked |
| **Stele-context** | `find_references`, `find_definition`, `map` | ✓ Worked |
| **Trammel** | `decompose` with scaffold, `create_plan`, `claim_step`, `record_step`, `complete_plan` | ✅ **TESTED & VALIDATED** |

### Database Refactoring Symbol Analysis

**Stele `find_references` on `getDatabase`**:
- Found 3 references (app.js, cli/index.js, db/index.js)
- Correctly identified import edges
- Verdict: "referenced"

**Stele `find_references` on `FileStore`**:
- Found 3 references (db/index.js, db/schema.js, definition)
- Correctly tracked class definition and imports
- Verdict: "referenced"

---

## Features Built for Stele-Context

### Feature 1: DynamicPluginRegistry with Runtime Symbol Registration

**Purpose**: Create symbol relationships that exist ONLY at runtime, invisible to static import analysis.

**Implementation**:
- `src/plugins/DynamicPluginManager.js` (118 LOC)
- `src/plugins/DynamicRegistry.js` (178 LOC)
- `tests/plugins/DynamicRegistry.test.js`

**Key Characteristics**:
- Runtime-only route registration
- Runtime-only service/hook registration
- Dynamic handler resolution via string lookup
- Event emitter pattern for plugin lifecycle

**Challenge**: 100% of coupling is dynamic - no static import edges exist.

---

### Feature 2: SemanticRecipeRelationshipAnalyzer

**Purpose**: Complex cross-module semantic relationships through content analysis.

**Implementation**: `src/services/relationshipAnalyzer.js` (714 LOC)

**Key Characteristics**:
- 8 semantic relationship types computed by content analysis
- Multi-dimensional similarity (title, instructions, ingredients, tags)
- Runtime relationship cache
- Semantic graph building with configurable depth

---

## Phase 7 Code Audit Findings

### Critical Bugs Found (Would Have Helped Stele Detect)

**app.js** had 3 critical bugs that could have been caught with better symbol tracking:
1. Factory functions treated as router objects with `.handle()` method
2. `serveStatic()` received string instead of parsed URL object
3. Would crash at runtime with `TypeError: Cannot read property 'handle' of undefined`

**Note**: Stele's `find_references` could help catch these if it tracked factory function patterns.

### Orphaned File: src/plugins/index.js

- `src/plugins/index.js` is completely orphaned (never imported anywhere)
- `find_references` confirmed: zero import edges
- **Verdict**: Delete or wire up - currently dead code

### Code Duplication Found (Architectural Debt)

| Pattern | Occurrences | Files |
|---------|-------------|-------|
| CRUD Routes | 8 identical | 8 route files |
| Error Handling Try-Catch | 40+ | 5+ route files |
| Model getAll() | 8 identical | 8 model files |
| Service constructor | 16 identical | 16 service files |
| Hook definitions | 18 identical | 18 hook files |

### DynamicPluginRegistry

**Challenge for Stele**: 100% dynamic coupling - no static import edges exist.

```javascript
// DynamicRegistry - runtime registration:
dynamicRegistry.registerRoute(pluginName, 'GET', '/api/recipes', handler);

// Stele CANNOT see:
// - handler is registered dynamically
// - No static import edge
// - Symbol exists only in runtime Map
```

**VERDICT**: Dynamic coupling requires symbol manifest support.

---

## Detailed Stele-Context Analysis

### CAPABILITY 1: `find_references` - Symbol Tracking

**WORKS for static imports**

- Static import edges: Correctly tracked
- Dynamic registration: NOT tracked (no import edge exists)

```javascript
stele.find_references({ symbol: 'getDatabase' })
// Returns: app.js, cli/index.js, db/index.js - 3 references
// verdict: "referenced"
```

**VERDICT: WORKS** for static imports. FAILS for dynamic symbol resolution.

---

### CAPABILITY 2: `find_definition` - Jump to Definition

**WORKS**

Accurate jump-to-definition for static import chains.

---

### CAPABILITY 3: `search` - Semantic Search

**NEEDS SORTING - Noisy for Domain Queries**

**Test Results**:
```
Query: "dynamic plugin registration"
Expected: DynamicPluginManager.js, DynamicRegistry.js
Actual: Mixed results, structural patterns weighted higher than content
```

**Root Cause**:
- Embedding model weights structural patterns over semantic content
- Domain-specific terms have weak embeddings
- No BM25/keyword fallback when semantic similarity is low

**VERDICT: NEEDS SORTING** - Requires BM25 fallback and domain-aware re-ranking.

---

### CAPABILITY 4: `coupling` - Semantic Coupling Detection

**WORKS** - But misses dynamic coupling.

```javascript
stele.coupling({ document_path: 'src/services/relationshipAnalyzer.js' })
// Static: Recipe.js, Ingredient.js found
// Dynamic (plugins): NOT FOUND
```

**VERDICT: WORKS** for static coupling. Dynamic coupling requires symbol manifest support.

---

### CAPABILITY 5: `impact_radius` - Impact Analysis

**NEEDS SORTING - Output Unusable**

```javascript
stele.impact_radius({
  document_path: 'src/services/relationshipAnalyzer.js',
  depth: 2
})
// Output: 147,000+ characters of nested JSON
// No summary mode available
```

**Proposed Fix - Summary Mode**:
```json
{
  "depth": 2,
  "totalFiles": 47,
  "summary": [
    { "path": "src/api/routes/", "depth": 0, "count": 5 },
    { "path": "src/services/", "depth": 1, "count": 18 },
    { "path": "src/models/", "depth": 2, "count": 24 }
  ]
}
```

**VERDICT: NEEDS SORTING** - Summary mode essential for usability.

---

### CAPABILITY 6: `index` - File Indexing

**WORKS**

- 129 documents indexed
- 128,032 total tokens
- Fast, reliable file chunking

**Limitation**: After indexing, search may not find new files effectively.

---

### CAPABILITY 7: `detect_changes` - Change Detection

**WORKS** - For known indexed files.

**Limitation**: Cannot discover NEW unindexed files.

---

### CAPABILITY 8: `map` - Project Overview

**WORKS**

Provides document count, chunk counts, token totals:
- Total documents: 129
- Total tokens: 128,032

---

## Critical Findings Requiring Attention

### Issue 1: `impact_radius` Unusable Output

**Evidence**: 147K char output for moderate analysis.

**Required Fix**: Summary/compact mode with per-depth file counts.

---

### Issue 2: `search` Domain Query Noise

**Evidence**: Domain-specific queries return noisy results.

**Required Fix**: BM25/keyword fallback when semantic similarity is low.

---

### Issue 3: Dynamic Symbol Tracking Gap

**Evidence**: Plugin marketplace has 100% dynamic coupling.

**Required Fix**: Symbol manifest support for runtime-only symbols.

---

## Summary

### What Stele-Context Does Well

1. **`find_references`**: Static symbol tracking (excellent for dead-code detection)
2. **`find_definition`**: Accurate jump-to-definition
3. **`coupling`**: Good bidirectional static coupling
4. **`index`**: Fast, reliable indexing
5. **`detect_changes`**: Change detection for indexed files
6. **`map`**: Project overview with token counts

### What Needs Sorting

1. **`impact_radius`**: Summary mode for usability
2. **`search`**: BM25 fallback for domain queries
3. **Dynamic symbols**: Symbol manifest for runtime relationships
4. **New file discoverability**: Filesystem scanning mode

### Phase 7 Integration

Stele-context worked alongside Chisel and Trammel for the database refactoring planning task:
- `find_references` correctly identified FileStore and getDatabase usage
- `map` confirmed 129 documents indexed
- Dynamic symbol tracking gap confirmed for PluginRegistry

---

## Feature Complexity Matrix

| Feature | LOC | Dynamic Symbols | Semantic Depth | Runtime Coupling |
|---------|-----|-----------------|----------------|------------------|
| DynamicPluginRegistry | 296 | 100% | Medium | 100% |
| RelationshipAnalyzer | 714 | 0% | Very High | 0% |

---

## Conclusion

**Overall Assessment**: Stele-Context has a solid foundation (`find_references`, `find_definition`, `coupling` all work), but **requires sorting** on `impact_radius` (summary mode), `search` (BM25 fallback), and **dynamic symbol tracking** before it can fully support modern plugin architectures.

**Phase 7 Audit**: Found orphaned `src/plugins/index.js` (never imported), and confirmed dynamic symbol tracking gap for PluginRegistry (100% runtime coupling invisible to static analysis).

**Trammel Validation**: ✅ **COMPLETED** - Database refactoring successfully executed using Trammel workflow.

---

*Report generated: 2026-03-26*
*RecipeLab Phase 7: MCP Challenge Features + Code Audit + Database Refactoring Integration*
*Status: NEEDS SORTING*
