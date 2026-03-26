# CLAUDE.md — RecipeLab

## Purpose

RecipeLab is a **local-first Recipe & Meal Planner API** built as a dedicated test project for validating three MCP servers: **Chisel**, **Stele-context**, and **Trammel**.

The codebase is intentionally designed to stress-test MCP capabilities that showed gaps during ConsistencyHub audits (Phases I–I.14). Every architectural decision should create signal for these tools.

## MCP Validation Results (7 Phases Complete)

Detailed findings per phase in `MCP_Findings/Phase 1 - 2/` through `MCP_Findings/Phase_7/`.

### Chisel — Code Intelligence

**VALIDATED (works):**
- [x] `coverage_gap` correctly identifies tested vs untested code — fixed in Phase 4 (require() parser)
- [x] `diff_impact` provides actionable guidance — traces import chains to impacted tests, best Chisel feature
- [x] `suggest_tests` recommends meaningful test targets — 48/21/49 granular suggestions post-Phase 4 fix
- [x] `churn` reliable across all 6 phases
- [x] `test_gaps` correctly ranks untested functions by churn risk

**NOT FIXED — needs MCP server code changes:**
- [ ] `coupling` returns 0.0 for ALL files across all 6 phases. Root cause: requires multi-author co-change history. Single-author bulk commits produce zero signal. **Fix needed: add import-graph static analysis as coupling source.**
- [ ] `suggest_tests` / `test_gaps` / `risk_map` cannot see untracked/uncommitted files. **Fix needed: analyze working tree, not just git history.**
- [ ] `coverage_gap` is binary (0.0 or 1.0) with no partial coverage. **Fix needed: weighted scoring based on import proximity.**
- [ ] `risk_map` doesn't warn when 3+ components are uniform, making composite scores misleading.

**Breakthrough moment:** Phase 4 — require() parser fix took test_edges from 0 → 7,209 and unblocked suggest_tests, coverage_gap, and stale_tests.

### Stele-context — Semantic Code Understanding

**VALIDATED (works):**
- [x] `find_references` precisely tracks symbols across modules — verdict field (referenced/unreferenced) is excellent for dead-code checks
- [x] `find_definition` accurate jump-to-definition
- [x] `detect_changes` reliably flags modified indexed files
- [x] `index` fast and reliable chunking
- [x] `coupling` (semantic) provides bidirectional relationships with shared symbols — Phase 4 standout

**NOT FIXED — needs MCP server code changes:**
- [ ] `search` (semantic) returns irrelevant results for specific domain queries. Phase 6: "allergen dietary compliance" returned units.test.js as #1. **Fix needed: BM25/keyword fallback when semantic similarity is low; domain-aware re-ranking.**
- [ ] `impact_radius` output is too large to use (193K chars for Recipe.js). **Fix needed: summary mode with file counts per depth level, path filtering.**
- [ ] `detect_changes` cannot discover new unindexed files. **Fix needed: optional filesystem scan mode.**
- [ ] `search` should boost recently-indexed content or allow timestamp filtering.

**Breakthrough moment:** Phase 4 — default import classification fixed; find_references became fully functional for CommonJS patterns.

### Trammel — Planning & Recipes

**VALIDATED (works):**
- [x] `claim_step` 100% reliable in single-agent workflows (28/28 successes)
- [x] `complete_plan` excellent for single-agent batch completion
- [x] `decompose` with `scaffold` produces correct dependency-aware steps (270 edges in Phase 7)
- [x] `estimate` gives reasonable file counts and language detection
- [x] Dependency graph accurately maps import chains
- [x] `decompose` + `create_plan` + `claim_step` + `record_step` + `complete_plan` full workflow validated end-to-end (Phase 7: 5-step database refactor, all passed)

**NOT FIXED — needs MCP server code changes:**
- [ ] `decompose` without scaffold cannot infer new files from goal description. Phase 3: returned 492 disconnected steps. **Fix needed: goal-text NLP to generate scaffold entries automatically.**
- [ ] Recipe matching scores too conservative (max ~0.2) and doesn't discriminate well between structurally similar tasks. **Fix needed: extract structural patterns (model+service+route+test) as matching features.**
- [ ] Relevance scoring on non-scaffold steps is near-binary (0.0–0.03). **Fix needed: graduated scoring based on goal keyword proximity.**
- [ ] No "apply recipe as scaffold" workflow. **Fix needed: recipe → scaffold conversion so matched recipes auto-generate file specs.**

**Breakthrough moment:** Phase 7 — Full end-to-end Trammel workflow validated: `decompose` with scaffold (2 creates, 3 updates), 270 dependency edges, 5-step plan executed successfully. Recipe saved automatically via `complete_plan`.

### Remaining Work (Estimated 2-3 Phases)

**Phase 7 target — Chisel fixes:**
1. Import-graph coupling (static analysis, not co-change dependent)
2. Working-tree awareness for untracked files
3. Graduated coverage_gap scoring

**Phase 8 target — Stele-context fixes:**
1. BM25/keyword fallback for semantic search
2. impact_radius summary mode
3. New-file filesystem scanning

**Phase 9 target — Trammel fixes:**
1. Goal-text → scaffold inference
2. Structural recipe matching features
3. Recipe → scaffold conversion workflow

## Tech Stack
- **Runtime**: Node.js (or Bun)
- **Database**: SQLite via better-sqlite3 (Phase 7: migrated from FileStore JSON)
- **API**: Express (24 routes)
- **Tests**: Jest + Babel (same as ConsistencyHub for apples-to-apples MCP comparison)
- **CLI**: Commander.js

## Architecture (Design for MCP Signal)

### Module Structure
```
src/
  models/          — Recipe, Ingredient, Tag, MealPlan, ShoppingList, Collection, DietaryProfile, CookingLog (8)
  api/routes/      — CRUD + service routes (24 files, +6 from Phase 7)
  services/        — Search, MealPlanner, ShoppingList, Nutrition, RecipeScaling, Collection, DietaryCompliance, Recommendation, CostEstimation + Phase 7: SimilarityService, CouplingExplorer, RelationshipAnalyzer, WorkflowEngine, MetricsAggregator, PluginMarketplace, RecipeTransformationPipeline (16+)
  importers/       — JSON, CSV, Paprika, Cookmate (4, NO tests — deliberate gap)
  exporters/       — JSON, CSV, Markdown, Paprika (4, NO tests — deliberate gap)
  plugins/         — Plugin system with 18 hooks + Phase 7: DynamicRegistry, DynamicPluginManager
  data/            — Nutrition, density, allergen, seasonal, prices (5)
  db/              — Phase 7: SQLite wrapper (sqlite.js), migration system (migrations.js), schema (schema.js)
  cli/             — Commander.js CLI
  utils/           — Validation, units, conversion, conversionEngine + Phase 7: CircularDependencyDetector, OpenApiGenerator
public/            — Web UI: 8 pages + CSS + JS
tests/             — 564 tests + Phase 7 additions
```

### Deliberate Test Gaps (for Chisel coverage_gap validation)
- `src/importers/*` — 4 files, zero tests
- `src/exporters/*` — 4 files, zero tests
- `src/services/collectionService.js` — no tests (Phase 6)
- `src/services/costEstimationService.js` — no tests (Phase 6)
- `src/cli/index.js` — no tests (highest risk_map score at 0.49)

## Completed Phases

1. **Phase 1** (2026-03-24): Models, CRUD API, basic CLI, Jest tests — 305 tests
2. **Phase 2** (2026-03-24): Search + import/export (4 formats) — MCP baseline
3. **Phase 3** (2026-03-24): Meal planner, shopping list, nutrition — 377 tests
4. **Phase 4** (2026-03-24): Plugin system, recipe scaling, conversion engine — 470 tests, **MCP breakthrough** (require() parser fixed)
5. **Phase 5** (2026-03-25): Web UI (8 pages) — 496 tests
6. **Phase 6** (2026-03-25): Collections, dietary compliance, recommendations — 564 tests
7. **Phase 7** (2026-03-26): SQLite database migration, dynamic plugin system, coupling/similarity/workflow services — **Trammel fully validated** (end-to-end decompose → plan → execute → complete)

## Planned Phases (MCP Server Fixes)

8. **Phase 8**: Fix Stele search (BM25 fallback), impact_radius summary mode
9. **Phase 9**: Fix Trammel scaffold inference, structural recipe matching
10. **Phase 10**: Fix Chisel coupling (import-graph analysis), working-tree awareness

## Environment
- **Installed tools:** Node.js, npm, Bun, Python
- **npm global prefix:** `~/.npm-global`
- **Local bin path:** `~/.local/bin`

## Git Configuration
- Username: IronAdamant
- Email: 18153828+IronAdamant@users.noreply.github.com
