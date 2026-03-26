'use strict';

const { getNutrition } = require('../data/nutritionData');
const { getDensity } = require('../data/densityData');
const { getAllergens } = require('../data/allergenData');
const { getSubstitutionRules, hasSubstitutionRules } = require('../data/substitutionRules');

/**
 * SubstitutionEngine - finds cooking substitutions that preserve recipe properties
 *
 * Given an ingredient, finds substitutes based on:
 * - Nutrition profile similarity
 * - Density/texture matching
 * - Allergen constraints
 * - Explicit substitution rules
 */
class SubstitutionEngine {
  /**
   * Find substitutes for an ingredient
   * @param {string} ingredientName - Name of the ingredient to substitute
   * @param {Object} constraints - Constraints to filter by
   * @param {string[]} constraints.avoidAllergens - Allergens to avoid
   * @param {Object} constraints.targetNutrition - Desired nutrition properties
   * @param {number} constraints.maxCost - Maximum cost (if price data available)
   * @returns {Array} Array of { substitute, score, reason, nutrition, density }
   */
  findSubstitutes(ingredientName, constraints = {}) {
    const { avoidAllergens = [], targetNutrition = {} } = constraints;

    // Step 1: Get nutrition profile for original ingredient
    const originalNutrition = getNutrition(ingredientName);

    // Step 2: Get density for original ingredient
    const originalDensity = getDensity(ingredientName);

    // Step 3: Get allergens for original ingredient

    // Step 4: Check for explicit substitution rules
    if (!hasSubstitutionRules(ingredientName)) {
      // No explicit rules, return intelligent suggestions based on nutrition/density
      return this._suggestByProfile(ingredientName, originalNutrition, originalDensity, avoidAllergens, targetNutrition);
    }

    const rules = getSubstitutionRules(ingredientName);
    if (!rules) return [];
    const substitutes = [];

    for (const rule of rules) {
      // Filter by allergen constraints
      if (rule.constraints && rule.constraints.avoidAllergens) {
        const substituteAllergens = getAllergens(rule.substitute);
        const hasConflict = rule.constraints.avoidAllergens.some(allergen =>
          substituteAllergens.includes(allergen)
        );
        if (hasConflict) continue;
      }

      // Filter by user-specified avoid allergens
      if (avoidAllergens.length > 0) {
        const substituteAllergens = getAllergens(rule.substitute);
        const hasConflict = avoidAllergens.some(allergen =>
          substituteAllergens.includes(allergen.toLowerCase())
        );
        if (hasConflict) continue;
      }

      // Get nutrition for substitute
      const substituteNutrition = getNutrition(rule.substitute);
      const substituteDensity = getDensity(rule.substitute);

      // Calculate compatibility score
      const compatibilityScore = this.getCompatibilityScore(
        ingredientName,
        rule.substitute,
        originalNutrition,
        substituteNutrition,
        originalDensity,
        substituteDensity
      );

      // Combine explicit rule score with compatibility score
      const finalScore = Math.round((rule.score * 0.6) + (compatibilityScore * 0.4));

      substitutes.push({
        substitute: rule.substitute,
        score: finalScore,
        reason: rule.reason,
        nutrition: substituteNutrition,
        density: substituteDensity,
        allergens: getAllergens(rule.substitute)
      });
    }

    // Sort by score descending
    substitutes.sort((a, b) => b.score - a.score);

    return substitutes;
  }

  /**
   * Suggest a swap for a recipe ingredient that satisfies a target constraint
   * @param {string} recipeId - Recipe ID (for future recipe integrity checking)
   * @param {string} ingredientToReplace - Name of ingredient to replace
   * @param {string} targetConstraint - Constraint to satisfy (e.g., 'nut-free', 'low-carb')
   * @returns {Object} Best substitute suggestion
   */
  suggestSwap(recipeId, ingredientToReplace, targetConstraint) {
    const constraints = this._parseConstraint(targetConstraint);
    const substitutes = this.findSubstitutes(ingredientToReplace, constraints);

    if (substitutes.length === 0) {
      return {
        found: false,
        message: `No substitutes found for "${ingredientToReplace}" matching constraint "${targetConstraint}"`,
        substitutes: []
      };
    }

    return {
      found: true,
      original: ingredientToReplace,
      constraint: targetConstraint,
      bestMatch: substitutes[0],
      alternatives: substitutes.slice(1, 4),
      message: `Found ${substitutes.length} substitutes for "${ingredientToReplace}"`
    };
  }

  /**
   * Get compatibility score between two ingredients (0-100)
   * Based on: nutrition similarity, density, cuisine typicality
   */
  getCompatibilityScore(original, substitute, originalNutrition, substituteNutrition, originalDensity, substituteDensity) {
    let score = 100;

    // Nutrition similarity scoring
    if (originalNutrition && substituteNutrition) {
      const nutritionDiff = this._calculateNutritionDiff(originalNutrition, substituteNutrition);
      // nutritionDiff is 0-100, subtract from score
      score -= nutritionDiff * 0.4; // 40% weight
    } else {
      score -= 10; // Penalty for missing nutrition data
    }

    // Density similarity scoring (important for baking)
    if (originalDensity && substituteDensity) {
      const densityRatio = substituteDensity / originalDensity;
      // Ideal ratio is 1.0, penalty increases as ratio deviates
      const densityPenalty = Math.abs(1 - densityRatio) * 30;
      score -= densityPenalty * 0.2; // 20% weight
    } else {
      score -= 5; // Smaller penalty for missing density
    }

    // Cuisine typicality (both ingredients should be commonly used together)
    const cuisineScore = this._getCuisineTypicality(original, substitute);
    score -= (100 - cuisineScore) * 0.15; // 15% weight

    // Allergen penalty
    const originalAllergens = getAllergens(original);
    const substituteAllergens = getAllergens(substitute);
    const newAllergens = substituteAllergens.filter(a => !originalAllergens.includes(a));
    if (newAllergens.length > 0) {
      score -= newAllergens.length * 5; // Small penalty for introducing new allergens
    }

    return Math.max(0, Math.min(100, Math.round(score)));
  }

  /**
   * Get nutrition difference between two ingredients (0-100)
   * Lower is better (more similar)
   */
  _calculateNutritionDiff(nutrition1, nutrition2) {
    if (!nutrition1 || !nutrition2) return 50; // Neutral if data missing

    const fields = ['calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'sodium'];
    let totalDiff = 0;

    for (const field of fields) {
      const val1 = nutrition1[field] || 0;
      const val2 = nutrition2[field] || 0;

      // Calculate relative difference (avoid division by zero)
      const maxVal = Math.max(val1, val2, 1);
      const diff = Math.abs(val1 - val2) / maxVal;
      totalDiff += diff;
    }

    // Average difference and scale to 0-100
    const avgDiff = totalDiff / fields.length;
    return Math.round(avgDiff * 100);
  }

  /**
   * Get cuisine typicality score (0-100)
   * Higher means ingredients are commonly used together
   */
  _getCuisineTypicality(original, substitute) {
    // Define ingredient categories
    const categories = {
      'fats': ['butter', 'oil', 'olive oil', 'vegetable oil', 'coconut oil', 'avocado', 'lard', 'ghee'],
      'dairy': ['milk', 'cream', 'cheese', 'yogurt', 'butter', 'sour cream', 'cream cheese'],
      'proteins': ['chicken', 'beef', 'pork', 'fish', 'tofu', 'tempeh', 'seitan', 'shrimp', 'salmon', 'tuna'],
      'grains': ['flour', 'rice', 'pasta', 'bread', 'oats', 'quinoa', 'cornmeal'],
      'sweeteners': ['sugar', 'honey', 'maple syrup', 'agave', 'molasses', 'coconut sugar'],
      'legumes': ['beans', 'lentils', 'chickpeas', 'tofu', 'peanuts', 'soy']
    };

    // Find categories for each ingredient
    let originalCategory = null;
    let substituteCategory = null;

    for (const [category, ingredients] of Object.entries(categories)) {
      if (ingredients.some(i => original.toLowerCase().includes(i))) {
        originalCategory = category;
      }
      if (ingredients.some(i => substitute.toLowerCase().includes(i))) {
        substituteCategory = category;
      }
    }

    // Same category = high typicality
    if (originalCategory === substituteCategory && originalCategory !== null) {
      return 90;
    }

    // Related categories
    const relatedCategories = {
      'dairy': ['fats'],
      'fats': ['dairy'],
      'proteins': ['legumes'],
      'legumes': ['proteins'],
      'grains': ['legumes']
    };

    if (relatedCategories[originalCategory]?.includes(substituteCategory)) {
      return 70;
    }

    // Cross-category substitutions are less typical
    return 50;
  }

  /**
   * Suggest substitutions based on nutrition profile when no explicit rules exist
   */
  _suggestByProfile(ingredientName, originalNutrition, originalDensity, avoidAllergens, targetNutrition) {
    // This would typically search through all ingredients to find similar ones
    // For now, return a message that no rules exist
    return [];
  }

  /**
   * Parse a constraint string into structured constraints
   */
  _parseConstraint(constraint) {
    const constraints = { avoidAllergens: [], targetNutrition: {} };

    if (!constraint) return constraints;

    const lowerConstraint = constraint.toLowerCase();

    // Common constraint patterns
    if (lowerConstraint.includes('nut-free') || lowerConstraint.includes('no nuts')) {
      constraints.avoidAllergens.push('tree nuts', 'peanuts');
    }
    if (lowerConstraint.includes('dairy-free') || lowerConstraint.includes('no dairy')) {
      constraints.avoidAllergens.push('dairy');
    }
    if (lowerConstraint.includes('gluten-free') || lowerConstraint.includes('no gluten')) {
      constraints.avoidAllergens.push('gluten');
    }
    if (lowerConstraint.includes('soy-free') || lowerConstraint.includes('no soy')) {
      constraints.avoidAllergens.push('soy');
    }
    if (lowerConstraint.includes('egg-free') || lowerConstraint.includes('no eggs')) {
      constraints.avoidAllergens.push('eggs');
    }
    if (lowerConstraint.includes('low-carb') || lowerConstraint.includes('low carb')) {
      constraints.targetNutrition.lowerCarbs = true;
    }
    if (lowerConstraint.includes('low-fat') || lowerConstraint.includes('low fat')) {
      constraints.targetNutrition.lowerFat = true;
    }
    if (lowerConstraint.includes('high-protein') || lowerConstraint.includes('high protein')) {
      constraints.targetNutrition.highProtein = true;
    }
    if (lowerConstraint.includes('vegan')) {
      constraints.avoidAllergens.push('dairy', 'eggs', 'fish', 'shellfish', 'honey');
    }
    if (lowerConstraint.includes('vegetarian')) {
      constraints.avoidAllergens.push('fish', 'shellfish', 'meat');
    }

    return constraints;
  }

  /**
   * Check if a substitute is valid for a constraint
   */
  isValidSubstitute(ingredientName, substituteName, constraint) {
    const constraints = this._parseConstraint(constraint);
    const substitutes = this.findSubstitutes(ingredientName, constraints);

    return substitutes.some(s =>
      s.substitute.toLowerCase() === substituteName.toLowerCase()
    );
  }
}

module.exports = SubstitutionEngine;
