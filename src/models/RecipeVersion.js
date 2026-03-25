/**
 * RecipeVersion Model
 * Version snapshot - stores complete recipe state at a point in time
 */

const crypto = require('crypto');

class RecipeVersion {
  constructor({
    id = null,
    commitHash = null,
    recipeId = null,
    branchName = 'main',
    snapshot = null,
    createdAt = null
  }) {
    this.id = id;
    this.commitHash = commitHash;
    this.recipeId = recipeId;
    this.branchName = branchName;
    this.snapshot = snapshot; // Full recipe state as JSON
    this.createdAt = createdAt || new Date().toISOString();
  }

  /**
   * Generate a version hash from commit hash and sequence number
   */
  static generateVersionHash(commitHash, sequence) {
    const data = `${commitHash}-v${sequence}`;
    return crypto.createHash('sha1').update(data).digest('hex').substring(0, 8);
  }

  /**
   * Create a version from a recipe and commit
   */
  static fromRecipeAndCommit(recipe, commit, branchName = 'main') {
    const snapshot = {
      title: recipe.title,
      description: recipe.description,
      ingredients: recipe.ingredients,
      instructions: recipe.instructions,
      servings: recipe.servings,
      prepTime: recipe.prepTime,
      cookTime: recipe.cookTime,
      totalTime: recipe.totalTime,
      difficulty: recipe.difficulty,
      cuisine: recipe.cuisine,
      mealType: recipe.mealType,
      tags: recipe.tags,
      nutrition: recipe.nutrition,
      dietaryFlags: recipe.dietaryFlags,
      images: recipe.images,
      source: recipe.source,
      notes: recipe.notes
    };

    return new RecipeVersion({
      commitHash: commit.hash,
      recipeId: recipe.id,
      branchName,
      snapshot
    });
  }

  /**
   * Serialize to database format
   */
  toDB() {
    return {
      id: this.id,
      commit_hash: this.commitHash,
      recipe_id: this.recipeId,
      branch_name: this.branchName,
      snapshot: JSON.stringify(this.snapshot),
      created_at: this.createdAt
    };
  }

  /**
   * Deserialize from database row
   */
  static fromDB(row) {
    if (!row) return null;
    return new RecipeVersion({
      id: row.id,
      commitHash: row.commit_hash,
      recipeId: row.recipe_id,
      branchName: row.branch_name,
      snapshot: typeof row.snapshot === 'string' ? JSON.parse(row.snapshot) : row.snapshot,
      createdAt: row.created_at
    });
  }

  /**
   * Get the recipe ID from snapshot
   */
  getRecipeId() {
    return this.recipeId;
  }

  /**
   * Validate version has required fields
   */
  validate() {
    const errors = [];
    if (!this.commitHash) errors.push('commitHash is required');
    if (!this.recipeId) errors.push('recipeId is required');
    if (!this.snapshot) errors.push('snapshot is required');
    return errors;
  }
}

module.exports = RecipeVersion;
