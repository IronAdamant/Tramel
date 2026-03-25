/**
 * ratingPredictor plugin
 * Predicts recipe ratings based on ingredient complexity and nutrition
 * NO TESTS - deliberate gap for Chisel coverage_gap validation
 */

function predictRating(ingredients, nutrition) {
  let score = 3.0; // Base rating

  // Complexity bonus
  if (ingredients && ingredients.length > 5) score += 0.5;
  if (ingredients && ingredients.length > 10) score += 0.5;

  // Nutrition bonus
  if (nutrition) {
    if (nutrition.protein && nutrition.protein > 20) score += 0.3;
    if (nutrition.fiber && nutrition.fiber > 5) score += 0.2;
    if (nutrition.calories && nutrition.calories < 500) score += 0.2;
  }

  return Math.min(5.0, score);
}

module.exports = {
  name: 'ratingPredictor',
  hooks: ['beforeCreate', 'afterCreate', 'onNutrientCalculated'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;

    if (hook === 'beforeCreate' || hook === 'afterCreate') {
      const [entity] = args;
      const ingredients = entity?.ingredients || [];
      const predictedRating = predictRating(ingredients, entity?.nutrition);

      console.log(`[ratingPredictor] Predicted rating for ${entity?.name || 'unknown'}: ${predictedRating.toFixed(1)}/5.0`);

      return { ...ctx, predictedRating };
    }

    if (hook === 'onNutrientCalculated') {
      const [recipe, nutrition] = args;
      const predictedRating = predictRating(recipe?.ingredients, nutrition);

      console.log(`[ratingPredictor] Updated prediction with nutrition: ${predictedRating.toFixed(1)}/5.0`);

      return { ...ctx, predictedRating };
    }

    return ctx;
  }
};
