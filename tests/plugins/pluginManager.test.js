'use strict';

const { describe, test, assert, equal, deepEqual, ok } = require('../testRunner');
const { PluginManager, HOOKS } = require('../../src/plugins/PluginManager');

describe('PluginManager', () => {
  describe('constructor', () => {
    test('should initialize with empty plugins map', () => {
      const manager = new PluginManager();
      ok(manager.plugins.size === 0);
    });

    test('should initialize hookHandlers for all 18 hooks', () => {
      const manager = new PluginManager();
      equal(Object.keys(manager.hookHandlers).length, 18);
      HOOKS.forEach(hook => {
        deepEqual(manager.hookHandlers[hook], []);
      });
    });
  });

  describe('registerPlugin', () => {
    test('should register a valid plugin', () => {
      const manager = new PluginManager();
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate', 'afterCreate'],
        handler: () => {}
      };

      manager.registerPlugin(plugin);

      ok(manager.hasPlugin('testPlugin'));
      equal(manager.getPlugins().length, 1);
    });

    test('should add handler to correct hook arrays', () => {
      const manager = new PluginManager();
      const handler = () => {};
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate', 'afterCreate'],
        handler
      };

      manager.registerPlugin(plugin);

      ok(manager.hookHandlers['beforeCreate'].includes(handler));
      ok(manager.hookHandlers['afterCreate'].includes(handler));
    });

    test('should throw error for plugin without name', () => {
      const manager = new PluginManager();
      const plugin = {
        hooks: ['beforeCreate'],
        handler: () => {}
      };

      assert.throws(() => manager.registerPlugin(plugin), /Plugin must have name, hooks array, and handler function/);
    });

    test('should throw error for plugin without hooks', () => {
      const manager = new PluginManager();
      const plugin = {
        name: 'testPlugin',
        handler: () => {}
      };

      assert.throws(() => manager.registerPlugin(plugin), /Plugin must have name, hooks array, and handler function/);
    });

    test('should throw error for plugin without handler', () => {
      const manager = new PluginManager();
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate']
      };

      assert.throws(() => manager.registerPlugin(plugin), /Plugin must have name, hooks array, and handler function/);
    });
  });

  describe('unregisterPlugin', () => {
    test('should remove plugin and its handlers', () => {
      const manager = new PluginManager();
      const handler = () => {};
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate', 'afterCreate'],
        handler
      };

      manager.registerPlugin(plugin);
      const result = manager.unregisterPlugin('testPlugin');

      equal(result, true);
      ok(!manager.hasPlugin('testPlugin'));
      ok(!manager.hookHandlers['beforeCreate'].includes(handler));
    });

    test('should return false for non-existent plugin', () => {
      const manager = new PluginManager();
      const result = manager.unregisterPlugin('nonExistent');
      equal(result, false);
    });
  });

  describe('enablePlugin / disablePlugin', () => {
    test('should enable a disabled plugin', () => {
      const manager = new PluginManager();
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate'],
        handler: () => {},
        enabled: false
      };

      manager.registerPlugin(plugin);
      manager.enablePlugin('testPlugin');

      const retrieved = manager.plugins.get('testPlugin');
      equal(retrieved.enabled, true);
    });

    test('should disable an enabled plugin', () => {
      const manager = new PluginManager();
      const plugin = {
        name: 'testPlugin',
        hooks: ['beforeCreate'],
        handler: () => {}
      };

      manager.registerPlugin(plugin);
      manager.disablePlugin('testPlugin');

      const retrieved = manager.plugins.get('testPlugin');
      equal(retrieved.enabled, false);
    });
  });

  describe('dispatch', () => {
    test('should call all handlers for a hook', async () => {
      const manager = new PluginManager();
      let callCount = 0;
      const handler1 = async () => { callCount++; return 'result1'; };
      const handler2 = async () => { callCount++; return 'result2'; };

      manager.registerPlugin({ name: 'p1', hooks: ['beforeCreate'], handler: handler1 });
      manager.registerPlugin({ name: 'p2', hooks: ['beforeCreate'], handler: handler2 });

      await manager.dispatch('beforeCreate', { entityType: 'recipe' }, { name: 'Test' });

      equal(callCount, 2);
    });

    test('should return result from last handler', async () => {
      const manager = new PluginManager();
      const handler1 = async () => 'result1';
      const handler2 = async () => 'result2';

      manager.registerPlugin({ name: 'p1', hooks: ['beforeCreate'], handler: handler1 });
      manager.registerPlugin({ name: 'p2', hooks: ['beforeCreate'], handler: handler2 });

      const result = await manager.dispatch('beforeCreate', {});
      equal(result, 'result2');
    });

    test('should handle hooks with no handlers', async () => {
      const manager = new PluginManager();
      const result = await manager.dispatch('nonExistentHook', {});
      equal(result, undefined);
    });

    test('should call onError hook when handler throws', async () => {
      const manager = new PluginManager();
      let errorHandlerCalled = false;
      const errorHandler = async (ctx, error) => { errorHandlerCalled = true; };
      const failingHandler = async () => { throw new Error('Test error'); };

      manager.registerPlugin({ name: 'failing', hooks: ['beforeCreate'], handler: failingHandler });
      manager.registerPlugin({ name: 'errorHandler', hooks: ['onError'], handler: errorHandler });

      try {
        await manager.dispatch('beforeCreate', {});
        ok(false, 'Should have thrown');
      } catch (err) {
        equal(err.message, 'Test error');
      }
      ok(errorHandlerCalled);
    });
  });

  describe('dispatchSync', () => {
    test('should call handlers synchronously', () => {
      const manager = new PluginManager();
      let called = false;
      const handler = () => { called = true; };

      manager.registerPlugin({ name: 'syncTest', hooks: ['beforeCreate'], handler });
      manager.dispatchSync('beforeCreate', { entityType: 'recipe' });

      ok(called);
    });
  });

  describe('getPlugins', () => {
    test('should return array of all plugins', () => {
      const manager = new PluginManager();
      manager.registerPlugin({ name: 'p1', hooks: ['beforeCreate'], handler: () => {} });
      manager.registerPlugin({ name: 'p2', hooks: ['afterCreate'], handler: () => {} });

      const plugins = manager.getPlugins();

      equal(plugins.length, 2);
      ok(plugins.map(p => p.name).includes('p1'));
      ok(plugins.map(p => p.name).includes('p2'));
    });
  });

  describe('getPluginsForHook', () => {
    test('should return plugin names registered for a hook', () => {
      const manager = new PluginManager();
      manager.registerPlugin({ name: 'p1', hooks: ['beforeCreate', 'afterCreate'], handler: () => {} });
      manager.registerPlugin({ name: 'p2', hooks: ['beforeCreate'], handler: () => {} });
      manager.registerPlugin({ name: 'p3', hooks: ['afterCreate'], handler: () => {} });

      const pluginsForHook = manager.getPluginsForHook('beforeCreate');

      ok(pluginsForHook.includes('p1'));
      ok(pluginsForHook.includes('p2'));
      ok(!pluginsForHook.includes('p3'));
    });
  });

  describe('getAvailableHooks', () => {
    test('should return all 18 hook names', () => {
      const manager = new PluginManager();
      const hooks = manager.getAvailableHooks();
      equal(hooks.length, 18);
      ok(hooks.includes('beforeCreate'));
      ok(hooks.includes('onError'));
    });
  });

  describe('hasPlugin', () => {
    test('should return true for registered plugin', () => {
      const manager = new PluginManager();
      manager.registerPlugin({ name: 'test', hooks: ['beforeCreate'], handler: () => {} });
      ok(manager.hasPlugin('test'));
    });

    test('should return false for non-registered plugin', () => {
      const manager = new PluginManager();
      ok(!manager.hasPlugin('nonExistent'));
    });
  });

  describe('clear', () => {
    test('should remove all plugins and reset handlers', () => {
      const manager = new PluginManager();
      manager.registerPlugin({ name: 'p1', hooks: ['beforeCreate'], handler: () => {} });
      manager.registerPlugin({ name: 'p2', hooks: ['afterCreate'], handler: () => {} });

      manager.clear();

      equal(manager.plugins.size, 0);
      equal(manager.getPlugins().length, 0);
      deepEqual(manager.hookHandlers['beforeCreate'], []);
    });
  });
});

describe('HOOKS constant', () => {
  test('should have exactly 18 hooks', () => {
    equal(HOOKS.length, 18);
  });

  test('should contain all required hooks', () => {
    const requiredHooks = [
      'beforeCreate', 'afterCreate',
      'beforeUpdate', 'afterUpdate',
      'beforeDelete', 'afterDelete',
      'beforeSearch', 'afterSearch',
      'beforeScale', 'afterScale',
      'beforeExport', 'afterExport',
      'onAllergenDetected',
      'onNutrientCalculated',
      'onMealPlanGenerated',
      'onShoppingListGenerated',
      'onRecipeRated',
      'onError'
    ];

    requiredHooks.forEach(hook => {
      ok(HOOKS.includes(hook), `Missing hook: ${hook}`);
    });
  });
});
