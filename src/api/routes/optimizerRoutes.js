'use strict';

const { createRouter } = require('../../utils/router');
const MealPlanOptimizer = require('../../services/optimizer/mealPlanOptimizer');
const Recipe = require('../../models/Recipe');
const DietaryProfile = require('../../models/DietaryProfile');
const { success, badRequest, notFound, error } = require('../../utils/response');

const router = createRouter();

/**
 * GET /optimize/meal-plan
 * Optimize a meal plan based on objectives and constraints
 *
 * Query params:
 * - minimizeCost: 'true'/'false' (default: true)
 * - maximizeNutrition: 'true'/'false' (default: true)
 * - maxVariety: 'true'/'false' (default: true)
 * - dietaryProfile: profile ID or 'veg'/'vegan'/'gf'
 * - maxCostPerMeal: number (max cost per serving)
 * - maxCalories: number (max calories per serving)
 * - days: number (default: 7)
 * - mealsPerDay: number (default: 3)
 * - recipeIds: comma-separated recipe IDs (optional)
 */
router.get('/meal-plan', (req, res) => {
  const { query } = req;

  // Parse query parameters
  const objectives = {
    minimizeCost: query.minimizeCost !== 'false',
    maximizeNutrition: query.maximizeNutrition !== 'false',
    maximizeVariety: query.maxVariety !== 'false'
  };

  const constraints = {};

  // Parse dietary profile
  if (query.dietaryProfile) {
    const profileId = resolveDietaryProfile(req.db, query.dietaryProfile);
    if (profileId) {
      constraints.dietaryProfile = profileId;
    }
  }

  // Parse numeric constraints
  if (query.maxCostPerMeal) {
    const maxCost = parseFloat(query.maxCostPerMeal);
    if (!isNaN(maxCost) && maxCost > 0) {
      constraints.maxCostPerMeal = maxCost;
    }
  }

  if (query.maxCalories) {
    const maxCalories = parseInt(query.maxCalories, 10);
    if (!isNaN(maxCalories) && maxCalories > 0) {
      constraints.maxCalories = maxCalories;
    }
  }

  // Parse config
  const config = {
    days: parseInt(query.days, 10) || 7,
    mealsPerDay: parseInt(query.mealsPerDay, 10) || 3
  };

  // Parse recipe IDs
  let recipeIds = null;
  if (query.recipeIds) {
    recipeIds = query.recipeIds.split(',').map(id => id.trim()).filter(Boolean);
  }

  // Get recipes
  const recipe = new Recipe(req.db);
  let recipes;

  if (recipeIds && recipeIds.length > 0) {
    recipes = recipeIds.map(id => recipe.getById(id)).filter(Boolean);
  } else {
    recipes = recipe.getAll({ limit: 1000 }).data;
  }

  if (recipes.length === 0) {
    return notFound(res, 'No recipes found');
  }

  // Run optimizer
  const optimizer = new MealPlanOptimizer(req.db);
  const result = optimizer.optimize({
    recipes,
    constraints,
    objectives,
    config
  });

  if (!result.success) {
    return badRequest(res, result.error);
  }

  return success(res, {
    meal_plan: result.meal_plan,
    variety_metrics: result.variety_metrics,
    pareto_frontier: result.pareto_frontier,
    statistics: result.statistics,
    parameters: {
      objectives,
      constraints,
      config
    }
  });
});

/**
 * Resolve dietary profile from string
 */
function resolveDietaryProfile(db, profileStr) {
  const profile = new DietaryProfile(db);

  // Check if it's a numeric ID
  if (/^\d+$/.test(profileStr)) {
    const existing = profile.getById(parseInt(profileStr, 10));
    if (existing) return existing.id;
  }

  // Check common aliases
  const aliases = {
    'veg': 'vegetarian',
    'vegetarian': 'vegetarian',
    'vegan': 'vegan',
    'gf': 'gluten-free',
    'gluten-free': 'gluten-free',
    'df': 'dairy-free',
    'dairy-free': 'dairy-free'
  };

  const normalized = aliases[profileStr.toLowerCase()];
  if (normalized) {
    const all = profile.getAll();
    const found = all.find(p =>
      p.name.toLowerCase() === normalized ||
      p.name.toLowerCase().includes(normalized)
    );
    if (found) return found.id;
  }

  return null;
}

/**
 * POST /optimize/meal-plan/compare
 * Compare multiple meal plans
 */
router.post('/meal-plan/compare', (req, res) => {
  const { mealPlans } = req.body;

  if (!Array.isArray(mealPlans) || mealPlans.length < 2) {
    return badRequest(res, 'At least 2 meal plans required for comparison');
  }

  const optimizer = new MealPlanOptimizer(req.db);
  const RecipeModel = new Recipe(req.db);

  const comparisons = mealPlans.map(plan => {
    const recipes = (plan.recipeIds || []).map(id => RecipeModel.getById(id)).filter(Boolean);
    const result = optimizer.optimize({
      recipes,
      constraints: plan.constraints || {},
      objectives: plan.objectives || {},
      config: plan.config || {}
    });

    return {
      plan_id: plan.id || plan.plan_id || `plan_${Math.random().toString(36).substr(2, 9)}`,
      ...result
    };
  });

  // Rank by overall score
  comparisons.sort((a, b) => {
    const scoreA = a.meal_plan?.reduce((s, m) => s + (m.scores?.total || 0), 0) / (a.meal_plan?.length || 1) || 0;
    const scoreB = b.meal_plan?.reduce((s, m) => s + (m.scores?.total || 0), 0) / (b.meal_plan?.length || 1) || 0;
    return scoreB - scoreA;
  });

  return success(res, {
    comparisons,
    ranked_plans: comparisons.map((c, i) => ({
      rank: i + 1,
      plan_id: c.plan_id,
      score: c.meal_plan?.reduce((s, m) => s + (m.scores?.total || 0), 0) / (c.meal_plan?.length || 1) || 0,
      meal_count: c.meal_plan?.length || 0
    }))
  });
});

module.exports = router;
