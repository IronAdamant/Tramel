/**
 * Relationship Analysis API Routes
 */

const express = require('express');
const router = express.Router();
const RelationshipAnalyzer = require('../../services/relationshipAnalyzer');

module.exports = (fileStore) => {
  const analyzer = new RelationshipAnalyzer(fileStore);

  /**
   * Analyze relationship between two recipes
   */
  router.post('/analyze', (req, res) => {
    try {
      const { recipeA, recipeB } = req.body;

      if (!recipeA || !recipeB) {
        return res.status(400).json({ error: 'recipeA and recipeB are required' });
      }

      const analysis = analyzer.analyzeRelationship(recipeA, recipeB);
      res.json(analysis);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Find related recipes for a given recipe
   */
  router.get('/related/:recipeId', (req, res) => {
    try {
      const { recipeId } = req.params;
      const { limit = 10, minConfidence = 0.3 } = req.query;

      const related = analyzer.findRelatedRecipes(recipeId, {
        limit: parseInt(limit),
        minConfidence: parseFloat(minConfidence)
      });

      res.json({ recipeId, related });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Build semantic graph for a recipe
   */
  router.get('/graph/:recipeId', (req, res) => {
    try {
      const { recipeId } = req.params;
      const { depth = 2, maxNodes = 50 } = req.query;

      const graph = analyzer.buildSemanticGraph(recipeId, {
        depth: parseInt(depth),
        maxNodes: parseInt(maxNodes)
      });

      res.json(graph);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Find relationship path between two recipes
   */
  router.get('/path/:recipeIdA/:recipeIdB', (req, res) => {
    try {
      const { recipeIdA, recipeIdB } = req.params;
      const { maxDepth = 4 } = req.query;

      const path = analyzer.findRelationshipPath(
        recipeIdA,
        recipeIdB,
        parseInt(maxDepth)
      );

      res.json(path);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Batch analyze multiple recipe pairs
   */
  router.post('/batch', (req, res) => {
    try {
      const { pairs } = req.body;

      if (!Array.isArray(pairs)) {
        return res.status(400).json({ error: 'pairs must be an array' });
      }

      const results = pairs.map(([recipeA, recipeB]) => {
        const analysis = analyzer.analyzeRelationship(recipeA, recipeB);
        return {
          recipeA: recipeA.id,
          recipeB: recipeB.id,
          analysis
        };
      });

      res.json({ results });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Clear analysis cache
   */
  router.post('/clear-cache', (req, res) => {
    try {
      const result = analyzer.clearCache();
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get relationship types
   */
  router.get('/types', (req, res) => {
    res.json({
      types: analyzer.relationshipTypes,
      description: 'Semantic relationship types used by the analyzer'
    });
  });

  return router;
};
