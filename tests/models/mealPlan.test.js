'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const MealPlan = require('../../src/models/MealPlan');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('MealPlan Model', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const mealPlan = new MealPlan(store);

  test('should create a meal plan', () => {
    const created = mealPlan.create({
      name: 'Week 1',
      start_date: '2024-01-01',
      end_date: '2024-01-07'
    });

    assert.ok(created.id !== undefined);
    equal(created.name, 'Week 1');
    equal(created.start_date, '2024-01-01');
  });

  test('should get meal plan with entries', () => {
    const created = mealPlan.create({
      name: 'With Entries',
      start_date: '2024-01-01'
    });

    mealPlan.addEntry({
      meal_plan_id: created.id,
      recipe_id: 'test-recipe-1',
      date: '2024-01-01',
      meal_type: 'breakfast',
      servings: 2
    });

    const fetched = mealPlan.getById(created.id);

    assert.ok(Array.isArray(fetched.entries));
    equal(fetched.entries.length, 1);
  });

  test('should add entry to meal plan', () => {
    const plan = mealPlan.create({
      name: 'Entry Test',
      start_date: '2024-01-01'
    });

    const entry = mealPlan.addEntry({
      meal_plan_id: plan.id,
      recipe_id: 'recipe-123',
      date: '2024-01-02',
      meal_type: 'lunch',
      servings: 3
    });

    assert.ok(entry.id !== undefined);
    equal(entry.meal_type, 'lunch');
    equal(entry.servings, 3);
  });

  test('should remove entry from meal plan', () => {
    const plan = mealPlan.create({
      name: 'Remove Entry Test',
      start_date: '2024-01-01'
    });

    const entry = mealPlan.addEntry({
      meal_plan_id: plan.id,
      recipe_id: 'recipe-1',
      date: '2024-01-01',
      meal_type: 'dinner',
      servings: 1
    });

    const result = mealPlan.removeEntry(entry.id);
    equal(result, true);
  });

  test('should delete meal plan and its entries', () => {
    const plan = mealPlan.create({
      name: 'Delete Test',
      start_date: '2024-01-01'
    });

    mealPlan.addEntry({
      meal_plan_id: plan.id,
      recipe_id: 'recipe-1',
      date: '2024-01-01',
      meal_type: 'breakfast',
      servings: 1
    });

    const result = mealPlan.delete(plan.id);
    equal(result, true);
  });
});
