/**
 * RecipeCommit Model
 * Commit record - stores commit metadata and hash
 */

const crypto = require('crypto');

class RecipeCommit {
  constructor({
    id = null,
    hash = null,
    recipeId = null,
    branchName = 'main',
    message = null,
    author = 'system',
    parentHashes = null,
    metadata = null,
    createdAt = null
  }) {
    this.id = id;
    this.hash = hash;
    this.recipeId = recipeId;
    this.branchName = branchName;
    this.message = message;
    this.author = author;
    this.parentHashes = parentHashes || []; // Array of parent commit hashes
    this.metadata = metadata || {}; // Extra commit info
    this.createdAt = createdAt || new Date().toISOString();
  }

  /**
   * Generate a commit hash from snapshot and metadata
   */
  static generateHash(snapshot, timestamp) {
    const data = JSON.stringify(snapshot) + timestamp;
    return crypto.createHash('sha1').update(data).digest('hex');
  }

  /**
   * Create a new commit from a recipe state
   */
  static create(recipeId, snapshot, message, author = 'system', branchName = 'main', parentHashes = []) {
    const timestamp = new Date().toISOString();
    const hash = RecipeCommit.generateHash(snapshot, timestamp);

    return new RecipeCommit({
      recipeId,
      branchName,
      message,
      author,
      parentHashes,
      metadata: {
        snapshotSize: JSON.stringify(snapshot).length
      }
    });
  }

  /**
   * Serialize to database format
   */
  toDB() {
    return {
      id: this.id,
      hash: this.hash,
      recipe_id: this.recipeId,
      branch_name: this.branchName,
      message: this.message,
      author: this.author,
      parent_hashes: JSON.stringify(this.parentHashes),
      metadata: JSON.stringify(this.metadata),
      created_at: this.createdAt
    };
  }

  /**
   * Deserialize from database row
   */
  static fromDB(row) {
    if (!row) return null;
    return new RecipeCommit({
      id: row.id,
      hash: row.hash,
      recipeId: row.recipe_id,
      branchName: row.branch_name,
      message: row.message,
      author: row.author,
      parentHashes: typeof row.parent_hashes === 'string' ? JSON.parse(row.parent_hashes) : row.parent_hashes,
      metadata: typeof row.metadata === 'string' ? JSON.parse(row.metadata) : row.metadata,
      createdAt: row.created_at
    });
  }

  /**
   * Check if this commit is a merge commit
   */
  isMergeCommit() {
    return this.parentHashes.length > 1;
  }

  /**
   * Validate commit has required fields
   */
  validate() {
    const errors = [];
    if (!this.hash) errors.push('hash is required');
    if (!this.recipeId) errors.push('recipeId is required');
    if (!this.message) errors.push('message is required');
    return errors;
  }

  /**
   * Get short hash (first 7 characters)
   */
  getShortHash() {
    return this.hash ? this.hash.substring(0, 7) : null;
  }
}

module.exports = RecipeCommit;
