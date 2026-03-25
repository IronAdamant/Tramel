'use strict';

const { validateRequired, sanitizeString, validateStringArray } = require('../utils/validation');

/**
 * DietaryProfile model
 */
class DietaryProfile {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'dietary_profiles';
  }

  /**
   * Create a new dietary profile
   */
  create({ name, restrictions, allergens, nutrition_goals }) {
    validateRequired({ name }, ['name']);

    return this.store.create(this.table, {
      name: sanitizeString(name),
      restrictions: restrictions || [],
      allergens: allergens || [],
      nutrition_goals: nutrition_goals || {}
    });
  }

  /**
   * Get dietary profile by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all dietary profiles
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a dietary profile
   */
  update(id, { name, restrictions, allergens, nutrition_goals }) {
    const updateData = {};

    if (name !== undefined) updateData.name = sanitizeString(name);
    if (restrictions !== undefined) updateData.restrictions = validateStringArray(restrictions, 'restrictions');
    if (allergens !== undefined) updateData.allergens = validateStringArray(allergens, 'allergens');
    if (nutrition_goals !== undefined) updateData.nutrition_goals = nutrition_goals;

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a dietary profile
   */
  delete(id) {
    return this.store.delete(this.table, id);
  }

  /**
   * Check if recipe complies with dietary profile
   */
  checkCompliance(recipeId) {
    const profile = this.getById(this.id);
    if (!profile) return { compliant: false, violations: ['Profile not found'] };

    const violations = [];

    // Get recipe ingredients
    const ingredients = this.store.findBy('ingredients', 'recipe_id', recipeId);

    // Check allergens
    for (const allergen of (profile.allergens || [])) {
      const matchingIngredients = ingredients.filter(ing =>
        (ing.allergens && ing.allergens.includes(allergen)) ||
        ing.name.toLowerCase().includes(allergen.toLowerCase())
      );
      if (matchingIngredients.length > 0) {
        violations.push(`Contains allergen: ${allergen}`);
      }
    }

    return {
      compliant: violations.length === 0,
      violations
    };
  }
}

module.exports = DietaryProfile;
