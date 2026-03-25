'use strict';

const { createRouter } = require('../../utils/router');
const NutritionService = require('../../services/nutritionService');
const { success, notFound } = require('../../utils/response');

const router = createRouter();

// Estimate nutrition for a recipe
router.get('/estimate/:recipeId', (req, res) => {
  const service = new NutritionService(req.db);

  const nutrition = service.estimateRecipeNutrition(req.params.recipeId);

  if (!nutrition) {
    return notFound(res, 'Recipe not found');
  }

  success(res, nutrition);
});

module.exports = router;
