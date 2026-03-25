'use strict';

const NutritionService = require('../nutritionService');
const CostEstimationService = require('../costEstimationService');

/**
 * ObjectiveFunction - Calculates weighted scores for recipes based on optimization objectives
 */
class ObjectiveFunction {
  constructor(fileStore) {
    this.store = fileStore;
    this.nutritionService = new NutritionService(fileStore);
    this.costService = new CostEstimationService(fileStore);
  }

  /**
   * Calculate weighted score for a recipe against objectives
   * @param {Object} recipe - The recipe to score
   * @param {Object} objectives - { minimizeCost, maximizeNutrition, maximizeVariety }
   * @returns {Object} { cost: 0-100, nutrition: 0-100, variety: 0-100, total: weighted sum }
   */
  score(recipe, objectives = {}) {
    const defaults = {
      minimizeCost: true,
      maximizeNutrition: true,
      maximizeVariety: true
    };

    const opts = { ...defaults, ...objectives };

    const scores = {
      cost: opts.minimizeCost ? this.scoreCost(recipe) : 100 - this.scoreCost(recipe),
      nutrition: opts.maximizeNutrition ? this.scoreNutrition(recipe) : 100 - this.scoreNutrition(recipe),
      variety: opts.maximizeVariety ? this.scoreVariety(recipe) : 100 - this.scoreVariety(recipe)
    };

    // Weighted sum (equal weights by default)
    const weights = { cost: 0.33, nutrition: 0.34, variety: 0.33 };
    scores.total = (
      scores.cost * weights.cost +
      scores.nutrition * weights.nutrition +
      scores.variety * weights.variety
    );

    return scores;
  }

  /**
   * Score recipe cost (0-100, lower cost = higher score)
   */
  scoreCost(recipe) {
    const costEstimate = this.costService.estimateRecipeCost(recipe.id);
    if (!costEstimate) return 50; // Default mid-score if no cost data

    // Assume max reasonable cost is $30 per serving
    const maxCost = 30;
    const actualCost = costEstimate.per_serving || 0;

    return this.normalize(actualCost, 0, maxCost);
  }

  /**
   * Score recipe nutrition (0-100, higher nutrition = higher score)
   */
  scoreNutrition(recipe) {
    const nutrition = this.nutritionService.estimateRecipeNutrition(recipe.id);
    if (!nutrition) return 50; // Default mid-score if no nutrition data

    // Score based on protein and fiber (beneficial) and calories (neutral)
    const proteinScore = Math.min(nutrition.per_serving.protein / 30 * 100, 100); // 30g = 100%
    const fiberScore = Math.min(nutrition.per_serving.fiber / 15 * 100, 100); // 15g = 100%
    const calorieScore = 100 - Math.min(nutrition.per_serving.calories / 800 * 100, 100); // 800 cal = 0%

    return (proteinScore * 0.4) + (fiberScore * 0.3) + (calorieScore * 0.3);
  }

  /**
   * Score variety based on ingredient diversity and category spread
   */
  scoreVariety(recipe) {
    if (!recipe.ingredients || recipe.ingredients.length === 0) {
      return 50;
    }

    // Number of unique ingredients
    const uniqueIngredients = new Set(
      recipe.ingredients.map(i => i.name.toLowerCase())
    ).size;

    // Normalize: 5+ ingredients = full score
    const ingredientScore = Math.min(uniqueIngredients / 5 * 100, 100);

    // Category diversity
    const categories = new Set(
      recipe.ingredients.map(i => i.category || 'other')
    );
    const categoryScore = Math.min(categories.size / 4 * 100, 100); // 4+ categories = full

    return (ingredientScore * 0.6) + (categoryScore * 0.4);
  }

  /**
   * Normalize a value to 0-100 range
   * @param {number} value - The value to normalize
   * @param {number} min - Minimum value
   * @param {number} max - Maximum value
   * @returns {number} Normalized value 0-100
   */
  normalize(value, min, max) {
    if (max === min) return 50; // Avoid division by zero
    const normalized = ((value - min) / (max - min)) * 100;
    return Math.max(0, Math.min(100, normalized));
  }

  /**
   * Calculate weighted score with custom weights
   * @param {Object} recipe - The recipe to score
   * @param {Object} weights - { cost: 0-1, nutrition: 0-1, variety: 0-1 }
   * @returns {number} Weighted total score
   */
  weightedScore(recipe, weights = {}) {
    const defaults = { cost: 0.33, nutrition: 0.34, variety: 0.33 };
    const w = { ...defaults, ...weights };

    const scores = this.score(recipe);

    return (
      scores.cost * w.cost +
      scores.nutrition * w.nutrition +
      scores.variety * w.variety
    );
  }

  /**
   * Score multiple recipes and return sorted by total score
   * @param {Array} recipes - Array of recipes to score
   * @param {Object} objectives - Optimization objectives
   * @returns {Array} Recipes with scores, sorted by total score descending
   */
  rankRecipes(recipes, objectives = {}) {
    return recipes
      .map(recipe => ({
        recipe,
        scores: this.score(recipe, objectives)
      }))
      .sort((a, b) => b.scores.total - a.scores.total);
  }
}

module.exports = ObjectiveFunction;
