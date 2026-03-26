/**
 * Tests for DynamicRegistry - Runtime registration system
 *
 * These tests challenge Stele-context because:
 * 1. They test runtime symbol resolution (getService by name)
 * 2. They verify dynamic route registration without static imports
 * 3. They test cross-plugin communication at runtime
 */

const { describe, test, assert, equal, deepEqual, ok } = require('../testRunner');
const DynamicRegistry = require('../../src/plugins/DynamicRegistry');

describe('DynamicRegistry', () => {
  let registry;

  beforeEach(() => {
    registry = new DynamicRegistry();
  });

  describe('route registration', () => {
    test('should register routes dynamically', () => {
      const handler = (req, res) => ({ ok: true });
      registry.registerRoute('test-plugin', 'GET', '/api/test', handler);

      const routes = registry.getRoutes();
      expect(routes).toHaveLength(1);
      expect(routes[0].path).toBe('/api/test');
      expect(routes[0].method).toBe('GET');
      expect(routes[0].pluginName).toBe('test-plugin');
    });

    it('should register multiple routes for same plugin', () => {
      registry.registerRoute('test-plugin', 'GET', '/api/test1', () => {});
      registry.registerRoute('test-plugin', 'POST', '/api/test2', () => {});

      const routes = registry.getRoutes();
      expect(routes).toHaveLength(2);
    });

    it('should allow route lookup by path', () => {
      const handler = (req, res) => ({ ok: true });
      registry.registerRoute('test-plugin', 'GET', '/api/lookup', handler);

      const routeKey = 'GET:/api/lookup';
      const found = registry.routeHandlers.get(routeKey);
      expect(found).toBeDefined();
      expect(found.handler).toBe(handler);
      expect(found.pluginName).toBe('test-plugin');
    });
  });

  describe('service registration', () => {
    it('should register services dynamically', () => {
      class TestService {
        getData() { return 'data'; }
      }

      const service = new TestService();
      registry.registerService('test-plugin', service);

      const retrieved = registry.getService('TestService');
      expect(retrieved).toBe(service);
    });

    it('should track service methods', () => {
      class TestService {
        getData() { return 'data'; }
        setData(data) { this.data = data; }
      }

      registry.registerService('test-plugin', new TestService());

      const entry = registry.registeredServices.get('test-plugin');
      expect(entry.methods).toContain('getData');
      expect(entry.methods).toContain('setData');
    });
  });

  describe('hook registration', () => {
    it('should register hooks dynamically', () => {
      const handler = async (context) => context;
      registry.registerHook('test-plugin', 'beforeSearch', handler);

      const handlers = registry.getHookHandlers('beforeSearch');
      expect(handlers).toHaveLength(1);
      expect(handlers[0].handler).toBe(handler);
      expect(handlers[0].pluginName).toBe('test-plugin');
    });

    it('should get handlers for specific hook', () => {
      registry.registerHook('plugin1', 'beforeSearch', () => 1);
      registry.registerHook('plugin2', 'beforeSearch', () => 2);
      registry.registerHook('plugin1', 'afterSearch', () => 3);

      const beforeHandlers = registry.getHookHandlers('beforeSearch');
      expect(beforeHandlers).toHaveLength(2);
    });
  });

  describe('middleware registration', () => {
    it('should register middleware', () => {
      const mw1 = (req, res, next) => next();
      const mw2 = (req, res, next) => next();

      registry.registerMiddleware('test-plugin', mw1);
      registry.registerMiddleware('test-plugin', mw2);

      const middleware = registry.getMiddleware('test-plugin');
      expect(middleware).toHaveLength(2);
    });

    it('should get all middleware', () => {
      registry.registerMiddleware('plugin1', (req, res, next) => next());
      registry.registerMiddleware('plugin2', (req, res, next) => next());

      const all = registry.getMiddleware();
      expect(all).toHaveLength(2);
    });
  });

  describe('plugin unregistration', () => {
    it('should remove all plugin entries on unregister', () => {
      registry.registerRoute('test-plugin', 'GET', '/api/test', () => {});
      registry.registerService('test-plugin', { constructor: { name: 'TestService' } });
      registry.registerHook('test-plugin', 'beforeSearch', () => {});
      registry.registerMiddleware('test-plugin', (req, res, next) => next());

      registry.unregisterPlugin('test-plugin');

      expect(registry.getRoutes()).toHaveLength(0);
      expect(registry.getHookHandlers('beforeSearch')).toHaveLength(0);
      expect(registry.getMiddleware('test-plugin')).toHaveLength(0);
    });
  });

  describe('events', () => {
    it('should emit events on registration', (done) => {
      registry.on('route:registered', (data) => {
        expect(data.pluginName).toBe('test-plugin');
        expect(data.path).toBe('/api/test');
        done();
      });

      registry.registerRoute('test-plugin', 'GET', '/api/test', () => {});
    });

    it('should emit events on service registration', (done) => {
      registry.on('service:registered', (data) => {
        expect(data.pluginName).toBe('test-plugin');
        expect(data.serviceName).toBe('TestService');
        done();
      });

      registry.registerService('test-plugin', { constructor: { name: 'TestService' } });
    });
  });

  describe('stats', () => {
    it('should return accurate registry stats', () => {
      registry.registerRoute('p1', 'GET', '/a', () => {});
      registry.registerRoute('p1', 'POST', '/b', () => {});
      registry.registerService('p1', { constructor: { name: 'S1' } });
      registry.registerHook('p2', 'beforeSearch', () => {});

      const stats = registry.getStats();
      expect(stats.totalRoutes).toBe(2);
      expect(stats.totalServices).toBe(1);
      expect(stats.totalHooks).toBe(1);
      expect(stats.plugins).toContain('p1');
      expect(stats.plugins).toContain('p2');
    });
  });
});
