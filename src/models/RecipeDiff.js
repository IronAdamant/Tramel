/**
 * RecipeDiff Model
 * Diff between versions - stores ingredient-level changes
 */

class RecipeDiff {
  constructor({
    id = null,
    recipeId = null,
    fromCommitHash = null,
    toCommitHash = null,
    added = null,
    removed = null,
    modified = null,
    metadata = null,
    createdAt = null
  }) {
    this.id = id;
    this.recipeId = recipeId;
    this.fromCommitHash = fromCommitHash;
    this.toCommitHash = toCommitHash;
    this.added = added || []; // Ingredients added
    this.removed = removed || []; // Ingredients removed
    this.modified = modified || []; // Ingredients modified { before, after }
    this.metadata = metadata || {}; // Extra diff info (field changes, etc.)
    this.createdAt = createdAt || new Date().toISOString();
  }

  /**
   * Create a diff between two sets of ingredients
   */
  static create(recipeId, fromCommitHash, toCommitHash, added, removed, modified, metadata = {}) {
    return new RecipeDiff({
      recipeId,
      fromCommitHash,
      toCommitHash,
      added,
      removed,
      modified,
      metadata
    });
  }

  /**
   * Check if there are any changes
   */
  isEmpty() {
    return this.added.length === 0 &&
           this.removed.length === 0 &&
           this.modified.length === 0;
  }

  /**
   * Get total number of changes
   */
  getChangeCount() {
    return this.added.length + this.removed.length + this.modified.length;
  }

  /**
   * Serialize to database format
   */
  toDB() {
    return {
      id: this.id,
      recipe_id: this.recipeId,
      from_commit_hash: this.fromCommitHash,
      to_commit_hash: this.toCommitHash,
      added: JSON.stringify(this.added),
      removed: JSON.stringify(this.removed),
      modified: JSON.stringify(this.modified),
      metadata: JSON.stringify(this.metadata),
      created_at: this.createdAt
    };
  }

  /**
   * Deserialize from database row
   */
  static fromDB(row) {
    if (!row) return null;
    return new RecipeDiff({
      id: row.id,
      recipeId: row.recipe_id,
      fromCommitHash: row.from_commit_hash,
      toCommitHash: row.to_commit_hash,
      added: typeof row.added === 'string' ? JSON.parse(row.added) : row.added,
      removed: typeof row.removed === 'string' ? JSON.parse(row.removed) : row.removed,
      modified: typeof row.modified === 'string' ? JSON.parse(row.modified) : row.modified,
      metadata: typeof row.metadata === 'string' ? JSON.parse(row.metadata) : row.metadata,
      createdAt: row.created_at
    });
  }

  /**
   * Format as text for display
   */
  toText() {
    const lines = [];
    lines.push(`Diff from ${this.fromCommitHash?.substring(0, 7)} to ${this.toCommitHash?.substring(0, 7)}:`);

    if (this.added.length > 0) {
      lines.push(`\n+ Added (${this.added.length}):`);
      this.added.forEach(ing => lines.push(`  + ${ing.name}: ${ing.quantity} ${ing.unit}`));
    }

    if (this.removed.length > 0) {
      lines.push(`\n- Removed (${this.removed.length}):`);
      this.removed.forEach(ing => lines.push(`  - ${ing.name}: ${ing.quantity} ${ing.unit}`));
    }

    if (this.modified.length > 0) {
      lines.push(`\n~ Modified (${this.modified.length}):`);
      this.modified.forEach(m => {
        lines.push(`  ~ ${m.before.name}:`);
        lines.push(`    before: ${m.before.quantity} ${m.before.unit}`);
        lines.push(`    after: ${m.after.quantity} ${m.after.unit}`);
      });
    }

    return lines.join('\n');
  }

  /**
   * Validate diff has required fields
   */
  validate() {
    const errors = [];
    if (!this.recipeId) errors.push('recipeId is required');
    if (!this.fromCommitHash) errors.push('fromCommitHash is required');
    if (!this.toCommitHash) errors.push('toCommitHash is required');
    return errors;
  }
}

module.exports = RecipeDiff;
