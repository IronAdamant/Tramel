/**
 * nutritionLogger plugin
 * Logs nutritional information whenever nutrients are calculated or recipes are scaled
 */

module.exports = {
  name: 'nutritionLogger',
  hooks: ['onNutrientCalculated', 'afterScale'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;

    if (hook === 'onNutrientCalculated') {
      const [recipe, nutritionData] = args;
      console.log(`[nutritionLogger] Nutrients calculated for recipe: ${recipe?.name || 'unknown'}`);
      console.log(`[nutritionLogger] Calories: ${nutritionData?.calories || 0}, Protein: ${nutritionData?.protein || 0}g`);
    }

    if (hook === 'afterScale') {
      const [scaledRecipe, scaleFactor] = args;
      console.log(`[nutritionLogger] Recipe scaled by factor: ${scaleFactor}`);
      console.log(`[nutritionLogger] Scaled recipe: ${scaledRecipe?.name || 'unknown'}`);
    }

    return ctx;
  }
};
