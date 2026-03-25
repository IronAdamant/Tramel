'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const Recipe = require('../../src/models/Recipe');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('Recipe Model', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const recipe = new Recipe(store);

  test('should create a recipe', () => {
    const created = recipe.create({
      title: 'Test Recipe',
      description: 'A test recipe',
      prep_time_minutes: 10,
      cook_time_minutes: 20,
      servings: 4
    });

    assert.ok(created.id !== undefined);
    equal(created.title, 'Test Recipe');
    equal(created.prep_time_minutes, 10);
    equal(created.cook_time_minutes, 20);
    equal(created.servings, 4);
  });

  test('should get recipe by id with ingredients and tags', () => {
    const created = recipe.create({
      title: 'Full Recipe',
      ingredients: [
        { name: 'flour', quantity: 2, unit: 'cups' },
        { name: 'sugar', quantity: 1, unit: 'cup' }
      ],
      tags: ['dessert', 'sweet']
    });

    const fetched = recipe.getById(created.id);

    assert.ok(fetched !== null);
    equal(fetched.title, 'Full Recipe');
    assert.ok(Array.isArray(fetched.ingredients));
    equal(fetched.ingredients.length, 2);
  });

  test('should get all recipes with pagination', () => {
    recipe.create({ title: 'Recipe 1' });
    recipe.create({ title: 'Recipe 2' });

    const result = recipe.getAll({ limit: 10, offset: 0 });

    assert.ok(Array.isArray(result.data));
    assert.ok(result.total >= 2);
  });

  test('should update a recipe', () => {
    const created = recipe.create({ title: 'Original' });
    const updated = recipe.update(created.id, { title: 'Updated' });

    equal(updated.title, 'Updated');
  });

  test('should delete a recipe and its related data', () => {
    const created = recipe.create({
      title: 'To Delete',
      ingredients: [{ name: 'test', quantity: 1 }]
    });

    const result = recipe.delete(created.id);
    equal(result, true);

    const fetched = recipe.getById(created.id);
    equal(fetched, null);
  });

  test('should search recipes by query', () => {
    recipe.create({ title: 'Pasta Carbonara', description: 'Italian pasta' });
    recipe.create({ title: 'Chicken Soup', description: 'Comfort food' });

    const results = recipe.search({ query: 'pasta' });

    assert.ok(results.length >= 1);
    assert.ok(results.some(r => r.title.includes('Pasta')));
  });

  test('should filter recipes by max time', () => {
    recipe.create({
      title: 'Quick Recipe',
      prep_time_minutes: 5,
      cook_time_minutes: 5
    });
    recipe.create({
      title: 'Long Recipe',
      prep_time_minutes: 30,
      cook_time_minutes: 60
    });

    const results = recipe.search({ maxTime: 15 });
    // Should only return recipes with total time <= 15
    for (const r of results) {
      const total = (r.prep_time_minutes || 0) + (r.cook_time_minutes || 0);
      if (total > 15) {
        throw new Error(`Recipe ${r.title} has total time ${total} > 15`);
      }
    }
  });

  test('should add ingredient to recipe', () => {
    const created = recipe.create({ title: 'Base Recipe' });
    const added = recipe.addIngredient(created.id, {
      name: 'New Ingredient',
      quantity: 2,
      unit: 'tbsp'
    });

    assert.ok(added.id !== undefined);
    equal(added.name, 'New Ingredient');
  });

  test('should calculate total time', () => {
    const created = recipe.create({
      title: 'Time Test',
      prep_time_minutes: 15,
      cook_time_minutes: 30
    });

    equal(recipe.getTotalTime(created.id), 45);
  });
});
