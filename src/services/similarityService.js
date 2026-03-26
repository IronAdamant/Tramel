/**
 * SimilarityService - Main service for recipe similarity calculations
 *
 * This challenges ALL THREE MCPs:
 *
 * STEFE-CONTEXT:
 * - Integrates with dynamic plugin system
 * - Uses runtime hook system for extending similarity calculations
 * - Dynamic service method resolution
 *
 * CHISEL:
 * - Multiple algorithm branches need coverage
 * - Complex caching logic needs testing
 * - Plugin hook integration points need coverage
 *
 * TRAMMEL:
 * - Complex multi-file dependency planning
 * - Algorithm implementations -> Vectorizer -> Service -> API
 */

const RecipeVectorizer = require('./similarityEngines/RecipeVectorizer');
const SimilarityAlgorithms = require('./similarityEngines/SimilarityAlgorithms');
const dynamicRegistry = require('../plugins/DynamicRegistry');

class SimilarityService {
  constructor(fileStore = null) {
    this.store = fileStore;
    this.vectorizer = new RecipeVectorizer();
    this.algorithms = SimilarityAlgorithms;
    this.cache = new Map();
    this.cacheEnabled = true;
    this.cacheMaxSize = 1000;
    this.stats = {
      calculations: 0,
      cacheHits: 0,
      cacheMisses: 0
    };
  }

  /**
   * Generate cache key for similarity calculation
   */
  getCacheKey(recipeIdA, recipeIdB, options = {}) {
    const sorted = [recipeIdA, recipeIdB].sort();
    const optionKey = JSON.stringify(options);
    return `${sorted[0]}:${sorted[1]}:${optionKey}`;
  }

  /**
   * Get from cache if enabled
   */
  getCached(recipeIdA, recipeIdB, options) {
    if (!this.cacheEnabled) return null;

    const key = this.getCacheKey(recipeIdA, recipeIdB, options);
    return this.cache.get(key);
  }

  /**
   * Store in cache with size limit
   */
  setCached(recipeIdA, recipeIdB, options, result) {
    if (!this.cacheEnabled) return;

    const key = this.getCacheKey(recipeIdA, recipeIdB, options);

    // Evict oldest if at capacity
    if (this.cache.size >= this.cacheMaxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }

    this.cache.set(key, result);
  }

  /**
   * Calculate similarity between two recipes
   */
  calculateSimilarity(recipeA, recipeB, options = {}) {
    this.stats.calculations++;

    // Check cache
    const cached = this.getCached(
      recipeA.id || 'unknown',
      recipeB.id || 'unknown',
      options
    );

    if (cached) {
      this.stats.cacheHits++;
      return cached;
    }

    this.stats.cacheMisses++;

    // Vectorize both recipes
    const vectorA = this.vectorizer.vectorize(recipeA);
    const vectorB = this.vectorizer.vectorize(recipeB);

    // Calculate similarity with breakdown
    const result = this.vectorizer.calculateSimilarity(vectorA, vectorB, {
      includeBreakdown: true,
      ...options
    });

    // Store in cache
    this.setCached(recipeA.id || 'unknown', recipeB.id || 'unknown', options, result);

    return result;
  }

  /**
   * Find similar recipes from a list
   */
  findSimilar(recipe, candidates, options = {}) {
    const {
      limit = 10,
      minSimilarity = 0,
      useCache = true
    } = options;

    // Invoke beforeSearch hook if available
    this.invokeHook('beforeSimilaritySearch', { recipe, candidates, options });

    const vectorizerOptions = { k: limit, minSimilarity };
    let results = this.vectorizer.findSimilar(recipe, candidates, vectorizerOptions);

    // Invoke afterSearch hook if available
    results = this.invokeHook('afterSimilaritySearch', { recipe, candidates, results });

    return results.slice(0, limit);
  }

  /**
   * Get all recipes similar to a given recipe
   */
  getSimilarRecipes(recipeId, options = {}) {
    const { limit = 10, minSimilarity = 0.1 } = options;

    const recipe = this.store?.readById?.('recipes', recipeId);
    if (!recipe) {
      return { error: 'Recipe not found' };
    }

    const allRecipes = this.store?.readAll?.('recipes') || [];
    const results = this.findSimilar(recipe, allRecipes, { limit, minSimilarity });

    return {
      recipeId,
      recipeName: recipe.name,
      similarCount: results.length,
      results
    };
  }

  /**
   * Calculate batch similarity for multiple recipe pairs
   */
  batchCalculate(pairs, options = {}) {
    const results = [];

    for (const [recipeA, recipeB] of pairs) {
      const result = this.calculateSimilarity(recipeA, recipeB, options);
      results.push({
        recipeA: recipeA.id || 'unknown',
        recipeB: recipeB.id || 'unknown',
        similarity: result.composite !== undefined ? result.composite : result,
        breakdown: result.breakdown
      });
    }

    return results;
  }

  /**
   * Build a similarity matrix for a set of recipes
   */
  buildSimilarityMatrix(recipes, options = {}) {
    const n = recipes.length;
    const matrix = Array(n).fill(null).map(() => Array(n).fill(0));

    for (let i = 0; i < n; i++) {
      matrix[i][i] = 1; // Self-similarity

      for (let j = i + 1; j < n; j++) {
        const similarity = this.calculateSimilarity(recipes[i], recipes[j], options);
        const score = similarity.composite !== undefined ? similarity.composite : similarity;

        matrix[i][j] = score;
        matrix[j][i] = score; // Symmetric
      }
    }

    return {
      matrix,
      recipes: recipes.map(r => ({ id: r.id, name: r.name })),
      dimensions: n
    };
  }

  /**
   * Find recipe clusters
   */
  clusterRecipes(recipes, options = {}) {
    const { k = 3 } = options;

    return this.vectorizer.cluster(recipes, { k });
  }

  /**
   * Get statistics about similarity calculations
   */
  getStats() {
    const cacheHitRate = this.stats.calculations > 0
      ? (this.stats.cacheHits / this.stats.calculations * 100).toFixed(2) + '%'
      : '0%';

    return {
      ...this.stats,
      cacheHitRate,
      cacheSize: this.cache.size,
      cacheCapacity: this.cacheMaxSize
    };
  }

  /**
   * Clear the similarity cache
   */
  clearCache() {
    this.cache.clear();
    return { cleared: true, size: 0 };
  }

  /**
   * Disable/enable caching
   */
  setCaching(enabled) {
    this.cacheEnabled = enabled;
    return { cachingEnabled: enabled };
  }

  /**
   * Invoke dynamic hooks if available
   */
  invokeHook(hookName, context) {
    try {
      const handlers = dynamicRegistry.getHookHandlers(hookName);
      let result = context;

      for (const { handler } of handlers) {
        if (typeof handler === 'function') {
          result = handler(result) || result;
        }
      }

      return result;
    } catch {
      // Dynamic hooks not available, continue without them
      return context;
    }
  }

  /**
   * Get supported algorithm names
   */
  getSupportedAlgorithms() {
    return [
      'jaccard',
      'cosine',
      'euclidean',
      'manhattan',
      'pearson',
      'dice',
      'overlap',
      'tanimoto'
    ];
  }

  /**
   * Compare using a specific algorithm only
   */
  compareWithAlgorithm(recipeA, recipeB, algorithm, options = {}) {
    const methodMap = {
      jaccard: 'calculateJaccard',
      cosine: 'calculateCosine',
      euclidean: 'calculateEuclidean',
      manhattan: 'calculateManhattan',
      pearson: 'calculatePearson',
      dice: 'calculateDice',
      overlap: 'calculateOverlap',
      tanimoto: 'calculateTanimoto'
    };

    const methodName = methodMap[algorithm];
    if (!methodName) {
      return { error: `Unknown algorithm: ${algorithm}` };
    }

    const vectorA = this.vectorizer.vectorize(recipeA);
    const vectorB = this.vectorizer.vectorize(recipeB);

    // Select appropriate data types for each algorithm
    let dataA, dataB;
    if (['jaccard', 'dice', 'overlap'].includes(algorithm)) {
      dataA = vectorA.ingredients;
      dataB = vectorB.ingredients;
    } else {
      dataA = vectorA.nutrition;
      dataB = vectorB.nutrition;
    }

    const method = this.algorithms[methodName];
    if (typeof method !== 'function') {
      return { error: `Algorithm ${algorithm} not implemented` };
    }

    const score = method.call(this.algorithms, dataA, dataB);

    return {
      algorithm,
      score,
      dataType: ['jaccard', 'dice', 'overlap'].includes(algorithm) ? 'ingredient_set' : 'nutrition_vector'
    };
  }
}

module.exports = SimilarityService;
