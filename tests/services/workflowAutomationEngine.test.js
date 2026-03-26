/**
 * Tests for RecipeWorkflowAutomationEngine
 */

'use strict';

const { describe, test, assert } = require('../testRunner');
const RecipeWorkflowAutomationEngine = require('../../src/services/workflowAutomationEngine');

describe('RecipeWorkflowAutomationEngine', () => {
  let engine;
  let mockStore;

  test('should register a workflow', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    engine.registerWorkflow({
      id: 'test-workflow',
      name: 'Test Workflow',
      description: 'A test workflow',
      steps: [
        { type: 'recipe.load' },
        { type: 'nutrition.calculate' }
      ]
    });

    assert.ok(engine.workflows.has('test-workflow'), 'Workflow should be registered');
  });

  test('should have built-in weekly-meal-planning workflow', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    assert.ok(engine.workflows.has('weekly-meal-planning'), 'Should have weekly workflow');
  });

  test('should have built-in recipe-analysis workflow', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    assert.ok(engine.workflows.has('recipe-analysis'), 'Should have recipe-analysis workflow');
  });

  test('should return error for unknown workflow', async () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const result = await engine.execute('unknown-workflow');

    assert.equal(result.success, false);
    assert.equal(result.error, 'Workflow not found');
  });

  test('should check conditions before execution', async () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    engine.registerWorkflow({
      id: 'conditional-workflow',
      name: 'Conditional',
      conditions: [
        { type: 'has_recipe_id', param: 'recipeId' }
      ],
      steps: [
        { type: 'recipe.load' }
      ]
    });

    const result = await engine.execute('conditional-workflow', {});

    assert.equal(result.status, 'failed');
  });

  test('should evaluate greater than condition', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const result = engine.evaluateCondition('calories > 800', { calories: 1000 });

    assert.equal(result, true);
  });

  test('should evaluate less than condition', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const result = engine.evaluateCondition('variety_score < 0.7', { variety_score: 0.5 });

    assert.equal(result, true);
  });

  test('should evaluate equals condition', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const result = engine.evaluateCondition('recipe_count == 5', { recipe_count: 5 });

    assert.equal(result, true);
  });

  test('should return false for invalid condition', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const result = engine.evaluateCondition('invalid', {});

    assert.equal(result, false);
  });

  test('should calculate health score correctly', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const nutrition = {
      calories: 500,
      sodium: 400,
      sugar: 10,
      fat: 15,
      protein: 30,
      fiber: 5
    };

    const score = engine.calculateHealthScore(nutrition);

    assert.ok(score > 0, 'Score should be positive');
    assert.ok(score <= 100, 'Score should be <= 100');
  });

  test('should penalize high calories', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const highCal = { calories: 1000, sodium: 0, sugar: 0, fat: 0, protein: 0, fiber: 0 };
    const lowCal = { calories: 300, sodium: 0, sugar: 0, fat: 0, protein: 0, fiber: 0 };

    const highScore = engine.calculateHealthScore(highCal);
    const lowScore = engine.calculateHealthScore(lowCal);

    assert.ok(lowScore > highScore, 'Low calorie should score higher');
  });

  test('should track execution history', async () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    engine.registerWorkflow({
      id: 'simple-workflow',
      name: 'Simple',
      steps: [
        { type: 'condition.check', params: { check: 'variety' } }
      ]
    });

    await engine.execute('simple-workflow', { varietyScore: 0.5 });

    assert.equal(engine.executionHistory.length, 1);
  });

  test('should return specific workflow', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const workflow = engine.getWorkflow('weekly-meal-planning');

    assert.ok(workflow !== null);
    assert.equal(workflow.id, 'weekly-meal-planning');
  });

  test('should return null for unknown workflow', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const workflow = engine.getWorkflow('nonexistent');

    assert.equal(workflow, null);
  });

  test('should return all workflows when no id provided', () => {
    mockStore = { readById: () => {}, readAll: () => {} };
    engine = new RecipeWorkflowAutomationEngine(mockStore);

    const workflows = engine.getWorkflow();

    assert.ok(Array.isArray(workflows));
    assert.ok(workflows.length > 0);
  });
});
