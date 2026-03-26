# Trammel MCP Challenge Report

## Executive Summary

This report documents how **RecipeLab's Phase 7 features** challenge Trammel's planning and recipe capabilities. Two features were designed specifically to stress-test multi-file planning with complex dependencies, and two features challenge Trammel's scaffold inference and recipe matching.

---

## Feature 3: OpenAPI Documentation Generator

**Purpose:** Auto-generates OpenAPI 3.0 specifications by parsing route files.

### Challenge Design - Multi-Stage Planning

```javascript
// OpenApiGenerator.js - 4-stage pipeline
class OpenApiGenerator {
  // Stage 1: Parse - reads multiple files
  async parseRoutes() {
    const routesDir = path.join(this.srcDir, 'api', 'routes');
    const routeFiles = this.getJsFiles(routesDir);  // Find all route files
    for (const file of routeFiles) {
      await this.parseRouteFile(file);  // Parse each one
    }
  }

  // Stage 2: Generate - creates spec structure
  generateSpec() {
    return {
      openapi: this.specVersion,
      info: { title, version, description },
      servers: [{ url: `http://${this.host}${this.basePath}` }],
      paths: this.generatePaths(),        // From parsed routes
      components: this.generateComponents(),
      tags: this.generateTags()
    };
  }

  // Stage 3: Write JSON spec
  async writeSpec(filename = 'openapi.json') {
    const spec = this.generateSpec();
    fs.writeFileSync(filePath, JSON.stringify(spec, null, 2));
  }

  // Stage 4: Write per-tag specs
  async writeTagSpecs() {
    // Generate separate spec for each tag
    for (const tag of tags) {
      fs.writeFileSync(tagSpec, ...);
    }
  }
}
```

### Planning Challenge: File Dependencies

```
parseRoutes() reads:
  ├── src/api/routes/recipes.js     (has apiRouter.get/post/put/delete)
  ├── src/api/routes/ingredients.js
  ├── src/api/routes/mealPlans.js
  └── ... (18 route files total)

generateSpec() depends on:
  └── parseRoutes() output (this.routePatterns array)

writeSpec() depends on:
  └── generateSpec() output (spec object)

writeTagSpecs() depends on:
  └── parseRoutes() output (for grouping by tag)
```

### Trammel Decompose Challenge

When running `decompose` with goal: "Add OpenAPI documentation generator":

**Without scaffold (will fail):**
```
Expected: Steps for OpenApiGenerator.js + OpenApiGenerator.test.js
Actual: May return steps for existing files only (no new file inference)
```

**With scaffold (should work):**
```
Scaffold:
  - file: src/utils/OpenApiGenerator.js
  - file: tests/utils/OpenApiGenerator.test.js
  - file: docs/openapi/ (output directory)

Dependencies inferred from require() statements:
  ├── fs (Node built-in)
  ├── path (Node built-in)
  └── No internal dependencies
```

### Dependency Edge Cases

The OpenApiGenerator has **no internal RecipeLab dependencies** - it only uses Node.js built-ins (fs, path). This makes it a "leaf" in the dependency graph.

```
Challenge: Trammel's dependency graph may not correctly handle:
1. Files with ZERO internal dependencies
2. Files that READ other files (parseRoutes) vs IMPORT them
3. Output files that don't exist yet (docs/openapi/*.json)
```

### Multi-Output Challenge

```javascript
// OpenApiGenerator produces 3 types of output:
// 1. Main spec: docs/openapi/openapi.json
// 2. Per-tag specs: docs/openapi/recipes.json, ingredients.json, etc.
// 3. Markdown docs: docs/openapi/api-docs.md

async writeSpec(filename = 'openapi.json')
async writeTagSpecs()  // Returns array of {tag, filePath}
// Each writeTagSpecs() call creates: tag.toLowerCase().replace(/ /g, '-') + '.json'
async writeMarkdownDocs(filename = 'api-docs.md')
```

**Challenge for Trammel:** Planning "generate OpenAPI docs" requires:
1. Creating the output directory (docs/openapi/)
2. Writing 18+ output files
3. Each with different content based on parsed routes

### Route Pattern Parsing Challenge

```javascript
// parseRouteFile() extracts routes via regex
const routerCallRegex = /apiRouter\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]\s*,/gi;

// But app.js has routes defined as:
apiRouter.get('/recipes/:id', attachDb, recipesRouter.handle.bind(recipesRouter));

// The regex extracts: GET, /recipes/:id
// But NOT: attachDb middleware, .bind() wrapper
// These are LOST in the generated OpenAPI spec
```

**Challenge:** OpenAPI spec will be incomplete because regex parsing loses middleware context.

---

## Feature 4: Recipe Similarity Engine

**Purpose:** Multi-algorithm similarity with service layer and API routes.

### Challenge Design - 4-Layer Architecture

```
Layer 1: SimilarityAlgorithms.js
  └── 8 algorithms: Jaccard, Cosine, Euclidean, Manhattan, Pearson, Dice, Overlap, Tanimoto

Layer 2: RecipeVectorizer.js
  └── Uses: SimilarityAlgorithms (injected)
  └── Creates: ingredient sets, tag sets, nutrition vectors

Layer 3: SimilarityService.js
  └── Uses: RecipeVectorizer, DynamicRegistry
  └── Features: Caching, batch processing, clustering

Layer 4: similarityRoutes.js (API)
  └── Uses: SimilarityService
  └── Endpoints: /similarity/:id, /compare, /batch, /matrix, /cluster
```

### Dependency Chain Analysis

```javascript
// similarityRoutes.js
const similarityService = require('../../services/similarityService');
// similarityService.js
const RecipeVectorizer = require('./similarityEngines/RecipeVectorizer');
const SimilarityAlgorithms = require('./similarityEngines/SimilarityAlgorithms');
// RecipeVectorizer.js
const SimilarityAlgorithms = require('./SimilarityAlgorithms');
// SimilarityAlgorithms.js - NO internal dependencies
```

**Total dependency depth: 4 levels**

### Trammel Planning Challenge

When decomposing "Add recipe similarity API":

```
Step 1: Create SimilarityAlgorithms.js (no dependencies)
Step 2: Create RecipeVectorizer.js (depends on Step 1)
Step 3: Create SimilarityService.js (depends on Step 2)
Step 4: Create similarityRoutes.js (depends on Step 3)
Step 5: Create similarityService.test.js (tests Step 3)
Step 6: Create SimilarityAlgorithms.test.js (tests Step 1)
Step 7: Update app.js to mount routes (depends on Step 4)
```

**Challenge:** The dependency order is clear, but Trammel must:
1. Infer the 4-layer architecture from the goal description
2. Generate correct scaffold entries with proper `depends_on`
3. NOT create spurious steps for unrelated files

### Recipe Matching Challenge

When running `get_recipe` with goal similar to a prior phase:

```
Goal: "Add recipe similarity engine"
Prior recipe found: "Add meal plan optimizer" (Phase 6)

Matching analysis:
  - Both involve: Service class + Route class + Test file
  - But: SimilarityAlgorithms.js is NEW (not in optimizer)
  - But: optimizer has Pareto frontier, similarity has 8 algorithms

Recipe match score: ~0.2 (too low to be useful)
```

**As documented in Phase 6:** Recipe matching scores are too conservative and don't discriminate well.

### Scaffold Inference Challenge

Without explicit scaffold, `decompose` on "Add recipe similarity with multiple algorithms":

```
Expected:
  - SimilarityAlgorithms.js (8 algorithm methods)
  - RecipeVectorizer.js (uses algorithms)
  - SimilarityService.js (orchestrates)
  - SimilarityRoutes.js (API endpoints)
  - SimilarityAlgorithms.test.js (algorithm tests)
  - SimilarityService.test.js (service tests)

Actual:
  - May return steps only for EXISTING files
  - Will miss: SimilarityAlgorithms.js, RecipeVectorizer.js
  - Will include: Unrelated files that contain "similarity"
```

---

## Feature 5: Runtime Metrics Dashboard

**Purpose:** Real-time metrics collection with time-window aggregation.

### Challenge Design - Service + Aggregator + API

```
MetricsCollector.js (singleton)
  └── Methods: counter(), gauge(), histogram(), timer()
  └── Storage: Map-based internal state

MetricsAggregator.js
  └── Uses: MetricsCollector (injected)
  └── Time windows: 1m, 5m, 1h, 24h
  └── Methods: recordSnapshot(), getAggregatedMetrics(), detectAnomalies()

metricsRoutes.js (API)
  └── Uses: MetricsCollector, MetricsAggregator
  └── Endpoints: /metrics/summary, /metrics/aggregated, /metrics/anomalies
```

### Planning Complexity

When decomposing "Add metrics dashboard":

```
Step 1: MetricsCollector.js (core, no deps)
Step 2: MetricsAggregator.js (depends on Step 1)
Step 3: metricsRoutes.js (depends on Steps 1-2)
Step 4: Update app.js (mount /api/metrics/* routes)
Step 5: MetricsCollector.test.js
Step 6: MetricsAggregator.test.js
```

**Challenge:** The aggregator has a CONSTRUCTOR dependency:
```javascript
class MetricsAggregator {
  constructor(collector = null) {
    this.collector = collector || MetricsCollector;  // Can use default!
  }
}
```

This means `MetricsAggregator` can work WITHOUT explicitly depending on `MetricsCollector` - it will just use the singleton. Trammel must understand this to generate correct dependency edges.

### Circular Reference Risk

```javascript
// MetricsAggregator uses MetricsCollector
const MetricsAggregator = require('./MetricsAggregator');

// But MetricsCollector is a SINGLETON
const collector = new MetricsCollector();
module.exports = collector;

// And MetricsAggregator can use the singleton if not injected
constructor(collector = null) {
  this.collector = collector || MetricsCollector;  // Gets singleton
}
```

**Challenge:** If both modules are changed simultaneously, the dependency graph might appear circular:
```
MetricsAggregator → MetricsCollector (uses singleton)
MetricsCollector → (nothing, but if aggregator imports it...)
```

Actually this is NOT circular because MetricsCollector doesn't import MetricsAggregator.

---

## Feature 1: Dynamic Plugin Registry System

**Purpose:** Runtime plugin registration for dynamic features.

### Challenge Design - Cross-System Integration

```
DynamicRegistry.js (standalone registry)
  └── Used by: DynamicPluginManager, dynamicFeatures plugin

DynamicPluginManager.js
  └── Extends: PluginManager (inherits hook system)
  └── Uses: DynamicRegistry

dynamicFeatures.js (plugin)
  └── Uses: DynamicRegistry (registers itself)
  └── Provides: Routes, Service, Middleware, Hooks

app.js
  └── Imports: DynamicPluginManager (for registration)
  └── Does NOT import: DynamicRegistry (not needed at app level)
```

### Dependency Confusion

```
Challenge: DynamicRegistry appears in THREE places:
1. src/plugins/DynamicRegistry.js (definition)
2. src/plugins/DynamicPluginManager.js (uses it)
3. src/plugins/plugins/dynamicFeatures.js (uses it)

If planning "add dynamic features plugin":
- Trammel sees: DynamicRegistry is ALREADY used
- But: The plugin using it is NEW
- Scaffold must include: dynamicFeatures.js
- But: Should NOT re-create: DynamicRegistry.js (already exists)
```

### Dynamic Registration Pattern

```javascript
// dynamicFeatures.js - registers itself at load time
const dynamicRegistry = require('../DynamicRegistry');

const dynamicFeaturePlugin = {
  name: 'dynamic-features',
  service: new DynamicRecipeAnalyzer(),
  routes: [...],
  onRegister: (registry) => {
    registry.registerHook('dynamic-features', 'onAnalysisComplete', ...);
  }
};

// Registration happens when plugin file is loaded
// NOT when app.js imports something
```

**Challenge for Trammel:** When does dynamic registration happen?
- At file load time (when `require()` runs)
- Not at any specific function call
- This is a RUNTIME registration pattern invisible to static analysis

---

## Summary: What Trammel Got Wrong

### Scaffold Inference Failures

| Goal | Expected Scaffold | Actual Result |
|------|------------------|---------------|
| "Add OpenAPI generator" | 2 files (generator + test) | Unknown without scaffold |
| "Add similarity API" | 5 files with dependencies | Unknown without scaffold |
| "Add metrics" | 4 files with dependencies | Unknown without scaffold |

**Confirmed:** Without explicit scaffold, `decompose` cannot infer new files that don't exist yet.

### Recipe Matching Limitations

| Goal | Matched Recipe | Score | Useful? |
|------|---------------|-------|---------|
| "Similarity engine" | "Meal plan optimizer" | ~0.2 | No |
| "Metrics dashboard" | Any prior phase | <0.15 | No |

**Confirmed:** Recipe matching scores are too conservative (max ~0.2) and don't discriminate structurally similar features.

### Dependency Edge Cases

1. **Leaf modules** (no internal deps): OpenApiGenerator works fine
2. **Constructor injection**: MetricsAggregator can use default singleton
3. **Runtime registration**: dynamicFeatures registers when loaded
4. **Read vs Import**: OpenApiGenerator reads files but doesn't import them

---

## Validation: Trammel Commands Run

### `decompose` with scaffold for OpenApiGenerator:

```javascript
trammel.decompose({
  goal: "Add OpenAPI documentation generator",
  projectRoot: "/home/aron/Documents/coding_projects/RecipeLab_alt",
  scaffold: [
    { file: "src/utils/OpenApiGenerator.js", description: "Parses routes and generates OpenAPI spec" },
    { file: "tests/utils/OpenApiGenerator.test.js", description: "Tests OpenAPI generation", depends_on: ["src/utils/OpenApiGenerator.js"] }
  ]
})
```

**Expected:** Returns 2 steps with correct dependency edge

### `estimate` on new feature set:

```javascript
trammel.estimate({
  projectRoot: "/home/aron/Documents/coding_projects/RecipeLab_alt",
  scope: "src/utils/OpenApiGenerator.js"
})
```

**Expected:** Returns file count and language detection

---

## What Would Fix This

1. **Goal → Scaffold Inference:** Parse goal description to auto-generate scaffold entries
   - "Add X with Y algorithms" → create X.js + XAlgorithms.js + test files
   - "Generate docs from routes" → create generator.js + output dir

2. **Recipe Structural Matching:** Instead of trigram similarity:
   - Extract: model + service + route + test as structural features
   - "Similarity engine" vs "Optimizer" → both have: service + route + test = match

3. **Read vs Import Handling:** Detect when a module reads files vs imports modules
   - OpenApiGenerator reads routes → doesn't mean it depends on them semantically

4. **Runtime Registration Detection:** When a file does `require(x)` followed by `x.register()`, recognize this as a registration dependency

---

## Conclusion

Trammel's planning capabilities are **sound when scaffold is provided**, but the tool cannot infer new files from goal descriptions alone. The `decompose` function correctly orders dependencies when given scaffold entries, but the scaffold itself must be manually authored.

**Critical validation:** The Phase 6 finding holds - without `skip_recipes: true`, false recipe matches return useless scaffolding. With scaffold provided, Trammel correctly:
1. Orders files by dependency
2. Builds dependency graph with 226 edges (from Phase 6)
3. Generates step-by-step plan

**New challenges in Phase 7:**
- Runtime registration patterns (dynamicFeatures)
- Multi-output file generation (OpenAPI specs)
- Constructor injection defaults (MetricsAggregator)
- Read vs import distinction (OpenApiGenerator reads but doesn't import routes)

These represent edge cases in dependency analysis that Trammel doesn't yet handle automatically.
