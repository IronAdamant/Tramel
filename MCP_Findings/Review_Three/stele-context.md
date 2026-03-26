# Stele-Context MCP Validation Report

## Executive Summary

This report documents the validation of stele-context MCP v2.0.0 against RecipeLab's Phase 7 features, specifically designed to stress-test semantic code understanding capabilities. **Four features were built to challenge stele-context**, with varying degrees of success in revealing capabilities and limitations.

---

## Features Built for Stele-Context

### Feature 1: Semantic Recipe Relationship Analyzer (Primary Challenge)

**Purpose**: Cross-module semantic relationship tracking that creates complex symbol dependencies through content analysis rather than static imports.

**Implementation**: `src/services/relationshipAnalyzer.js`

**Key Characteristics**:
- 8 relationship types (derives_from, substitutes, enhances, contradicts, seasonal_variant, cuisine_share, technique_share, ingredient_overlap)
- Semantic similarity calculated through content analysis (title, instructions, ingredients, tags)
- Runtime relationship resolution based on content, not imports
- Semantic graph building with configurable depth

**Files Created**:
- `src/services/relationshipAnalyzer.js` (560 LOC)
- `src/api/routes/relationshipRoutes.js`
- `tests/services/relationshipAnalyzer.test.js`

**MCP Interaction Points**:

| Stele-Ctx Function | Challenge Aspect | Result |
|---------------------|------------------|--------|
| `find_references` | Semantic relationships cross 8+ modules (models, services, API routes) | PARTIALLY WORKS |
| `find_definition` | Symbol jumps across service/model boundaries | WORKS |
| `search` | Semantic query "recipe relationship analysis" | RELEVANT BUT NOISY |
| `impact_radius` | Deep transitive dependency chains | UNUSABLE (too large) |
| `coupling` | Cross-module semantic relationships | WORKS (bidirectional) |
| `index` | New files with complex relationships | WORKS |

---

### Feature 2: Dynamic Import-Graph Coupling Explorer

**Purpose**: Creates complex import relationships that stress stele's coupling detection.

**Implementation**: `src/services/couplingExplorer.js`

**Key Characteristics**:
- Dynamic module registration (runtime, not static imports)
- Circular dependency detection
- Import-graph coupling metrics (fan-in, fan-out, instability)
- Tarjan's algorithm for strongly connected components

**Files Created**:
- `src/services/couplingExplorer.js` (400+ LOC)
- `src/api/routes/couplingRoutes.js`
- `tests/services/couplingExplorer.test.js`

---

### Feature 3: Multi-Phase Recipe Transformation Pipeline

**Purpose**: Orchestration across 6+ services with implicit ordering requirements.

**Implementation**: `src/services/recipeTransformationPipeline.js`

**Key Characteristics**:
- 7 pipeline phases with dependencies
- Phases: loadAndValidate → calculateNutrition → dietaryCompliance → estimateCosts → scaleRecipe → applySubstitutions → generateOutput
- Complex cross-service orchestration
- Conditional branching based on intermediate results

**Files Created**:
- `src/services/recipeTransformationPipeline.js` (500+ LOC)
- `src/api/routes/transformationRoutes.js`
- `tests/services/recipeTransformationPipeline.test.js`

---

### Feature 4: Plugin Marketplace with Dynamic Discovery (ALL THREE)

**Purpose**: Hot-reloadable plugin system that challenges both static and semantic analysis.

**Implementation**: `src/services/pluginMarketplace.js`

**Key Characteristics**:
- Dynamic plugin registration (runtime, invisible to static analysis)
- Semantic search over plugin metadata
- Dependency graph with circular dependency detection
- Hook-based extensibility

**Files Created**:
- `src/services/pluginMarketplace.js` (500+ LOC)
- `src/api/routes/marketplaceRoutes.js`
- `tests/services/pluginMarketplace.test.js`

---

## Detailed Stele-Context Analysis

### CAPABILITY 1: `find_references` - Symbol Tracking

**What Works**:
- Precise symbol tracking across modules
- Correctly identifies bidirectional relationships
- Handles import/require patterns properly

**Test Case**:
```javascript
// In relationshipAnalyzer.js
const Recipe = require('../models/Recipe');
const NutritionService = require('./nutritionService');

// Stele correctly identifies: relationshipAnalyzer → Recipe, NutritionService
```

**Challenge Found**: When symbols are used dynamically (e.g., `dynamicRegistry.getHookHandlers(hookName)`), stele cannot trace the relationship because there's no static import edge.

**VERDICT: WORKS WELL** for static import relationships. Fails for dynamic symbol resolution.

---

### CAPABILITY 2: `find_definition` - Jump to Definition

**What Works**:
- Accurate jump-to-definition
- Works across service/model boundaries
- Handles prototype methods correctly

**VERDICT: WORKS WELL**

---

### CAPABILITY 3: `search` - Semantic Search

**What Works**:
- Returns indexed files
- Supports keyword matching
- Reasonable ranking for obvious queries

**Challenge Found**: Tested with query "recipe relationship analysis" against the codebase:
- Returns relevant results but with significant noise
- Plugin metadata descriptions sometimes rank higher than actual implementation files
- Phase 6 finding confirmed: "semantic search returns irrelevant results for specific domain queries"

**Test Results**:
```
Query: "relationship analysis"
Expected: relationshipAnalyzer.js
Actual: Correct file returned, but with other service files mixed in
```

**VERDICT: PARTIALLY WORKS** - Better than Phase 6, but still needs keyword fallback for precision.

---

### CAPABILITY 4: `impact_radius` - Impact Analysis

**Critical Issue Found**: This capability produced **193K characters of output** when analyzing the relationship analyzer's impact on the codebase. The output was essentially unusable without manual parsing.

**Root Cause**:
- Impact radius calculates transitive dependents through the symbol graph
- RecipeLab's 100+ file codebase with many cross-dependencies produces massive output
- No summary mode or depth limiting available

**Test**:
```javascript
// Impact of relationshipAnalyzer.js on the codebase
stele.impact_radius({ document_path: "src/services/relationshipAnalyzer.js" })
// Output: 193,000+ characters of nested JSON
```

**VERDICT: UNUSABLE** without a summary/compact mode. This is a known issue from Phase 6.

---

### CAPABILITY 5: `coupling` - Semantic Coupling Detection

**What Works**:
- Correctly identifies bidirectional relationships
- Returns shared symbols between files
- Direction awareness (depends_on vs depended_on_by)

**Challenge Found**: Coupling is calculated from import relationships. For the Plugin Marketplace (which uses dynamic registration), coupling detection cannot see runtime-only dependencies.

**Test Results**:
```
PluginMarketplace couples with: DynamicRegistry (via require)
DynamicRegistry hook handlers: NOT visible to coupling (runtime only)
```

**VERDICT: WORKS** for static coupling. Missing dynamic/runtime coupling detection.

---

### CAPABILITY 6: `index` - File Indexing

**What Works**:
- Fast chunking
- Reliable indexing
- Automatic chunk ID generation

**Challenge Found**: After creating new files, search may not find them effectively until re-indexed.

**VERDICT: WORKS** - Reliable indexing but search relevance on new files is questionable.

---

## Summary of Findings

### What Stele-Context Does Well (Phase 7 Validation)

1. **`find_references`**: Precise symbol tracking with import graph
2. **`find_definition`**: Accurate jump-to-definition
3. **`coupling`**: Good bidirectional semantic relationship detection
4. **`index`**: Fast, reliable chunking
5. **`detect_changes`**: Correctly flags modified indexed files

### What Stele-Context Struggles With (Phase 7 Findings)

1. **`search`**: Returns irrelevant results for domain-specific queries. Query "allergen dietary compliance" still returns test files as top results.

2. **`impact_radius`**: Output is too large to use (193K chars). Needs a **summary mode with file counts per depth level**.

3. **`search`**: No **BM25/keyword fallback when semantic similarity is low**. Domain-specific queries suffer.

4. **Dynamic symbol resolution**: Runtime-only symbols (like plugin hooks) are invisible because there's no static import edge.

5. **New file discoverability**: Files created since last index are not discovered by `detect_changes` without explicit `index` call.

### Known Issues (Phase 1-6) NOT Fixed in Phase 7

These issues were identified in prior phases and remain unresolved:

1. **`search` relevance scoring** - Still weights structural patterns (Express routes, test boilerplate) over semantic meaning
2. **`impact_radius` output** - Still produces massive unstructured output
3. **`detect_changes` blind spots** - Still cannot discover new unindexed files

---

## Recommendations for Stele-Context Improvement

### Priority 1: Fix `impact_radius`

**Current Problem**: 193K character output makes the capability unusable.

**Proposed Fix**: Add a `compact: true` mode that returns:
```json
{
  "depth": 2,
  "fileCount": 15,
  "summary": [
    { "path": "src/api/routes/", "depth": 0, "count": 3 },
    { "path": "src/services/", "depth": 1, "count": 7 },
    { "path": "src/models/", "depth": 2, "count": 5 }
  ]
}
```

### Priority 2: Fix `search` with BM25 Fallback

**Current Problem**: Semantic embeddings weight structural patterns over content.

**Proposed Fix**: When semantic similarity is below threshold (e.g., 0.3), fall back to BM25 keyword matching with the query terms.

### Priority 3: Add Dynamic Symbol Tracking

**Current Problem**: Plugin hooks and runtime registrations are invisible.

**Proposed Fix**: Support a "symbol manifest" that MCP servers can register, allowing tools to see runtime-only symbol relationships.

---

## Feature Complexity Matrix

| Feature | Files | LOC | Cross-Module | Dynamic | Semantic Depth |
|---------|-------|-----|--------------|---------|----------------|
| Relationship Analyzer | 3 | 700+ | 8+ modules | Yes | Very High |
| Coupling Explorer | 3 | 500+ | High | Yes | Medium |
| Transformation Pipeline | 3 | 600+ | 6+ services | No | Medium |
| Plugin Marketplace | 3 | 600+ | Variable | Yes | Medium |

---

## Conclusion

Stele-context remains a powerful semantic code understanding tool, with `find_references` and `coupling` being its strongest features. However, `search` and `impact_radius` continue to underperform for real-world domain-specific queries. The dynamic symbol tracking gap (plugin hooks, runtime registration) represents a fundamental architectural limitation.

**Overall Assessment**: Stele-context is **production-ready for static analysis** but needs fixes for `search` (BM25 fallback), `impact_radius` (summary mode), and **dynamic symbol tracking** before it can fully support modern plugin-based architectures.

---

*Report generated: 2026-03-26*
*RecipeLab Phase 7: MCP Challenge Features*
