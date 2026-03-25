/**
 * Branch Routes
 * REST routes for /recipes/:id/branches endpoint
 */

const { Router } = require('../../utils/router');
const { success, error, created, notFound } = require('../../utils/response');
const VersionControlService = require('../../services/versionControlService');

function createBranchRoutes(db) {
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
   * GET /recipes/:id/branches
   * Get all branches for a recipe
   */
  router.get('/recipes/:id/branches', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;

      const branches = vcService.getBranches(id);
      const currentBranch = vcService.getCurrentBranch(id);

      res.json(success({
        recipeId: id,
        currentBranch,
        count: branches.length,
        branches: branches.map(b => ({
          name: b.name,
          headCommitHash: b.headCommitHash,
          shortHeadHash: b.headCommitHash ? b.headCommitHash.substring(0, 7) : null,
          baseCommitHash: b.baseCommitHash,
          isActive: b.isActive,
          createdAt: b.createdAt,
          updatedAt: b.updatedAt
        }))
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * GET /recipes/:id/branches/:name
   * Get a specific branch
   */
  router.get('/recipes/:id/branches/:name', (req, res) => {
    try {
      ensureInit();
      const { id, name } = req.params;

      const branch = vcService.getBranch(id, name);

      if (!branch) {
        return res.status(404).json(notFound(`Branch '${name}' not found`));
      }

      const commits = vcService.getCommitsForBranch(id, name);

      res.json(success({
        recipeId: id,
        branch: {
          name: branch.name,
          headCommitHash: branch.headCommitHash,
          shortHeadHash: branch.headCommitHash.substring(0, 7),
          baseCommitHash: branch.baseCommitHash,
          isActive: branch.isActive,
          createdAt: branch.createdAt,
          updatedAt: branch.updatedAt
        },
        commitCount: commits.length,
        recentCommits: commits.slice(0, 10).map(c => ({
          hash: c.hash,
          shortHash: c.getShortHash(),
          message: c.message,
          author: c.author,
          createdAt: c.createdAt
        }))
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * POST /recipes/:id/branches
   * Create a new branch
   */
  router.post('/recipes/:id/branches', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { name, fromBranch } = req.body;

      if (!name) {
        return res.status(400).json(error('branch name is required'));
      }

      const result = vcService.branch(id, name, fromBranch);

      if (!result.success) {
        return res.status(400).json(error(result.error));
      }

      res.status(201).json(created({
        recipeId: id,
        branch: {
          name: result.branch.name,
          headCommitHash: result.branch.headCommitHash,
          shortHeadHash: result.branch.headCommitHash.substring(0, 7),
          createdAt: result.branch.createdAt
        },
        fromCommit: result.fromCommit ? {
          hash: result.fromCommit.hash,
          shortHash: result.fromCommit.getShortHash(),
          message: result.fromCommit.message
        } : null
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * DELETE /recipes/:id/branches/:name
   * Delete a branch
   */
  router.delete('/recipes/:id/branches/:name', (req, res) => {
    try {
      ensureInit();
      const { id, name } = req.params;

      const result = vcService.deleteBranch(id, name);

      if (!result.success) {
        return res.status(400).json(error(result.error));
      }

      res.json(success({
        recipeId: id,
        deletedBranch: name,
        message: `Branch '${name}' deleted successfully`
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * POST /recipes/:id/branches/:name/merge
   * Merge another branch into this branch
   */
  router.post('/recipes/:id/branches/:name/merge', (req, res) => {
    try {
      ensureInit();
      const { id, name } = req.params;
      const { fromBranch } = req.body;

      if (!fromBranch) {
        return res.status(400).json(error('source branch (fromBranch) is required'));
      }

      const result = vcService.merge(id, fromBranch, name);

      if (!result.success) {
        if (result.hasConflicts) {
          return res.status(409).json({
            success: false,
            hasConflicts: true,
            message: 'Merge completed with conflicts',
            commit: {
              hash: result.commit.hash,
              shortHash: result.commit.getShortHash(),
              message: result.commit.message,
              createdAt: result.commit.createdAt
            },
            conflicts: result.conflicts.map(c => ({
              type: c.type,
              field: c.fieldPath,
              base: c.baseValue,
              target: c.targetValue,
              source: c.sourceValue
            })),
            partialResult: result.partialResult
          });
        }
        return res.status(400).json(error(result.error));
      }

      res.json(success({
        recipeId: id,
        merge: {
          success: true,
          commit: {
            hash: result.commit.hash,
            shortHash: result.commit.getShortHash(),
            message: result.commit.message,
            author: result.commit.author,
            createdAt: result.commit.createdAt
          },
          targetBranch: name,
          sourceBranch: fromBranch
        },
        result: result.result
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  return router;
}

module.exports = createBranchRoutes;
