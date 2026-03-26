/**
 * Tests for PluginMarketplace
 */

'use strict';

const { describe, test, assert } = require('../testRunner');
const PluginMarketplace = require('../../src/services/pluginMarketplace');

describe('PluginMarketplace', () => {
  let marketplace;

  test('should register a plugin', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Test Plugin',
      version: '1.0.0',
      description: 'A test plugin',
      author: 'Tester',
      tags: ['test', 'utility']
    });

    assert.ok(marketplace.plugins.has('test-plugin'), 'Plugin should be registered');
  });

  test('should store plugin metadata', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Test Plugin',
      version: '1.0.0',
      description: 'A test plugin',
      author: 'Tester',
      tags: ['test']
    });

    const metadata = marketplace.getPlugin('test-plugin');

    assert.equal(metadata.name, 'Test Plugin');
    assert.equal(metadata.version, '1.0.0');
    assert.equal(metadata.author, 'Tester');
  });

  test('should build search index', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Nutrition Logger',
      description: 'Logs nutrition information',
      tags: ['nutrition', 'logging']
    });

    const searchEntry = marketplace.searchIndex.get('test-plugin');

    assert.ok(searchEntry.terms.includes('nutrition'), 'Should index nutrition');
    assert.ok(searchEntry.terms.includes('logger'), 'Should index logger');
  });

  test('should find plugins by name', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'plugin-a',
      name: 'Nutrition Logger',
      description: 'Logs nutrition data',
      tags: ['nutrition']
    });

    marketplace.registerPlugin({
      id: 'plugin-b',
      name: 'Allergen Checker',
      description: 'Checks for allergens',
      tags: ['allergen']
    });

    const results = marketplace.search('Nutrition');

    assert.ok(results.length > 0);
    assert.equal(results[0].name, 'Nutrition Logger');
  });

  test('should find plugins by description', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'plugin-a',
      name: 'Nutrition Logger',
      description: 'Logs nutrition data',
      tags: ['nutrition']
    });

    marketplace.registerPlugin({
      id: 'plugin-b',
      name: 'Allergen Checker',
      description: 'Checks for allergens',
      tags: ['allergen']
    });

    const results = marketplace.search('allergen');

    assert.ok(results.some(r => r.name === 'Allergen Checker'));
  });

  test('should sort by relevance score', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'plugin-a',
      name: 'Nutrition Logger',
      description: 'Logs nutrition data',
      tags: ['nutrition']
    });

    marketplace.registerPlugin({
      id: 'plugin-b',
      name: 'Nutrition Analyzer',
      description: 'Analyzes nutrition data',
      tags: ['nutrition', 'analysis']
    });

    const results = marketplace.search('nutrition');

    for (let i = 1; i < results.length; i++) {
      assert.ok(results[i - 1].score >= results[i].score, 'Results should be sorted by score');
    }
  });

  test('should install a plugin without dependencies', async () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'simple-plugin',
      name: 'Simple Plugin',
      dependencies: []
    });

    const result = await marketplace.install('simple-plugin');

    assert.equal(result.success, true);
    assert.ok(marketplace.installedPlugins.has('simple-plugin'));
  });

  test('should fail if plugin not found', async () => {
    marketplace = new PluginMarketplace();

    const result = await marketplace.install('nonexistent');

    assert.equal(result.success, false);
    assert.equal(result.error, 'Plugin not found');
  });

  test('should check dependencies', async () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'dependent-plugin',
      name: 'Dependent Plugin',
      dependencies: ['simple-plugin']
    });

    const result = await marketplace.install('dependent-plugin');

    assert.equal(result.success, false);
    assert.ok(result.missing.includes('simple-plugin'));
  });

  test('should activate an installed plugin', async () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Test'
    });

    await marketplace.install('test-plugin');
    const result = await marketplace.activate('test-plugin');

    assert.equal(result.success, true);
    assert.ok(marketplace.activePlugins.has('test-plugin'));
  });

  test('should fail to activate if not installed', () => {
    marketplace = new PluginMarketplace();

    const result = marketplace.activate('nonexistent');

    assert.equal(result.success, false);
    assert.equal(result.error, 'Plugin not installed');
  });

  test('should uninstall a plugin', async () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Test',
      dependencies: []
    });

    await marketplace.install('test-plugin');
    marketplace.uninstall('test-plugin');

    assert.ok(!marketplace.installedPlugins.has('test-plugin'));
  });

  test('should find dependents', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'base',
      name: 'Base'
    });

    marketplace.registerPlugin({
      id: 'dep1',
      name: 'Dep1',
      dependencies: ['base']
    });

    marketplace.registerPlugin({
      id: 'dep2',
      name: 'Dep2',
      dependencies: ['base']
    });

    const dependents = marketplace.findDependents('base');

    assert.ok(dependents.includes('dep1'));
    assert.ok(dependents.includes('dep2'));
  });

  test('should build dependency graph', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'a',
      name: 'A',
      version: '1.0.0',
      dependencies: ['b']
    });

    marketplace.registerPlugin({
      id: 'b',
      name: 'B',
      version: '2.0.0',
      dependencies: []
    });

    const graph = marketplace.buildDependencyGraph();

    assert.equal(graph.nodes.length, 2);
    assert.equal(graph.edges.length, 1);
  });

  test('should return correct topological order', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'a',
      name: 'A',
      dependencies: ['b']
    });

    marketplace.registerPlugin({
      id: 'b',
      name: 'B',
      dependencies: ['c']
    });

    marketplace.registerPlugin({
      id: 'c',
      name: 'C',
      dependencies: []
    });

    const order = marketplace.getInstallOrder(['a', 'b', 'c']);

    assert.ok(order.indexOf('c') < order.indexOf('b'));
    assert.ok(order.indexOf('b') < order.indexOf('a'));
  });

  test('should return marketplace statistics', () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'plugin-1',
      name: 'Plugin 1',
      tags: ['test']
    });

    marketplace.registerPlugin({
      id: 'plugin-2',
      name: 'Plugin 2',
      tags: ['test', 'utility']
    });

    const stats = marketplace.getStats();

    assert.equal(stats.totalPlugins, 2);
    assert.ok(typeof stats.tagCounts === 'object');
  });

  test('should invoke registered hook handlers', async () => {
    marketplace = new PluginMarketplace();

    marketplace.registerPlugin({
      id: 'test-plugin',
      name: 'Test'
    });

    marketplace.registerHook('test-plugin', 'testHook', async (context) => {
      return { ...context, modified: true };
    });

    const result = await marketplace.invokeHook('testHook', { original: true });

    assert.equal(result.modified, true);
  });
});
