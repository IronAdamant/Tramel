'use strict';

const { validateRequired, validatePositiveInt, sanitizeString } = require('../utils/validation');

/**
 * MealPlan model
 */
class MealPlan {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'meal_plans';
    this.entriesTable = 'meal_plan_entries';
  }

  /**
   * Create a new meal plan
   */
  create({ name, start_date, end_date }) {
    validateRequired({ name, start_date }, ['name', 'start_date']);

    return this.store.create(this.table, {
      name: sanitizeString(name),
      start_date,
      end_date: end_date || null
    });
  }

  /**
   * Get meal plan by ID
   */
  getById(id) {
    const plan = this.store.readById(this.table, id);
    if (!plan) return null;

    // Load entries
    plan.entries = this.store.findBy(this.entriesTable, 'meal_plan_id', id);

    return plan;
  }

  /**
   * Get all meal plans
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a meal plan
   */
  update(id, fields) {
    const allowedFields = ['name', 'start_date', 'end_date'];
    const updateData = {};

    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updateData[field] = field === 'name' ? sanitizeString(fields[field]) : fields[field];
      }
    }

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a meal plan and its entries
   */
  delete(id) {
    // Delete entries first
    const entries = this.store.findBy(this.entriesTable, 'meal_plan_id', id);
    entries.forEach(entry => this.store.delete(this.entriesTable, entry.id));

    return this.store.delete(this.table, id);
  }

  /**
   * Add entry to meal plan
   */
  addEntry({ meal_plan_id, recipe_id, date, meal_type, servings }) {
    validateRequired({ meal_plan_id, recipe_id, date, meal_type }, ['meal_plan_id', 'recipe_id', 'date', 'meal_type']);

    return this.store.create(this.entriesTable, {
      meal_plan_id,
      recipe_id,
      date,
      meal_type,
      servings: validatePositiveInt(servings || 1, 'servings')
    });
  }

  /**
   * Remove entry from meal plan
   */
  removeEntry(entryId) {
    return this.store.delete(this.entriesTable, entryId);
  }

  /**
   * Update entry
   */
  updateEntry(entryId, fields) {
    const allowedFields = ['recipe_id', 'date', 'meal_type', 'servings'];
    const updateData = {};

    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updateData[field] = fields[field];
      }
    }

    return this.store.update(this.entriesTable, entryId, updateData);
  }
}

module.exports = MealPlan;
