'use strict';

const { createRouter } = require('../../utils/router');
const RecipeScalingService = require('../../services/recipeScalingService');
const { success, notFound } = require('../../utils/response');

const router = createRouter();

// Scale a recipe
router.post('/', (req, res) => {
  const service = new RecipeScalingService(req.db);
  const { scaleFactor, targetServings } = req.body;

  const scaled = service.scaleRecipe(req.params.recipeId, {
    scaleFactor: scaleFactor ? parseFloat(scaleFactor) : undefined,
    targetServings: targetServings ? parseInt(targetServings, 10) : undefined
  });

  if (!scaled) {
    return notFound(res, 'Recipe not found');
  }

  success(res, scaled);
});

module.exports = router;
