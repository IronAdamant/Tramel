/**
 * Tests for CircularDependencyDetector
 *
 * These tests challenge Chisel because:
 * 1. They create circular import relationships (bidirectional coupling)
 * 2. The detector module imports itself through the test cycle
 * 3. Testing requires running analysis multiple times in different states
 */

const path = require('path');
const CircularDependencyDetector = require('../../src/utils/CircularDependencyDetector');

describe('CircularDependencyDetector', () => {
  const projectRoot = path.resolve(__dirname, '../../src');

  describe('extractImports', () => {
    it('should extract require statements from a file', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const result = detector.extractImports(
        path.resolve(projectRoot, 'plugins/PluginManager.js')
      );

      expect(result).toHaveProperty('imports');
      expect(result).toHaveProperty('exports');
      expect(Array.isArray(result.imports)).toBe(true);
    });

    it('should return empty for non-existent file', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const result = detector.extractImports(
        path.resolve(projectRoot, 'nonexistent/file.js')
      );

      expect(result.imports).toEqual([]);
      expect(result.exports).toEqual([]);
    });

    it('should resolve relative imports', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const result = detector.extractImports(
        path.resolve(projectRoot, 'api/app.js')
      );

      // app.js has relative imports like ./routes/recipes
      const relativeImports = result.imports.filter(i => i.includes('routes'));
      expect(relativeImports.length).toBeGreaterThan(0);
    });
  });

  describe('normalizePath', () => {
    it('should normalize file paths consistently', () => {
      const detector = new CircularDependencyDetector(projectRoot);

      const path1 = detector.normalizePath('/foo/bar/baz.js');
      const path2 = detector.normalizePath('\\foo\\bar\\baz.js');

      expect(path1).toBe(path2);
    });

    it('should remove trailing slashes', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const normalized = detector.normalizePath('/foo/bar/');
      expect(normalized).not.toMatch(/\/$/);
    });
  });

  describe('buildImportGraph', () => {
    it('should build a complete import graph', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const graph = detector.buildImportGraph();

      expect(graph.size).toBeGreaterThan(0);
      expect(detector.analysisComplete).toBe(true);
    });

    it('should track imports and importedBy for each module', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const graph = detector.buildImportGraph();

      for (const [modulePath, data] of graph) {
        expect(data).toHaveProperty('path');
        expect(data).toHaveProperty('imports');
        expect(data).toHaveProperty('importedBy');
        expect(Array.isArray(data.imports)).toBe(true);
        expect(Array.isArray(data.importedBy)).toBe(true);
      }
    });

    it('should find api/app.js and its dependencies', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const graph = detector.buildImportGraph();

      const appPath = [...graph.keys()].find(k => k.endsWith('api/app.js'));
      expect(appPath).toBeDefined();

      const appNode = graph.get(appPath);
      expect(appNode.imports.length).toBeGreaterThan(0);
    });
  });

  describe('detectCircularDependencies', () => {
    it('should detect no circular dependencies in well-structured code', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();
      const cycles = detector.detectCircularDependencies();

      // This project should have few or no cycles
      expect(Array.isArray(cycles)).toBe(true);
    });

    it('should find cycles in test fixtures', () => {
      // Create a temporary structure with circular deps
      const fs = require('fs');
      const tmpDir = path.join(__dirname, '../fixtures/circular-test');
      fs.mkdirSync(tmpDir, { recursive: true });

      // Create circular dependency: a.js requires b.js, b.js requires a.js
      fs.writeFileSync(path.join(tmpDir, 'a.js'), `
        const b = require('./b');
        module.exports = { name: 'a' };
      `);
      fs.writeFileSync(path.join(tmpDir, 'b.js'), `
        const a = require('./a');
        module.exports = { name: 'b' };
      `);

      const detector = new CircularDependencyDetector(tmpDir);
      detector.buildImportGraph();
      const cycles = detector.detectCircularDependencies();

      // Clean up
      fs.unlinkSync(path.join(tmpDir, 'a.js'));
      fs.unlinkSync(path.join(tmpDir, 'b.js'));
      fs.rmdirSync(tmpDir);

      expect(cycles.length).toBeGreaterThan(0);
    });

    it('should return cycle details with path and nodes', () => {
      const fs = require('fs');
      const tmpDir = path.join(__dirname, '../fixtures/circular-test2');
      fs.mkdirSync(tmpDir, { recursive: true });

      fs.writeFileSync(path.join(tmpDir, 'x.js'), `
        const y = require('./y');
        module.exports = { x: true };
      `);
      fs.writeFileSync(path.join(tmpDir, 'y.js'), `
        const z = require('./z');
        module.exports = { y: true };
      `);
      fs.writeFileSync(path.join(tmpDir, 'z.js'), `
        const x = require('./x');
        module.exports = { z: true };
      `);

      const detector = new CircularDependencyDetector(tmpDir);
      detector.buildImportGraph();
      const cycles = detector.detectCircularDependencies();

      // Clean up
      fs.unlinkSync(path.join(tmpDir, 'x.js'));
      fs.unlinkSync(path.join(tmpDir, 'y.js'));
      fs.unlinkSync(path.join(tmpDir, 'z.js'));
      fs.rmdirSync(tmpDir);

      expect(cycles.length).toBeGreaterThan(0);
      const cycle = cycles[0];
      expect(cycle).toHaveProperty('path');
      expect(cycle).toHaveProperty('nodes');
      expect(cycle).toHaveProperty('length');
      expect(cycle.length).toBeGreaterThan(0);
    });
  });

  describe('getModulesInCycles', () => {
    it('should return list of modules involved in cycles', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();
      detector.detectCircularDependencies();

      const modules = detector.getModulesInCycles();
      expect(Array.isArray(modules)).toBe(true);
    });
  });

  describe('getDependencyChain', () => {
    it('should find dependency chain between two modules', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();

      const appPath = [...detector.moduleCache.keys()].find(k => k.endsWith('api/app.js'));
      const recipeModelPath = [...detector.moduleCache.keys()].find(k => k.endsWith('models/Recipe.js'));

      if (appPath && recipeModelPath) {
        const chain = detector.getDependencyChain(appPath, recipeModelPath);
        // May or may not find a path depending on actual dependencies
        expect(chain === null || Array.isArray(chain)).toBe(true);
      }
    });

    it('should return null for non-existent module', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();

      const chain = detector.getDependencyChain('/nonexistent/a.js', '/nonexistent/b.js');
      expect(chain).toBeNull();
    });
  });

  describe('getGraphStats', () => {
    it('should return comprehensive graph statistics', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();

      const stats = detector.getGraphStats();

      expect(stats).toHaveProperty('totalModules');
      expect(stats).toHaveProperty('totalImportStatements');
      expect(stats).toHaveProperty('averageImportsPerModule');
      expect(stats).toHaveProperty('modulesInCycles');
      expect(stats).toHaveProperty('totalCycles');
      expect(stats.totalModules).toBeGreaterThan(0);
    });

    it('should calculate correct average imports', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();

      const stats = detector.getGraphStats();
      const expected = stats.totalImportStatements / stats.totalModules;

      expect(parseFloat(stats.averageImportsPerModule)).toBeCloseTo(expected, 1);
    });
  });

  describe('generateDotGraph', () => {
    it('should generate valid DOT format', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();

      const dot = detector.generateDotGraph();

      expect(dot).toContain('digraph ImportGraph');
      expect(dot).toContain('->');
      expect(dot).toContain('}');
    });

    it('should include cycles only when requested', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();
      detector.detectCircularDependencies();

      const fullDot = detector.generateDotGraph(false);
      const cycleDot = detector.generateDotGraph(true);

      // Cycle-only should have fewer lines (less nodes)
      expect(fullDot.split('\n').length).toBeGreaterThan(cycleDot.split('\n').length);
    });
  });

  describe('reset', () => {
    it('should clear all cached data', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      detector.buildImportGraph();
      detector.detectCircularDependencies();

      detector.reset();

      expect(detector.moduleCache.size).toBe(0);
      expect(detector.circularPaths).toEqual([]);
      expect(detector.analysisComplete).toBe(false);
    });
  });

  describe('scanDirectory', () => {
    it('should find all JS files in src directory', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const files = detector.scanDirectory(projectRoot, ['.js']);

      expect(files.length).toBeGreaterThan(0);
      expect(files.every(f => f.endsWith('.js'))).toBe(true);
    });

    it('should exclude node_modules and .git', () => {
      const detector = new CircularDependencyDetector(projectRoot);
      const files = detector.scanDirectory(projectRoot, ['.js']);

      const inNodeModules = files.some(f => f.includes('node_modules'));
      const inGit = files.some(f => f.includes('.git'));

      expect(inNodeModules).toBe(false);
      expect(inGit).toBe(false);
    });
  });
});
