'use strict';

/**
 * OptimizationObjective - Defines an objective for meal plan optimization
 */
class OptimizationObjective {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'optimization_objectives';
  }

  /**
   * Create a new objective
   */
  create({ name, type, weight, direction, enabled = true }) {
    // direction: 'minimize' or 'maximize'
    return this.store.create(this.table, {
      name,
      type, // 'cost', 'nutrition', 'variety', 'calories', 'protein', 'time'
      weight: weight || 1.0,
      direction: direction || 'maximize',
      enabled
    });
  }

  /**
   * Get objective by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all enabled objectives
   */
  getEnabled() {
    const all = this.store.readAll(this.table);
    return all.filter(o => o.enabled !== false);
  }

  /**
   * Get objectives by type
   */
  getByType(type) {
    return this.store.findBy(this.table, 'type', type);
  }

  /**
   * Update an objective
   */
  update(id, fields) {
    const allowedFields = ['name', 'type', 'weight', 'direction', 'enabled'];
    const updateData = {};

    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updateData[field] = fields[field];
      }
    }

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete an objective
   */
  delete(id) {
    return this.store.delete(this.table, id);
  }

  /**
   * Check if objective is minimization
   */
  isMinimization(id) {
    const obj = this.getById(id);
    return obj && obj.direction === 'minimize';
  }

  /**
   * Check if objective is maximization
   */
  isMaximization(id) {
    const obj = this.getById(id);
    return obj && obj.direction === 'maximize';
  }
}

module.exports = OptimizationObjective;
