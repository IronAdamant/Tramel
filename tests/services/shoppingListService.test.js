'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const ShoppingListService = require('../../src/services/shoppingListService');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('ShoppingListService', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const service = new ShoppingListService(store);

  test('should categorize ingredients', () => {
    const items = [
      { ingredient_name: 'tomato', quantity: 2 },
      { ingredient_name: 'chicken breast', quantity: 1 },
      { ingredient_name: 'milk', quantity: 1 },
      { ingredient_name: 'bread', quantity: 1 }
    ];

    const categorized = service.categorizeIngredients(items);

    assert.ok(Array.isArray(categorized.Produce));
    assert.ok(Array.isArray(categorized.Meat));
    assert.ok(Array.isArray(categorized.Dairy));
    assert.ok(Array.isArray(categorized.Bakery));
  });

  test('should estimate quantities', () => {
    const items = [
      { ingredient_name: 'flour', quantity: 1, unit: 'cup' },
      { ingredient_name: 'flour', quantity: 0.5, unit: 'cup' }
    ];

    const estimated = service.estimateQuantities(items);

    equal(estimated.length, 1);
    equal(estimated[0].quantity, 1.5);
  });
});
