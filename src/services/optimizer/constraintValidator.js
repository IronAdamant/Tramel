'use strict';

const NutritionService = require('../nutritionService');
const CostEstimationService = require('../costEstimationService');
const DietaryComplianceService = require('../dietaryComplianceService');

/**
 * ConstraintValidator - Validates recipes against hard constraints
 */
class ConstraintValidator {
  constructor(fileStore) {
    this.store = fileStore;
    this.nutritionService = new NutritionService(fileStore);
    this.costService = new CostEstimationService(fileStore);
    this.dietaryService = new DietaryComplianceService(fileStore);
  }

  /**
   * Validate a recipe against all constraints
   * @param {Object} recipe - The recipe to validate
   * @param {Object} constraints - { maxCalories, dietaryProfile, maxCostPerMeal, maxPrepTime, etc }
   * @returns {Object} { valid: boolean, violations: string[] }
   */
  validate(recipe, constraints = {}) {
    const violations = [];

    if (!recipe) {
      return { valid: false, violations: ['Recipe is required'] };
    }

    // Check max calories
    if (constraints.maxCalories) {
      const calResult = this.checkCalorieLimit(recipe, constraints.maxCalories);
      if (!calResult.valid) {
        violations.push(calResult.violation);
      }
    }

    // Check dietary profile
    if (constraints.dietaryProfile) {
      const dietaryResult = this.checkDietaryCompliance(recipe, constraints.dietaryProfile);
      if (!dietaryResult.valid) {
        violations.push(...dietaryResult.violations);
      }
    }

    // Check cost limit
    if (constraints.maxCostPerMeal) {
      const costResult = this.checkCostLimit(recipe, constraints.maxCostPerMeal);
      if (!costResult.valid) {
        violations.push(costResult.violation);
      }
    }

    // Check max prep time
    if (constraints.maxPrepTime) {
      const timeResult = this.checkPrepTime(recipe, constraints.maxPrepTime);
      if (!timeResult.valid) {
        violations.push(timeResult.violation);
      }
    }

    // Check min protein
    if (constraints.minProtein) {
      const proteinResult = this.checkMinProtein(recipe, constraints.minProtein);
      if (!proteinResult.valid) {
        violations.push(proteinResult.violation);
      }
    }

    return {
      valid: violations.length === 0,
      violations
    };
  }

  /**
   * Check if recipe meets calorie limit
   */
  checkCalorieLimit(recipe, maxCalories) {
    const nutrition = this.nutritionService.estimateRecipeNutrition(recipe.id);
    if (!nutrition) {
      return { valid: true }; // Cannot validate, assume ok
    }

    const calories = nutrition.per_serving.calories;
    if (calories > maxCalories) {
      return {
        valid: false,
        violation: `exceeds max calories (${calories} > ${maxCalories})`
      };
    }

    return { valid: true };
  }

  /**
   * Check dietary compliance using dietaryComplianceService
   */
  checkDietaryCompliance(recipe, profileId) {
    const result = this.dietaryService.checkRecipeCompliance(recipe.id, profileId);

    if (result.error) {
      return { valid: true }; // Cannot validate, assume ok
    }

    if (!result.compliant) {
      const violationMessages = result.violations.map(v => {
        if (v.type === 'allergen') {
          return `contains allergen: ${v.allergen}`;
        }
        if (v.type === 'restriction') {
          return `violates restriction: ${v.restriction}`;
        }
        return `dietary violation`;
      });

      return {
        valid: false,
        violations: violationMessages
      };
    }

    return { valid: true };
  }

  /**
   * Check if recipe cost is within limit
   */
  checkCostLimit(recipe, maxCost) {
    const cost = this.costService.estimateRecipeCost(recipe.id);
    if (!cost) {
      return { valid: true }; // Cannot validate, assume ok
    }

    const perServing = cost.per_serving || 0;
    if (perServing > maxCost) {
      return {
        valid: false,
        violation: `exceeds max cost ($${perServing.toFixed(2)} > $${maxCost})`
      };
    }

    return { valid: true };
  }

  /**
   * Check prep time limit
   */
  checkPrepTime(recipe, maxPrepTime) {
    const prepTime = recipe.prep_time_minutes || 0;
    if (prepTime > maxPrepTime) {
      return {
        valid: false,
        violation: `exceeds max prep time (${prepTime} > ${maxPrepTime} min)`
      };
    }

    return { valid: true };
  }

  /**
   * Check minimum protein requirement
   */
  checkMinProtein(recipe, minProtein) {
    const nutrition = this.nutritionService.estimateRecipeNutrition(recipe.id);
    if (!nutrition) {
      return { valid: true }; // Cannot validate, assume ok
    }

    const protein = nutrition.per_serving.protein;
    if (protein < minProtein) {
      return {
        valid: false,
        violation: `below min protein (${protein}g < ${minProtein}g)`
      };
    }

    return { valid: true };
  }

  /**
   * Validate a meal plan (collection of recipes)
   */
  validateMealPlan(recipes, constraints = {}) {
    const allViolations = [];

    for (const recipe of recipes) {
      const result = this.validate(recipe, constraints);
      if (!result.valid) {
        allViolations.push({
          recipe_id: recipe.id,
          recipe_title: recipe.title,
          violations: result.violations
        });
      }
    }

    return {
      valid: allViolations.length === 0,
      meal_plan_violations: allViolations,
      total_violations: allViolations.length
    };
  }

  /**
   * Filter recipes that pass all constraints
   */
  filterValidRecipes(recipes, constraints = {}) {
    return recipes.filter(recipe => {
      const result = this.validate(recipe, constraints);
      return result.valid;
    });
  }
}

module.exports = ConstraintValidator;
