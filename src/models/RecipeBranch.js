/**
 * RecipeBranch Model
 * Branch record - stores branch pointers and history
 */

class RecipeBranch {
  constructor({
    id = null,
    name = null,
    recipeId = null,
    headCommitHash = null,
    baseCommitHash = null,
    isActive = true,
    metadata = null,
    createdAt = null,
    updatedAt = null
  }) {
    this.id = id;
    this.name = name;
    this.recipeId = recipeId;
    this.headCommitHash = headCommitHash; // Current HEAD of branch
    this.baseCommitHash = baseCommitHash; // Commit where branch was created
    this.isActive = isActive;
    this.metadata = metadata || {};
    this.createdAt = createdAt || new Date().toISOString();
    this.updatedAt = updatedAt || new Date().toISOString();
  }

  /**
   * Create a new branch from a commit
   */
  static create(name, recipeId, headCommitHash, baseCommitHash = null) {
    return new RecipeBranch({
      name,
      recipeId,
      headCommitHash,
      baseCommitHash: baseCommitHash || headCommitHash,
      isActive: true
    });
  }

  /**
   * Update HEAD to a new commit
   */
  updateHead(commitHash) {
    this.headCommitHash = commitHash;
    this.updatedAt = new Date().toISOString();
  }

  /**
   * Serialize to database format
   */
  toDB() {
    return {
      id: this.id,
      name: this.name,
      recipe_id: this.recipeId,
      head_commit_hash: this.headCommitHash,
      base_commit_hash: this.baseCommitHash,
      is_active: this.isActive ? 1 : 0,
      metadata: JSON.stringify(this.metadata),
      created_at: this.createdAt,
      updated_at: this.updatedAt
    };
  }

  /**
   * Deserialize from database row
   */
  static fromDB(row) {
    if (!row) return null;
    return new RecipeBranch({
      id: row.id,
      name: row.name,
      recipeId: row.recipe_id,
      headCommitHash: row.head_commit_hash,
      baseCommitHash: row.base_commit_hash,
      isActive: row.is_active === 1,
      metadata: typeof row.metadata === 'string' ? JSON.parse(row.metadata) : row.metadata,
      createdAt: row.created_at,
      updatedAt: row.updated_at
    });
  }

  /**
   * Validate branch has required fields
   */
  validate() {
    const errors = [];
    if (!this.name) errors.push('name is required');
    if (!this.recipeId) errors.push('recipeId is required');
    if (!this.headCommitHash) errors.push('headCommitHash is required');
    return errors;
  }

  /**
   * Check if branch name is valid (alphanumeric, hyphens, underscores)
   */
  static isValidName(name) {
    return /^[a-zA-Z0-9_-]+$/.test(name) && name.length <= 100;
  }
}

module.exports = RecipeBranch;
