/**
 * Plugin Marketplace API Routes
 */

const express = require('express');
const router = express.Router();
const PluginMarketplace = require('../../services/pluginMarketplace');

module.exports = (fileStore, pluginManager) => {
  const marketplace = new PluginMarketplace(pluginManager);

  /**
   * Register a plugin
   */
  router.post('/plugins', (req, res) => {
    try {
      const pluginInfo = req.body;

      if (!pluginInfo.id || !pluginInfo.name) {
        return res.status(400).json({ error: 'id and name are required' });
      }

      marketplace.registerPlugin(pluginInfo);
      res.json({ success: true, pluginId: pluginInfo.id });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Search plugins
   */
  router.get('/search', (req, res) => {
    try {
      const { q, limit = 10, tags } = req.query;

      if (!q) {
        return res.status(400).json({ error: 'q (query) is required' });
      }

      const results = marketplace.search(q, {
        limit: parseInt(limit),
        tags: tags ? tags.split(',') : []
      });

      res.json({ results });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Install a plugin
   */
  router.post('/plugins/:pluginId/install', async (req, res) => {
    try {
      const result = await marketplace.install(req.params.pluginId);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Activate a plugin
   */
  router.post('/plugins/:pluginId/activate', (req, res) => {
    try {
      const result = marketplace.activate(req.params.pluginId);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Deactivate a plugin
   */
  router.post('/plugins/:pluginId/deactivate', (req, res) => {
    try {
      const result = marketplace.deactivate(req.params.pluginId);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Uninstall a plugin
   */
  router.post('/plugins/:pluginId/uninstall', (req, res) => {
    try {
      const result = marketplace.uninstall(req.params.pluginId);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get plugin details
   */
  router.get('/plugins/:pluginId', (req, res) => {
    try {
      const plugin = marketplace.getPlugin(req.params.pluginId);

      if (!plugin) {
        return res.status(404).json({ error: 'Plugin not found' });
      }

      res.json(plugin);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * List all plugins
   */
  router.get('/plugins', (req, res) => {
    try {
      const { filter } = req.query;

      let plugins;
      switch (filter) {
        case 'installed':
          plugins = marketplace.getInstalledPlugins();
          break;
        case 'active':
          plugins = marketplace.getActivePlugins();
          break;
        default:
          plugins = marketplace.getAllPlugins();
      }

      res.json({ plugins });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get plugins by tag
   */
  router.get('/tags/:tag/plugins', (req, res) => {
    try {
      const plugins = marketplace.getPluginsByTag(req.params.tag);
      res.json({ plugins });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get marketplace stats
   */
  router.get('/stats', (req, res) => {
    try {
      const stats = marketplace.getStats();
      res.json(stats);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get dependency graph
   */
  router.get('/graph', (req, res) => {
    try {
      const graph = marketplace.buildDependencyGraph();
      res.json(graph);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get install order
   */
  router.post('/order', (req, res) => {
    try {
      const { pluginIds } = req.body;

      if (!Array.isArray(pluginIds)) {
        return res.status(400).json({ error: 'pluginIds must be an array' });
      }

      const order = marketplace.getInstallOrder(pluginIds);
      res.json({ order });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Check circular dependencies
   */
  router.get('/cycles', (req, res) => {
    try {
      const cycles = marketplace.detectCircularDependencies();
      res.json({ cycles });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Discover plugins from directory
   */
  router.post('/discover', (req, res) => {
    try {
      const { directory } = req.body;

      if (!directory) {
        return res.status(400).json({ error: 'directory is required' });
      }

      const discovered = marketplace.discoverPlugins(directory);
      res.json({ discovered });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Invoke a hook
   */
  router.post('/hooks/:hookName', async (req, res) => {
    try {
      const context = req.body || {};
      const result = await marketplace.invokeHook(req.params.hookName, context);
      res.json({ result });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
};
