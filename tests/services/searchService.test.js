'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const SearchService = require('../../src/services/searchService');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('SearchService', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const service = new SearchService(store);

  test('should search recipes by query', () => {
    store.create('recipes', { title: 'Chocolate Cake', description: 'Delicious dessert' });
    store.create('recipes', { title: 'Vanilla Ice Cream', description: 'Sweet treat' });

    const results = service.search({ query: 'chocolate' });

    assert.ok(Array.isArray(results));
    assert.ok(results.some(r => r.title.includes('Chocolate')));
  });

  test('should find recipes by ingredient', () => {
    const recipe = store.create('recipes', { title: 'Test Recipe' });
    store.create('ingredients', { recipe_id: recipe.id, name: 'tomato' });

    const results = service.findByIngredient('tomato');

    assert.ok(results.length >= 1);
  });

  test('should find quick recipes', () => {
    store.create('recipes', {
      title: 'Quick Recipe',
      prep_time_minutes: 5,
      cook_time_minutes: 5
    });
    store.create('recipes', {
      title: 'Long Recipe',
      prep_time_minutes: 30,
      cook_time_minutes: 60
    });

    const results = service.findQuickRecipes(15);

    assert.ok(results.every(r => {
      const total = (r.prep_time_minutes || 0) + (r.cook_time_minutes || 0);
      return total <= 30;
    }));
  });
});
