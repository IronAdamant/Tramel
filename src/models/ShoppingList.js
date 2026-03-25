'use strict';

const { validateRequired, sanitizeString } = require('../utils/validation');

/**
 * ShoppingList model
 */
class ShoppingList {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'shopping_lists';
    this.itemsTable = 'shopping_list_items';
  }

  /**
   * Create a new shopping list
   */
  create({ name, meal_plan_id }) {
    validateRequired({ name }, ['name']);

    return this.store.create(this.table, {
      name: sanitizeString(name),
      meal_plan_id: meal_plan_id || null
    });
  }

  /**
   * Get shopping list by ID with items
   */
  getById(id) {
    const list = this.store.readById(this.table, id);
    if (!list) return null;

    // Load items
    list.items = this.store.findBy(this.itemsTable, 'shopping_list_id', id);

    return list;
  }

  /**
   * Get all shopping lists
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a shopping list
   */
  update(id, { name, meal_plan_id }) {
    const updateData = {};
    if (name !== undefined) updateData.name = sanitizeString(name);
    if (meal_plan_id !== undefined) updateData.meal_plan_id = meal_plan_id;

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a shopping list and its items
   */
  delete(id) {
    // Delete items first
    const items = this.store.findBy(this.itemsTable, 'shopping_list_id', id);
    items.forEach(item => this.store.delete(this.itemsTable, item.id));

    return this.store.delete(this.table, id);
  }

  /**
   * Add item to shopping list
   */
  addItem({ shopping_list_id, ingredient_name, quantity, unit, recipe_id }) {
    validateRequired({ shopping_list_id, ingredient_name }, ['shopping_list_id', 'ingredient_name']);

    return this.store.create(this.itemsTable, {
      shopping_list_id,
      ingredient_name: sanitizeString(ingredient_name),
      quantity: quantity || null,
      unit: unit || '',
      checked: false,
      recipe_id: recipe_id || null
    });
  }

  /**
   * Update item
   */
  updateItem(itemId, { ingredient_name, quantity, unit, checked }) {
    const updateData = {};
    if (ingredient_name !== undefined) updateData.ingredient_name = sanitizeString(ingredient_name);
    if (quantity !== undefined) updateData.quantity = quantity;
    if (unit !== undefined) updateData.unit = unit;
    if (checked !== undefined) updateData.checked = checked;

    return this.store.update(this.itemsTable, itemId, updateData);
  }

  /**
   * Toggle item checked status
   */
  toggleItem(itemId) {
    const item = this.store.readById(this.itemsTable, itemId);
    if (!item) return null;

    return this.store.update(this.itemsTable, itemId, { checked: !item.checked });
  }

  /**
   * Remove item from shopping list
   */
  removeItem(itemId) {
    return this.store.delete(this.itemsTable, itemId);
  }
}

module.exports = ShoppingList;
