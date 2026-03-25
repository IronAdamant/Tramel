'use strict';

/**
 * OptimizationConstraint - Defines a constraint for meal plan optimization
 */
class OptimizationConstraint {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'optimization_constraints';
  }

  /**
   * Create a new constraint
   */
  create({ name, type, value, enabled = true }) {
    return this.store.create(this.table, {
      name,
      type, // 'maxCalories', 'maxCost', 'dietaryProfile', 'maxServings', 'minProtein'
      value,
      enabled
    });
  }

  /**
   * Get constraint by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all enabled constraints
   */
  getEnabled() {
    const all = this.store.readAll(this.table);
    return all.filter(c => c.enabled !== false);
  }

  /**
   * Get constraints by type
   */
  getByType(type) {
    return this.store.findBy(this.table, 'type', type);
  }

  /**
   * Update a constraint
   */
  update(id, fields) {
    const allowedFields = ['name', 'type', 'value', 'enabled'];
    const updateData = {};

    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updateData[field] = fields[field];
      }
    }

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a constraint
   */
  delete(id) {
    return this.store.delete(this.table, id);
  }

  /**
   * Disable a constraint
   */
  disable(id) {
    return this.update(id, { enabled: false });
  }

  /**
   * Enable a constraint
   */
  enable(id) {
    return this.update(id, { enabled: true });
  }
}

module.exports = OptimizationConstraint;
