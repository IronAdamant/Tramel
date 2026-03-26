'use strict';

/**
 * Nutrition estimation service
 */
const Recipe = require('../models/Recipe');

class NutritionService {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Estimate nutrition for a recipe
   */
  estimateRecipeNutrition(recipeId) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe || !recipe.ingredients) {
      return null;
    }

    const nutrition = {
      calories: 0,
      protein: 0,
      carbs: 0,
      fat: 0,
      fiber: 0,
      sugar: 0,
      sodium: 0
    };

    // Simple estimation based on ingredient categories
    // In a real app, this would use actual nutrition data
    for (const ingredient of recipe.ingredients) {
      const estimated = this.estimateIngredientNutrition(ingredient);
      nutrition.calories += estimated.calories;
      nutrition.protein += estimated.protein;
      nutrition.carbs += estimated.carbs;
      nutrition.fat += estimated.fat;
      nutrition.fiber += estimated.fiber;
      nutrition.sugar += estimated.sugar;
      nutrition.sodium += estimated.sodium;
    }

    // Per-serving values
    const servings = recipe.servings || 1;
    return {
      total: nutrition,
      per_serving: {
        calories: Math.round(nutrition.calories / servings),
        protein: Math.round(nutrition.protein / servings),
        carbs: Math.round(nutrition.carbs / servings),
        fat: Math.round(nutrition.fat / servings),
        fiber: Math.round(nutrition.fiber / servings),
        sugar: Math.round(nutrition.sugar / servings),
        sodium: Math.round(nutrition.sodium / servings)
      },
      servings
    };
  }

  /**
   * Estimate nutrition for a single ingredient
   */
  estimateIngredientNutrition(ingredient) {
    // Very simplified estimation
    // In production, this would use actual nutrition data lookup
    const qty = ingredient.quantity || 100;
    const basePer100g = {
      vegetable: { calories: 25, protein: 1, carbs: 5, fat: 0, fiber: 2, sugar: 3, sodium: 10 },
      meat: { calories: 200, protein: 25, carbs: 0, fat: 12, fiber: 0, sugar: 0, sodium: 60 },
      dairy: { calories: 150, protein: 8, carbs: 12, fat: 8, fiber: 0, sugar: 12, sodium: 150 },
      grain: { calories: 350, protein: 10, carbs: 75, fat: 2, fiber: 3, sugar: 2, sodium: 5 },
      fruit: { calories: 50, protein: 1, carbs: 12, fat: 0, fiber: 2, sugar: 10, sodium: 5 }
    };

    const name = (ingredient.name || '').toLowerCase();
    let category = 'grain';

    if (name.includes('chicken') || name.includes('beef') || name.includes('pork')) {
      category = 'meat';
    } else if (name.includes('milk') || name.includes('cheese') || name.includes('yogurt')) {
      category = 'dairy';
    } else if (name.includes('tomato') || name.includes('onion') || name.includes('carrot') || name.includes('lettuce')) {
      category = 'vegetable';
    } else if (name.includes('apple') || name.includes('banana') || name.includes('orange')) {
      category = 'fruit';
    }

    const base = basePer100g[category];
    const multiplier = qty / 100;

    return {
      calories: base.calories * multiplier,
      protein: base.protein * multiplier,
      carbs: base.carbs * multiplier,
      fat: base.fat * multiplier,
      fiber: base.fiber * multiplier,
      sugar: base.sugar * multiplier,
      sodium: base.sodium * multiplier
    };
  }

  /**
   * Estimate nutrition for a meal plan
   */
  estimateMealPlanNutrition(mealPlanId) {
    const entries = this.store.findBy('meal_plan_entries', 'meal_plan_id', mealPlanId);

    const totalNutrition = {
      calories: 0,
      protein: 0,
      carbs: 0,
      fat: 0
    };

    for (const entry of entries) {
      const nutrition = this.estimateRecipeNutrition(entry.recipe_id);
      if (nutrition) {
        const multiplier = (entry.servings || 1) / nutrition.servings;
        totalNutrition.calories += nutrition.total.calories * multiplier;
        totalNutrition.protein += nutrition.total.protein * multiplier;
        totalNutrition.carbs += nutrition.total.carbs * multiplier;
        totalNutrition.fat += nutrition.total.fat * multiplier;
      }
    }

    return totalNutrition;
  }

  /**
   * Get daily breakdown
   */
  getDailyBreakdown(mealPlanId) {
    const entries = this.store.findBy('meal_plan_entries', 'meal_plan_id', mealPlanId);

    const byDate = {};

    for (const entry of entries) {
      if (!byDate[entry.date]) {
        byDate[entry.date] = {
          calories: 0,
          protein: 0,
          carbs: 0,
          fat: 0,
          meals: 0
        };
      }

      const nutrition = this.estimateRecipeNutrition(entry.recipe_id);
      if (nutrition) {
        const multiplier = (entry.servings || 1) / nutrition.servings;
        byDate[entry.date].calories += nutrition.total.calories * multiplier;
        byDate[entry.date].protein += nutrition.total.protein * multiplier;
        byDate[entry.date].carbs += nutrition.total.carbs * multiplier;
        byDate[entry.date].fat += nutrition.total.fat * multiplier;
        byDate[entry.date].meals++;
      }
    }

    return byDate;
  }
}

module.exports = NutritionService;
