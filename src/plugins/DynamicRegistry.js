/**
 * DynamicRegistry - Runtime registration system for plugins
 *
 * This module challenges Stele-context because it creates symbol relationships
 * that are established DYNAMICALLY at runtime, not through static imports.
 * Stele's symbol graph relies on import statements - this breaks that assumption.
 */

const EventEmitter = require('events');

class DynamicRegistry extends EventEmitter {
  constructor() {
    super();
    // Dynamic registrations - these are NOT visible to static analysis
    this.registeredRoutes = new Map();     // pluginName -> [{method, path, handler}]
    this.registeredServices = new Map();   // pluginName -> {name, methods}
    this.registeredHooks = new Map();      // pluginName -> [{hook, handler}]
    this.registeredMiddlewares = new Map(); // pluginName -> [middlewareFn]
    this.routeHandlers = new Map();        // path -> handler (for dynamic lookup)
    this.serviceInstances = new Map();     // serviceName -> instance
  }

  /**
   * Register a route handler dynamically
   * This creates a runtime-only symbol relationship
   */
  registerRoute(pluginName, method, path, handler) {
    if (!this.registeredRoutes.has(pluginName)) {
      this.registeredRoutes.set(pluginName, []);
    }

    const route = { method: method.toUpperCase(), path, handler, pluginName };
    this.registeredRoutes.get(pluginName).push(route);

    // Also index by path for fast lookup
    const routeKey = `${method.toUpperCase()}:${path}`;
    this.routeHandlers.set(routeKey, { handler, pluginName });

    this.emit('route:registered', { pluginName, method, path });
  }

  /**
   * Register a service dynamically
   * Services are registered without static import statements
   */
  registerService(pluginName, serviceInstance) {
    const serviceName = serviceInstance.constructor.name;
    this.registeredServices.set(pluginName, {
      name: serviceName,
      instance: serviceInstance,
      methods: Object.getOwnPropertyNames(Object.getPrototypeOf(serviceInstance))
    });
    this.serviceInstances.set(serviceName, serviceInstance);

    this.emit('service:registered', { pluginName, serviceName });
  }

  /**
   * Register a hook handler dynamically
   */
  registerHook(pluginName, hookName, handler) {
    if (!this.registeredHooks.has(pluginName)) {
      this.registeredHooks.set(pluginName, []);
    }
    this.registeredHooks.get(pluginName).push({ hook: hookName, handler });
    this.emit('hook:registered', { pluginName, hookName });
  }

  /**
   * Register middleware dynamically
   */
  registerMiddleware(pluginName, middleware) {
    if (!this.registeredMiddlewares.has(pluginName)) {
      this.registeredMiddlewares.set(pluginName, []);
    }
    this.registeredMiddlewares.get(pluginName).push(middleware);
    this.emit('middleware:registered', { pluginName });
  }

  /**
   * Get all registered routes (for route matching)
   */
  getRoutes() {
    const routes = [];
    for (const [pluginName, routeList] of this.registeredRoutes) {
      routes.push(...routeList);
    }
    return routes;
  }

  /**
   * Get service by name (runtime lookup)
   */
  getService(serviceName) {
    return this.serviceInstances.get(serviceName);
  }

  /**
   * Get all services registered by a plugin
   */
  getServicesForPlugin(pluginName) {
    const service = this.registeredServices.get(pluginName);
    return service ? service.instance : null;
  }

  /**
   * Get all hooks for a specific hook name
   */
  getHookHandlers(hookName) {
    const handlers = [];
    for (const [pluginName, hooks] of this.registeredHooks) {
      const matching = hooks.filter(h => h.hook === hookName);
      handlers.push(...matching);
    }
    return handlers;
  }

  /**
   * Get all middleware for a plugin or all middleware
   */
  getMiddleware(pluginName = null) {
    if (pluginName) {
      return this.registeredMiddlewares.get(pluginName) || [];
    }
    const all = [];
    for (const [, mw] of this.registeredMiddlewares) {
      all.push(...mw);
    }
    return all;
  }

  /**
   * Unregister all entries for a plugin
   */
  unregisterPlugin(pluginName) {
    // Remove routes
    const routes = this.registeredRoutes.get(pluginName) || [];
    for (const route of routes) {
      const key = `${route.method}:${route.path}`;
      this.routeHandlers.delete(key);
    }
    this.registeredRoutes.delete(pluginName);

    // Remove services
    const service = this.registeredServices.get(pluginName);
    if (service) {
      this.serviceInstances.delete(service.name);
    }
    this.registeredServices.delete(pluginName);

    // Remove hooks
    this.registeredHooks.delete(pluginName);

    // Remove middleware
    this.registeredMiddlewares.delete(pluginName);

    this.emit('plugin:unregistered', { pluginName });
  }

  /**
   * Get registry stats (for debugging)
   */
  getStats() {
    return {
      totalRoutes: this.getRoutes().length,
      totalServices: this.serviceInstances.size,
      totalHooks: [...this.registeredHooks.values()].reduce((sum, h) => sum + h.length, 0),
      totalMiddleware: this.getMiddleware().length,
      plugins: [...this.registeredRoutes.keys()]
    };
  }
}

// Singleton instance
const registry = new DynamicRegistry();

module.exports = registry;
