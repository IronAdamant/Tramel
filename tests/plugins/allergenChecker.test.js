'use strict';

const { describe, test, ok } = require('../testRunner');
const allergenChecker = require('../../src/plugins/plugins/allergenChecker');

describe('allergenChecker plugin', () => {
  describe('plugin structure', () => {
    test('should have correct name', () => {
      ok(allergenChecker.name === 'allergenChecker');
    });

    test('should subscribe to beforeCreate, beforeUpdate, and onAllergenDetected hooks', () => {
      ok(allergenChecker.hooks.includes('beforeCreate'));
      ok(allergenChecker.hooks.includes('beforeUpdate'));
      ok(allergenChecker.hooks.includes('onAllergenDetected'));
      ok(allergenChecker.hooks.length === 3);
    });

    test('should have handler function', () => {
      ok(typeof allergenChecker.handler === 'function');
    });
  });

  describe('handler - beforeCreate and beforeUpdate', () => {
    test('should detect peanuts in ingredients', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {
        ingredients: [
          { name: 'Peanuts' },
          { name: 'Roasted Peanuts' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens !== undefined);
      ok(result.allergens.length === 2);
      ok(result.allergens[0].allergen === 'peanuts');
      ok(result.allergens[1].allergen === 'peanuts');
    });

    test('should detect milk and eggs in ingredients', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {
        ingredients: [
          { name: 'Milk' },
          { name: 'Eggs' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens.length === 2);
      ok(result.allergens.map(a => a.allergen).includes('milk'));
      ok(result.allergens.map(a => a.allergen).includes('eggs'));
    });

    test('should detect wheat allergen in bread', async () => {
      const ctx = { hook: 'beforeUpdate' };
      const entity = {
        ingredients: [
          { name: 'Whole Wheat Bread' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens !== undefined);
      ok(result.allergens.length === 1);
      ok(result.allergens[0].allergen === 'wheat');
    });

    test('should return context without allergens when none detected', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {
        ingredients: [
          { name: 'Rice' },
          { name: 'Chicken' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens === undefined);
    });

    test('should handle entity with no ingredients', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {};

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens === undefined);
    });

    test('should handle array of ingredients', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {
        ingredients: [
          { name: 'Peanuts' },
          { name: 'Milk' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens !== undefined);
      ok(result.allergens.length === 2);
    });

    test('should do case-insensitive matching', async () => {
      const ctx = { hook: 'beforeCreate' };
      const entity = {
        ingredients: [
          { name: 'MILK' },
          { name: 'Eggs' }
        ]
      };

      const result = await allergenChecker.handler(ctx, entity);

      ok(result.allergens.length === 2);
    });
  });

  describe('handler - onAllergenDetected', () => {
    test('should log allergen detection event', async () => {
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'onAllergenDetected' };
      const allergenInfo = { ingredient: 'Peanuts', allergen: 'peanuts' };

      await allergenChecker.handler(ctx, allergenInfo);

      console.log = originalLog;
      ok(logged);
    });

    test('should return context on onAllergenDetected hook', async () => {
      const ctx = { hook: 'onAllergenDetected' };
      const allergenInfo = {};

      const result = await allergenChecker.handler(ctx, allergenInfo);

      ok(result === ctx);
    });
  });
});
