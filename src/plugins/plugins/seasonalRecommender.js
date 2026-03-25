/**
 * seasonalRecommender plugin
 * Recommends seasonal ingredients based on current month
 * NO TESTS - deliberate gap for Chisel coverage_gap validation
 */

const SEASONAL_DATA = {
  spring: ['asparagus', 'artichokes', 'peas', 'radishes', 'spinach'],
  summer: ['tomatoes', 'corn', 'zucchini', 'berries', 'peaches'],
  fall: ['pumpkin', 'squash', 'apples', 'cranberries', 'brussels sprouts'],
  winter: ['citrus', 'root vegetables', 'kale', 'cabbage', 'turnips']
};

function getCurrentSeason() {
  const month = new Date().getMonth();
  if (month >= 2 && month <= 4) return 'spring';
  if (month >= 5 && month <= 7) return 'summer';
  if (month >= 8 && month <= 10) return 'fall';
  return 'winter';
}

module.exports = {
  name: 'seasonalRecommender',
  hooks: ['beforeSearch', 'afterSearch', 'onMealPlanGenerated'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;
    const currentSeason = getCurrentSeason();
    const seasonalIngredients = SEASONAL_DATA[currentSeason] || [];

    if (hook === 'beforeSearch') {
      const [query, options] = args;
      console.log(`[seasonalRecommender] Current season: ${currentSeason}`);

      return { ...ctx, seasonalIngredients, currentSeason };
    }

    if (hook === 'afterSearch') {
      const [results] = args;
      const enhancedResults = results.map(recipe => ({
        ...recipe,
        isSeasonal: seasonalIngredients.some(ing =>
          recipe.ingredients?.some(i => i.name?.toLowerCase().includes(ing))
        )
      }));

      console.log(`[seasonalRecommender] Enhanced ${results.length} results with seasonal data`);

      return { ...ctx, results: enhancedResults, seasonalCount: enhancedResults.filter(r => r.isSeasonal).length };
    }

    if (hook === 'onMealPlanGenerated') {
      const [mealPlan] = args;
      let seasonalMealCount = 0;

      if (mealPlan && mealPlan.meals) {
        mealPlan.meals.forEach(meal => {
          if (seasonalIngredients.some(ing =>
            meal.ingredients?.some(i => i.name?.toLowerCase().includes(ing))
          )) {
            seasonalMealCount++;
          }
        });
      }

      console.log(`[seasonalRecommender] ${seasonalMealCount} seasonal meals in plan`);

      return { ...ctx, seasonalMealCount };
    }

    return ctx;
  }
};
