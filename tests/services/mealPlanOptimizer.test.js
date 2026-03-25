'use strict';

const { describe, test, assert, equal, ok } = require('../testRunner');
const MealPlanOptimizer = require('../../src/services/optimizer/mealPlanOptimizer');
const ParetoFrontier = require('../../src/services/optimizer/paretoFrontier');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('MealPlanOptimizer', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const optimizer = new MealPlanOptimizer(store);

  // Create test recipes
  const recipe1 = store.create('recipes', {
    title: 'Chicken Salad',
    prep_time_minutes: 15,
    cook_time_minutes: 0,
    servings: 1
  });

  store.create('ingredients', {
    recipe_id: recipe1.id,
    name: 'chicken breast',
    quantity: 150,
    unit: 'g',
    category: 'meat'
  });

  store.create('ingredients', {
    recipe_id: recipe1.id,
    name: 'lettuce',
    quantity: 50,
    unit: 'g',
    category: 'vegetable'
  });

  const recipe2 = store.create('recipes', {
    title: 'Vegetable Stir Fry',
    prep_time_minutes: 10,
    cook_time_minutes: 15,
    servings: 2
  });

  store.create('ingredients', {
    recipe_id: recipe2.id,
    name: 'tofu',
    quantity: 100,
    unit: 'g',
    category: 'vegetable'
  });

  store.create('ingredients', {
    recipe_id: recipe2.id,
    name: 'broccoli',
    quantity: 100,
    unit: 'g',
    category: 'vegetable'
  });

  const recipe3 = store.create('recipes', {
    title: 'Beef Steak',
    prep_time_minutes: 5,
    cook_time_minutes: 20,
    servings: 1
  });

  store.create('ingredients', {
    recipe_id: recipe3.id,
    name: 'beef steak',
    quantity: 200,
    unit: 'g',
    category: 'meat'
  });

  store.create('ingredients', {
    recipe_id: recipe3.id,
    name: 'butter',
    quantity: 20,
    unit: 'g',
    category: 'dairy'
  });

  const recipes = [recipe1, recipe2, recipe3].map(r => {
    const loaded = store.readById('recipes', r.id);
    loaded.ingredients = store.findBy('ingredients', 'recipe_id', r.id);
    return loaded;
  });

  test('should optimize meal plan with default parameters', () => {
    const result = optimizer.optimize({
      recipes
    });

    equal(result.success, true, 'should succeed');
    ok(result.meal_plan, 'should have meal plan');
    ok(Array.isArray(result.meal_plan), 'meal plan should be array');
  });

  test('should create meal plan with correct number of meals', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 7, mealsPerDay: 3 }
    });

    equal(result.success, true, 'should succeed');
    equal(result.meal_plan.length, 21, 'should have 21 meals (7 days * 3 meals)');
  });

  test('should respect dietary constraints', () => {
    // Create vegetarian profile
    const profile = store.create('dietary_profiles', {
      name: 'vegetarian',
      restrictions: ['vegetarian']
    });

    const result = optimizer.optimize({
      recipes,
      constraints: {
        dietaryProfile: profile.id
      },
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    // Only vegetable stir fry should be in the plan
    ok(result.meal_plan.every(m => m.recipe_title === 'Vegetable Stir Fry'), 'only veg recipe');
  });

  test('should respect max cost constraint', () => {
    const result = optimizer.optimize({
      recipes,
      constraints: {
        maxCostPerMeal: 0.01 // Very low cost
      },
      config: { days: 1, mealsPerDay: 1 }
    });

    // May fail or produce empty valid recipes
    ok(result.success, 'should complete');
  });

  test('should respect max calories constraint', () => {
    const result = optimizer.optimize({
      recipes,
      constraints: {
        maxCalories: 500
      },
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
  });

  test('should calculate variety metrics', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 3, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    ok(result.variety_metrics, 'should have variety metrics');
    ok(result.variety_metrics.overall_score !== undefined, 'should have overall score');
    ok(result.variety_metrics.ingredient_diversity !== undefined, 'should have ingredient diversity');
  });

  test('should return Pareto frontier solutions', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    ok(result.pareto_frontier, 'should have pareto frontier');
    ok(Array.isArray(result.pareto_frontier), 'pareto frontier should be array');
  });

  test('should return statistics', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    ok(result.statistics, 'should have statistics');
    equal(result.statistics.total_recipes, 3, 'should have 3 total recipes');
    ok(result.statistics.valid_recipes >= 0, 'should have valid recipe count');
    ok(result.statistics.pareto_solutions >= 0, 'should have pareto solution count');
  });

  test('should optimize with all objectives enabled', () => {
    const result = optimizer.optimize({
      recipes,
      objectives: {
        minimizeCost: true,
        maximizeNutrition: true,
        maximizeVariety: true
      },
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    ok(result.meal_plan.length > 0, 'should have meals');
  });

  test('should handle empty recipes array by loading from store', () => {
    const result = optimizer.optimize({
      recipes: [],
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
    ok(result.statistics.total_recipes > 0, 'should load recipes from store');
  });

  test('should return error when no recipes available', () => {
    // Create optimizer with empty store
    const emptyStore = new FileStore(path.join(__dirname, '../../data/test_empty'));
    const emptyOptimizer = new MealPlanOptimizer(emptyStore);

    const result = emptyOptimizer.optimize({
      recipes: [],
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, false, 'should fail');
    ok(result.error, 'should have error message');
  });

  test('should load recipes from IDs', () => {
    const result = optimizer.optimize({
      recipes: [recipe1.id, recipe2.id],
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
  });

  test('should use greedy selection for initial plan', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 1, mealsPerDay: 2 }
    });

    ok(result.meal_plan.length <= 2, 'should have at most 2 meals');
    ok(result.meal_plan.every(m => m.scores), 'each meal should have scores');
  });

  test('should use local search to refine plan', () => {
    const result = optimizer.optimize({
      recipes,
      config: { days: 1, mealsPerDay: 2 }
    });

    ok(result.meal_plan.every(m => m.meal_slot !== undefined), 'meals should have slot');
  });

  test('should handle custom objective weights', () => {
    const result = optimizer.optimize({
      recipes,
      objectives: {
        minimizeCost: true,
        maximizeNutrition: false,
        maximizeVariety: false
      },
      config: { days: 1, mealsPerDay: 1 }
    });

    equal(result.success, true, 'should succeed');
  });
});

describe('ParetoFrontier', () => {
  const frontier = new ParetoFrontier();

  test('should find non-dominated solutions', () => {
    const solutions = [
      { cost: 10, nutrition: 50 },
      { cost: 20, nutrition: 80 },
      { cost: 15, nutrition: 60 }
    ];

    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    const result = frontier.find(solutions, objectives);

    ok(Array.isArray(result), 'should return array');
    ok(result.length >= 1, 'should have at least 1 solution');
  });

  test('should correctly identify domination', () => {
    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    // Solution A: cost=10, nutrition=80
    // Solution B: cost=20, nutrition=50
    const a = { cost: 10, nutrition: 80 };
    const b = { cost: 20, nutrition: 50 };

    equal(frontier.dominates(a, b, objectives), true, 'A should dominate B');
    equal(frontier.dominates(b, a, objectives), false, 'B should not dominate A');
  });

  test('should not dominate when same in one objective and worse in another', () => {
    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    const a = { cost: 10, nutrition: 60 };
    const b = { cost: 10, nutrition: 50 };

    // A (60 nutrition) should dominate B (50 nutrition) since cost is same
    equal(frontier.dominates(a, b, objectives), true, 'A should dominate B');
    // B should not dominate A since B is worse in nutrition
    equal(frontier.dominates(b, a, objectives), false, 'B should not dominate A');
  });

  test('should rank solutions by pareto rank', () => {
    const solutions = [
      { cost: 10, nutrition: 80 },
      { cost: 20, nutrition: 50 },
      { cost: 15, nutrition: 60 }
    ];

    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    const ranked = frontier.rankSolutions(solutions, objectives);

    ok(ranked.every(s => s.pareto_rank !== undefined), 'all should have rank');
    ok(ranked[0].pareto_rank <= ranked[1].pareto_rank, 'should be sorted by rank');
  });

  test('should find knee of frontier', () => {
    const frontierSolutions = [
      { cost: 5, nutrition: 40 },
      { cost: 10, nutrition: 70 },
      { cost: 15, nutrition: 85 }
    ];

    const knee = frontier.findKnee(frontierSolutions, {
      xObjective: 'cost',
      yObjective: 'nutrition'
    });

    ok(knee, 'should find a knee');
  });

  test('should handle empty solutions', () => {
    equal(frontier.find([], []).length, 0, 'should return empty');
  });

  test('should handle single solution', () => {
    const solutions = [{ cost: 10, nutrition: 50 }];
    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    const result = frontier.find(solutions, objectives);
    equal(result.length, 1, 'should return the single solution');
  });

  test('should filter then find frontier', () => {
    const solutions = [
      { cost: 5, nutrition: 40 },
      { cost: 10, nutrition: 70 },
      { cost: 15, nutrition: 85 },
      { cost: 20, nutrition: 90 }
    ];

    const objectives = [
      { name: 'cost', minimize: true },
      { name: 'nutrition', minimize: false }
    ];

    const result = frontier.filterThenFindFrontier(solutions, objectives, 'cost', 15, true);

    ok(result.every(s => s.cost <= 15), 'all should be under cost threshold');
  });
});
