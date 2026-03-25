/**
 * priceTagger plugin
 * Tags recipes and ingredients with estimated prices
 * NO TESTS - deliberate gap for Chisel coverage_gap validation
 */

const DEFAULT_PRICE_PER_SERVING = 5.00;

module.exports = {
  name: 'priceTagger',
  hooks: ['afterCreate', 'afterUpdate', 'onMealPlanGenerated'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;

    if (hook === 'afterCreate' || hook === 'afterUpdate') {
      const [entity] = args;
      const estimatedPrice = this?.estimatedPrice ||
        (entity.servings ? entity.servings * DEFAULT_PRICE_PER_SERVING : DEFAULT_PRICE_PER_SERVING);

      console.log(`[priceTagger] Tagged ${entity?.name || 'unknown'} with estimated price: $${estimatedPrice.toFixed(2)}`);

      return { ...ctx, estimatedPrice };
    }

    if (hook === 'onMealPlanGenerated') {
      const [mealPlan] = args;
      let totalEstimate = 0;

      if (mealPlan && mealPlan.meals) {
        mealPlan.meals.forEach(meal => {
          totalEstimate += meal.estimatedPrice || DEFAULT_PRICE_PER_SERVING;
        });
      }

      console.log(`[priceTagger] Meal plan total estimated: $${totalEstimate.toFixed(2)}`);

      return { ...ctx, totalEstimatedPrice: totalEstimate };
    }

    return ctx;
  }
};
