/**
 * Tests for DynamicImportGraphCouplingExplorer
 */

'use strict';

const { describe, test, assert } = require('../testRunner');
const DynamicImportGraphCouplingExplorer = require('../../src/services/couplingExplorer');

describe('DynamicImportGraphCouplingExplorer', () => {
  let explorer;

  test('should register a module with dependencies', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('module-a', {
      path: '/src/module-a.js',
      dependencies: ['module-b', 'module-c'],
      exports: ['funcA', 'funcB']
    });

    assert.ok(explorer.modules.has('module-a'), 'Module should be registered');
    const module = explorer.modules.get('module-a');
    assert.equal(module.dependencies.length, 2, 'Should have 2 dependencies');
  });

  test('should calculate fan-in and fan-out', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('module-a', {
      path: '/src/module-a.js',
      dependencies: ['module-b', 'module-c']
    });

    explorer.registerModule('module-b', {
      path: '/src/module-b.js',
      dependencies: ['module-c']
    });

    explorer.registerModule('module-c', {
      path: '/src/module-c.js',
      dependencies: []
    });

    const couplingA = explorer.couplingScores.get('module-a');
    assert.equal(couplingA.fanOut, 2, 'module-a should have fan-out of 2');

    const couplingC = explorer.couplingScores.get('module-c');
    assert.equal(couplingC.fanIn, 2, 'module-c should have fan-in of 2');
  });

  test('should detect simple cycle', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.registerModule('b', { path: '/b.js', dependencies: ['a'] });

    const cycles = explorer.detectCircularDependencies();

    assert.ok(cycles.length > 0, 'Should find cycles');
  });

  test('should return empty cycles for acyclic graph', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.registerModule('b', { path: '/b.js', dependencies: ['c'] });
    explorer.registerModule('c', { path: '/c.js', dependencies: [] });

    const cycles = explorer.detectCircularDependencies();

    assert.equal(cycles.length, 0, 'Should have no cycles');
  });

  test('should find strongly connected components', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.registerModule('b', { path: '/b.js', dependencies: ['a'] });
    explorer.registerModule('c', { path: '/c.js', dependencies: [] });

    const sccs = explorer.findStronglyConnectedComponents();

    assert.ok(sccs.length >= 2, 'Should find at least 2 SCCs');
  });

  test('should calculate system-wide metrics', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.registerModule('b', { path: '/b.js', dependencies: ['c'] });
    explorer.registerModule('c', { path: '/c.js', dependencies: [] });

    const metrics = explorer.getSystemCouplingMetrics();

    assert.equal(metrics.totalModules, 3, 'Should have 3 modules');
    assert.equal(metrics.totalDependencies, 2, 'Should have 2 dependencies');
  });

  test('should find affected modules', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.registerModule('b', { path: '/b.js', dependencies: ['c'] });
    explorer.registerModule('c', { path: '/c.js', dependencies: [] });
    explorer.registerModule('d', { path: '/d.js', dependencies: [] });

    const affected = explorer.getAffectedModules('c');

    assert.ok(affected.includes('b'), 'b should be affected');
    assert.ok(affected.includes('a'), 'a should be affected');
    assert.ok(!affected.includes('d'), 'd should not be affected');
  });

  test('should return error for unknown module', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    const report = explorer.getModuleCouplingReport('unknown');

    assert.equal(report.error, 'Module not found');
  });

  test('should reset all state', () => {
    explorer = new DynamicImportGraphCouplingExplorer();

    explorer.registerModule('a', { path: '/a.js', dependencies: ['b'] });
    explorer.reset();

    assert.equal(explorer.modules.size, 0, 'Should have no modules after reset');
  });
});
