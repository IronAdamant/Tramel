'use strict';

const DietaryProfile = require('../models/DietaryProfile');

/**
 * Dietary compliance checking service
 */
class DietaryComplianceService {
  constructor(fileStore) {
    this.store = fileStore;
    this.profile = new DietaryProfile(fileStore);
  }

  /**
   * Check if a recipe complies with a dietary profile
   */
  checkRecipeCompliance(recipeId, profileId) {
    // Get profile
    const dietaryProfile = profileId
      ? this.profile.getById(profileId)
      : this.store.readAll('dietary_profiles')[0];

    if (!dietaryProfile) {
      return { error: 'Dietary profile not found' };
    }

    // Get recipe with ingredients
    const recipe = this.store.readById('recipes', recipeId);
    if (!recipe) {
      return { error: 'Recipe not found' };
    }

    const ingredients = this.store.findBy('ingredients', 'recipe_id', recipeId);

    const violations = [];
    const warnings = [];

    // Check allergens
    for (const allergen of (dietaryProfile.allergens || [])) {
      const allergenLower = allergen.toLowerCase();
      const matchingIngredients = ingredients.filter(ing =>
        (ing.allergens && ing.allergens.some(a => a.toLowerCase().includes(allergenLower))) ||
        ing.name.toLowerCase().includes(allergenLower)
      );

      if (matchingIngredients.length > 0) {
        violations.push({
          type: 'allergen',
          allergen,
          found_in: matchingIngredients.map(i => i.name)
        });
      }
    }

    // Check restrictions
    for (const restriction of (dietaryProfile.restrictions || [])) {
      const restrictionLower = restriction.toLowerCase();

      // Simple restriction checks
      if (restrictionLower === 'vegan') {
        const nonVegan = ingredients.filter(ing => {
          const name = ing.name.toLowerCase();
          return name.includes('meat') || name.includes('chicken') || name.includes('beef') ||
            name.includes('pork') || name.includes('fish') || name.includes('egg') ||
            name.includes('milk') || name.includes('cheese') || name.includes('honey');
        });

        if (nonVegan.length > 0) {
          violations.push({
            type: 'restriction',
            restriction: 'vegan',
            violated_by: nonVegan.map(i => i.name)
          });
        }
      }

      if (restrictionLower === 'vegetarian') {
        const nonVegetarian = ingredients.filter(ing => {
          const name = ing.name.toLowerCase();
          return name.includes('meat') || name.includes('chicken') || name.includes('beef') ||
            name.includes('pork') || name.includes('fish');
        });

        if (nonVegetarian.length > 0) {
          violations.push({
            type: 'restriction',
            restriction: 'vegetarian',
            violated_by: nonVegetarian.map(i => i.name)
          });
        }
      }

      if (restrictionLower === 'gluten-free') {
        const glutenItems = ['wheat', 'flour', 'bread', 'pasta', 'barley', 'rye'];
        const containsGluten = ingredients.filter(ing =>
          glutenItems.some(item => ing.name.toLowerCase().includes(item))
        );

        if (containsGluten.length > 0) {
          violations.push({
            type: 'restriction',
            restriction: 'gluten-free',
            violated_by: containsGluten.map(i => i.name)
          });
        }
      }

      if (restrictionLower === 'dairy-free') {
        const dairyItems = ['milk', 'cheese', 'butter', 'cream', 'yogurt'];
        const containsDairy = ingredients.filter(ing =>
          dairyItems.some(item => ing.name.toLowerCase().includes(item))
        );

        if (containsDairy.length > 0) {
          violations.push({
            type: 'restriction',
            restriction: 'dairy-free',
            violated_by: containsDairy.map(i => i.name)
          });
        }
      }
    }

    return {
      recipe_id: recipeId,
      profile_id: dietaryProfile.id,
      profile_name: dietaryProfile.name,
      compliant: violations.length === 0,
      violations,
      warnings
    };
  }

  /**
   * Check multiple recipes against a profile
   */
  checkMultipleRecipes(recipeIds, profileId) {
    const results = [];

    for (const recipeId of recipeIds) {
      results.push(this.checkRecipeCompliance(recipeId, profileId));
    }

    return {
      compliant: results.filter(r => r.compliant).length,
      non_compliant: results.filter(r => !r.compliant).length,
      results
    };
  }

  /**
   * Find recipes that comply with a profile
   */
  findCompliantRecipes(profileId) {
    const recipes = this.store.readAll('recipes');
    const compliant = [];

    for (const recipe of recipes) {
      const result = this.checkRecipeCompliance(recipe.id, profileId);
      if (result.compliant) {
        compliant.push(recipe);
      }
    }

    return compliant;
  }
}

module.exports = DietaryComplianceService;
