/**
 * MergeService Tests
 * Tests for 3-way merge with conflict detection
 */

const { describe, test, assert } = require('../testRunner');
const MergeService = require('../../src/services/mergeService');

describe('MergeService', () => {
  const mergeService = new MergeService();

  describe('threeWayMerge()', () => {
    test('should merge identical states without conflicts', () => {
      const base = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix dry ingredients'],
        title: 'Recipe'
      };
      const target = JSON.parse(JSON.stringify(base));
      const source = JSON.parse(JSON.stringify(base));

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.strictEqual(result.conflicts.length, 0);
      assert.strictEqual(result.result.ingredients.length, 1);
    });

    test('should detect conflict when same field modified differently', () => {
      const base = {
        ingredients: [],
        instructions: [],
        title: 'Original Title'
      };
      const target = {
        ingredients: [],
        instructions: [],
        title: 'Target Title'
      };
      const source = {
        ingredients: [],
        instructions: [],
        title: 'Source Title'
      };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.ok(result.conflicts.length > 0);
      assert.ok(result.conflicts.some(c => c.fieldPath === 'title'));
    });

    test('should auto-merge when only target changed', () => {
      const base = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };
      const target = {
        ingredients: [{ name: 'Flour', quantity: '3', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };
      const source = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.strictEqual(result.result.ingredients[0].quantity, '3');
    });

    test('should auto-merge when only source changed', () => {
      const base = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };
      const target = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };
      const source = {
        ingredients: [{ name: 'Flour', quantity: '3', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.strictEqual(result.result.ingredients[0].quantity, '3');
    });

    test('should add new ingredients from both branches', () => {
      const base = {
        ingredients: [],
        instructions: [],
        title: 'Recipe'
      };
      const target = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: [],
        title: 'Recipe'
      };
      const source = {
        ingredients: [{ name: 'Sugar', quantity: '1', unit: 'cup' }],
        instructions: [],
        title: 'Recipe'
      };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.strictEqual(result.result.ingredients.length, 2);
      assert.ok(result.result.ingredients.some(i => i.name === 'Flour'));
      assert.ok(result.result.ingredients.some(i => i.name === 'Sugar'));
    });

    test('should handle missing base gracefully', () => {
      const base = null;
      const target = {
        ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };
      const source = {
        ingredients: [{ name: 'Sugar', quantity: '1', unit: 'cup' }],
        instructions: ['Mix'],
        title: 'Recipe'
      };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, false);
      assert.ok(result.error.includes('required'));
    });

    test('should merge tags arrays', () => {
      const base = { tags: ['easy'], ingredients: [], instructions: [], title: 'Recipe' };
      const target = { tags: ['easy', 'quick'], ingredients: [], instructions: [], title: 'Recipe' };
      const source = { tags: ['easy', 'dessert'], ingredients: [], instructions: [], title: 'Recipe' };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.ok(result.result.tags.includes('easy'));
      assert.ok(result.result.tags.includes('quick'));
      assert.ok(result.result.tags.includes('dessert'));
    });

    test('should merge dietaryFlags objects', () => {
      const base = { dietaryFlags: { vegan: false }, ingredients: [], instructions: [], title: 'Recipe' };
      const target = { dietaryFlags: { vegan: false, glutenFree: true }, ingredients: [], instructions: [], title: 'Recipe' };
      const source = { dietaryFlags: { vegan: true }, ingredients: [], instructions: [], title: 'Recipe' };

      const result = mergeService.threeWayMerge(base, target, source);

      assert.strictEqual(result.success, true);
      assert.strictEqual(result.result.dietaryFlags.vegan, true);
      assert.strictEqual(result.result.dietaryFlags.glutenFree, true);
    });
  });

  describe('detectConflict()', () => {
    test('should detect conflict when both modified differently', () => {
      const base = { name: 'Flour', quantity: '2' };
      const target = { name: 'Flour', quantity: '3' };
      const source = { name: 'Flour', quantity: '4' };

      const result = mergeService.detectConflict(target, source, base);

      assert.strictEqual(result, true);
    });

    test('should not detect conflict when same change made', () => {
      const base = { name: 'Flour', quantity: '2' };
      const target = { name: 'Flour', quantity: '3' };
      const source = { name: 'Flour', quantity: '3' };

      const result = mergeService.detectConflict(target, source, base);

      assert.strictEqual(result, false);
    });

    test('should not detect conflict when neither changed', () => {
      const base = { name: 'Flour', quantity: '2' };
      const target = { name: 'Flour', quantity: '2' };
      const source = { name: 'Flour', quantity: '2' };

      const result = mergeService.detectConflict(target, source, base);

      assert.strictEqual(result, false);
    });

    test('should detect conflict when source removed item target modified', () => {
      const base = { name: 'Flour', quantity: '2' };
      const target = { name: 'Flour', quantity: '3' };
      const source = null;

      const result = mergeService.detectConflict(target, source, base);

      assert.strictEqual(result, true);
    });
  });

  describe('resolveConflict()', () => {
    test('should resolve with target value', () => {
      const conflict = {
        targetValue: 'target value',
        sourceValue: 'source value'
      };

      const result = mergeService.resolveConflict(conflict, 'target');

      assert.strictEqual(result, 'target value');
    });

    test('should resolve with source value', () => {
      const conflict = {
        targetValue: 'target value',
        sourceValue: 'source value'
      };

      const result = mergeService.resolveConflict(conflict, 'source');

      assert.strictEqual(result, 'source value');
    });

    test('should resolve with manual value', () => {
      const conflict = {
        targetValue: 'target value',
        sourceValue: 'source value'
      };

      const result = mergeService.resolveConflict(conflict, 'manual', 'manual value');

      assert.strictEqual(result, 'manual value');
    });

    test('should default to target when resolution unknown', () => {
      const conflict = {
        targetValue: 'target value',
        sourceValue: 'source value'
      };

      const result = mergeService.resolveConflict(conflict, 'unknown');

      assert.strictEqual(result, 'target value');
    });
  });

  describe('mergeIngredients()', () => {
    test('should merge ingredients with different additions', () => {
      const base = [];
      const target = [{ name: 'Flour', quantity: '2', unit: 'cups' }];
      const source = [{ name: 'Sugar', quantity: '1', unit: 'cup' }];
      const conflicts = [];

      const result = mergeService.mergeIngredients(base, target, source, conflicts);

      assert.strictEqual(result.length, 2);
      assert.strictEqual(conflicts.length, 0);
    });

    test('should detect conflict when same ingredient modified differently', () => {
      const base = [{ name: 'Flour', quantity: '2', unit: 'cups' }];
      const target = [{ name: 'Flour', quantity: '3', unit: 'cups' }];
      const source = [{ name: 'Flour', quantity: '4', unit: 'cups' }];
      const conflicts = [];

      mergeService.mergeIngredients(base, target, source, conflicts);

      assert.ok(conflicts.length > 0);
    });
  });

  describe('mergeInstructions()', () => {
    test('should merge instructions present in both', () => {
      const base = ['Step 1', 'Step 2'];
      const target = ['Step 1', 'Step 2', 'Step 3'];
      const source = ['Step 1', 'Step 2', 'Step 4'];
      const conflicts = [];

      const result = mergeService.mergeInstructions(base, target, source, conflicts);

      assert.ok(result.includes('Step 1'));
      assert.ok(result.includes('Step 2'));
      assert.ok(result.includes('Step 3'));
      assert.ok(result.includes('Step 4'));
      assert.strictEqual(conflicts.length, 0);
    });

    test('should add new instructions from source', () => {
      const base = ['Step 1'];
      const target = ['Step 1'];
      const source = ['Step 1', 'New Step'];
      const conflicts = [];

      const result = mergeService.mergeInstructions(base, target, source, conflicts);

      assert.ok(result.includes('New Step'));
    });
  });

  describe('mergeArrays()', () => {
    test('should merge arrays combining all unique items', () => {
      const base = ['a', 'b'];
      const target = ['a', 'c'];
      const source = ['b', 'd'];

      const result = mergeService.mergeArrays(base, target, source);

      assert.ok(result.includes('a'));
      assert.ok(result.includes('b'));
      assert.ok(result.includes('c'));
      assert.ok(result.includes('d'));
    });

    test('should handle null/undefined arrays', () => {
      const result = mergeService.mergeArrays(null, undefined, ['a']);

      assert.ok(result.includes('a'));
    });
  });

  describe('mergeObjects()', () => {
    test('should merge objects with different keys', () => {
      const base = {};
      const target = { key1: 'value1' };
      const source = { key2: 'value2' };

      const result = mergeService.mergeObjects(base, target, source);

      assert.strictEqual(result.key1, 'value1');
      assert.strictEqual(result.key2, 'value2');
    });

    test('should handle conflicting values by preferring target', () => {
      const base = {};
      const target = { key: 'target' };
      const source = { key: 'source' };

      const result = mergeService.mergeObjects(base, target, source);

      assert.strictEqual(result.key, 'target');
    });
  });
});
