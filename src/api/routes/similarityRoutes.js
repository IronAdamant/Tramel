/**
 * Similarity API Routes
 *
 * These routes challenge Stele-context because:
 * - They integrate with the dynamic plugin system
 * - They use runtime service resolution
 */

const { createRouter } = require('../../utils/router');
const SimilarityService = require('../../services/similarityService');
const dynamicRegistry = require('../../plugins/DynamicRegistry');

const router = createRouter();

// Initialize similarity service with dynamic capabilities
let similarityService = null;

function getSimilarityService(req) {
  if (!similarityService) {
    similarityService = new SimilarityService(req.app?.fileStore);
  }

  // Try to get dynamic service if registered
  const dynamicSimilarity = dynamicRegistry.getService('SimilarityService');
  return dynamicSimilarity || similarityService;
}

/**
 * GET /api/similarity/:recipeId
 * Get similar recipes for a given recipe
 */
router.get('/similarity/:recipeId', (req, res) => {
  const { recipeId } = req.params;
  const { limit = 10, minSimilarity = 0.1 } = req.query;

  const service = getSimilarityService(req);
  const result = service.getSimilarRecipes(recipeId, {
    limit: parseInt(limit, 10),
    minSimilarity: parseFloat(minSimilarity)
  });

  if (result.error) {
    return res.status(404).json({ error: result.error });
  }

  res.json(result);
});

/**
 * POST /api/similarity/compare
 * Compare two recipes directly
 */
router.post('/compare', (req, res) => {
  const { recipeA, recipeB, algorithm, weights } = req.body;

  if (!recipeA || !recipeB) {
    return res.status(400).json({ error: 'recipeA and recipeB are required' });
  }

  const service = getSimilarityService(req);

  if (algorithm) {
    // Use specific algorithm
    const result = service.compareWithAlgorithm(recipeA, recipeB, algorithm, weights);
    if (result.error) {
      return res.status(400).json({ error: result.error });
    }
    return res.json(result);
  }

  // Use composite similarity
  const result = service.calculateSimilarity(recipeA, recipeB, weights);
  res.json(result);
});

/**
 * POST /api/similarity/batch
 * Batch calculate similarity for multiple pairs
 */
router.post('/batch', (req, res) => {
  const { pairs, weights } = req.body;

  if (!Array.isArray(pairs) || pairs.length === 0) {
    return res.status(400).json({ error: 'pairs array is required' });
  }

  const service = getSimilarityService(req);
  const results = service.batchCalculate(pairs, weights);

  res.json({ results, count: results.length });
});

/**
 * POST /api/similarity/matrix
 * Build similarity matrix for a set of recipes
 */
router.post('/matrix', (req, res) => {
  const { recipes, weights } = req.body;

  if (!Array.isArray(recipes) || recipes.length === 0) {
    return res.status(400).json({ error: 'recipes array is required' });
  }

  if (recipes.length > 50) {
    return res.status(400).json({ error: 'Maximum 50 recipes for matrix calculation' });
  }

  const service = getSimilarityService(req);
  const result = service.buildSimilarityMatrix(recipes, weights);

  res.json(result);
});

/**
 * POST /api/similarity/cluster
 * Cluster recipes by similarity
 */
router.post('/cluster', (req, res) => {
  const { recipes, k = 3 } = req.body;

  if (!Array.isArray(recipes) || recipes.length === 0) {
    return res.status(400).json({ error: 'recipes array is required' });
  }

  const service = getSimilarityService(req);
  const clusters = service.clusterRecipes(recipes, { k: parseInt(k, 10) });

  res.json({ clusters, count: clusters.length });
});

/**
 * GET /api/similarity/algorithms
 * Get supported similarity algorithms
 */
router.get('/algorithms', (req, res) => {
  const service = getSimilarityService(req);
  const algorithms = service.getSupportedAlgorithms();

  res.json({ algorithms });
});

/**
 * GET /api/similarity/stats
 * Get similarity calculation statistics
 */
router.get('/stats', (req, res) => {
  const service = getSimilarityService(req);
  const stats = service.getStats();

  res.json(stats);
});

/**
 * DELETE /api/similarity/cache
 * Clear similarity cache
 */
router.delete('/cache', (req, res) => {
  const service = getSimilarityService(req);
  const result = service.clearCache();

  res.json(result);
});

/**
 * PATCH /api/similarity/cache
 * Enable/disable caching
 */
router.patch('/cache', (req, res) => {
  const { enabled } = req.body;
  const service = getSimilarityService(req);

  if (typeof enabled !== 'boolean') {
    return res.status(400).json({ error: 'enabled must be a boolean' });
  }

  const result = service.setCaching(enabled);
  res.json(result);
});

module.exports = router;
