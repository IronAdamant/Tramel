/**
 * DynamicPluginManager - Extended plugin system with runtime registration
 *
 * Extends the base PluginManager with dynamic route/service registration.
 * This is the PRIMARY challenge for Stele-context because:
 * 1. Routes registered via this system are NOT connected through static imports
 * 2. Service methods are resolved at runtime, not through static analysis
 * 3. Symbol references cross plugin boundaries dynamically
 */

const PluginManager = require('./PluginManager');
const dynamicRegistry = require('./DynamicRegistry');

class DynamicPluginManager extends PluginManager {
  constructor() {
    super();
    this.dynamicEnabled = true;
  }

  /**
   * Register a plugin with FULL dynamic capabilities
   * Routes, services, and hooks are all registered dynamically
   */
  registerPlugin(plugin) {
    // Call parent registration for hooks
    super.registerPlugin(plugin);

    // If plugin has routes, register them dynamically
    if (plugin.routes) {
      plugin.routes.forEach(route => {
        dynamicRegistry.registerRoute(
          plugin.name,
          route.method || 'GET',
          route.path,
          route.handler
        );
      });
    }

    // If plugin has a service, register it dynamically
    if (plugin.service) {
      dynamicRegistry.registerService(plugin.name, plugin.service);
    }

    // If plugin has custom middleware
    if (plugin.middleware && Array.isArray(plugin.middleware)) {
      plugin.middleware.forEach(mw => {
        dynamicRegistry.registerMiddleware(plugin.name, mw);
      });
    }

    // Additional dynamic hooks for plugin lifecycle
    if (plugin.onRegister) {
      plugin.onRegister(dynamicRegistry);
    }
  }

  /**
   * Create a dynamic route handler that invokes registered plugin services
   * This creates a runtime call chain: route -> pluginService -> dynamic method
   */
  createDynamicHandler(serviceName, methodName) {
    return async (req, res, ...args) => {
      const service = dynamicRegistry.getService(serviceName);
      if (!service) {
        return { error: `Service ${serviceName} not found` };
      }

      // Get the method - this is a RUNTIME symbol resolution
      const method = service[methodName];
      if (typeof method !== 'function') {
        return { error: `Method ${methodName} not found on ${serviceName}` };
      }

      // Invoke the method with request context
      return method.call(service, req, ...args);
    };
  }

  /**
   * Get all dynamic routes from all plugins
   */
  getDynamicRoutes() {
    return dynamicRegistry.getRoutes();
  }

  /**
   * Get a dynamic service by name
   */
  getDynamicService(name) {
    return dynamicRegistry.getService(name);
  }

  /**
   * Invoke a hook across all registered plugins
   */
  async invokeDynamicHook(hookName, context) {
    const handlers = dynamicRegistry.getHookHandlers(hookName);
    const results = [];

    for (const { handler, pluginName } of handlers) {
      try {
        // Check if plugin is enabled
        const plugin = this.plugins.get(pluginName);
        if (plugin && plugin.enabled) {
          const result = await Promise.resolve(handler(context));
          results.push({ plugin: pluginName, success: true, result });
        }
      } catch (error) {
        results.push({ plugin: pluginName, success: false, error: error.message });
      }
    }

    return results;
  }
}

module.exports = new DynamicPluginManager();
