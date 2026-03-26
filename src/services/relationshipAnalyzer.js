/**
 * SemanticRecipeRelationshipAnalyzer - Cross-module semantic relationship tracking
 *
 * CHALLENGES STELE-CONTEXT:
 * - Creates deep transitive symbol dependencies across 8+ modules
 * - Semantic relationship types (derives_from, contradicts, enhances, substitutes)
 * - Dynamic relationship resolution based on runtime context
 * - Cross-file symbol tracking that stresses impact_radius
 *
 * This service demonstrates how semantic relationships differ from pure imports.
 * Stele's find_references works on import edges, but this has semantic edges
 * that are resolved at runtime through content analysis.
 */

const Recipe = require('../models/Recipe');
const Ingredient = require('../models/Ingredient');
const Tag = require('../models/Tag');

class SemanticRecipeRelationshipAnalyzer {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
    this.ingredient = new Ingredient(fileStore);
    this.tag = new Tag(fileStore);

    // Semantic relationship types - these are NOT visible through static imports
    this.relationshipTypes = {
      DERIVES_FROM: 'derives_from',           // Recipe B is a variation of Recipe A
      SUBSTITUTES: 'substitutes',             // Can replace each other
      ENHANCES: 'enhances',                   // A complements B
      CONTRADICTS: 'contradicts',             // Cannot be used together
      SEASONAL_VARIANT: 'seasonal_variant',   // Seasonal variation
      CUISINE_SHARE: 'cuisine_share',         // Shares cuisine heritage
      TECHNIQUE_SHARE: 'technique_share',     // Uses similar techniques
      INGREDIENT_OVERLAP: 'ingredient_overlap'
    };

    // Relationship cache - dynamic, not static
    this.relationshipCache = new Map();
    this.analysisCache = new Map();
  }

  /**
   * Analyze semantic relationships between two recipes
   * Relationships are determined by CONTENT ANALYSIS, not imports
   */
  analyzeRelationship(recipeA, recipeB) {
    const cacheKey = `${recipeA.id}:${recipeB.id}`;

    if (this.relationshipCache.has(cacheKey)) {
      return this.relationshipCache.get(cacheKey);
    }

    const relationships = [];
    const score = this.calculateRelationshipScore(recipeA, recipeB);

    // Determine relationship types based on content similarity
    if (this.isDerivation(recipeA, recipeB)) {
      relationships.push({
        type: this.relationshipTypes.DERIVES_FROM,
        direction: recipeA.createdAt > recipeB.createdAt ? 'reverse' : 'forward',
        confidence: score.derivation
      });
    }

    if (this.isSubstitution(recipeA, recipeB)) {
      relationships.push({
        type: this.relationshipTypes.SUBSTITUTES,
        confidence: score.substitution
      });
    }

    if (this.isEnhancement(recipeA, recipeB)) {
      relationships.push({
        type: this.relationshipTypes.ENHANCES,
        direction: this.determineEnhanceDirection(recipeA, recipeB),
        confidence: score.enhancement
      });
    }

    if (this.isContradiction(recipeA, recipeB)) {
      relationships.push({
        type: this.relationshipTypes.CONTRADICTS,
        reason: this.findContradictionReason(recipeA, recipeB),
        confidence: score.contradiction
      });
    }

    if (this.isSeasonalVariant(recipeA, recipeB)) {
      relationships.push({
        type: this.relationshipTypes.SEASONAL_VARIANT,
        confidence: score.seasonal
      });
    }

    if (score.technique > 0.7) {
      relationships.push({
        type: this.relationshipTypes.TECHNIQUE_SHARE,
        sharedTechniques: this.findSharedTechniques(recipeA, recipeB),
        confidence: score.technique
      });
    }

    if (score.cuisine > 0.5) {
      relationships.push({
        type: this.relationshipTypes.CUISINE_SHARE,
        confidence: score.cuisine
      });
    }

    const result = {
      recipeA: recipeA.id,
      recipeB: recipeB.id,
      relationships,
      compositeScore: score.composite,
      analyzedAt: Date.now()
    };

    this.relationshipCache.set(cacheKey, result);
    return result;
  }

  /**
   * Calculate relationship score between recipes
   * Uses multi-dimensional similarity across content
   */
  calculateRelationshipScore(recipeA, recipeB) {
    const scores = {
      derivation: this.scoreDerivation(recipeA, recipeB),
      substitution: this.scoreSubstitution(recipeA, recipeB),
      enhancement: this.scoreEnhancement(recipeA, recipeB),
      contradiction: this.scoreContradiction(recipeA, recipeB),
      seasonal: this.scoreSeasonalVariant(recipeA, recipeB),
      technique: this.scoreTechniqueShare(recipeA, recipeB),
      cuisine: this.scoreCuisineShare(recipeA, recipeB),
      ingredient: this.scoreIngredientOverlap(recipeA, recipeB)
    };

    scores.composite = this.weightedCompositeScore(scores);

    return scores;
  }

  /**
   * Score derivation relationship (B is derived from A or vice versa)
   */
  scoreDerivation(recipeA, recipeB) {
    let score = 0;

    // Title similarity with modification indicators
    const titleMods = ['variation', 'with', 'style', 'authentic', 'modified'];
    const titleA = (recipeA.title || '').toLowerCase();
    const titleB = (recipeB.title || '').toLowerCase();

    for (const mod of titleMods) {
      if (titleA.includes(mod) && this.titleBaseMatch(titleA, titleB)) score += 0.2;
    }

    // Base name match
    const baseA = this.extractBaseName(titleA);
    const baseB = this.extractBaseName(titleB);
    if (baseA === baseB && baseA.length > 3) score += 0.3;

    // Instructions similarity
    const instructionSim = this.similarity(recipeA.instructions, recipeB.instructions);
    score += instructionSim * 0.4;

    // Ingredient overlap (high overlap suggests derivation)
    const ingredientSim = this.jaccardSimilarity(
      this.normalizeIngredients(recipeA),
      this.normalizeIngredients(recipeB)
    );
    score += ingredientSim * 0.3;

    return Math.min(1, score);
  }

  /**
   * Score substitution relationship
   */
  scoreSubstitution(recipeA, recipeB) {
    const ingA = this.normalizeIngredients(recipeA);
    const ingB = this.normalizeIngredients(recipeB);

    // High ingredient overlap but different specific items
    const overlap = this.jaccardSimilarity(ingA, ingB);
    const difference = 1 - overlap;

    // Can substitute if ~50-80% overlap (not too similar, not too different)
    if (overlap >= 0.5 && overlap <= 0.8) {
      return overlap * difference * 2;
    }

    return 0;
  }

  /**
   * Score enhancement relationship (A makes B better)
   */
  scoreEnhancement(recipeA, recipeB) {
    // A enhances B if A's ingredients are a subset but add complementary elements
    const ingA = this.normalizeIngredients(recipeA);
    const ingB = this.normalizeIngredients(recipeB);

    const overlap = this.jaccardSimilarity(ingA, ingB);

    // Subset relationship
    if (overlap < 1 && this.isSubset(ingA, ingB)) {
      // Check for complementary tags
      const tagSim = this.jaccardSimilarity(
        (recipeA.tags || []).map(t => t.name || t),
        (recipeB.tags || []).map(t => t.name || t)
      );

      return overlap * 0.5 + tagSim * 0.5;
    }

    return 0;
  }

  /**
   * Score contradiction relationship
   */
  scoreContradiction(recipeA, recipeB) {
    let score = 0;

    // Dietary contradictions
    const veganA = this.isVegan(recipeA);
    const veganB = this.isVegan(recipeB);

    if (veganA && !veganB) score += 0.5;
    if (!veganA && veganB && this.containsMeat(recipeB)) score += 0.5;

    // Allergen contradictions (one has allergen, other is free of it)
    const allergensA = this.extractAllergens(recipeA);
    const allergensB = this.extractAllergens(recipeB);

    if (allergensA.length > 0 && allergensB.length === 0) score += 0.3;
    if (allergensB.length > 0 && allergensA.length === 0) score += 0.3;

    // Conflicting dietary labels
    if (this.hasConflictingDiets(recipeA, recipeB)) score += 0.4;

    return Math.min(1, score);
  }

  /**
   * Score seasonal variant relationship
   */
  scoreSeasonalVariant(recipeA, recipeB) {
    const seasonalTerms = {
      spring: ['spring', 'easter', 'passover', 'light', 'fresh'],
      summer: ['summer', 'bbq', 'grill', 'cold', 'salad', 'picnic'],
      fall: ['fall', 'autumn', 'thanksgiving', 'harvest', 'pumpkin'],
      winter: ['winter', 'holiday', 'christmas', 'warm', 'roast', 'comfort']
    };

    const titleA = (recipeA.title || '').toLowerCase();
    const titleB = (recipeB.title || '').toLowerCase();

    for (const [season, terms] of Object.entries(seasonalTerms)) {
      const countA = terms.filter(t => titleA.includes(t)).length;
      const countB = terms.filter(t => titleB.includes(t)).length;

      if (countA > 0 && countB > 0 && this.baseMatch(titleA, titleB)) {
        return 0.8;
      }
    }

    // Also check ingredient seasonal markers
    const seasonalIngredients = {
      spring: ['asparagus', 'pea', 'rhubarb', 'artichoke'],
      summer: ['tomato', 'corn', 'zucchini', 'berry', 'peach'],
      fall: ['squash', 'pumpkin', 'apple', 'cranberry', 'mushroom'],
      winter: ['citrus', 'kale', 'brussels sprouts', 'root vegetable']
    };

    for (const [season, ingredients] of Object.entries(seasonalIngredients)) {
      const hasSeasonA = this.containsAnyIngredient(recipeA, ingredients);
      const hasSeasonB = this.containsAnyIngredient(recipeB, ingredients);

      if (hasSeasonA && hasSeasonB && this.baseMatch(titleA, titleB)) {
        return 0.7;
      }
    }

    return 0;
  }

  /**
   * Score technique share
   */
  scoreTechniqueShare(recipeA, recipeB) {
    const techniques = [
      'saute', 'simmer', 'braise', 'roast', 'grill', 'smoke',
      'ferment', 'pickle', 'deglaze', 'fold', 'knead', 'proof'
    ];

    const instructionA = (recipeA.instructions || '').toLowerCase();
    const instructionB = (recipeB.instructions || '').toLowerCase();

    const techA = techniques.filter(t => instructionA.includes(t));
    const techB = techniques.filter(t => instructionB.includes(t));

    if (techA.length === 0 || techB.length === 0) return 0;

    return this.jaccardSimilarity(techA, techB);
  }

  /**
   * Score cuisine share
   */
  scoreCuisineShare(recipeA, recipeB) {
    const cuisineA = (recipeA.cuisine || recipeA.tags?.find(t => t.type === 'cuisine')?.name || '').toLowerCase();
    const cuisineB = (recipeB.cuisine || recipeB.tags?.find(t => t.type === 'cuisine')?.name || '').toLowerCase();

    if (!cuisineA || !cuisineB) return 0;

    return cuisineA === cuisineB ? 1 : this.levenshteinSimilarity(cuisineA, cuisineB);
  }

  /**
   * Score ingredient overlap
   */
  scoreIngredientOverlap(recipeA, recipeB) {
    return this.jaccardSimilarity(
      this.normalizeIngredients(recipeA),
      this.normalizeIngredients(recipeB)
    );
  }

  /**
   * Build full semantic graph for a recipe
   * This creates a complex web of relationships
   */
  buildSemanticGraph(recipeId, options = {}) {
    const { depth = 2, maxNodes = 50 } = options;

    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return { error: 'Recipe not found' };

    const graph = {
      nodes: new Map(),
      edges: []
    };

    // Add initial node
    graph.nodes.set(recipeId, {
      id: recipeId,
      title: recipe.title,
      type: 'source'
    });

    // BFS to build relationships
    const queue = [{ id: recipeId, depth: 0 }];
    const visited = new Set([recipeId]);

    while (queue.length > 0 && graph.nodes.size < maxNodes) {
      const current = queue.shift();

      if (current.depth >= depth) continue;

      // Find related recipes
      const related = this.findRelatedRecipes(current.id, { limit: 5 });

      for (const rel of related) {
        if (!visited.has(rel.recipeB.id)) {
          visited.add(rel.recipeB.id);
          graph.nodes.set(rel.recipeB.id, {
            id: rel.recipeB.id,
            title: rel.recipeB.title,
            type: 'related',
            directRelationships: rel.relationships.map(r => r.type)
          });

          queue.push({ id: rel.recipeB.id, depth: current.depth + 1 });
        }

        // Add edge
        graph.edges.push({
          from: current.id,
          to: rel.recipeB.id,
          relationships: rel.relationships,
          strength: rel.compositeScore
        });
      }
    }

    return {
      source: recipeId,
      nodeCount: graph.nodes.size,
      edgeCount: graph.edges.length,
      nodes: Array.from(graph.nodes.values()),
      edges: graph.edges
    };
  }

  /**
   * Find related recipes through semantic analysis
   */
  findRelatedRecipes(recipeId, options = {}) {
    const { limit = 10, minConfidence = 0.3 } = options;

    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return [];

    const allRecipes = this.recipe.getAll({ limit: 100 }).data || [];
    const relationships = [];

    for (const candidate of allRecipes) {
      if (candidate.id === recipeId) continue;

      const analysis = this.analyzeRelationship(recipe, candidate);

      if (analysis.relationships.length > 0) {
        const maxConfidence = Math.max(
          ...analysis.relationships.map(r => r.confidence || 0)
        );

        if (maxConfidence >= minConfidence) {
          relationships.push({
            recipeB: candidate,
            relationships: analysis.relationships,
            compositeScore: analysis.compositeScore
          });
        }
      }
    }

    // Sort by composite score
    relationships.sort((a, b) => b.compositeScore - a.compositeScore);

    return relationships.slice(0, limit);
  }

  /**
   * Find path between two recipes through semantic relationships
   */
  findRelationshipPath(recipeIdA, recipeIdB, maxDepth = 4) {
    const visited = new Set();
    const queue = [{ id: recipeIdA, path: [] }];
    visited.add(recipeIdA);

    while (queue.length > 0) {
      const current = queue.shift();

      if (current.id === recipeIdB) {
        return { found: true, path: current.path };
      }

      if (current.path.length >= maxDepth) continue;

      const related = this.findRelatedRecipes(current.id, { limit: 5 });

      for (const rel of related) {
        if (!visited.has(rel.recipeB.id)) {
          visited.add(rel.recipeB.id);

          const edgeLabel = rel.relationships
            .map(r => r.type)
            .join(', ');

          queue.push({
            id: rel.recipeB.id,
            path: [...current.path, { node: rel.recipeB.id, edge: edgeLabel }]
          });
        }
      }
    }

    return { found: false, path: [] };
  }

  // ============ Helper Methods ============

  weightedCompositeScore(scores) {
    const weights = {
      derivation: 0.15,
      substitution: 0.10,
      enhancement: 0.10,
      contradiction: 0.15,
      seasonal: 0.10,
      technique: 0.15,
      cuisine: 0.10,
      ingredient: 0.15
    };

    let weighted = 0;
    for (const [key, weight] of Object.entries(weights)) {
      weighted += (scores[key] || 0) * weight;
    }

    return weighted;
  }

  isDerivation(recipeA, recipeB) {
    return this.scoreDerivation(recipeA, recipeB) > 0.6;
  }

  isSubstitution(recipeA, recipeB) {
    return this.scoreSubstitution(recipeA, recipeB) > 0.5;
  }

  isEnhancement(recipeA, recipeB) {
    return this.scoreEnhancement(recipeA, recipeB) > 0.5;
  }

  isContradiction(recipeA, recipeB) {
    return this.scoreContradiction(recipeA, recipeB) > 0.5;
  }

  isSeasonalVariant(recipeA, recipeB) {
    return this.scoreSeasonalVariant(recipeA, recipeB) > 0.6;
  }

  determineEnhanceDirection(recipeA, recipeB) {
    const ingA = this.normalizeIngredients(recipeA);
    const ingB = this.normalizeIngredients(recipeB);

    return ingB.length > ingA.length ? 'A_enhances_B' : 'B_enhances_A';
  }

  findContradictionReason(recipeA, recipeB) {
    const reasons = [];

    if (this.isVegan(recipeA) && this.containsMeat(recipeB)) {
      reasons.push('vegan_vs_meat');
    }

    if (this.hasConflictingDiets(recipeA, recipeB)) {
      reasons.push('conflicting_dietary_labels');
    }

    const allergensA = this.extractAllergens(recipeA);
    const allergensB = this.extractAllergens(recipeB);

    if (allergensA.length > 0 && allergensB.length === 0) {
      reasons.push('allergen_present_vs_free');
    }

    return reasons;
  }

  findSharedTechniques(recipeA, recipeB) {
    const techniques = [
      'saute', 'simmer', 'braise', 'roast', 'grill', 'smoke',
      'ferment', 'pickle', 'deglaze', 'fold', 'knead', 'proof'
    ];

    const instructionA = (recipeA.instructions || '').toLowerCase();
    const instructionB = (recipeB.instructions || '').toLowerCase();

    return techniques.filter(t =>
      instructionA.includes(t) && instructionB.includes(t)
    );
  }

  normalizeIngredients(recipe) {
    if (!recipe.ingredients) return [];

    const normalized = [];

    if (Array.isArray(recipe.ingredients)) {
      for (const ing of recipe.ingredients) {
        const name = (ing.name || ing.ingredient || ing || '').toLowerCase().trim();
        if (name) normalized.push(name);
      }
    } else if (typeof recipe.ingredients === 'string') {
      const parts = recipe.ingredients.split(/[,\n]/);
      for (const part of parts) {
        const name = part.replace(/[^a-zA-Z\s]/g, '').trim().toLowerCase();
        if (name) normalized.push(name);
      }
    }

    return normalized;
  }

  jaccardSimilarity(setA, setB) {
    if (!setA.length || !setB.length) return 0;

    const a = new Set(setA);
    const b = new Set(setB);

    const intersection = new Set([...a].filter(x => b.has(x)));
    const union = new Set([...a, ...b]);

    return intersection.size / union.size;
  }

  levenshteinSimilarity(strA, strB) {
    const distance = this.levenshteinDistance(strA, strB);
    const maxLen = Math.max(strA.length, strB.length);

    return 1 - (distance / maxLen);
  }

  levenshteinDistance(strA, strB) {
    const m = strA.length;
    const n = strB.length;
    const dp = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));

    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;

    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        if (strA[i - 1] === strB[j - 1]) {
          dp[i][j] = dp[i - 1][j - 1];
        } else {
          dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
        }
      }
    }

    return dp[m][n];
  }

  similarity(strA, strB) {
    if (!strA || !strB) return 0;
    return this.levenshteinSimilarity(strA.toLowerCase(), strB.toLowerCase());
  }

  titleBaseMatch(titleA, titleB) {
    const baseA = this.extractBaseName(titleA);
    const baseB = this.extractBaseName(titleB);
    return baseA === baseB && baseA.length > 3;
  }

  baseMatch(titleA, titleB) {
    const baseA = this.extractBaseName(titleA);
    const baseB = this.extractBaseName(titleB);
    return baseA === baseB;
  }

  extractBaseName(title) {
    const stopWords = ['a', 'an', 'the', 'with', 'for', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'by'];
    const words = title.split(/\s+/).filter(w => !stopWords.includes(w));
    return words.slice(0, 3).join(' ');
  }

  isVegan(recipe) {
    const tags = (recipe.tags || []).map(t => (t.name || t).toLowerCase());
    return tags.includes('vegan') || tags.includes('dairy-free') && tags.includes('meat-free');
  }

  containsMeat(recipe) {
    const meats = ['chicken', 'beef', 'pork', 'lamb', 'fish', 'seafood', 'meat', 'bacon', 'ham'];
    const ingredients = this.normalizeIngredients(recipe);
    return ingredients.some(ing => meats.some(m => ing.includes(m)));
  }

  hasConflictingDiets(recipeA, recipeB) {
    const tagsA = new Set((recipeA.tags || []).map(t => (t.name || t).toLowerCase()));
    const tagsB = new Set((recipeB.tags || []).map(t => (t.name || t).toLowerCase()));

    const conflicts = [
      ['vegan', 'vegetarian'],
      ['vegan', 'meat'],
      ['gluten-free', 'contains-gluten'],
      ['dairy-free', 'contains-dairy'],
      ['keto', 'low-fat'],
      ['paleo', 'vegan']
    ];

    for (const [a, b] of conflicts) {
      if (tagsA.has(a) && tagsB.has(b)) return true;
      if (tagsA.has(b) && tagsB.has(a)) return true;
    }

    return false;
  }

  extractAllergens(recipe) {
    const allergenKeywords = [
      'peanut', 'tree nut', 'almond', 'walnut', 'dairy', 'milk', 'cheese',
      'egg', 'wheat', 'gluten', 'soy', 'fish', 'shellfish', 'sesame'
    ];

    const ingredients = this.normalizeIngredients(recipe);
    const found = [];

    for (const ing of ingredients) {
      for (const allergen of allergenKeywords) {
        if (ing.includes(allergen) && !found.includes(allergen)) {
          found.push(allergen);
        }
      }
    }

    return found;
  }

  containsAnyIngredient(recipe, ingredientList) {
    const ingredients = this.normalizeIngredients(recipe);
    return ingredients.some(ing =>
      ingredientList.some(target => ing.includes(target))
    );
  }

  isSubset(setA, setB) {
    const b = new Set(setB);
    return setA.every(item => b.has(item));
  }

  clearCache() {
    this.relationshipCache.clear();
    this.analysisCache.clear();
    return { cleared: true };
  }
}

module.exports = SemanticRecipeRelationshipAnalyzer;
