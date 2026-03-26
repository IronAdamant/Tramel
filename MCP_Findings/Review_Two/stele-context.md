# Stele-context MCP Challenge Report

## Executive Summary

This report documents how **RecipeLab's Phase 7 features** challenge Stele-context's semantic code understanding capabilities. Three features were designed specifically to stress-test symbol tracking, and one feature (Recipe Similarity Engine) was designed to challenge all three MCPs.

---

## Feature 1: Dynamic Plugin Registry System

**Purpose:** Runtime plugin registration that bypasses static import analysis.

### Challenge Design

The Dynamic Registry creates symbol relationships that are established **DYNAMICALLY at runtime**, not through static imports:

```javascript
// DynamicRegistry.js - symbol registered at runtime
class DynamicRegistry {
  registerRoute(pluginName, method, path, handler) {
    // Routes stored in Map, looked up by name at runtime
    this.routeHandlers.set(`${method}:${path}`, { handler, pluginName });
  }

  getService(serviceName) {
    return this.serviceInstances.get(serviceName); // Runtime lookup
  }
}

// dynamicFeatures.js - plugin uses dynamic registration
const dynamicFeaturePlugin = {
  service: new DynamicRecipeAnalyzer(),  // Registered dynamically
  routes: dynamicRoutes,                  // No static import linking
  middleware: dynamicMiddleware
};
```

### Stele-context Behavior Observed

After indexing and searching for `DynamicRegistry`:

```
symbol: "DynamicRegistry"
verdict: "unreferenced"
definitions: [
  { symbol: "DynamicRegistry", kind: "class", document_path: "src/plugins/DynamicRegistry.js" }
]
references: []
```

**Critical Finding:** The symbol is marked as "unreferenced" despite being actively used through the dynamic plugin system. This proves that Stele's symbol tracking relies on static import statements.

### Root Cause Analysis

1. **Static Import Assumption:** Stele's `find_references` traces symbols through `require()` statements
2. **Runtime Resolution Breakage:** DynamicRegistry uses `Map.get(serviceName)` which is a string-based runtime lookup
3. **No Import Graph for Dynamic Symbols:** There's no mechanism to track `dynamicRegistry.getService('SimilarityAlgorithms')` since the service name is a string, not a symbol

### Impact on Symbol Tracking

| Pattern | Stele Tracking | Challenge |
|---------|---------------|-----------|
| `const x = require('./x')` | Tracks symbol X | Standard case - works |
| `Map.set('dynamic', obj)` | Cannot track string keys | Breaks tracking |
| `obj['methodName']()` | Cannot resolve method symbol | Breaks symbol resolution |
| Dynamic route registration | No static import edge | Symbol appears unreferenced |

### Secondary Challenges in Feature 1

The `SimilarityAlgorithms` symbol also showed issues:

```
symbol: "SimilarityAlgorithms"
verdict: "external"
definitions: []
references: [
  { symbol: "SimilarityAlgorithms", document_path: "src/services/similarityService.js" }
]
```

The singleton export pattern `module.exports = new SimilarityAlgorithms()` is not being parsed correctly - the class definition is invisible despite the import existing.

---

## Feature 4: Recipe Similarity Engine

**Purpose:** Multi-algorithm similarity with dynamic plugin integration.

### Challenge Design

The Similarity Engine creates complex symbol chains that cross module boundaries:

```
similarityService.js
  ├── imports: SimilarityAlgorithms (singleton)
  ├── imports: RecipeVectorizer (class)
  ├── imports: DynamicRegistry (runtime lookup)
  │
  ├── SimilarityAlgorithms.calculateJaccard()     <- Dynamic method call
  ├── SimilarityAlgorithms.calculateCosine()      <- Dynamic method call
  └── dynamicRegistry.getService('hookHandler')  <- String-based lookup
```

### Symbol Resolution Chain Test

When searching for `calculateJaccard`:

```
Expected: Found in SimilarityAlgorithms
Actual: NOT FOUND as a tracked symbol
Reason: Method is called via algorithm object, not direct symbol reference
```

### Dynamic Hook Integration

```javascript
// similarityService.js - invokes dynamic hooks at runtime
invokeHook(hookName, context) {
  const handlers = dynamicRegistry.getHookHandlers(hookName);
  //                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^- String-based lookup
  // handlers is array of {handler, pluginName} from dynamic registration
}
```

This creates a call chain that Stele cannot trace:
1. User calls `/api/similarity/compare`
2. `similarityRoutes.js` calls `similarityService.calculateSimilarity()`
3. `calculateSimilarity()` calls `vectorizer.vectorize()`
4. `vectorize()` calls `algorithms.calculateJaccard()`
5. Result flows back through the chain

**Stele's Limitation:** Without static import edges for each step, the entire call chain appears as separate, unconnected symbols.

---

## Feature 5: Runtime Metrics Dashboard

**Purpose:** Real-time metrics with time-window aggregation.

### Challenge Design

```javascript
// MetricsCollector.js - singleton with dynamic registration
const collector = new MetricsCollector();
module.exports = collector;

// MetricsAggregator.js - aggregates across time windows
class MetricsAggregator {
  recordSnapshot() {
    const metrics = this.collector.getAllMetrics();
    // Metrics collected dynamically, stored in Maps
  }
}
```

### Symbol Tracking in Aggregator

The `MetricsAggregator` depends on `MetricsCollector` but:
- Both are singletons
- Both use internal Maps for storage
- Time-window data is accessed via string keys (`'1m'`, `'5m'`)

This pattern produces symbol references that Stele cannot properly attribute.

---

## Summary: What Stele-context Got Wrong

### 1. False Positives (Should be referenced, marked unreferenced)
- `DynamicRegistry` - Used via dynamicRegistry module but marked "unreferenced"
- `SimilarityAlgorithms.calculateJaccard` - Called dynamically but method not tracked

### 2. False Negatives (Should have definitions, marked external)
- `SimilarityAlgorithms` class - Defined in SimilarityAlgorithms.js but marked "external"

### 3. Structural Blindness
- Dynamic Registry patterns (Map-based runtime lookup)
- String-keyed service discovery
- Plugin-based routing without static edges

---

## What Would Fix This

1. **String-based Symbol Tracking:** Track symbols that are looked up via strings, not just imports
2. **Runtime Registry Index:** Build a secondary index of dynamic registrations
3. **Singleton Pattern Support:** Better handling of `module.exports = new Class()` patterns
4. **Call Graph Inference:** When method is called on object from require, trace the edge

---

## Test Coverage for These Findings

| Feature | Files | Tests | Status |
|---------|-------|-------|--------|
| Dynamic Registry | 3 | 14 test cases | Written, framework mismatch |
| Similarity Engine | 4 | 25+ test cases | Written, framework mismatch |
| Metrics Dashboard | 3 | 20+ test cases | Written, framework mismatch |

---

## Conclusion

Stele-context's fundamental assumption is that code relationships are established through **static import statements**. When features use dynamic registration patterns (runtime string-based lookups, Map-based registries, plugin systems), the tool becomes blind to these relationships.

This is not a bug - it's a design limitation of semantic analysis based on static parsing. Runtime symbol resolution is fundamentally unobservable without execution traces.

**Validation:** The `find_references` tool correctly identifies that `DynamicRegistry` has zero static references despite being used extensively. This proves the tool is working as designed, but the design cannot see runtime patterns.
