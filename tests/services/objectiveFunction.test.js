'use strict';

const { describe, test, assert, equal, deepEqual, ok } = require('../testRunner');
const ObjectiveFunction = require('../../src/services/optimizer/objectiveFunction');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('ObjectiveFunction', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const objectiveFunction = new ObjectiveFunction(store);

  // Create test recipe
  const testRecipe = store.create('recipes', {
    title: 'Test Recipe',
    prep_time_minutes: 15,
    cook_time_minutes: 30,
    servings: 2
  });

  // Add test ingredients
  store.create('ingredients', {
    recipe_id: testRecipe.id,
    name: 'chicken breast',
    quantity: 200,
    unit: 'g',
    category: 'meat'
  });

  store.create('ingredients', {
    recipe_id: testRecipe.id,
    name: 'tomato',
    quantity: 100,
    unit: 'g',
    category: 'vegetable'
  });

  store.create('ingredients', {
    recipe_id: testRecipe.id,
    name: 'rice',
    quantity: 100,
    unit: 'g',
    category: 'grain'
  });

  const loadedRecipe = store.readById('recipes', testRecipe.id);
  loadedRecipe.ingredients = store.findBy('ingredients', 'recipe_id', testRecipe.id);

  test('should score recipe with defaults', () => {
    const result = objectiveFunction.score(loadedRecipe);

    ok(result.cost !== undefined, 'should have cost score');
    ok(result.nutrition !== undefined, 'should have nutrition score');
    ok(result.variety !== undefined, 'should have variety score');
    ok(result.total !== undefined, 'should have total score');
    ok(result.cost >= 0 && result.cost <= 100, 'cost should be 0-100');
    ok(result.nutrition >= 0 && result.nutrition <= 100, 'nutrition should be 0-100');
    ok(result.variety >= 0 && result.variety <= 100, 'variety should be 0-100');
  });

  test('should calculate cost score', () => {
    const result = objectiveFunction.scoreCost(loadedRecipe);

    equal(typeof result, 'number', 'should return a number');
    ok(result >= 0 && result <= 100, 'should be between 0 and 100');
  });

  test('should calculate nutrition score', () => {
    const result = objectiveFunction.scoreNutrition(loadedRecipe);

    equal(typeof result, 'number', 'should return a number');
    ok(result >= 0 && result <= 100, 'should be between 0 and 100');
  });

  test('should calculate variety score', () => {
    const result = objectiveFunction.scoreVariety(loadedRecipe);

    equal(typeof result, 'number', 'should return a number');
    ok(result >= 0 && result <= 100, 'should be between 0 and 100');
  });

  test('should normalize values correctly', () => {
    equal(objectiveFunction.normalize(50, 0, 100), 50);
    equal(objectiveFunction.normalize(0, 0, 100), 0);
    equal(objectiveFunction.normalize(100, 0, 100), 100);
    equal(objectiveFunction.normalize(25, 0, 100), 25);
  });

  test('should handle zero range in normalization', () => {
    equal(objectiveFunction.normalize(50, 50, 50), 50); // max === min
  });

  test('should handle values outside range in normalization', () => {
    equal(objectiveFunction.normalize(150, 0, 100), 100); // Clamped to max
    equal(objectiveFunction.normalize(-50, 0, 100), 0);   // Clamped to min
  });

  test('should calculate weighted score', () => {
    const result = objectiveFunction.weightedScore(loadedRecipe, {
      cost: 0.5,
      nutrition: 0.3,
      variety: 0.2
    });

    equal(typeof result, 'number', 'should return a number');
    ok(result >= 0 && result <= 100, 'should be between 0 and 100');
  });

  test('should rank recipes by total score', () => {
    const recipe2 = store.create('recipes', {
      title: 'Test Recipe 2',
      prep_time_minutes: 10,
      cook_time_minutes: 20,
      servings: 1
    });

    store.create('ingredients', {
      recipe_id: recipe2.id,
      name: 'beef',
      quantity: 150,
      unit: 'g',
      category: 'meat'
    });

    const loaded2 = store.readById('recipes', recipe2.id);
    loaded2.ingredients = store.findBy('ingredients', 'recipe_id', recipe2.id);

    const ranked = objectiveFunction.rankRecipes([loadedRecipe, loaded2]);

    ok(Array.isArray(ranked), 'should return an array');
    equal(ranked.length, 2, 'should have 2 items');
    ok(ranked[0].scores, 'first item should have scores');
    ok(ranked[1].scores, 'second item should have scores');
    ok(ranked[0].scores.total >= ranked[1].scores.total, 'first should have >= score');
  });

  test('should respect minimizeCost objective', () => {
    const withMinimize = objectiveFunction.score(loadedRecipe, { minimizeCost: true });
    const withoutMinimize = objectiveFunction.score(loadedRecipe, { minimizeCost: false });

    // When minimizeCost is true, lower cost = higher score
    // When minimizeCost is false, higher cost = higher score (inverted)
    // The cost score component should be different
    ok(withMinimize.cost !== withoutMinimize.cost, 'cost scores should differ');
  });

  test('should respect maximizeNutrition objective', () => {
    const withMax = objectiveFunction.score(loadedRecipe, { maximizeNutrition: true });
    const withoutMax = objectiveFunction.score(loadedRecipe, { maximizeNutrition: false });

    ok(withMax.nutrition !== withoutMax.nutrition, 'nutrition scores should differ');
  });

  test('should respect maximizeVariety objective', () => {
    const withMax = objectiveFunction.score(loadedRecipe, { maximizeVariety: true });
    const withoutMax = objectiveFunction.score(loadedRecipe, { maximizeVariety: false });

    ok(withMax.variety !== withoutMax.variety, 'variety scores should differ');
  });

  test('should use default weights when calculating total', () => {
    const result = objectiveFunction.score(loadedRecipe);

    // Total should be approximately weighted sum
    const expectedTotal = result.cost * 0.33 + result.nutrition * 0.34 + result.variety * 0.33;
    ok(Math.abs(result.total - expectedTotal) < 0.01, 'total should be weighted sum');
  });

  test('should handle empty objectives object', () => {
    const result = objectiveFunction.score(loadedRecipe, {});

    ok(result.cost !== undefined, 'should have cost');
    ok(result.nutrition !== undefined, 'should have nutrition');
    ok(result.variety !== undefined, 'should have variety');
  });

  test('should handle recipe with no ingredients', () => {
    const emptyRecipe = store.create('recipes', {
      title: 'Empty Recipe',
      prep_time_minutes: 5,
      cook_time_minutes: 5,
      servings: 1
    });

    const loaded = store.readById('recipes', emptyRecipe.id);
    loaded.ingredients = [];

    const result = objectiveFunction.scoreVariety(loaded);
    equal(result, 50, 'should return default score of 50 for empty ingredients');
  });
});
