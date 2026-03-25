/**
 * Version Routes
 * REST routes for /recipes/:id/versions endpoint
 */

const { Router } = require('../../utils/router');
const { success, error, created, notFound } = require('../../utils/response');
const VersionControlService = require('../../services/versionControlService');

function createVersionRoutes(db) {
  const router = new Router();
  const vcService = new VersionControlService(db);

  // Initialize tables on first request
  let initialized = false;
  const ensureInit = () => {
    if (!initialized) {
      vcService.initializeTables();
      initialized = true;
    }
  };

  /**
   * GET /recipes/:id/versions
   * Get version history for a recipe
   */
  router.get('/recipes/:id/versions', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { limit = 50, branch } = req.query;

      const commits = vcService.history(id, parseInt(limit), branch);

      res.json(success({
        recipeId: id,
        branch: branch || 'all',
        count: commits.length,
        commits: commits.map(c => ({
          hash: c.hash,
          shortHash: c.getShortHash(),
          message: c.message,
          author: c.author,
          branchName: c.branchName,
          isMerge: c.isMergeCommit(),
          parentCount: c.parentHashes.length,
          createdAt: c.createdAt
        }))
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * GET /recipes/:id/versions/:commitHash
   * Get a specific version
   */
  router.get('/recipes/:id/versions/:commitHash', (req, res) => {
    try {
      ensureInit();
      const { id, commitHash } = req.params;

      const result = vcService.checkout(id, commitHash);

      if (!result.success) {
        return res.status(404).json(notFound(result.error));
      }

      res.json(success({
        recipeId: id,
        commit: {
          hash: result.commit.hash,
          shortHash: result.commit.getShortHash(),
          message: result.commit.message,
          author: result.commit.author,
          branchName: result.commit.branchName,
          createdAt: result.commit.createdAt
        },
        recipe: result.recipe,
        branchName: result.branchName
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * POST /recipes/:id/versions
   * Create a new commit (version)
   */
  router.post('/recipes/:id/versions', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { recipe, message, author = 'system', branch = 'main' } = req.body;

      if (!recipe) {
        return res.status(400).json(error('recipe is required'));
      }
      if (!message) {
        return res.status(400).json(error('message is required'));
      }

      const result = vcService.commit(id, recipe, message, author, branch);

      res.status(201).json(created({
        recipeId: id,
        commit: {
          hash: result.hash,
          shortHash: result.commit.getShortHash(),
          message: result.commit.message,
          author: result.commit.author,
          branchName: result.commit.branchName,
          createdAt: result.commit.createdAt
        },
        version: {
          commitHash: result.version.commitHash,
          createdAt: result.version.createdAt
        }
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * GET /recipes/:id/versions/latest
   * Get the latest version
   */
  router.get('/recipes/:id/versions/latest', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { branch } = req.query;

      const commits = vcService.history(id, 1, branch);

      if (commits.length === 0) {
        return res.status(404).json(notFound('No versions found'));
      }

      const commit = commits[0];
      const result = vcService.checkout(id, commit.hash);

      if (!result.success) {
        return res.status(404).json(notFound(result.error));
      }

      res.json(success({
        recipeId: id,
        commit: {
          hash: commit.hash,
          shortHash: commit.getShortHash(),
          message: commit.message,
          author: commit.author,
          branchName: commit.branchName,
          createdAt: commit.createdAt
        },
        recipe: result.recipe
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  return router;
}

module.exports = createVersionRoutes;
