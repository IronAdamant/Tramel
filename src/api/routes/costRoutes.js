'use strict';

const { createRouter } = require('../../utils/router');
const CostEstimationService = require('../../services/costEstimationService');
const { success, notFound } = require('../../utils/response');

const router = createRouter();

// Estimate cost for a recipe
router.get('/estimate/:recipeId', (req, res) => {
  const service = new CostEstimationService(req.db);

  const cost = service.estimateRecipeCost(req.params.recipeId);

  if (!cost) {
    return notFound(res, 'Recipe not found');
  }

  success(res, cost);
});

module.exports = router;
