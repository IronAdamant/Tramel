/**
 * PluginManager - Registry and hook dispatcher for RecipeLab plugin system
 * Manages plugin registration and dispatches events to registered hooks
 */

const HOOKS = [
  'beforeCreate', 'afterCreate',      // Entity creation
  'beforeUpdate', 'afterUpdate',        // Entity updates
  'beforeDelete', 'afterDelete',        // Entity deletion
  'beforeSearch', 'afterSearch',         // Search operations
  'beforeScale', 'afterScale',           // Recipe scaling
  'beforeExport', 'afterExport',         // Export operations
  'onAllergenDetected',                  // Allergen detection
  'onNutrientCalculated',                // Nutrition calculation
  'onMealPlanGenerated',                 // Meal plan generation
  'onShoppingListGenerated',             // Shopping list generation
  'onRecipeRated',                       // Recipe rating
  'onError'                              // Error handling
];

class PluginManager {
  constructor() {
    this.plugins = new Map(); // name -> { hooks: [], handler: function, enabled: bool }
    this.hookHandlers = {};   // hookName -> [handlers]
    this.initializeHookHandlers();
  }

  /**
   * Initialize empty handler arrays for all known hooks
   */
  initializeHookHandlers() {
    HOOKS.forEach(hook => {
      this.hookHandlers[hook] = [];
    });
  }

  /**
   * Register a plugin with the manager
   * @param {Object} plugin - Plugin object with name, hooks array, and handler function
   * @param {string} plugin.name - Unique plugin name
   * @param {string[]} plugin.hooks - Array of hook names to subscribe to
   * @param {Function} plugin.handler - Handler function called when hook fires
   */
  registerPlugin(plugin) {
    if (!plugin.name || !plugin.hooks || !plugin.handler) {
      throw new Error('Plugin must have name, hooks array, and handler function');
    }

    const pluginEntry = {
      name: plugin.name,
      hooks: plugin.hooks,
      handler: plugin.handler,
      enabled: plugin.enabled !== false
    };

    this.plugins.set(plugin.name, pluginEntry);

    // Register handler for each hook
    plugin.hooks.forEach(hook => {
      if (!this.hookHandlers[hook]) {
        this.hookHandlers[hook] = [];
      }
      if (typeof plugin.handler === 'function') {
        this.hookHandlers[hook].push(plugin.handler);
      }
    });
  }

  /**
   * Unregister a plugin by name
   * @param {string} name - Plugin name to unregister
   * @returns {boolean} True if plugin was found and removed
   */
  unregisterPlugin(name) {
    const plugin = this.plugins.get(name);
    if (!plugin) return false;

    // Remove handlers for each hook
    plugin.hooks.forEach(hook => {
      if (this.hookHandlers[hook]) {
        this.hookHandlers[hook] = this.hookHandlers[hook].filter(h => h !== plugin.handler);
      }
    });

    this.plugins.delete(name);
    return true;
  }

  /**
   * Enable a plugin by name
   * @param {string} name - Plugin name to enable
   */
  enablePlugin(name) {
    const plugin = this.plugins.get(name);
    if (plugin) {
      plugin.enabled = true;
    }
  }

  /**
   * Disable a plugin by name
   * @param {string} name - Plugin name to disable
   */
  disablePlugin(name) {
    const plugin = this.plugins.get(name);
    if (plugin) {
      plugin.enabled = false;
    }
  }

  /**
   * Dispatch a hook to all registered handlers
   * @param {string} hook - Hook name
   * @param {Object} context - Context object passed to handlers
   * @param {...*} args - Additional arguments passed to handlers
   * @returns {*} Result from the last handler
   */
  async dispatch(hook, context = {}, ...args) {
    const handlers = this.hookHandlers[hook] || [];
    let result;

    for (const handler of handlers) {
      try {
        result = await handler({ ...context, hook }, ...args);
      } catch (error) {
        // Dispatch to onError hook if this isn't already an onError hook
        if (hook !== 'onError') {
          await this.dispatch('onError', { ...context, hook }, error);
        }
        throw error;
      }
    }

    return result;
  }

  /**
   * Dispatch a hook synchronously (no async handlers)
   * @param {string} hook - Hook name
   * @param {Object} context - Context object passed to handlers
   * @param {...*} args - Additional arguments passed to handlers
   * @returns {*} Result from the last handler
   */
  dispatchSync(hook, context = {}, ...args) {
    const handlers = this.hookHandlers[hook] || [];
    let result;

    for (const handler of handlers) {
      try {
        result = handler({ ...context, hook }, ...args);
      } catch (error) {
        if (hook !== 'onError') {
          this.dispatch('onError', { ...context, hook }, error).catch(() => {});
        }
        throw error;
      }
    }

    return result;
  }

  /**
   * Get all registered plugins
   * @returns {Array} Array of plugin objects
   */
  getPlugins() {
    return Array.from(this.plugins.values());
  }

  /**
   * Get plugins registered for a specific hook
   * @param {string} hook - Hook name
   * @returns {Array} Array of plugin names
   */
  getPluginsForHook(hook) {
    return Array.from(this.plugins.values())
      .filter(p => p.hooks.includes(hook))
      .map(p => p.name);
  }

  /**
   * Get all available hook names
   * @returns {string[]} Array of hook names
   */
  getAvailableHooks() {
    return [...HOOKS];
  }

  /**
   * Check if a plugin is registered
   * @param {string} name - Plugin name
   * @returns {boolean}
   */
  hasPlugin(name) {
    return this.plugins.has(name);
  }

  /**
   * Clear all registered plugins
   */
  clear() {
    this.plugins.clear();
    this.initializeHookHandlers();
  }
}

// Export singleton instance and class for testing
module.exports = { PluginManager, HOOKS };
