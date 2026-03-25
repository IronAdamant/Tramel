'use strict';

/**
 * MealPlanScore - Represents the result of optimizing a meal plan
 */
class MealPlanScore {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'meal_plan_scores';
  }

  /**
   * Create a new meal plan score record
   */
  create({ meal_plan_id, recipe_id, score, objectives, constraints, pareto_rank }) {
    return this.store.create(this.table, {
      meal_plan_id,
      recipe_id,
      score: score || 0,
      objectives: objectives || {},
      constraints: constraints || {},
      pareto_rank: pareto_rank || 0
    });
  }

  /**
   * Get score by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all scores for a meal plan
   */
  getForMealPlan(mealPlanId) {
    return this.store.findBy(this.table, 'meal_plan_id', mealPlanId);
  }

  /**
   * Get all scores for a recipe
   */
  getForRecipe(recipeId) {
    return this.store.findBy(this.table, 'recipe_id', recipeId);
  }

  /**
   * Get top scores by pareto rank
   */
  getByParetoRank(rank) {
    return this.store.findBy(this.table, 'pareto_rank', rank);
  }

  /**
   * Delete scores for a meal plan
   */
  deleteForMealPlan(mealPlanId) {
    const scores = this.getForMealPlan(mealPlanId);
    for (const score of scores) {
      this.store.delete(this.table, score.id);
    }
    return true;
  }
}

module.exports = MealPlanScore;
