/**
 * PluginMarketplace - Dynamic plugin discovery and management system
 *
 * CHALLENGES ALL THREE MCPS:
 *
 * STELE-CONTEXT:
 * - Dynamic plugin registration creates runtime symbol relationships
 * - Plugin metadata is semantic (descriptions, tags) that semantic search should find
 * - Cross-file symbol tracking through plugin hooks
 *
 * CHISEL:
 * - Plugin files are dynamically loaded (not through static imports)
 * - Plugin coupling is runtime-only, invisible to static analysis
 * - Partial coverage: core marketplace tested, plugins less so
 *
 * TRAMMEL:
 * - Plugin installation is a multi-step process with dependencies
 * - Plugin hooks create implicit ordering requirements
 * - Plugin ecosystem has ambiguous relationships
 */

const fs = require('fs');
const path = require('path');

class PluginMarketplace {
  constructor(pluginManager = null) {
    this.pluginManager = pluginManager;

    // Plugin registry - dynamic, not static imports
    this.plugins = new Map();
    this.pluginMetadata = new Map();
    this.dependencies = new Map();
    this.versions = new Map();

    // Marketplace state
    this.installedPlugins = new Set();
    this.activePlugins = new Set();
    this.pluginPaths = new Map();

    // Search index - semantic metadata
    this.searchIndex = new Map();
  }

  /**
   * Register a plugin from marketplace
   * This is DYNAMIC registration - no static import
   */
  registerPlugin(pluginInfo) {
    const {
      id,
      name,
      version,
      description,
      author,
      tags = [],
      dependencies = [],
      entryPoint,
      hooks = [],
      filePath
    } = pluginInfo;

    const metadata = {
      id,
      name,
      version,
      description,
      author,
      tags,
      dependencies,
      entryPoint,
      hooks,
      registeredAt: Date.now(),
      downloads: 0,
      rating: 0
    };

    this.plugins.set(id, metadata);
    this.pluginMetadata.set(id, metadata);
    this.dependencies.set(id, dependencies);
    this.versions.set(id, version);

    if (filePath) {
      this.pluginPaths.set(id, filePath);
    }

    // Build search index
    this.indexPlugin(id, metadata);

    return this;
  }

  /**
   * Index plugin for semantic search
   */
  indexPlugin(pluginId, metadata) {
    const searchEntry = {
      id: pluginId,
      terms: this.extractSearchTerms(metadata),
      tags: metadata.tags,
      description: metadata.description,
      name: metadata.name
    };

    this.searchIndex.set(pluginId, searchEntry);
  }

  /**
   * Extract searchable terms from metadata
   */
  extractSearchTerms(metadata) {
    const terms = new Set();

    // Add name words
    if (metadata.name) {
      metadata.name.toLowerCase().split(/[\s-_]/).forEach(t => terms.add(t));
    }

    // Add description words
    if (metadata.description) {
      metadata.description.toLowerCase()
        .split(/[\s,.!?]+/)
        .filter(w => w.length > 2)
        .forEach(t => terms.add(t));
    }

    // Add tags
    if (metadata.tags) {
      metadata.tags.forEach(t => terms.add(t.toLowerCase()));
    }

    return Array.from(terms);
  }

  /**
   * Search plugins semantically
   */
  search(query, options = {}) {
    const { limit = 10, tags = [] } = options;

    const queryTerms = query.toLowerCase().split(/[\s,.!?]+/).filter(w => w.length > 2);
    const results = [];

    for (const [pluginId, entry] of this.searchIndex) {
      // Calculate relevance score
      let score = 0;

      // Name match (highest weight)
      const nameLower = entry.name.toLowerCase();
      for (const term of queryTerms) {
        if (nameLower.includes(term)) {
          score += 10;
          if (nameLower.startsWith(term)) score += 5;
        }
      }

      // Tag match
      for (const tag of entry.tags) {
        for (const term of queryTerms) {
          if (tag.toLowerCase().includes(term)) {
            score += 5;
          }
        }
      }

      // Description match
      for (const term of queryTerms) {
        if (entry.description && entry.description.toLowerCase().includes(term)) {
          score += 2;
        }
        if (entry.terms.some(t => t.includes(term) || term.includes(t))) {
          score += 1;
        }
      }

      // Filter by tags if specified
      if (tags.length > 0) {
        const hasMatchingTag = tags.some(t =>
          entry.tags.map(tag => tag.toLowerCase()).includes(t.toLowerCase())
        );
        if (!hasMatchingTag) continue;
      }

      if (score > 0) {
        results.push({
          pluginId,
          name: entry.name,
          score,
          tags: entry.tags,
          description: entry.description
        });
      }
    }

    // Sort by score
    results.sort((a, b) => b.score - a.score);

    return results.slice(0, limit);
  }

  /**
   * Install a plugin
   */
  async install(pluginId) {
    const metadata = this.plugins.get(pluginId);
    if (!metadata) {
      return { success: false, error: 'Plugin not found' };
    }

    // Check dependencies
    const depCheck = this.checkDependencies(pluginId);
    if (!depCheck.satisfied) {
      return {
        success: false,
        error: 'Dependencies not met',
        missing: depCheck.missing
      };
    }

    // Load plugin dynamically
    const loadResult = await this.loadPlugin(pluginId);
    if (!loadResult.success) {
      return loadResult;
    }

    this.installedPlugins.add(pluginId);

    return {
      success: true,
      pluginId,
      installedAt: Date.now()
    };
  }

  /**
   * Load plugin dynamically from file
   * This creates RUNTIME coupling - invisible to static analysis
   */
  async loadPlugin(pluginId) {
    const filePath = this.pluginPaths.get(pluginId);

    if (!filePath) {
      // Plugin doesn't have a file, it's a virtual plugin
      return { success: true, virtual: true };
    }

    try {
      // Dynamic require - NOT visible through static import analysis!
      delete require.cache[require.resolve(filePath)];
      const plugin = require(filePath);

      // Initialize plugin
      if (typeof plugin.initialize === 'function') {
        await plugin.initialize(this.pluginManager);
      }

      // Register hooks if plugin has them
      if (plugin.hooks) {
        for (const [hookName, handler] of Object.entries(plugin.hooks)) {
          this.registerHook(pluginId, hookName, handler);
        }
      }

      return { success: true, plugin };

    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  }

  /**
   * Register a hook handler from a plugin
   */
  registerHook(pluginId, hookName, handler) {
    if (!this.hookHandlers) {
      this.hookHandlers = new Map();
    }

    if (!this.hookHandlers.has(hookName)) {
      this.hookHandlers.set(hookName, []);
    }

    this.hookHandlers.get(hookName).push({
      pluginId,
      handler,
      registeredAt: Date.now()
    });
  }

  /**
   * Activate a plugin
   */
  activate(pluginId) {
    if (!this.installedPlugins.has(pluginId)) {
      return { success: false, error: 'Plugin not installed' };
    }

    this.activePlugins.add(pluginId);

    return {
      success: true,
      pluginId,
      activatedAt: Date.now()
    };
  }

  /**
   * Deactivate a plugin
   */
  deactivate(pluginId) {
    this.activePlugins.delete(pluginId);

    return {
      success: true,
      pluginId,
      deactivatedAt: Date.now()
    };
  }

  /**
   * Uninstall a plugin
   */
  uninstall(pluginId) {
    // Check if other plugins depend on this one
    const dependents = this.findDependents(pluginId);
    if (dependents.length > 0) {
      return {
        success: false,
        error: 'Other plugins depend on this',
        dependents
      };
    }

    this.deactivate(pluginId);
    this.installedPlugins.delete(pluginId);

    return {
      success: true,
      pluginId,
      uninstalledAt: Date.now()
    };
  }

  /**
   * Check if plugin dependencies are met
   */
  checkDependencies(pluginId) {
    const deps = this.dependencies.get(pluginId) || [];
    const missing = [];

    for (const depId of deps) {
      if (!this.installedPlugins.has(depId)) {
        missing.push(depId);
      } else if (!this.activePlugins.has(depId)) {
        // Dependency is installed but not active
        missing.push(`${depId} (not active)`);
      }
    }

    return {
      satisfied: missing.length === 0,
      missing
    };
  }

  /**
   * Find plugins that depend on a given plugin
   */
  findDependents(pluginId) {
    const dependents = [];

    for (const [id, deps] of this.dependencies) {
      if (deps.includes(pluginId)) {
        dependents.push(id);
      }
    }

    return dependents;
  }

  /**
   * Get plugin by ID
   */
  getPlugin(pluginId) {
    return this.pluginMetadata.get(pluginId) || null;
  }

  /**
   * Get all plugins
   */
  getAllPlugins() {
    return Array.from(this.plugins.values());
  }

  /**
   * Get installed plugins
   */
  getInstalledPlugins() {
    return Array.from(this.installedPlugins).map(id => this.plugins.get(id));
  }

  /**
   * Get active plugins
   */
  getActivePlugins() {
    return Array.from(this.activePlugins).map(id => this.plugins.get(id));
  }

  /**
   * Get plugins by tag
   */
  getPluginsByTag(tag) {
    const results = [];

    for (const [id, metadata] of this.plugins) {
      if (metadata.tags.includes(tag)) {
        results.push(metadata);
      }
    }

    return results;
  }

  /**
   * Discover plugins from a directory
   */
  discoverPlugins(directory) {
    const discovered = [];

    const walk = (dir) => {
      try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });

        for (const entry of entries) {
          const fullPath = path.join(dir, entry.name);

          if (entry.isDirectory()) {
            // Check if this is a plugin directory
            const manifestPath = path.join(fullPath, 'plugin.json');
            if (fs.existsSync(manifestPath)) {
              try {
                const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
                discovered.push({
                  ...manifest,
                  filePath: fullPath
                });
              } catch {
                // Invalid manifest
              }
            } else {
              walk(fullPath);
            }
          }
        }
      } catch {
        // Skip inaccessible directories
      }
    };

    walk(directory);
    return discovered;
  }

  /**
   * Build dependency graph
   */
  buildDependencyGraph() {
    const graph = {
      nodes: [],
      edges: []
    };

    for (const [id, metadata] of this.plugins) {
      graph.nodes.push({
        id,
        name: metadata.name,
        version: metadata.version
      });

      const deps = this.dependencies.get(id) || [];
      for (const depId of deps) {
        graph.edges.push({
          from: id,
          to: depId,
          type: 'depends_on'
        });
      }
    }

    return graph;
  }

  /**
   * Topological sort of plugins (install order)
   */
  getInstallOrder(pluginIds) {
    const visited = new Set();
    const order = [];

    const visit = (pluginId) => {
      if (visited.has(pluginId)) return;
      visited.add(pluginId);

      const deps = this.dependencies.get(pluginId) || [];
      for (const dep of deps) {
        if (pluginIds.includes(dep)) {
          visit(dep);
        }
      }

      order.push(pluginId);
    };

    for (const pluginId of pluginIds) {
      visit(pluginId);
    }

    return order;
  }

  /**
   * Check for circular dependencies
   */
  detectCircularDependencies() {
    const cycles = [];
    const visited = new Set();
    const recursionStack = new Set();

    const detectCycle = (pluginId, path = []) => {
      if (recursionStack.has(pluginId)) {
        const cycleStart = path.indexOf(pluginId);
        cycles.push([...path.slice(cycleStart), pluginId]);
        return;
      }

      if (visited.has(pluginId)) return;

      visited.add(pluginId);
      recursionStack.add(pluginId);
      path.push(pluginId);

      const deps = this.dependencies.get(pluginId) || [];
      for (const dep of deps) {
        detectCycle(dep, [...path]);
      }

      recursionStack.delete(pluginId);
    };

    for (const pluginId of this.plugins.keys()) {
      detectCycle(pluginId, []);
    }

    return cycles;
  }

  /**
   * Get marketplace statistics
   */
  getStats() {
    return {
      totalPlugins: this.plugins.size,
      installedPlugins: this.installedPlugins.size,
      activePlugins: this.activePlugins.size,
      totalDownloads: Array.from(this.plugins.values())
        .reduce((sum, p) => sum + (p.downloads || 0), 0),
      averageRating: this.calculateAverageRating(),
      tagCounts: this.getTagCounts()
    };
  }

  calculateAverageRating() {
    const plugins = Array.from(this.plugins.values());
    if (plugins.length === 0) return 0;

    const total = plugins.reduce((sum, p) => sum + (p.rating || 0), 0);
    return total / plugins.length;
  }

  getTagCounts() {
    const counts = new Map();

    for (const metadata of this.plugins.values()) {
      for (const tag of metadata.tags) {
        counts.set(tag, (counts.get(tag) || 0) + 1);
      }
    }

    return Object.fromEntries(counts);
  }

  /**
   * Invoke a hook across all active plugins
   */
  async invokeHook(hookName, context) {
    const handlers = this.hookHandlers?.get(hookName) || [];
    let result = context;

    for (const { handler } of handlers) {
      try {
        if (typeof handler === 'function') {
          result = await handler(result) || result;
        }
      } catch (error) {
        // Log but continue
        console.error(`Hook ${hookName} error:`, error.message);
      }
    }

    return result;
  }
}

module.exports = PluginMarketplace;
