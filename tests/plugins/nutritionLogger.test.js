'use strict';

const { describe, test, ok } = require('../testRunner');
const nutritionLogger = require('../../src/plugins/plugins/nutritionLogger');

describe('nutritionLogger plugin', () => {
  describe('plugin structure', () => {
    test('should have correct name', () => {
      ok(nutritionLogger.name === 'nutritionLogger');
    });

    test('should subscribe to onNutrientCalculated and afterScale hooks', () => {
      ok(nutritionLogger.hooks.includes('onNutrientCalculated'));
      ok(nutritionLogger.hooks.includes('afterScale'));
      ok(nutritionLogger.hooks.length === 2);
    });

    test('should have handler function', () => {
      ok(typeof nutritionLogger.handler === 'function');
    });
  });

  describe('handler - onNutrientCalculated', () => {
    test('should log nutrient calculation with recipe name', async () => {
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'onNutrientCalculated' };
      const recipe = { name: 'Test Recipe' };
      const nutritionData = { calories: 500, protein: 30 };

      await nutritionLogger.handler(ctx, recipe, nutritionData);

      console.log = originalLog;
      ok(logged);
    });

    test('should log nutrient calculation with unknown recipe for missing name', async () => {
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'onNutrientCalculated' };
      const recipe = {};
      const nutritionData = { calories: 100, protein: 10 };

      await nutritionLogger.handler(ctx, recipe, nutritionData);

      console.log = originalLog;
      ok(logged);
    });

    test('should return context object', async () => {
      const ctx = { hook: 'onNutrientCalculated' };

      const result = await nutritionLogger.handler(ctx, {}, {});

      ok(result === ctx);
    });
  });

  describe('handler - afterScale', () => {
    test('should log scale operation with factor', async () => {
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'afterScale' };
      const scaledRecipe = { name: 'Scaled Recipe' };
      const scaleFactor = 2;

      await nutritionLogger.handler(ctx, scaledRecipe, scaleFactor);

      console.log = originalLog;
      ok(logged);
    });
  });
});
