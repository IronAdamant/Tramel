'use strict';

/**
 * VarietyScorer - Scores meal plans based on variety and diversity
 * NO TESTS - deliberate gap for Chisel coverage_gap validation
 */
class VarietyScorer {
  constructor(fileStore) {
    this.store = fileStore;
  }

  /**
   * Calculate variety score for a meal plan
   * @param {Array} mealPlan - Array of recipe IDs or recipe objects
   * @returns {Object} Variety metrics
   */
  scoreMealPlanVariety(mealPlan) {
    if (!mealPlan || mealPlan.length === 0) {
      return {
        overall_score: 0,
        ingredient_diversity: 0,
        category_diversity: 0,
        cuisine_diversity: 0,
        repetition_penalty: 0
      };
    }

    const ingredientDiversity = this.calculateIngredientDiversity(mealPlan);
    const categoryDiversity = this.calculateCategoryDiversity(mealPlan);
    const cuisineDiversity = this.calculateCuisineDiversity(mealPlan);
    const repetitionPenalty = this.calculateRepetitionPenalty(mealPlan);

    // Weighted combination
    const overallScore = (
      ingredientDiversity * 0.4 +
      categoryDiversity * 0.3 +
      cuisineDiversity * 0.2 +
      repetitionPenalty * 0.1
    );

    return {
      overall_score: Math.round(overallScore * 100) / 100,
      ingredient_diversity: Math.round(ingredientDiversity * 100) / 100,
      category_diversity: Math.round(categoryDiversity * 100) / 100,
      cuisine_diversity: Math.round(cuisineDiversity * 100) / 100,
      repetition_penalty: Math.round(repetitionPenalty * 100) / 100
    };
  }

  /**
   * Calculate diversity based on unique ingredients
   */
  calculateIngredientDiversity(mealPlan) {
    const allIngredients = [];

    for (const entry of mealPlan) {
      const recipe = typeof entry === 'object' ? entry : this.store.readById('recipes', entry);
      if (recipe && recipe.ingredients) {
        allIngredients.push(...recipe.ingredients.map(i => i.name.toLowerCase()));
      }
    }

    const uniqueIngredients = new Set(allIngredients).size;
    const totalIngredients = allIngredients.length;

    if (totalIngredients === 0) return 0;

    // Shannon diversity index approximation
    const normalizedDiversity = uniqueIngredients / Math.sqrt(totalIngredients);
    return Math.min(normalizedDiversity, 1);
  }

  /**
   * Calculate diversity based on ingredient categories
   */
  calculateCategoryDiversity(mealPlan) {
    const allCategories = [];

    for (const entry of mealPlan) {
      const recipe = typeof entry === 'object' ? entry : this.store.readById('recipes', entry);
      if (recipe && recipe.ingredients) {
        allCategories.push(...recipe.ingredients.map(i => i.category || 'other'));
      }
    }

    const uniqueCategories = new Set(allCategories).size;
    // Target: 5+ categories for full score
    return Math.min(uniqueCategories / 5, 1);
  }

  /**
   * Calculate diversity based on cuisines
   */
  calculateCuisineDiversity(mealPlan) {
    const cuisines = [];

    for (const entry of mealPlan) {
      const recipe = typeof entry === 'object' ? entry : this.store.readById('recipes', entry);
      if (recipe && recipe.cuisine) {
        cuisines.push(recipe.cuisine.toLowerCase());
      }
    }

    const uniqueCuisines = new Set(cuisines).size;
    // Target: 3+ cuisines for full score
    return Math.min(uniqueCuisines / 3, 1);
  }

  /**
   * Calculate penalty for repeated ingredients across meals
   */
  calculateRepetitionPenalty(mealPlan) {
    if (mealPlan.length <= 1) return 1;

    const ingredientCounts = {};
    let totalIngredients = 0;

    for (const entry of mealPlan) {
      const recipe = typeof entry === 'object' ? entry : this.store.readById('recipes', entry);
      if (recipe && recipe.ingredients) {
        for (const ing of recipe.ingredients) {
          const name = ing.name.toLowerCase();
          ingredientCounts[name] = (ingredientCounts[name] || 0) + 1;
          totalIngredients++;
        }
      }
    }

    if (totalIngredients === 0) return 1;

    // Count repeated ingredients
    let repeatedCount = 0;
    for (const count of Object.values(ingredientCounts)) {
      if (count > 1) {
        repeatedCount += count - 1;
      }
    }

    // Penalty: more repetition = lower score
    const repetitionRatio = repeatedCount / totalIngredients;
    return 1 - repetitionRatio;
  }

  /**
   * Calculate weekly variety score (7 days with 3 meals each)
   */
  scoreWeeklyVariety(weeklyMealPlan) {
    // weeklyMealPlan: { monday: [breakfast, lunch, dinner], tuesday: [...], ... }
    const allMeals = [];

    for (const dayMeals of Object.values(weeklyMealPlan)) {
      if (Array.isArray(dayMeals)) {
        allMeals.push(...dayMeals);
      }
    }

    return this.scoreMealPlanVariety(allMeals);
  }
}

module.exports = VarietyScorer;
