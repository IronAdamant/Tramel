'use strict';

const { validateRequired, validatePositiveNumber, sanitizeString } = require('../utils/validation');

/**
 * Ingredient model
 */
class Ingredient {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'ingredients';
  }

  /**
   * Create a new ingredient
   */
  create({ recipe_id, name, quantity, unit, notes, sort_order, category, allergens }) {
    validateRequired({ recipe_id, name }, ['recipe_id', 'name']);

    return this.store.create(this.table, {
      recipe_id,
      name: sanitizeString(name),
      quantity: quantity !== undefined ? validatePositiveNumber(quantity, 'quantity') : null,
      unit: unit || '',
      notes: notes || '',
      sort_order: sort_order || 0,
      category: category || '',
      allergens: allergens || []
    });
  }

  /**
   * Get ingredient by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all ingredients for a recipe
   */
  getByRecipeId(recipeId) {
    return this.store.findBy(this.table, 'recipe_id', recipeId);
  }

  /**
   * Get all ingredients with pagination
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update an ingredient
   */
  update(id, fields) {
    const allowedFields = ['name', 'quantity', 'unit', 'notes', 'sort_order', 'category', 'allergens'];
    const updateData = {};

    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        if (field === 'quantity') {
          updateData[field] = validatePositiveNumber(fields[field], field);
        } else {
          updateData[field] = fields[field];
        }
      }
    }

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete an ingredient
   */
  delete(id) {
    return this.store.delete(this.table, id);
  }

  /**
   * Bulk create ingredients
   */
  bulkCreate(recipeId, ingredients) {
    const created = [];
    for (const ing of ingredients) {
      const createdIng = this.create({
        recipe_id: recipeId,
        ...ing
      });
      created.push(createdIng);
    }
    return created;
  }
}

module.exports = Ingredient;
