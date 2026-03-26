/**
 * RecipeTransformationPipeline - Multi-phase orchestration engine
 *
 * CHALLENGES TRAMMEL:
 * - Complex dependency chains across 6+ services
 * - Implicit ordering that trammel must infer from data flow
 * - Conditional branching based on intermediate results
 * - Pipeline steps that cross service/model/utils boundaries
 *
 * This demonstrates how real-world features require orchestration
 * across many files with dependencies that aren't explicit in any single place.
 */

const Recipe = require('../models/Recipe');
const NutritionService = require('./nutritionService');
const DietaryComplianceService = require('./dietaryComplianceService');
const CostEstimationService = require('./costEstimationService');
const RecipeScalingService = require('./recipeScalingService');
const SubstitutionEngine = require('./substitutionEngine');

class RecipeTransformationPipeline {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
    this.nutritionService = new NutritionService(fileStore);
    this.dietaryService = new DietaryComplianceService(fileStore);
    this.costService = new CostEstimationService(fileStore);
    this.scalingService = new RecipeScalingService(fileStore);
    this.substitutionEngine = new SubstitutionEngine(fileStore);

    // Pipeline execution state
    this.executionLog = [];
    this.phaseResults = new Map();
  }

  /**
   * Execute a complete transformation pipeline on a recipe
   *
   * Pipeline phases (implicit order - trammel must infer):
   * 1. Load and validate recipe
   * 2. Calculate nutrition
   * 3. Check dietary compliance
   * 4. Estimate costs
   * 5. Apply scaling (if needed)
   * 6. Apply substitutions (if needed)
   * 7. Generate final output
   */
  async execute(recipeId, options = {}) {
    const {
      targetServings,
      dietaryProfile,
      budgetConstraint,
      applySubstitutions = false,
      allowExpensive = true
    } = options;

    this.executionLog = [];
    this.phaseResults.clear();

    const context = {
      recipeId,
      startTime: Date.now(),
      options,
      errors: [],
      warnings: []
    };

    try {
      // Phase 1: Load and validate
      const loadResult = await this.phaseLoadAndValidate(recipeId);
      if (!loadResult.success) {
        return { success: false, error: loadResult.error, phases: this.getPhaseSummary() };
      }
      context.recipe = loadResult.recipe;

      // Phase 2: Calculate nutrition
      const nutritionResult = await this.phaseCalculateNutrition(context.recipe);
      context.nutrition = nutritionResult;

      // Phase 3: Check dietary compliance
      const complianceResult = await this.phaseCheckDietaryCompliance(
        context.recipe,
        dietaryProfile
      );
      context.compliance = complianceResult;

      if (!complianceResult.isCompliant && options.strictDietary) {
        context.errors.push('Recipe does not meet dietary requirements');
      }

      // Phase 4: Estimate costs
      const costResult = await this.phaseEstimateCosts(context.recipe, budgetConstraint);
      context.cost = costResult;

      if (!allowExpensive && costResult.exceedsBudget) {
        context.errors.push('Recipe exceeds budget constraint');
      }

      // Phase 5: Scale if needed
      if (targetServings && targetServings !== context.recipe.yield) {
        const scaleResult = await this.phaseScaleRecipe(
          context.recipe,
          targetServings,
          { ...context, scaledNutrition: true }
        );
        context.recipe = scaleResult.scaledRecipe;
        context.scaledServings = targetServings;
      }

      // Phase 6: Apply substitutions if needed
      if (applySubstitutions) {
        const substitutionResult = await this.phaseApplySubstitutions(
          context.recipe,
          dietaryProfile
        );
        context.substitutions = substitutionResult;
        context.recipe = substitutionResult.modifiedRecipe;
      }

      // Phase 7: Generate output
      const outputResult = this.phaseGenerateOutput(context);

      return {
        success: context.errors.length === 0,
        errors: context.errors,
        warnings: context.warnings,
        phases: this.getPhaseSummary(),
        result: outputResult
      };

    } catch (error) {
      context.errors.push(`Pipeline error: ${error.message}`);
      return {
        success: false,
        error: error.message,
        phases: this.getPhaseSummary()
      };
    }
  }

  /**
   * Phase 1: Load and validate recipe
   */
  async phaseLoadAndValidate(recipeId) {
    this.logPhase(1, 'loadAndValidate', 'started');

    try {
      const recipe = this.recipe.getById(recipeId);

      if (!recipe) {
        this.logPhase(1, 'loadAndValidate', 'failed', { error: 'Recipe not found' });
        return { success: false, error: 'Recipe not found' };
      }

      // Validate required fields
      const validation = this.validateRecipeStructure(recipe);
      if (!validation.valid) {
        this.logPhase(1, 'loadAndValidate', 'failed', { errors: validation.errors });
        return { success: false, error: validation.errors.join(', ') };
      }

      this.phaseResults.set('loadAndValidate', { recipe, validation });
      this.logPhase(1, 'loadAndValidate', 'completed', { recipeId, title: recipe.title });

      return { success: true, recipe };

    } catch (error) {
      this.logPhase(1, 'loadAndValidate', 'error', { error: error.message });
      return { success: false, error: error.message };
    }
  }

  /**
   * Phase 2: Calculate nutrition
   */
  async phaseCalculateNutrition(recipe) {
    this.logPhase(2, 'calculateNutrition', 'started');

    try {
      // nutritionService.calculateNutrition is called
      const nutrition = this.nutritionService.calculateNutrition(recipe);

      // Build nutrition breakdown
      const breakdown = {
        calories: nutrition.calories || 0,
        protein: nutrition.protein || 0,
        carbohydrates: nutrition.carbohydrates || 0,
        fat: nutrition.fat || 0,
        fiber: nutrition.fiber || 0,
        sugar: nutrition.sugar || 0,
        sodium: nutrition.sodium || 0
      };

      // Calculate health score
      const healthScore = this.calculateHealthScore(breakdown);

      this.phaseResults.set('calculateNutrition', { nutrition: breakdown, healthScore });
      this.logPhase(2, 'calculateNutrition', 'completed', breakdown);

      return breakdown;

    } catch (error) {
      this.logPhase(2, 'calculateNutrition', 'error', { error: error.message });
      return { error: error.message };
    }
  }

  /**
   * Phase 3: Check dietary compliance
   */
  async phaseCheckDietaryCompliance(recipe, dietaryProfile) {
    this.logPhase(3, 'dietaryCompliance', 'started');

    try {
      if (!dietaryProfile) {
        this.logPhase(3, 'dietaryCompliance', 'skipped', { reason: 'No profile' });
        return { isCompliant: true, skipped: true };
      }

      // Check each dietary requirement
      const checks = [];

      if (dietaryProfile.vegan) {
        checks.push(this.checkVeganCompliance(recipe));
      }

      if (dietaryProfile.glutenFree) {
        checks.push(this.checkGlutenFreeCompliance(recipe));
      }

      if (dietaryProfile.dairyFree) {
        checks.push(this.checkDairyFreeCompliance(recipe));
      }

      if (dietaryProfile.allergens) {
        checks.push(this.checkAllergenCompliance(recipe, dietaryProfile.allergens));
      }

      const isCompliant = checks.every(c => c.pass);

      this.phaseResults.set('dietaryCompliance', { isCompliant, checks });
      this.logPhase(3, 'dietaryCompliance', 'completed', { isCompliant, checkCount: checks.length });

      return { isCompliant, checks };

    } catch (error) {
      this.logPhase(3, 'dietaryCompliance', 'error', { error: error.message });
      return { isCompliant: false, error: error.message };
    }
  }

  /**
   * Phase 4: Estimate costs
   */
  async phaseEstimateCosts(recipe, budgetConstraint) {
    this.logPhase(4, 'estimateCosts', 'started');

    try {
      const costEstimate = this.costService.estimateCost(recipe);
      const totalCost = costEstimate.totalCost || 0;
      const costPerServing = costEstimate.perServing || 0;

      const exceedsBudget = budgetConstraint
        ? totalCost > budgetConstraint
        : false;

      this.phaseResults.set('estimateCosts', { costEstimate, exceedsBudget });
      this.logPhase(4, 'estimateCosts', 'completed', {
        totalCost,
        perServing: costPerServing,
        exceedsBudget
      });

      return {
        totalCost,
        perServing: costPerServing,
        breakdown: costEstimate.breakdown || [],
        exceedsBudget,
        budgetConstraint
      };

    } catch (error) {
      this.logPhase(4, 'estimateCosts', 'error', { error: error.message });
      return { error: error.message };
    }
  }

  /**
   * Phase 5: Scale recipe
   */
  async phaseScaleRecipe(recipe, targetServings, context = {}) {
    this.logPhase(5, 'scaleRecipe', 'started');

    try {
      const originalServings = recipe.yield || 1;
      const scaleFactor = targetServings / originalServings;

      // Use scaling service to scale recipe
      const scaledRecipe = this.scalingService.scale(recipe, targetServings);

      // Recalculate nutrition if scaled
      if (context.scaledNutrition) {
        const scaledNutrition = this.nutritionService.calculateNutrition(scaledRecipe);
        this.phaseResults.set('scaledNutrition', scaledNutrition);
      }

      this.phaseResults.set('scaleRecipe', { originalServings, targetServings, scaleFactor });
      this.logPhase(5, 'scaleRecipe', 'completed', {
        originalServings,
        targetServings,
        scaleFactor
      });

      return { scaledRecipe, scaleFactor };

    } catch (error) {
      this.logPhase(5, 'scaleRecipe', 'error', { error: error.message });
      return { error: error.message };
    }
  }

  /**
   * Phase 6: Apply substitutions
   */
  async phaseApplySubstitutions(recipe, dietaryProfile) {
    this.logPhase(6, 'applySubstitutions', 'started');

    try {
      if (!dietaryProfile) {
        this.logPhase(6, 'applySubstitutions', 'skipped', { reason: 'No profile' });
        return { modifiedRecipe: recipe, substitutions: [], skipped: true };
      }

      const substitutions = [];

      // Find and apply substitutions based on dietary profile
      if (dietaryProfile.dairyFree) {
        const dairySubs = this.substitutionEngine.findDairySubstitutes(recipe);
        substitutions.push(...dairySubs);
      }

      if (dietaryProfile.glutenFree) {
        const glutenSubs = this.substitutionEngine.findGlutenSubstitutes(recipe);
        substitutions.push(...glutenSubs);
      }

      if (dietaryProfile.vegan) {
        const meatSubs = this.substitutionEngine.findMeatSubstitutes(recipe);
        substitutions.push(...meatSubs);
      }

      // Apply substitutions
      let modifiedRecipe = { ...recipe };
      for (const sub of substitutions) {
        modifiedRecipe = this.substitutionEngine.applySubstitution(
          modifiedRecipe,
          sub.original,
          sub.substitute
        );
      }

      this.phaseResults.set('applySubstitutions', { substitutions });
      this.logPhase(6, 'applySubstitutions', 'completed', {
        count: substitutions.length,
        types: substitutions.map(s => s.type)
      });

      return { modifiedRecipe, substitutions };

    } catch (error) {
      this.logPhase(6, 'applySubstitutions', 'error', { error: error.message });
      return { error: error.message };
    }
  }

  /**
   * Phase 7: Generate output
   */
  phaseGenerateOutput(context) {
    this.logPhase(7, 'generateOutput', 'started');

    const output = {
      recipe: {
        id: context.recipe?.id,
        title: context.recipe?.title,
        servings: context.scaledServings || context.recipe?.yield
      },
      nutrition: context.nutrition,
      compliance: context.compliance,
      cost: context.cost,
      substitutions: context.substitutions?.substitutions || [],
      execution: {
        duration: Date.now() - context.startTime,
        phases: this.getPhaseSummary()
      }
    };

    this.phaseResults.set('generateOutput', output);
    this.logPhase(7, 'generateOutput', 'completed');

    return output;
  }

  // ============ Helper Methods ============

  validateRecipeStructure(recipe) {
    const errors = [];

    if (!recipe.title) errors.push('Missing title');
    if (!recipe.ingredients || recipe.ingredients.length === 0) {
      errors.push('Missing ingredients');
    }
    if (!recipe.instructions) errors.push('Missing instructions');

    return { valid: errors.length === 0, errors };
  }

  calculateHealthScore(nutrition) {
    let score = 100;

    // Deduct for high sodium
    if (nutrition.sodium > 600) score -= 10;
    if (nutrition.sodium > 1500) score -= 20;

    // Deduct for high sugar
    if (nutrition.sugar > 15) score -= 10;
    if (nutrition.sugar > 30) score -= 15;

    // Deduct for high fat
    if (nutrition.fat > 20) score -= 5;
    if (nutrition.fat > 40) score -= 10;

    // Add for high protein
    if (nutrition.protein > 15) score += 5;
    if (nutrition.protein > 30) score += 10;

    // Add for high fiber
    if (nutrition.fiber > 3) score += 5;
    if (nutrition.fiber > 6) score += 10;

    return Math.max(0, Math.min(100, score));
  }

  checkVeganCompliance(recipe) {
    const nonVegan = ['meat', 'chicken', 'beef', 'pork', 'fish', 'seafood', 'egg', 'milk', 'cheese', 'butter', 'honey'];
    const ingredients = (recipe.ingredients || []).map(i =>
      (i.name || i.ingredient || i || '').toLowerCase()
    );

    const violations = ingredients.filter(ing =>
      nonVegan.some(n => ing.includes(n))
    );

    return {
      requirement: 'vegan',
      pass: violations.length === 0,
      violations
    };
  }

  checkGlutenFreeCompliance(recipe) {
    const glutenSources = ['wheat', 'barley', 'rye', 'flour', 'bread', 'pasta', 'couscous'];
    const ingredients = (recipe.ingredients || []).map(i =>
      (i.name || i.ingredient || i || '').toLowerCase()
    );

    const violations = ingredients.filter(ing =>
      glutenSources.some(g => ing.includes(g))
    );

    return {
      requirement: 'gluten-free',
      pass: violations.length === 0,
      violations
    };
  }

  checkDairyFreeCompliance(recipe) {
    const dairySources = ['milk', 'cheese', 'butter', 'cream', 'yogurt', 'whey', 'casein'];
    const ingredients = (recipe.ingredients || []).map(i =>
      (i.name || i.ingredient || i || '').toLowerCase()
    );

    const violations = ingredients.filter(ing =>
      dairySources.some(d => ing.includes(d))
    );

    return {
      requirement: 'dairy-free',
      pass: violations.length === 0,
      violations
    };
  }

  checkAllergenCompliance(recipe, allergens) {
    const violations = [];

    for (const allergen of allergens) {
      const ingredientList = (recipe.ingredients || []).map(i =>
        (i.name || i.ingredient || i || '').toLowerCase()
      );

      const hasAllergen = ingredientList.some(ing =>
        ing.includes(allergen.toLowerCase())
      );

      if (hasAllergen) {
        violations.push(allergen);
      }
    }

    return {
      requirement: 'allergens',
      allergens,
      pass: violations.length === 0,
      violations
    };
  }

  logPhase(phaseNum, name, status, data = {}) {
    this.executionLog.push({
      phase: phaseNum,
      name,
      status,
      data,
      timestamp: Date.now()
    });
  }

  getPhaseSummary() {
    return this.executionLog.map(log => ({
      phase: log.phase,
      name: log.name,
      status: log.status
    }));
  }

  /**
   * Get dependency order for pipeline phases
   * This is what TRAMMEL should infer when decomposing
   */
  getPhaseDependencies() {
    return {
      loadAndValidate: [],
      calculateNutrition: ['loadAndValidate'],
      dietaryCompliance: ['loadAndValidate'],
      estimateCosts: ['loadAndValidate'],
      scaleRecipe: ['loadAndValidate'],
      applySubstitutions: ['loadAndValidate', 'dietaryCompliance'],
      generateOutput: [
        'calculateNutrition',
        'dietaryCompliance',
        'estimateCosts',
        'scaleRecipe',
        'applySubstitutions'
      ]
    };
  }

  /**
   * Get all files involved in this pipeline
   * For TRAMMEL decomposition reference
   */
  getInvolvedFiles() {
    return [
      'src/models/Recipe.js',
      'src/services/nutritionService.js',
      'src/services/dietaryComplianceService.js',
      'src/services/costEstimationService.js',
      'src/services/recipeScalingService.js',
      'src/services/substitutionEngine.js',
      'src/services/recipeTransformationPipeline.js',
      'src/api/routes/transformationRoutes.js',
      'tests/services/recipeTransformationPipeline.test.js'
    ];
  }
}

module.exports = RecipeTransformationPipeline;
