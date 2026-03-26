/**
 * Coupling Explorer API Routes
 */

const express = require('express');
const router = express.Router();
const CouplingExplorer = require('../../services/couplingExplorer');

module.exports = (fileStore) => {
  const explorer = new CouplingExplorer();

  /**
   * Register a module
   */
  router.post('/modules', (req, res) => {
    try {
      const { moduleId, path, dependencies, exports } = req.body;

      explorer.registerModule(moduleId, { path, dependencies, exports });

      res.json({ success: true, moduleId });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Register dynamic dependency
   */
  router.post('/modules/:moduleId/dependencies', (req, res) => {
    try {
      const { moduleId } = req.params;
      const { dependency } = req.body;

      explorer.registerDynamicDependency(moduleId, dependency);

      res.json({ success: true });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get module coupling report
   */
  router.get('/modules/:moduleId', (req, res) => {
    try {
      const report = explorer.getModuleCouplingReport(req.params.moduleId);
      res.json(report);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get system coupling metrics
   */
  router.get('/system', (req, res) => {
    try {
      const metrics = explorer.getSystemCouplingMetrics();
      res.json(metrics);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get complete system analysis
   */
  router.get('/analysis', (req, res) => {
    try {
      const analysis = explorer.getSystemAnalysis();
      res.json(analysis);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Detect circular dependencies
   */
  router.get('/cycles', (req, res) => {
    try {
      const cycles = explorer.detectCircularDependencies();
      res.json({ cycles });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get strongly connected components
   */
  router.get('/scc', (req, res) => {
    try {
      const sccs = explorer.findStronglyConnectedComponents();
      res.json({ sccs });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get affected modules
   */
  router.get('/modules/:moduleId/affected', (req, res) => {
    try {
      const affected = explorer.getAffectedModules(req.params.moduleId);
      res.json({ affected });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Analyze file imports
   */
  router.post('/analyze', (req, res) => {
    try {
      const { filePath } = req.body;

      if (!filePath) {
        return res.status(400).json({ error: 'filePath is required' });
      }

      const analysis = explorer.analyzeFileImports(filePath);
      res.json(analysis);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Build import graph from directory
   */
  router.post('/discover', (req, res) => {
    try {
      const { directory, extensions } = req.body;

      if (!directory) {
        return res.status(400).json({ error: 'directory is required' });
      }

      const graph = explorer.buildImportGraphFromDirectory(
        directory,
        extensions || ['.js']
      );

      res.json({ graph });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Reset explorer state
   */
  router.post('/reset', (req, res) => {
    try {
      explorer.reset();
      res.json({ success: true });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
};
