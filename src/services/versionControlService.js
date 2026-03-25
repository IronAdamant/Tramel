/**
 * VersionControlService
 * Core version control: commit, checkout, branch, merge, diff, history
 */

const crypto = require('crypto');
const path = require('path');
const fs = require('fs');

const RecipeCommit = require('../models/RecipeCommit');
const RecipeVersion = require('../models/RecipeVersion');
const RecipeBranch = require('../models/RecipeBranch');
const RecipeDiff = require('../models/RecipeDiff');
const RecipeConflict = require('../models/RecipeConflict');
const DiffService = require('./diffService');
const MergeService = require('./mergeService');

class VersionControlService {
  constructor(db) {
    this.db = db;
    this.diffService = new DiffService();
    this.mergeService = new MergeService();
  }

  /**
   * Initialize version control tables
   */
  initializeTables() {
    const stmt = `
      CREATE TABLE IF NOT EXISTS recipe_commits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hash TEXT UNIQUE NOT NULL,
        recipe_id TEXT NOT NULL,
        branch_name TEXT DEFAULT 'main',
        message TEXT NOT NULL,
        author TEXT DEFAULT 'system',
        parent_hashes TEXT DEFAULT '[]',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS recipe_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        commit_hash TEXT NOT NULL,
        recipe_id TEXT NOT NULL,
        branch_name TEXT DEFAULT 'main',
        snapshot TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (commit_hash) REFERENCES recipe_commits(hash)
      );

      CREATE TABLE IF NOT EXISTS recipe_branches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        recipe_id TEXT NOT NULL,
        head_commit_hash TEXT NOT NULL,
        base_commit_hash TEXT,
        is_active INTEGER DEFAULT 1,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(recipe_id, name)
      );

      CREATE TABLE IF NOT EXISTS recipe_diffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id TEXT NOT NULL,
        from_commit_hash TEXT NOT NULL,
        to_commit_hash TEXT NOT NULL,
        added TEXT DEFAULT '[]',
        removed TEXT DEFAULT '[]',
        modified TEXT DEFAULT '[]',
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS recipe_conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id TEXT NOT NULL,
        merge_commit_hash TEXT NOT NULL,
        branch_name TEXT,
        conflict_type TEXT NOT NULL,
        field_path TEXT,
        base_value TEXT,
        target_value TEXT,
        source_value TEXT,
        resolution TEXT DEFAULT 'pending',
        resolved_value TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now'))
      );

      CREATE INDEX IF NOT EXISTS idx_commits_recipe ON recipe_commits(recipe_id);
      CREATE INDEX IF NOT EXISTS idx_commits_hash ON recipe_commits(hash);
      CREATE INDEX IF NOT EXISTS idx_versions_recipe ON recipe_versions(recipe_id);
      CREATE INDEX IF NOT EXISTS idx_branches_recipe ON recipe_branches(recipe_id);
      CREATE INDEX IF NOT EXISTS idx_diffs_recipe ON recipe_diffs(recipe_id);
      CREATE INDEX IF NOT EXISTS idx_conflicts_recipe ON recipe_conflicts(recipe_id);
    `;

    this.db.exec(stmt);
  }

  /**
   * Create a new commit
   * @param {string} recipeId - Recipe ID
   * @param {Object} recipe - Current recipe state
   * @param {string} message - Commit message
   * @param {string} author - Author name
   * @param {string} branchName - Branch name
   * @returns {Object} Commit result
   */
  commit(recipeId, recipe, message, author = 'system', branchName = 'main') {
    // Get current HEAD
    const currentHead = this.getBranchHead(recipeId, branchName);
    const parentHashes = currentHead ? [currentHead.hash] : [];

    // Create snapshot
    const snapshot = this.createSnapshot(recipe);

    // Create commit
    const timestamp = new Date().toISOString();
    const hash = RecipeCommit.generateHash(snapshot, timestamp);
    const commit = new RecipeCommit({
      recipeId,
      branchName,
      message,
      author,
      parentHashes,
      metadata: { snapshotSize: JSON.stringify(snapshot).length }
    });
    commit.hash = hash;

    // Save commit to DB
    const commitStmt = this.db.prepare(`
      INSERT INTO recipe_commits (hash, recipe_id, branch_name, message, author, parent_hashes, metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    commitStmt.run(
      commit.hash,
      commit.recipeId,
      commit.branchName,
      commit.message,
      commit.author,
      JSON.stringify(commit.parentHashes),
      JSON.stringify(commit.metadata),
      timestamp
    );

    // Create version snapshot
    const version = RecipeVersion.fromRecipeAndCommit(recipe, commit, branchName);
    const versionStmt = this.db.prepare(`
      INSERT INTO recipe_versions (commit_hash, recipe_id, branch_name, snapshot, created_at)
      VALUES (?, ?, ?, ?, ?)
    `);
    versionStmt.run(
      version.commitHash,
      version.recipeId,
      version.branchName,
      JSON.stringify(version.snapshot),
      timestamp
    );

    // Update branch HEAD
    this.updateBranchHead(recipeId, branchName, commit.hash);

    return {
      commit: commit,
      version: version,
      hash: commit.hash
    };
  }

  /**
   * Create a snapshot from recipe
   */
  createSnapshot(recipe) {
    return {
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
      tags: recipe.tags || [],
      nutrition: recipe.nutrition,
      dietaryFlags: recipe.dietaryFlags,
      images: recipe.images,
      source: recipe.source,
      notes: recipe.notes
    };
  }

  /**
   * Checkout a specific commit
   * @param {string} recipeId - Recipe ID
   * @param {string} commitHash - Commit hash to checkout
   * @returns {Object} Recipe at that commit
   */
  checkout(recipeId, commitHash) {
    const commit = this.getCommitByHash(commitHash);
    if (!commit || commit.recipeId !== recipeId) {
      return { success: false, error: 'Commit not found' };
    }

    const version = this.getVersionByCommitHash(commitHash);
    if (!version) {
      return { success: false, error: 'Version not found' };
    }

    return {
      success: true,
      commit,
      recipe: version.snapshot,
      branchName: commit.branchName
    };
  }

  /**
   * Create a new branch
   * @param {string} recipeId - Recipe ID
   * @param {string} branchName - New branch name
   * @param {string} fromBranch - Source branch (default: current branch)
   * @returns {Object} Branch creation result
   */
  branch(recipeId, branchName, fromBranch = null) {
    if (!RecipeBranch.isValidName(branchName)) {
      return { success: false, error: 'Invalid branch name' };
    }

    // Check if branch already exists
    const existing = this.getBranch(recipeId, branchName);
    if (existing) {
      return { success: false, error: 'Branch already exists' };
    }

    // Get HEAD from source branch or current branch
    const sourceBranchName = fromBranch || this.getCurrentBranch(recipeId) || 'main';
    const head = this.getBranchHead(recipeId, sourceBranchName);

    if (!head) {
      return { success: false, error: 'No commits found to branch from' };
    }

    // Create new branch
    const branch = RecipeBranch.create(branchName, recipeId, head.hash, head.hash);
    const stmt = this.db.prepare(`
      INSERT INTO recipe_branches (name, recipe_id, head_commit_hash, base_commit_hash, is_active, metadata, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      branch.name,
      branch.recipeId,
      branch.headCommitHash,
      branch.baseCommitHash,
      branch.isActive ? 1 : 0,
      JSON.stringify(branch.metadata),
      branch.createdAt,
      branch.updatedAt
    );

    return {
      success: true,
      branch,
      fromCommit: head
    };
  }

  /**
   * Merge one branch into another
   * @param {string} recipeId - Recipe ID
   * @param {string} sourceBranch - Branch to merge from
   * @param {string} targetBranch - Branch to merge into (default: main)
   * @returns {Object} Merge result
   */
  merge(recipeId, sourceBranch, targetBranch = 'main') {
    const sourceHead = this.getBranchHead(recipeId, sourceBranch);
    const targetHead = this.getBranchHead(recipeId, targetBranch);

    if (!sourceHead) {
      return { success: false, error: `Source branch '${sourceBranch}' not found` };
    }

    if (!targetHead) {
      return { success: false, error: `Target branch '${targetBranch}' not found` };
    }

    if (sourceBranch === targetBranch) {
      return { success: false, error: 'Cannot merge branch into itself' };
    }

    // Get versions for merge
    const sourceVersion = this.getVersionByCommitHash(sourceHead.hash);
    const targetVersion = this.getVersionByCommitHash(targetHead.hash);

    if (!sourceVersion || !targetVersion) {
      return { success: false, error: 'Could not find versions for merge' };
    }

    // Find base (common ancestor) - simplified: find first common ancestor
    const base = this.findCommonAncestor(recipeId, targetHead.hash, sourceHead.hash);
    const baseVersion = base ? this.getVersionByCommitHash(base.hash) : null;

    // Perform 3-way merge
    const mergeResult = this.mergeService.threeWayMerge(
      baseVersion ? baseVersion.snapshot : null,
      targetVersion.snapshot,
      sourceVersion.snapshot
    );

    if (!mergeResult.success) {
      // There are conflicts - create merge commit with conflicts recorded
      const timestamp = new Date().toISOString();
      const mergeHash = RecipeCommit.generateHash(mergeResult.result, timestamp);

      const mergeCommit = new RecipeCommit({
        recipeId,
        branchName: targetBranch,
        message: `Merge branch '${sourceBranch}' into ${targetBranch} (with conflicts)`,
        author: 'system',
        parentHashes: [targetHead.hash, sourceHead.hash],
        metadata: { hasConflicts: true, conflictCount: mergeResult.conflicts.length }
      });
      mergeCommit.hash = mergeHash;

      // Save merge commit
      const commitStmt = this.db.prepare(`
        INSERT INTO recipe_commits (hash, recipe_id, branch_name, message, author, parent_hashes, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `);
      commitStmt.run(
        mergeCommit.hash,
        mergeCommit.recipeId,
        mergeCommit.branchName,
        mergeCommit.message,
        mergeCommit.author,
        JSON.stringify(mergeCommit.parentHashes),
        JSON.stringify(mergeCommit.metadata),
        timestamp
      );

      // Save conflicts
      for (const conflict of mergeResult.conflicts) {
        const conflictRecord = RecipeConflict.create(
          recipeId,
          mergeHash,
          sourceBranch,
          conflict.type,
          conflict.fieldPath,
          conflict.baseValue,
          conflict.targetValue,
          conflict.sourceValue
        );
        this.saveConflict(conflictRecord);
      }

      return {
        success: false,
        hasConflicts: true,
        commit: mergeCommit,
        conflicts: mergeResult.conflicts,
        partialResult: mergeResult.result
      };
    }

    // Successful merge - create merge commit
    const timestamp = new Date().toISOString();
    const mergeHash = RecipeCommit.generateHash(mergeResult.result, timestamp);

    const mergeCommit = new RecipeCommit({
      recipeId,
      branchName: targetBranch,
      message: `Merge branch '${sourceBranch}' into ${targetBranch}`,
      author: 'system',
      parentHashes: [targetHead.hash, sourceHead.hash],
      metadata: { hasConflicts: false }
    });
    mergeCommit.hash = mergeHash;

    // Save merge commit
    const commitStmt = this.db.prepare(`
      INSERT INTO recipe_commits (hash, recipe_id, branch_name, message, author, parent_hashes, metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    commitStmt.run(
      mergeCommit.hash,
      mergeCommit.recipeId,
      mergeCommit.branchName,
      mergeCommit.message,
      mergeCommit.author,
      JSON.stringify(mergeCommit.parentHashes),
      JSON.stringify(mergeCommit.metadata),
      timestamp
    );

    // Create version
    const versionStmt = this.db.prepare(`
      INSERT INTO recipe_versions (commit_hash, recipe_id, branch_name, snapshot, created_at)
      VALUES (?, ?, ?, ?, ?)
    `);
    versionStmt.run(
      mergeCommit.hash,
      recipeId,
      targetBranch,
      JSON.stringify(mergeResult.result),
      timestamp
    );

    // Update branch HEAD
    this.updateBranchHead(recipeId, targetBranch, mergeCommit.hash);

    return {
      success: true,
      commit: mergeCommit,
      result: mergeResult.result,
      conflicts: []
    };
  }

  /**
   * Find common ancestor of two commits
   */
  findCommonAncestor(recipeId, hash1, hash2) {
    const ancestors1 = this.getAncestors(recipeId, hash1, new Set());
    const ancestors2 = this.getAncestors(recipeId, hash2, new Set());

    for (const ancestor of ancestors1) {
      if (ancestors2.has(ancestor.hash)) {
        return ancestor;
      }
    }

    return null; // No common ancestor found
  }

  /**
   * Get all ancestors of a commit
   */
  getAncestors(recipeId, hash, visited = new Set()) {
    if (visited.has(hash)) return visited;

    const commit = this.getCommitByHash(hash);
    if (!commit) return visited;

    visited.add(hash);

    for (const parentHash of commit.parentHashes) {
      this.getAncestors(recipeId, parentHash, visited);
    }

    return visited;
  }

  /**
   * Get diff between two commits
   * @param {string} recipeId - Recipe ID
   * @param {string} commit1 - First commit hash
   * @param {string} commit2 - Second commit hash
   * @returns {Object} Diff result
   */
  diff(recipeId, commit1, commit2) {
    const version1 = this.getVersionByCommitHash(commit1);
    const version2 = this.getVersionByCommitHash(commit2);

    if (!version1 || !version2) {
      return { success: false, error: 'One or both commits not found' };
    }

    // Diff ingredients
    const ingredientDiff = this.diffService.diff(
      version1.snapshot.ingredients,
      version2.snapshot.ingredients
    );

    // Diff fields
    const fieldChanges = this.diffService.diffRecipeFields(
      version1.snapshot,
      version2.snapshot
    );

    // Diff instructions
    const instructionDiff = this.diffService.diffInstructions(
      version1.snapshot.instructions,
      version2.snapshot.instructions
    );

    const diff = RecipeDiff.create(
      recipeId,
      commit1,
      commit2,
      ingredientDiff.added,
      ingredientDiff.removed,
      ingredientDiff.modified,
      { fieldChanges, instructionDiff }
    );

    // Save diff
    const stmt = this.db.prepare(`
      INSERT INTO recipe_diffs (recipe_id, from_commit_hash, to_commit_hash, added, removed, modified, metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      recipeId,
      commit1,
      commit2,
      JSON.stringify(ingredientDiff.added),
      JSON.stringify(ingredientDiff.removed),
      JSON.stringify(ingredientDiff.modified),
      JSON.stringify(diff.metadata),
      diff.createdAt
    );

    return {
      success: true,
      diff,
      ingredients: ingredientDiff,
      fields: fieldChanges,
      instructions: instructionDiff
    };
  }

  /**
   * Get commit history for a recipe
   * @param {string} recipeId - Recipe ID
   * @param {number} limit - Max number of commits to return
   * @param {string} branchName - Optional branch filter
   * @returns {Array} List of commits
   */
  history(recipeId, limit = 50, branchName = null) {
    let query = `
      SELECT * FROM recipe_commits
      WHERE recipe_id = ?
    `;
    const params = [recipeId];

    if (branchName) {
      query += ` AND branch_name = ?`;
      params.push(branchName);
    }

    query += ` ORDER BY created_at DESC LIMIT ?`;
    params.push(limit);

    const stmt = this.db.prepare(query);
    const rows = stmt.all(...params);

    return rows.map(row => RecipeCommit.fromDB(row));
  }

  /**
   * Get all branches for a recipe
   * @param {string} recipeId - Recipe ID
   * @returns {Array} List of branches
   */
  getBranches(recipeId) {
    const stmt = this.db.prepare(`
      SELECT * FROM recipe_branches
      WHERE recipe_id = ? AND is_active = 1
      ORDER BY created_at ASC
    `);
    const rows = stmt.all(recipeId);
    return rows.map(row => RecipeBranch.fromDB(row));
  }

  /**
   * Get a specific branch
   */
  getBranch(recipeId, branchName) {
    const stmt = this.db.prepare(`
      SELECT * FROM recipe_branches
      WHERE recipe_id = ? AND name = ?
    `);
    const row = stmt.get(recipeId, branchName);
    return row ? RecipeBranch.fromDB(row) : null;
  }

  /**
   * Get current branch for a recipe
   */
  getCurrentBranch(recipeId) {
    const stmt = this.db.prepare(`
      SELECT branch_name FROM recipe_commits
      WHERE recipe_id = ?
      ORDER BY created_at DESC
      LIMIT 1
    `);
    const row = stmt.get(recipeId);
    return row ? row.branch_name : 'main';
  }

  /**
   * Get branch HEAD commit
   */
  getBranchHead(recipeId, branchName) {
    const branch = this.getBranch(recipeId, branchName);
    if (!branch) return null;
    return this.getCommitByHash(branch.headCommitHash);
  }

  /**
   * Update branch HEAD
   */
  updateBranchHead(recipeId, branchName, commitHash) {
    const stmt = this.db.prepare(`
      UPDATE recipe_branches
      SET head_commit_hash = ?, updated_at = datetime('now')
      WHERE recipe_id = ? AND name = ?
    `);
    stmt.run(commitHash, recipeId, branchName);
  }

  /**
   * Get commit by hash
   */
  getCommitByHash(hash) {
    const stmt = this.db.prepare(`SELECT * FROM recipe_commits WHERE hash = ?`);
    const row = stmt.get(hash);
    return row ? RecipeCommit.fromDB(row) : null;
  }

  /**
   * Get version by commit hash
   */
  getVersionByCommitHash(commitHash) {
    const stmt = this.db.prepare(`SELECT * FROM recipe_versions WHERE commit_hash = ?`);
    const row = stmt.get(commitHash);
    return row ? RecipeVersion.fromDB(row) : null;
  }

  /**
   * Save conflict record
   */
  saveConflict(conflict) {
    const stmt = this.db.prepare(`
      INSERT INTO recipe_conflicts (recipe_id, merge_commit_hash, branch_name, conflict_type, field_path, base_value, target_value, source_value, resolution, resolved_value, metadata, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      conflict.recipeId,
      conflict.mergeCommitHash,
      conflict.branchName,
      conflict.conflictType,
      conflict.fieldPath,
      JSON.stringify(conflict.baseValue),
      JSON.stringify(conflict.targetValue),
      JSON.stringify(conflict.sourceValue),
      conflict.resolution,
      JSON.stringify(conflict.resolvedValue),
      JSON.stringify(conflict.metadata),
      conflict.createdAt
    );
  }

  /**
   * Get commits for a branch
   */
  getCommitsForBranch(recipeId, branchName, limit = 50) {
    return this.history(recipeId, limit, branchName);
  }

  /**
   * Delete a branch
   */
  deleteBranch(recipeId, branchName) {
    if (branchName === 'main') {
      return { success: false, error: 'Cannot delete main branch' };
    }

    const stmt = this.db.prepare(`
      UPDATE recipe_branches
      SET is_active = 0
      WHERE recipe_id = ? AND name = ?
    `);
    stmt.run(recipeId, branchName);

    return { success: true };
  }
}

module.exports = VersionControlService;
