'use strict';

const Recipe = require('../../models/Recipe');
const ObjectiveFunction = require('./objectiveFunction');
const ConstraintValidator = require('./constraintValidator');
const VarietyScorer = require('./varietyScorer');
const ParetoFrontier = require('./paretoFrontier');

/**
 * MealPlanOptimizer - Multi-objective optimization for meal planning
 * Minimizes cost, maximizes nutrition, maximizes variety while respecting constraints
 */
class MealPlanOptimizer {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
    this.objectiveFunction = new ObjectiveFunction(fileStore);
    this.constraintValidator = new ConstraintValidator(fileStore);
    this.varietyScorer = new VarietyScorer(fileStore);
    this.paretoFrontier = new ParetoFrontier();
  }

  /**
   * Optimize a meal plan
   * @param {Object} params - Optimization parameters
   * @param {Array} params.recipes - Array of recipe objects (or IDs)
   * @param {Object} params.constraints - { maxCalories, dietaryProfile, maxCostPerMeal }
   * @param {Object} params.objectives - { minimizeCost, maximizeNutrition, maximizeVariety }
   * @param {Object} params.config - { days: 7, mealsPerDay: 3 }
   * @returns {Object} Optimization result with Pareto-optimal solutions
   */
  optimize({ recipes, constraints = {}, objectives = {}, config = {} }) {
    const defaults = {
      days: 7,
      mealsPerDay: 3
    };

    const opts = { ...defaults, ...config };

    // 1. Load recipes if IDs were passed
    const loadedRecipes = this.loadRecipes(recipes);
    if (loadedRecipes.length === 0) {
      return {
        success: false,
        error: 'No recipes available for optimization'
      };
    }

    // 2. Filter recipes by hard constraints
    const validRecipes = this.constraintValidator.filterValidRecipes(loadedRecipes, constraints);

    if (validRecipes.length === 0) {
      return {
        success: false,
        error: 'No recipes satisfy the given constraints'
      };
    }

    // 3. Score each recipe against all objectives
    const scoredRecipes = validRecipes.map(recipe => ({
      recipe,
      scores: this.objectiveFunction.score(recipe, objectives)
    }));

    // 4. Build initial meal plan using greedy selection
    const initialPlan = this.greedyMealPlan(scoredRecipes, opts);

    // 5. Refine using local search
    const refinedPlan = this.localSearch(initialPlan, scoredRecipes, opts);

    // 6. Calculate variety metrics for the plan
    const varietyMetrics = this.varietyScorer.scoreMealPlanVariety(refinedPlan);

    // 7. Build Pareto frontier from multiple weightings
    const paretoSolutions = this.buildParetoSolutions(scoredRecipes, opts);

    // 8. Return the optimization result
    return {
      success: true,
      meal_plan: refinedPlan,
      variety_metrics: varietyMetrics,
      pareto_frontier: paretoSolutions,
      statistics: {
        total_recipes: loadedRecipes.length,
        valid_recipes: validRecipes.length,
        plan_meals: refinedPlan.length,
        pareto_solutions: paretoSolutions.length
      }
    };
  }

  /**
   * Load recipes from IDs or use directly if already objects
   */
  loadRecipes(recipes) {
    if (!recipes || recipes.length === 0) {
      return this.recipe.getAll({ limit: 1000 }).data;
    }

    return recipes.map(r => {
      if (typeof r === 'object') return r;
      return this.recipe.getById(r);
    }).filter(Boolean);
  }

  /**
   * Greedy meal plan construction
   * Selects best-scoring recipe for each meal slot
   */
  greedyMealPlan(scoredRecipes, config) {
    const { days, mealsPerDay } = config;
    const totalMeals = days * mealsPerDay;
    const plan = [];
    const usedRecipeIds = new Set();

    // Sort by total score
    const sorted = [...scoredRecipes].sort((a, b) => b.scores.total - a.scores.total);

    for (let i = 0; i < totalMeals && sorted.length > 0; i++) {
      // Find best unselected recipe
      let selected = null;
      for (const entry of sorted) {
        if (!usedRecipeIds.has(entry.recipe.id)) {
          selected = entry;
          usedRecipeIds.add(entry.recipe.id);
          break;
        }
      }

      // If all used, pick the best available (allow reuse)
      if (!selected && sorted.length > 0) {
        selected = sorted[i % sorted.length];
      }

      if (selected) {
        plan.push({
          recipe_id: selected.recipe.id,
          recipe_title: selected.recipe.title,
          scores: selected.scores,
          meal_slot: i
        });
      }
    }

    return plan;
  }

  /**
   * Local search refinement
   * Tries to improve the meal plan by swapping recipes
   */
  localSearch(initialPlan, scoredRecipes, config) {
    const { days, mealsPerDay } = config;
    const maxIterations = 10;
    let currentPlan = [...initialPlan];
    let currentScore = this.calculatePlanScore(currentPlan);

    for (let iter = 0; iter < maxIterations; iter++) {
      let improved = false;

      // Try swapping each meal with a better option
      for (let i = 0; i < currentPlan.length; i++) {
        const currentMeal = currentPlan[i];

        for (const candidate of scoredRecipes) {
          if (candidate.recipe.id === currentMeal.recipe_id) continue;

          // Try the swap
          const newPlan = [...currentPlan];
          newPlan[i] = {
            recipe_id: candidate.recipe.id,
            recipe_title: candidate.recipe.title,
            scores: candidate.scores,
            meal_slot: i
          };

          const newScore = this.calculatePlanScore(newPlan);

          if (newScore > currentScore) {
            currentPlan = newPlan;
            currentScore = newScore;
            improved = true;
          }
        }
      }

      if (!improved) break;
    }

    return currentPlan;
  }

  /**
   * Calculate total score for a meal plan
   */
  calculatePlanScore(plan) {
    if (!plan || plan.length === 0) return 0;

    return plan.reduce((sum, meal) => sum + (meal.scores?.total || 0), 0) / plan.length;
  }

  /**
   * Build multiple Pareto-optimal solutions with different weightings
   */
  buildParetoSolutions(scoredRecipes, config) {
    const weightings = [
      { cost: 0.6, nutrition: 0.3, variety: 0.1 },  // Cost-focused
      { cost: 0.1, nutrition: 0.6, variety: 0.3 },  // Nutrition-focused
      { cost: 0.1, nutrition: 0.3, variety: 0.6 },  // Variety-focused
      { cost: 0.33, nutrition: 0.34, variety: 0.33 } // Balanced
    ];

    const solutions = weightings.map(weights => {
      const ranked = scoredRecipes.map(entry => ({
        recipe_id: entry.recipe.id,
        recipe_title: entry.recipe.title,
        cost: entry.scores.cost,
        nutrition: entry.scores.nutrition,
        variety: entry.scores.variety,
        total: this.objectiveFunction.weightedScore(entry.recipe, weights),
        weights
      }));

      // Get best recipe for this weighting
      ranked.sort((a, b) => b.total - a.total);
      const best = ranked[0];

      return {
        ...best,
        strategy: weights.cost > weights.nutrition && weights.cost > weights.variety
          ? 'cost_optimized'
          : weights.nutrition > weights.variety
            ? 'nutrition_optimized'
            : 'variety_optimized'
      };
    });

    // Find Pareto frontier
    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false },
      { name: 'variety', minimize: false }
    ];

    return this.paretoFrontier.find(solutions, objectives);
  }

  /**
   * Find Pareto frontier from solutions
   */
  findParetoFrontier(solutions) {
    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false },
      { name: 'variety', minimize: false }
    ];

    return this.paretoFrontier.find(solutions, objectives);
  }
}

module.exports = MealPlanOptimizer;
