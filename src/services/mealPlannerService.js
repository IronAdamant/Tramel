'use strict';

const MealPlan = require('../models/MealPlan');
const Recipe = require('../models/Recipe');

/**
 * Meal planning service
 */
class MealPlannerService {
  constructor(fileStore) {
    this.store = fileStore;
    this.mealPlan = new MealPlan(fileStore);
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Generate a weekly meal plan
   */
  generateWeeklyPlan({ startDate, endDate, servings = 2 }) {
    const start = startDate ? new Date(startDate) : new Date();
    const end = endDate ? new Date(endDate) : new Date(start.getTime() + 7 * 24 * 60 * 60 * 1000);

    // Get all recipes
    const recipes = this.store.readAll('recipes');

    if (recipes.length === 0) {
      return {
        plan: null,
        message: 'No recipes available'
      };
    }

    // Create meal plan
    const plan = this.mealPlan.create({
      name: `Week of ${start.toISOString().split('T')[0]}`,
      start_date: start.toISOString().split('T')[0],
      end_date: end.toISOString().split('T')[0]
    });

    // Generate entries for each day
    const mealTypes = ['breakfast', 'lunch', 'dinner'];
    const currentDate = new Date(start);

    while (currentDate <= end) {
      for (const mealType of mealTypes) {
        // Pick a random recipe
        const randomRecipe = recipes[Math.floor(Math.random() * recipes.length)];

        this.mealPlan.addEntry({
          meal_plan_id: plan.id,
          recipe_id: randomRecipe.id,
          date: currentDate.toISOString().split('T')[0],
          meal_type: mealType,
          servings
        });
      }
      currentDate.setDate(currentDate.getDate() + 1);
    }

    return this.mealPlan.getById(plan.id);
  }

  /**
   * Suggest meals for planning
   */
  suggestMeals({ count = 7 }) {
    const recipes = this.store.readAll('recipes');

    if (recipes.length === 0) {
      return [];
    }

    // Shuffle and pick
    const shuffled = [...recipes].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, count).map(recipe => ({
      recipe,
      total_time: (recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0)
    }));
  }

  /**
   * Check variety in a meal plan
   */
  checkVariety(mealPlanId) {
    const plan = this.mealPlan.getById(mealPlanId);
    if (!plan || !plan.entries) {
      return { error: 'Meal plan not found' };
    }

    const recipeIds = [...new Set(plan.entries.map(e => e.recipe_id))];
    const totalEntries = plan.entries.length;

    return {
      unique_recipes: recipeIds.length,
      total_meals: totalEntries,
      variety_score: totalEntries > 0 ? recipeIds.length / totalEntries : 0,
      recipes_used: recipeIds.map(id => this.store.readById('recipes', id)).filter(Boolean)
    };
  }

  /**
   * Get week summary
   */
  getWeekSummary(mealPlanId) {
    const plan = this.mealPlan.getById(mealPlanId);
    if (!plan || !plan.entries) {
      return { error: 'Meal plan not found' };
    }

    const summary = {
      total_meals: plan.entries.length,
      by_meal_type: {},
      total_time: 0,
      recipes: []
    };

    plan.entries.forEach(entry => {
      // Count by meal type
      if (!summary.by_meal_type[entry.meal_type]) {
        summary.by_meal_type[entry.meal_type] = 0;
      }
      summary.by_meal_type[entry.meal_type]++;

      // Get recipe info
      const recipe = this.store.readById('recipes', entry.recipe_id);
      if (recipe) {
        summary.total_time += (recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0);
        if (!summary.recipes.find(r => r.id === recipe.id)) {
          summary.recipes.push(recipe);
        }
      }
    });

    return summary;
  }
}

module.exports = MealPlannerService;
