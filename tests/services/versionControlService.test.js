/**
 * VersionControlService Tests
 * Tests for commit, checkout, branch, merge, diff, history operations
 */

const { describe, test, assert } = require('../testRunner');
const VersionControlService = require('../../src/services/versionControlService');

// Mock database for testing
class MockDB {
  constructor() {
    this.data = {
      recipe_commits: [],
      recipe_versions: [],
      recipe_branches: [],
      recipe_diffs: [],
      recipe_conflicts: []
    };
  }

  prepare() {
    return {
      run: (...args) => {
        this.lastRun = args;
        // Store in appropriate collection based on query
        const query = this._lastQuery || '';
        if (query.includes('recipe_commits')) {
          this.data.recipe_commits.push(args[0]);
        } else if (query.includes('recipe_versions')) {
          this.data.recipe_versions.push(args[0]);
        } else if (query.includes('recipe_branches')) {
          this.data.recipe_branches.push({ name: args[0], recipe_id: args[1], head_commit_hash: args[2] });
        }
        return { changes: 1 };
      },
      all: (...args) => {
        const query = this._lastQuery || '';
        if (query.includes('recipe_commits')) {
          return this.data.recipe_commits;
        }
        return [];
      },
      get: (...args) => {
        const hash = args[0];
        const found = this.data.recipe_commits.find(c => c.hash === hash);
        if (found) return found;
        // Check if it's a branch query
        if (args.length >= 2 && typeof args[1] === 'string') {
          return this.data.recipe_branches.find(b => b.name === args[1]);
        }
        return null;
      }
    };
  }

  exec() {}
}

// Mock RecipeCommit for testing
const RecipeCommit = require('../../src/models/RecipeCommit');
const RecipeBranch = require('../../src/models/RecipeBranch');
const RecipeDiff = require('../../src/models/RecipeDiff');
const RecipeConflict = require('../../src/models/RecipeConflict');

describe('VersionControlService', () => {
  let vcService;
  let mockDb;

  beforeEach_helper: (() => {
    mockDb = new MockDB();
    vcService = new VersionControlService(mockDb);
    vcService.initializeTables();
  });

  test('should create a new commit', () => {
    const mockDb = new MockDB();
    const vcService = new VersionControlService(mockDb);
    vcService.initializeTables();

    const recipe = {
      id: 'recipe-1',
      title: 'Test Recipe',
      description: 'A test recipe',
      ingredients: [{ name: 'Flour', quantity: '2', unit: 'cups' }],
      instructions: ['Mix ingredients'],
      servings: 4
    };

    const result = vcService.commit('recipe-1', recipe, 'Initial commit');

    assert.ok(result);
    assert.ok(result.hash);
    assert.strictEqual(result.commit.message, 'Initial commit');
    assert.strictEqual(result.commit.recipeId, 'recipe-1');
    assert.strictEqual(result.commit.branchName, 'main');
  });

  test('should generate unique hashes for different commits', () => {
    const mockDb = new MockDB();
    const vcService = new VersionControlService(mockDb);
    vcService.initializeTables();

    const recipe1 = {
      id: 'recipe-1',
      title: 'Recipe 1',
      ingredients: [{ name: 'A', quantity: '1', unit: 'cup' }],
      instructions: ['Step 1']
    };
    const recipe2 = {
      id: 'recipe-1',
      title: 'Recipe 2',
      ingredients: [{ name: 'B', quantity: '2', unit: 'cup' }],
      instructions: ['Step 2']
    };

    const result1 = vcService.commit('recipe-1', recipe1, 'Commit 1');
    const result2 = vcService.commit('recipe-1', recipe2, 'Commit 2');

    assert.notStrictEqual(result1.hash, result2.hash);
  });

  test('should fail for non-existent commit', () => {
    const mockDb = new MockDB();
    const vcService = new VersionControlService(mockDb);
    vcService.initializeTables();

    const result = vcService.checkout('recipe-1', 'nonexistent-hash');

    assert.strictEqual(result.success, false);
    assert.ok(result.error.includes('not found'));
  });
});

describe('RecipeCommit Model', () => {
  test('should generate hash from snapshot and timestamp', () => {
    const snapshot = { title: 'Test', ingredients: [] };
    const timestamp = '2024-01-01T00:00:00.000Z';

    const hash = RecipeCommit.generateHash(snapshot, timestamp);

    assert.ok(hash);
    assert.strictEqual(typeof hash, 'string');
    assert.strictEqual(hash.length, 40);
  });

  test('should create commit with parent hashes', () => {
    const commit = RecipeCommit.create(
      'recipe-1',
      { title: 'Test' },
      'Test message',
      'author',
      'main',
      ['parent-hash-1', 'parent-hash-2']
    );

    assert.strictEqual(commit.recipeId, 'recipe-1');
    assert.strictEqual(commit.message, 'Test message');
    assert.strictEqual(commit.parentHashes.length, 2);
  });

  test('should detect merge commit', () => {
    const mergeCommit = new RecipeCommit({
      hash: 'abc',
      recipeId: 'r1',
      message: 'merge',
      parentHashes: ['hash1', 'hash2']
    });

    assert.strictEqual(mergeCommit.isMergeCommit(), true);
  });

  test('should get short hash', () => {
    const commit = new RecipeCommit({
      hash: 'abcdef1234567890'
    });

    assert.strictEqual(commit.getShortHash(), 'abcdef1');
  });
});

describe('RecipeBranch Model', () => {
  test('should validate branch name', () => {
    assert.strictEqual(RecipeBranch.isValidName('valid-name'), true);
    assert.strictEqual(RecipeBranch.isValidName('valid_name'), true);
    assert.strictEqual(RecipeBranch.isValidName('validName123'), true);
    assert.strictEqual(RecipeBranch.isValidName('invalid name'), false);
    assert.strictEqual(RecipeBranch.isValidName('invalid/name'), false);
  });

  test('should update HEAD', () => {
    const branch = new RecipeBranch({
      name: 'test',
      recipeId: 'r1',
      headCommitHash: 'old-hash'
    });

    branch.updateHead('new-hash');

    assert.strictEqual(branch.headCommitHash, 'new-hash');
    assert.ok(branch.updatedAt);
  });
});

describe('RecipeDiff Model', () => {
  test('should create diff with changes', () => {
    const diff = RecipeDiff.create(
      'recipe-1',
      'hash1',
      'hash2',
      [{ name: 'Sugar' }],
      [{ name: 'Salt' }],
      [{ before: { name: 'Flour' }, after: { name: 'Almond Flour' } }]
    );

    assert.strictEqual(diff.added.length, 1);
    assert.strictEqual(diff.removed.length, 1);
    assert.strictEqual(diff.modified.length, 1);
  });

  test('should check if empty', () => {
    const emptyDiff = new RecipeDiff({ recipeId: 'r1', fromCommitHash: 'h1', toCommitHash: 'h2' });
    assert.strictEqual(emptyDiff.isEmpty(), true);

    const nonEmptyDiff = RecipeDiff.create('r1', 'h1', 'h2', [{ name: 'A' }], [], []);
    assert.strictEqual(nonEmptyDiff.isEmpty(), false);
  });

  test('should format as text', () => {
    const diff = RecipeDiff.create(
      'recipe-1',
      'hash1',
      'hash2',
      [{ name: 'Sugar', quantity: '1', unit: 'cup' }],
      [],
      []
    );

    const text = diff.toText();

    assert.ok(text.includes('Added'));
    assert.ok(text.includes('Sugar'));
  });
});

describe('RecipeConflict Model', () => {
  test('should create conflict record', () => {
    const conflict = RecipeConflict.create(
      'recipe-1',
      'merge-hash',
      'feature',
      'field',
      'title',
      'Base Title',
      'Target Title',
      'Source Title'
    );

    assert.strictEqual(conflict.recipeId, 'recipe-1');
    assert.strictEqual(conflict.conflictType, 'field');
    assert.strictEqual(conflict.resolution, 'pending');
  });

  test('should resolve conflict', () => {
    const conflict = new RecipeConflict({
      recipeId: 'r1',
      mergeCommitHash: 'm1',
      conflictType: 'field',
      fieldPath: 'title',
      targetValue: 'target',
      sourceValue: 'source'
    });

    conflict.resolve('manual value', 'manual');

    assert.strictEqual(conflict.resolvedValue, 'manual value');
    assert.strictEqual(conflict.resolution, 'manual');
    assert.strictEqual(conflict.isResolved(), true);
  });

  test('should get description', () => {
    const conflict = new RecipeConflict({
      conflictType: 'ingredient',
      fieldPath: 'ingredients.0'
    });

    assert.ok(conflict.getDescription().includes('Ingredient'));
  });
});
