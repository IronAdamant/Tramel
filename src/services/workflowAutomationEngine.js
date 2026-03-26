/**
 * RecipeWorkflowAutomationEngine - Conditional workflow orchestration
 *
 * CHALLENGES ALL THREE MCPS:
 *
 * STELE-CONTEXT:
 * - Workflow definitions are semantic documents that semantic search should understand
 * - Workflow steps reference symbols across many files
 * - Cross-module orchestration tracking
 *
 * CHISEL:
 * - Workflow has conditional branches (partial execution paths)
 * - Complex import chains between workflow engine and services
 * - Multiple algorithms need varied coverage
 *
 * TRAMMEL:
 * - Workflow execution has complex implicit ordering
 * - Conditional branches depend on runtime state
 * - Multi-file orchestration with dynamic decision points
 */

const Recipe = require('../models/Recipe');
const NutritionService = require('./nutritionService');
const MealPlannerService = require('./mealPlannerService');
const ShoppingListService = require('./shoppingListService');

class RecipeWorkflowAutomationEngine {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
    this.nutritionService = new NutritionService(fileStore);
    this.mealPlannerService = new MealPlannerService(fileStore);
    this.shoppingListService = new ShoppingListService(fileStore);

    // Workflow definitions
    this.workflows = new Map();

    // Execution state
    this.activeExecutions = new Map();
    this.executionHistory = [];

    // Register built-in workflow types
    this.registerBuiltInWorkflows();
  }

  /**
   * Register a workflow definition
   */
  registerWorkflow(workflowDef) {
    const {
      id,
      name,
      description,
      steps,
      triggers,
      conditions,
      onSuccess,
      onFailure
    } = workflowDef;

    this.workflows.set(id, {
      id,
      name,
      description,
      steps: this.validateSteps(steps),
      triggers: triggers || [],
      conditions: conditions || [],
      onSuccess: onSuccess || null,
      onFailure: onFailure || null,
      createdAt: Date.now(),
      executionCount: 0
    });

    return this;
  }

  /**
   * Validate workflow steps
   */
  validateSteps(steps) {
    const validStepTypes = [
      'recipe.load',
      'recipe.create',
      'recipe.update',
      'recipe.delete',
      'nutrition.calculate',
      'nutrition.analyze',
      'mealplan.generate',
      'mealplan.optimize',
      'shoppinglist.create',
      'shoppinglist.consolidate',
      'condition.check',
      'condition.branch',
      'transform.scale',
      'transform.substitute',
      'export.json',
      'export.csv'
    ];

    return steps.map((step, index) => ({
      ...step,
      index,
      valid: validStepTypes.includes(step.type) || step.type?.startsWith('custom.')
    }));
  }

  /**
   * Register built-in workflow templates
   */
  registerBuiltInWorkflows() {
    // Weekly meal planning workflow
    this.registerWorkflow({
      id: 'weekly-meal-planning',
      name: 'Weekly Meal Planning',
      description: 'Generate a complete weekly meal plan with shopping list',
      triggers: ['scheduled', 'manual'],
      conditions: [
        { type: 'has_recipes', param: 'recipeIds' },
        { type: 'has_dietary_profile', param: 'dietaryProfile' }
      ],
      steps: [
        { type: 'mealplan.generate', params: { days: 7, mealsPerDay: 3 } },
        { type: 'condition.check', params: { check: 'variety' } },
        {
          type: 'condition.branch',
          branches: [
            { condition: 'variety_score > 0.7', nextStep: 'shoppinglist.create' },
            { condition: 'variety_score <= 0.7', nextStep: 'mealplan.optimize' }
          ]
        },
        { type: 'mealplan.optimize', params: { objectives: ['variety', 'nutrition', 'cost'] } },
        { type: 'shoppinglist.create' },
        { type: 'shoppinglist.consolidate' }
      ],
      onSuccess: { type: 'notify', message: 'Meal plan ready' },
      onFailure: { type: 'retry', maxAttempts: 3 }
    });

    // Recipe analysis workflow
    this.registerWorkflow({
      id: 'recipe-analysis',
      name: 'Complete Recipe Analysis',
      description: 'Load recipe and perform complete nutrition and compliance analysis',
      triggers: ['manual'],
      conditions: [
        { type: 'has_recipe_id', param: 'recipeId' }
      ],
      steps: [
        { type: 'recipe.load' },
        { type: 'nutrition.calculate' },
        { type: 'nutrition.analyze', params: { healthScore: true } },
        { type: 'condition.check', params: { check: 'calories' } },
        {
          type: 'condition.branch',
          branches: [
            { condition: 'calories > 800', nextStep: 'transform.scale' },
            { condition: 'calories <= 800', nextStep: 'end' }
          ]
        },
        { type: 'transform.scale', params: { targetCalories: 600 } }
      ],
      onSuccess: { type: 'return', data: 'analysis_result' },
      onFailure: { type: 'return', data: 'error' }
    });

    // Batch import and optimize workflow
    this.registerWorkflow({
      id: 'batch-import-optimize',
      name: 'Import and Optimize',
      description: 'Import multiple recipes and generate optimized meal plan',
      triggers: ['manual', 'webhook'],
      conditions: [],
      steps: [
        { type: 'recipe.load', params: { multiple: true } },
        { type: 'condition.check', params: { check: 'recipe_count' } },
        {
          type: 'condition.branch',
          branches: [
            { condition: 'recipe_count >= 10', nextStep: 'mealplan.optimize' },
            { condition: 'recipe_count < 10', nextStep: 'end' }
          ]
        },
        { type: 'mealplan.generate' },
        { type: 'mealplan.optimize' },
        { type: 'shoppinglist.create' }
      ],
      onSuccess: { type: 'return', data: 'optimized_plan' },
      onFailure: { type: 'return', data: 'partial_results' }
    });
  }

  /**
   * Execute a workflow
   */
  async execute(workflowId, context = {}) {
    const workflow = this.workflows.get(workflowId);
    if (!workflow) {
      return { success: false, error: 'Workflow not found' };
    }

    const executionId = this.generateExecutionId();
    const execution = {
      id: executionId,
      workflowId,
      startedAt: Date.now(),
      status: 'running',
      currentStep: 0,
      context: { ...context },
      results: new Map(),
      errors: [],
      logs: []
    };

    this.activeExecutions.set(executionId, execution);

    this.log(executionId, 'Workflow started', { workflowId });

    try {
      // Check conditions
      const conditionsMet = await this.checkConditions(workflow.conditions, context);
      if (!conditionsMet) {
        execution.status = 'failed';
        execution.error = 'Entry conditions not met';
        return this.finalizeExecution(execution);
      }

      // Execute steps
      for (let i = 0; i < workflow.steps.length; i++) {
        const step = workflow.steps[i];
        execution.currentStep = i;

        this.log(executionId, `Executing step ${i}`, { type: step.type });

        const stepResult = await this.executeStep(step, execution.context);

        execution.results.set(i, stepResult);

        if (!stepResult.success) {
          execution.errors.push({ step: i, error: stepResult.error });

          if (workflow.onFailure) {
            await this.handleWorkflowFailure(execution, workflow.onFailure);
          }

          execution.status = 'failed';
          return this.finalizeExecution(execution);
        }

        // Update context with step results
        if (stepResult.data) {
          execution.context = { ...execution.context, ...stepResult.data };
        }

        // Handle conditional branching
        if (step.type === 'condition.branch') {
          const nextStep = await this.resolveBranch(step, execution.context);
          if (nextStep !== null) {
            // Skip to specific step
            const nextStepIndex = workflow.steps.findIndex(s => s.index === nextStep);
            if (nextStepIndex !== -1) {
              execution.currentStep = nextStepIndex;
            }
          }
        }
      }

      // Handle success
      if (workflow.onSuccess) {
        await this.handleWorkflowSuccess(execution, workflow.onSuccess);
      }

      execution.status = 'completed';
      execution.completedAt = Date.now();

      this.log(executionId, 'Workflow completed', {
        duration: execution.completedAt - execution.startedAt
      });

      return this.finalizeExecution(execution);

    } catch (error) {
      execution.errors.push({ step: execution.currentStep, error: error.message });
      execution.status = 'failed';
      execution.error = error.message;

      return this.finalizeExecution(execution);
    }
  }

  /**
   * Execute a single workflow step
   */
  async executeStep(step, context) {
    try {
      switch (step.type) {
        case 'recipe.load':
          return await this.stepRecipeLoad(step, context);

        case 'recipe.create':
          return await this.stepRecipeCreate(step, context);

        case 'nutrition.calculate':
          return await this.stepNutritionCalculate(step, context);

        case 'nutrition.analyze':
          return await this.stepNutritionAnalyze(step, context);

        case 'mealplan.generate':
          return await this.stepMealPlanGenerate(step, context);

        case 'mealplan.optimize':
          return await this.stepMealPlanOptimize(step, context);

        case 'shoppinglist.create':
          return await this.stepShoppingListCreate(step, context);

        case 'shoppinglist.consolidate':
          return await this.stepShoppingListConsolidate(step, context);

        case 'condition.check':
          return await this.stepConditionCheck(step, context);

        case 'condition.branch':
          return await this.stepConditionBranch(step, context);

        case 'transform.scale':
          return await this.stepTransformScale(step, context);

        case 'transform.substitute':
          return await this.stepTransformSubstitute(step, context);

        default:
          return { success: false, error: `Unknown step type: ${step.type}` };
      }
    } catch (error) {
      return { success: false, error: error.message };
    }
  }

  // ============ Step Implementations ============

  async stepRecipeLoad(step, context) {
    const recipeId = context.recipeId || context.recipe?.id;

    if (!recipeId) {
      return { success: false, error: 'No recipe ID in context' };
    }

    const recipe = this.recipe.getById(recipeId);
    if (!recipe) {
      return { success: false, error: 'Recipe not found' };
    }

    return {
      success: true,
      data: { recipe }
    };
  }

  async stepRecipeCreate(step, context) {
    const recipeData = context.recipeData || step.params?.data;
    if (!recipeData) {
      return { success: false, error: 'No recipe data provided' };
    }

    const recipe = this.recipe.create(recipeData);

    return {
      success: true,
      data: { recipe }
    };
  }

  async stepNutritionCalculate(step, context) {
    const recipe = context.recipe;
    if (!recipe) {
      return { success: false, error: 'No recipe loaded' };
    }

    const nutrition = this.nutritionService.calculateNutrition(recipe);

    return {
      success: true,
      data: { nutrition }
    };
  }

  async stepNutritionAnalyze(step, context) {
    const nutrition = context.nutrition;
    if (!nutrition) {
      return { success: false, error: 'No nutrition data' };
    }

    const analysis = {
      ...nutrition,
      healthScore: this.calculateHealthScore(nutrition),
      analyzedAt: Date.now()
    };

    if (step.params?.healthScore) {
      analysis.healthScore = analysis.healthScore;
    }

    return {
      success: true,
      data: { nutritionAnalysis: analysis }
    };
  }

  async stepMealPlanGenerate(step, context) {
    const recipes = context.recipes || [];
    const days = step.params?.days || 7;
    const mealsPerDay = step.params?.mealsPerDay || 3;

    const result = this.mealPlannerService.generate({
      recipes,
      days,
      mealsPerDay
    });

    return {
      success: true,
      data: { mealPlan: result }
    };
  }

  async stepMealPlanOptimize(step, context) {
    const mealPlan = context.mealPlan;
    if (!mealPlan) {
      return { success: false, error: 'No meal plan to optimize' };
    }

    const objectives = step.params?.objectives || ['variety', 'nutrition', 'cost'];

    const optimized = this.mealPlannerService.optimize(mealPlan, objectives);

    return {
      success: true,
      data: { optimizedMealPlan: optimized }
    };
  }

  async stepShoppingListCreate(step, context) {
    const mealPlan = context.mealPlan || context.optimizedMealPlan;
    if (!mealPlan) {
      return { success: false, error: 'No meal plan for shopping list' };
    }

    const shoppingList = this.shoppingListService.createFromMealPlan(mealPlan);

    return {
      success: true,
      data: { shoppingList }
    };
  }

  async stepShoppingListConsolidate(step, context) {
    const shoppingList = context.shoppingList;
    if (!shoppingList) {
      return { success: false, error: 'No shopping list to consolidate' };
    }

    const consolidated = this.shoppingListService.consolidate(shoppingList);

    return {
      success: true,
      data: { consolidatedShoppingList: consolidated }
    };
  }

  async stepConditionCheck(step, context) {
    const check = step.params?.check;

    switch (check) {
      case 'variety':
        // Check variety score
        const varietyScore = context.varietyScore || 0.5;
        return {
          success: true,
          data: { varietyScore }
        };

      case 'calories':
        const nutrition = context.nutrition || {};
        return {
          success: true,
          data: { calories: nutrition.calories || 0 }
        };

      case 'recipe_count':
        const recipes = context.recipes || [];
        return {
          success: true,
          data: { recipe_count: recipes.length }
        };

      default:
        return { success: true, data: {} };
    }
  }

  async stepConditionBranch(step, context) {
    // Branch evaluation happens in execute(), this just validates
    return { success: true, data: {} };
  }

  async stepTransformScale(step, context) {
    const recipe = context.recipe;
    const targetCalories = step.params?.targetCalories || 600;

    if (!recipe) {
      return { success: false, error: 'No recipe to scale' };
    }

    const currentCalories = context.nutrition?.calories || 500;
    const scaleFactor = targetCalories / currentCalories;

    const scaledRecipe = {
      ...recipe,
      yield: Math.round((recipe.yield || 1) * scaleFactor)
    };

    return {
      success: true,
      data: { scaledRecipe }
    };
  }

  async stepTransformSubstitute(step, context) {
    const recipe = context.recipe;
    if (!recipe) {
      return { success: false, error: 'No recipe for substitutions' };
    }

    // Apply dietary-based substitutions
    const substitutions = [];

    if (context.dietaryProfile?.dairyFree) {
      substitutions.push({ from: 'milk', to: 'oat milk' });
    }

    return {
      success: true,
      data: { substitutions }
    };
  }

  // ============ Helper Methods ============

  async checkConditions(conditions, context) {
    if (!conditions || conditions.length === 0) return true;

    for (const condition of conditions) {
      switch (condition.type) {
        case 'has_recipes':
          if (!context.recipeIds || context.recipeIds.length === 0) return false;
          break;
        case 'has_dietary_profile':
          if (!context.dietaryProfile) return false;
          break;
        case 'has_recipe_id':
          if (!context.recipeId) return false;
          break;
      }
    }

    return true;
  }

  async resolveBranch(branchStep, context) {
    const branches = branchStep.branches || [];

    for (const branch of branches) {
      if (this.evaluateCondition(branch.condition, context)) {
        return branch.nextStep;
      }
    }

    return null;
  }

  evaluateCondition(condition, context) {
    // Simple condition evaluation
    // e.g., "variety_score > 0.7" or "calories > 800"
    const match = condition.match(/(\w+)\s*(>|<|>=|<=|==|!=)\s*([\d.]+)/);

    if (!match) return false;

    const [, field, operator, valueStr] = match;
    const value = parseFloat(valueStr);
    const contextValue = context[field] ?? context.nutrition?.[field] ?? 0;

    switch (operator) {
      case '>': return contextValue > value;
      case '<': return contextValue < value;
      case '>=': return contextValue >= value;
      case '<=': return contextValue <= value;
      case '==': return contextValue === value;
      case '!=': return contextValue !== value;
      default: return false;
    }
  }

  async handleWorkflowFailure(execution, handler) {
    switch (handler.type) {
      case 'retry':
        // Retry logic
        execution.retryCount = (execution.retryCount || 0) + 1;
        if (execution.retryCount < (handler.maxAttempts || 3)) {
          execution.status = 'retrying';
        }
        break;

      case 'notify':
        this.log(execution.id, 'Failure notification', { message: handler.message });
        break;
    }
  }

  async handleWorkflowSuccess(execution, handler) {
    switch (handler.type) {
      case 'notify':
        this.log(execution.id, 'Success notification', { message: handler.message });
        break;

      case 'return':
        execution.returnData = handler.data;
        break;
    }
  }

  calculateHealthScore(nutrition) {
    let score = 100;

    if (nutrition.calories > 800) score -= 15;
    if (nutrition.sodium > 600) score -= 10;
    if (nutrition.sugar > 20) score -= 10;
    if (nutrition.fat > 30) score -= 5;
    if (nutrition.protein > 40) score += 5;
    if (nutrition.fiber > 8) score += 10;

    return Math.max(0, Math.min(100, score));
  }

  log(executionId, message, data = {}) {
    const execution = this.activeExecutions.get(executionId);
    if (execution) {
      execution.logs.push({
        message,
        data,
        timestamp: Date.now()
      });
    }
  }

  generateExecutionId() {
    return `exec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  finalizeExecution(execution) {
    this.activeExecutions.delete(execution.id);
    this.executionHistory.push(execution);

    // Limit history size
    if (this.executionHistory.length > 100) {
      this.executionHistory = this.executionHistory.slice(-100);
    }

    return {
      id: execution.id,
      workflowId: execution.workflowId,
      status: execution.status,
      startedAt: execution.startedAt,
      completedAt: execution.completedAt,
      duration: execution.completedAt
        ? execution.completedAt - execution.startedAt
        : Date.now() - execution.startedAt,
      results: Array.from(execution.results.values()),
      errors: execution.errors,
      logs: execution.logs,
      returnData: execution.returnData
    };
  }

  /**
   * Get workflow definitions
   */
  getWorkflow(id = null) {
    if (id) {
      return this.workflows.get(id) || null;
    }
    return Array.from(this.workflows.values());
  }

  /**
   * Get execution history
   */
  getHistory(limit = 20) {
    return this.executionHistory.slice(-limit);
  }

  /**
   * Get active executions
   */
  getActiveExecutions() {
    return Array.from(this.activeExecutions.values()).map(e => ({
      id: e.id,
      workflowId: e.workflowId,
      status: e.status,
      currentStep: e.currentStep,
      startedAt: e.startedAt
    }));
  }
}

module.exports = RecipeWorkflowAutomationEngine;
