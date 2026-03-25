/**
 * Diff Routes
 * REST routes for /recipes/:id/diff endpoint
 */

const { Router } = require('../../utils/router');
const { success, error, notFound } = require('../../utils/response');
const VersionControlService = require('../../services/versionControlService');
const DiffService = require('../../services/diffService');

function createDiffRoutes(db) {
  const router = new Router();
  const vcService = new VersionControlService(db);
  const diffService = new DiffService();

  // Initialize tables on first request
  let initialized = false;
  const ensureInit = () => {
    if (!initialized) {
      vcService.initializeTables();
      initialized = true;
    }
  };

  /**
   * GET /recipes/:id/diff
   * Get diff between two commits
   */
  router.get('/recipes/:id/diff', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { from, to, format = 'json' } = req.query;

      if (!from || !to) {
        return res.status(400).json(error('Both "from" and "to" commit hashes are required'));
      }

      const result = vcService.diff(id, from, to);

      if (!result.success) {
        return res.status(404).json(notFound(result.error));
      }

      if (format === 'text') {
        const textOutput = diffService.formatDiff(result.ingredients, 'text');
        return res.json(success({
          recipeId: id,
          from: {
            hash: from,
            shortHash: from.substring(0, 7)
          },
          to: {
            hash: to,
            shortHash: to.substring(0, 7)
          },
          format: 'text',
          text: textOutput,
          summary: {
            added: result.ingredients.added.length,
            removed: result.ingredients.removed.length,
            modified: result.ingredients.modified.length,
            fieldChanges: result.fields.length
          }
        }));
      }

      res.json(success({
        recipeId: id,
        from: {
          hash: from,
          shortHash: from.substring(0, 7)
        },
        to: {
          hash: to,
          shortHash: to.substring(0, 7)
        },
        format: 'json',
        ingredients: {
          added: result.ingredients.added,
          removed: result.ingredients.removed,
          modified: result.ingredients.modified
        },
        fields: result.fields,
        instructions: result.instructions,
        summary: {
          added: result.ingredients.added.length,
          removed: result.ingredients.removed.length,
          modified: result.ingredients.modified.length,
          fieldChanges: result.fields.length
        }
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * GET /recipes/:id/diff/commits
   * Get all commits for diff selection
   */
  router.get('/recipes/:id/diff/commits', (req, res) => {
    try {
      ensureInit();
      const { id } = req.params;
      const { limit = 20 } = req.query;

      const commits = vcService.history(id, parseInt(limit));

      res.json(success({
        recipeId: id,
        count: commits.length,
        commits: commits.map(c => ({
          hash: c.hash,
          shortHash: c.getShortHash(),
          message: c.message,
          author: c.author,
          branchName: c.branchName,
          createdAt: c.createdAt
        }))
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  /**
   * POST /recipes/:id/diff/ingredients
   * Diff two sets of ingredients directly (no commits needed)
   */
  router.post('/recipes/:id/diff/ingredients', (req, res) => {
    try {
      const { id } = req.params;
      const { ingredients1, ingredients2, format = 'json' } = req.body;

      if (!ingredients1 || !ingredients2) {
        return res.status(400).json(error('Both ingredients1 and ingredients2 are required'));
      }

      const diff = diffService.diff(ingredients1, ingredients2);

      if (format === 'text') {
        return res.json(success({
          recipeId: id,
          format: 'text',
          text: diffService.formatDiff(diff, 'text')
        }));
      }

      res.json(success({
        recipeId: id,
        format: 'json',
        diff
      }));
    } catch (err) {
      res.status(500).json(error(err.message));
    }
  });

  return router;
}

module.exports = createDiffRoutes;
