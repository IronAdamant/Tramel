/**
 * RecipeConflict Model
 * Merge conflict record - stores conflict details during merge
 */

class RecipeConflict {
  constructor({
    id = null,
    recipeId = null,
    mergeCommitHash = null,
    branchName = null,
    conflictType = null, // 'ingredient', 'field', 'instruction'
    fieldPath = null, // e.g., 'ingredients.0', 'title', 'instructions.2'
    baseValue = null,
    targetValue = null,
    sourceValue = null,
    resolution = null, // 'pending', 'target', 'source', 'manual'
    resolvedValue = null,
    metadata = null,
    createdAt = null
  }) {
    this.id = id;
    this.recipeId = recipeId;
    this.mergeCommitHash = mergeCommitHash;
    this.branchName = branchName;
    this.conflictType = conflictType;
    this.fieldPath = fieldPath;
    this.baseValue = baseValue; // Common ancestor value
    this.targetValue = targetValue; // Current branch value
    this.sourceValue = sourceValue; // Branch being merged value
    this.resolution = resolution || 'pending';
    this.resolvedValue = resolvedValue;
    this.metadata = metadata || {};
    this.createdAt = createdAt || new Date().toISOString();
  }

  /**
   * Create a conflict record
   */
  static create(recipeId, mergeCommitHash, branchName, conflictType, fieldPath, baseValue, targetValue, sourceValue) {
    return new RecipeConflict({
      recipeId,
      mergeCommitHash,
      branchName,
      conflictType,
      fieldPath,
      baseValue,
      targetValue,
      sourceValue
    });
  }

  /**
   * Check if conflict is resolved
   */
  isResolved() {
    return this.resolution !== 'pending';
  }

  /**
   * Resolve the conflict with a value
   */
  resolve(value, resolution = 'manual') {
    this.resolvedValue = value;
    this.resolution = resolution;
  }

  /**
   * Get conflict description
   */
  getDescription() {
    switch (this.conflictType) {
      case 'ingredient':
        return `Ingredient conflict at ${this.fieldPath}`;
      case 'field':
        return `Field conflict at '${this.fieldPath}'`;
      case 'instruction':
        return `Instruction conflict at ${this.fieldPath}`;
      default:
        return `Unknown conflict at ${this.fieldPath}`;
    }
  }

  /**
   * Serialize to database format
   */
  toDB() {
    return {
      id: this.id,
      recipe_id: this.recipeId,
      merge_commit_hash: this.mergeCommitHash,
      branch_name: this.branchName,
      conflict_type: this.conflictType,
      field_path: this.fieldPath,
      base_value: JSON.stringify(this.baseValue),
      target_value: JSON.stringify(this.targetValue),
      source_value: JSON.stringify(this.sourceValue),
      resolution: this.resolution,
      resolved_value: JSON.stringify(this.resolvedValue),
      metadata: JSON.stringify(this.metadata),
      created_at: this.createdAt
    };
  }

  /**
   * Deserialize from database row
   */
  static fromDB(row) {
    if (!row) return null;
    return new RecipeConflict({
      id: row.id,
      recipeId: row.recipe_id,
      mergeCommitHash: row.merge_commit_hash,
      branchName: row.branch_name,
      conflictType: row.conflict_type,
      fieldPath: row.field_path,
      baseValue: typeof row.base_value === 'string' ? JSON.parse(row.base_value) : row.base_value,
      targetValue: typeof row.target_value === 'string' ? JSON.parse(row.target_value) : row.target_value,
      sourceValue: typeof row.source_value === 'string' ? JSON.parse(row.source_value) : row.source_value,
      resolution: row.resolution,
      resolvedValue: typeof row.resolved_value === 'string' ? JSON.parse(row.resolved_value) : row.resolved_value,
      metadata: typeof row.metadata === 'string' ? JSON.parse(row.metadata) : row.metadata,
      createdAt: row.created_at
    });
  }

  /**
   * Format for display
   */
  toDisplay() {
    return {
      id: this.id,
      type: this.conflictType,
      field: this.fieldPath,
      description: this.getDescription(),
      base: this.baseValue,
      target: this.targetValue,
      source: this.sourceValue,
      resolution: this.resolution,
      resolved: this.resolvedValue
    };
  }

  /**
   * Validate conflict has required fields
   */
  validate() {
    const errors = [];
    if (!this.recipeId) errors.push('recipeId is required');
    if (!this.mergeCommitHash) errors.push('mergeCommitHash is required');
    if (!this.conflictType) errors.push('conflictType is required');
    if (!this.fieldPath) errors.push('fieldPath is required');
    return errors;
  }
}

module.exports = RecipeConflict;
