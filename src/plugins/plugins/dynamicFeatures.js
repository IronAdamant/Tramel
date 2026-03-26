/**
 * DynamicFeaturePlugin - Example plugin using dynamic registration
 *
 * This plugin demonstrates RUNTIME-ONLY symbol relationships:
 * - Routes are registered dynamically (no static imports)
 * - Service methods are resolved at runtime
 * - Symbol references cross plugin boundaries dynamically
 *
 * STEFE-CONTEXT CHALLENGE: The symbol 'DynamicRecipeAnalyzer' is
 * registered at runtime and called dynamically. There is NO static
 * import statement linking this file to the code that calls it.
 */

const dynamicRegistry = require('../DynamicRegistry');

class DynamicRecipeAnalyzer {
  constructor() {
    this.name = 'DynamicRecipeAnalyzer';
    this.analysisCache = new Map();
  }

  /**
   * Analyze recipe complexity based on ingredient count, steps, etc.
   * This method is called DYNAMICALLY at runtime
   */
  analyzeComplexity(recipe) {
    if (!recipe) return null;

    const ingredientCount = recipe.ingredients?.length || 0;
    const stepCount = recipe.steps?.length || 0;
    const hasMultipleCuisines = recipe.cuisine?.includes(',') || false;

    const complexity = {
      score: ingredientCount * 0.3 + stepCount * 0.5 + (hasMultipleCuisines ? 2 : 0),
      level: 'simple',
      factors: []
    };

    if (complexity.score > 10) complexity.level = 'moderate';
    if (complexity.score > 20) complexity.level = 'complex';
    if (complexity.score > 35) complexity.level = 'expert';

    complexity.factors.push(`${ingredientCount} ingredients`);
    complexity.factors.push(`${stepCount} steps`);
    if (hasMultipleCuisines) complexity.factors.push('fusion cuisine');

    return complexity;
  }

  /**
   * Calculate recipe similarity scores
   * Uses a RUNTIME algorithm that stele cannot trace statically
   */
  calculateSimilarity(recipeA, recipeB) {
    if (!recipeA || !recipeB) return 0;

    // Jaccard similarity on tags
    const tagsA = new Set(recipeA.tags || []);
    const tagsB = new Set(recipeB.tags || []);
    const intersection = new Set([...tagsA].filter(x => tagsB.has(x)));
    const union = new Set([...tagsA, ...tagsB]);
    const jaccard = union.size > 0 ? intersection.size / union.size : 0;

    // Ingredient overlap
    const ingA = new Set((recipeA.ingredients || []).map(i => i.name?.toLowerCase()));
    const ingB = new Set((recipeB.ingredients || []).map(i => i.name?.toLowerCase()));
    const ingIntersection = new Set([...ingA].filter(x => ingB.has(x)));
    const ingUnion = new Set([...ingA, ...ingB]);
    const ingJaccard = ingUnion.size > 0 ? ingIntersection.size / ingUnion.size : 0;

    // Time similarity
    const timeDiff = Math.abs((recipeA.totalTime || 0) - (recipeB.totalTime || 0));
    const timeSimilarity = Math.max(0, 1 - timeDiff / 120); // 2 hours max diff

    return {
      overall: (jaccard * 0.3 + ingJaccard * 0.5 + timeSimilarity * 0.2),
      tagSimilarity: jaccard,
      ingredientSimilarity: ingJaccard,
      timeSimilarity
    };
  }

  /**
   * Get trending attributes based on recent recipes
   */
  getTrendingAttributes(recipes = []) {
    const tagCounts = {};
    const cuisineCounts = {};
    const timeRanges = { quick: 0, medium: 0, long: 0 };

    recipes.forEach(recipe => {
      // Count tags
      (recipe.tags || []).forEach(tag => {
        tagCounts[tag] = (tagCounts[tag] || 0) + 1;
      });

      // Count cuisines
      if (recipe.cuisine) {
        cuisineCounts[recipe.cuisine] = (cuisineCounts[recipe.cuisine] || 0) + 1;
      }

      // Count time ranges
      const time = recipe.totalTime || 0;
      if (time <= 30) timeRanges.quick++;
      else if (time <= 60) timeRanges.medium++;
      else timeRanges.long++;
    });

    return {
      topTags: Object.entries(tagCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([tag, count]) => ({ tag, count })),
      topCuisines: Object.entries(cuisineCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([cuisine, count]) => ({ cuisine, count })),
      timeDistribution: timeRanges
    };
  }
}

/**
 * Dynamic route handlers - these are NOT connected via static imports
 * The route is registered at RUNTIME by the plugin system
 */
const dynamicRoutes = [
  {
    method: 'GET',
    path: '/api/dynamic/analyze/:recipeId',
    handler: async (req, res) => {
      const { recipeId } = req.params;
      const analyzer = dynamicRegistry.getService('DynamicRecipeAnalyzer');

      if (!analyzer) {
        return { error: 'Analyzer not initialized' };
      }

      // RUNTIME symbol resolution - stele cannot see this statically
      const recipe = req.db?.recipes?.findById?.(recipeId);
      const analysis = analyzer.analyzeComplexity(recipe);

      return { recipeId, analysis };
    }
  },
  {
    method: 'GET',
    path: '/api/dynamic/similar/:recipeId',
    handler: async (req, res) => {
      const { recipeId } = req.params;
      const analyzer = dynamicRegistry.getService('DynamicRecipeAnalyzer');

      // Get the source recipe
      const sourceRecipe = req.db?.recipes?.findById?.(recipeId);
      if (!sourceRecipe) {
        return { error: 'Recipe not found' };
      }

      // Get all recipes for comparison
      const allRecipes = req.db?.recipes?.readAll?.() || [];
      const similarities = allRecipes
        .filter(r => r.id !== recipeId)
        .map(r => ({
          recipeId: r.id,
          similarity: analyzer.calculateSimilarity(sourceRecipe, r)
        }))
        .sort((a, b) => b.similarity.overall - a.similarity.overall)
        .slice(0, 10);

      return { recipeId, similarities };
    }
  },
  {
    method: 'GET',
    path: '/api/dynamic/trending',
    handler: async (req, res) => {
      const analyzer = dynamicRegistry.getService('DynamicRecipeAnalyzer');
      const recipes = req.db?.recipes?.readAll?.() || [];
      const trending = analyzer.getTrendingAttributes(recipes);
      return trending;
    }
  }
];

/**
 * Dynamic middleware - registered at runtime
 */
const dynamicMiddleware = [
  async (req, res, next) => {
    // Add dynamic analysis metadata to request
    req.dynamicMeta = {
      timestamp: Date.now(),
      analyzerVersion: '1.0.0'
    };
    next();
  }
];

/**
 * Plugin definition - registered dynamically
 */
const dynamicFeaturePlugin = {
  name: 'dynamic-features',
  hooks: ['beforeSearch', 'afterSearch', 'onRecipeRated'],

  // Service instance - registered dynamically
  service: new DynamicRecipeAnalyzer(),

  // Routes - registered dynamically
  routes: dynamicRoutes,

  // Middleware - registered dynamically
  middleware: dynamicMiddleware,

  /**
   * Called when plugin is registered
   * The hook system uses this to establish runtime connections
   */
  onRegister: (registry) => {
    // Dynamically register additional hooks
    registry.registerHook('dynamic-features', 'onAnalysisComplete', async (context) => {
      // Post-analysis processing
      return { analyzed: true, timestamp: Date.now() };
    });
  },

  /**
   * Hook handler - called at runtime
   */
  handler: async (hookName, context) => {
    const analyzer = dynamicRegistry.getService('DynamicRecipeAnalyzer');
    if (!analyzer) return context;

    switch (hookName) {
      case 'beforeSearch':
        context.queryMeta = { analyzed: true, complexity: 'pending' };
        break;
      case 'afterSearch':
        if (context.results) {
          context.results = context.results.map(r => ({
            ...r,
            dynamicScore: Math.random() // Runtime calculation
          }));
        }
        break;
      case 'onRecipeRated':
        // Triggered when a recipe is rated
        break;
    }

    return context;
  }
};

module.exports = dynamicFeaturePlugin;
