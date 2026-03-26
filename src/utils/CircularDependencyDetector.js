/**
 * CircularDependencyDetector - Analyzes import graph for circular dependencies
 *
 * This module challenges Chisel because:
 * 1. It creates BIDIRECTIONAL coupling relationships (A->B and B->A)
 * 2. The dependency graph has cycles, which may confuse diff_impact
 * 3. Testing circular analysis requires testing the same files in different orders
 */

const fs = require('fs');
const path = require('path');

class CircularDependencyDetector {
  constructor(projectRoot) {
    this.projectRoot = projectRoot;
    this.moduleCache = new Map(); // path -> { imports: [], importedBy: [] }
    this.circularPaths = [];      // Found circular dependency paths
    this.analysisComplete = false;
  }

  /**
   * Extract require/import statements from a file
   */
  extractImports(filePath) {
    if (!fs.existsSync(filePath)) {
      return { imports: [], exports: [] };
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    const imports = [];

    // Match CommonJS require statements
    const requireRegex = /require\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
    let match;

    while ((match = requireRegex.exec(content)) !== null) {
      const importPath = match[1];
      // Resolve relative imports
      if (importPath.startsWith('.')) {
        const resolved = path.resolve(path.dirname(filePath), importPath);
        const normalized = this.normalizePath(resolved);
        imports.push(normalized);
      } else if (!importPath.startsWith('node_modules')) {
        // Internal module (no ./ or ../ but also not node_modules)
        const resolved = path.resolve(this.projectRoot, 'src', importPath);
        const normalized = this.normalizePath(resolved);
        imports.push(normalized);
      }
    }

    // Match ES6 exports for reference
    const exports = [];
    const exportRegex = /(?:module\.exports|export\s+(?:default|const|function|class))\s+/g;
    while ((match = exportRegex.exec(content)) !== null) {
      exports.push(match[0]);
    }

    return { imports, exports };
  }

  /**
   * Normalize file path for consistent comparison
   */
  normalizePath(filePath) {
    return path.normalize(filePath).replace(/\\/g, '/');
  }

  /**
   * Build the full import graph by scanning all JS files
   */
  buildImportGraph(extensions = ['.js']) {
    const files = this.scanDirectory(this.projectRoot, extensions);
    const graph = new Map();

    for (const file of files) {
      const normalized = this.normalizePath(file);
      const { imports } = this.extractImports(file);

      graph.set(normalized, {
        path: normalized,
        imports: [],
        importedBy: [],
        relativePath: path.relative(this.projectRoot, file)
      });

      // First pass: collect direct imports
      for (const imp of imports) {
        if (graph.has(imp)) {
          graph.get(normalized).imports.push(imp);
        }
      }
    }

    // Second pass: build reverse index (importedBy)
    for (const [filePath, data] of graph) {
      for (const imp of data.imports) {
        if (graph.has(imp)) {
          graph.get(imp).importedBy.push(filePath);
        }
      }
    }

    this.moduleCache = graph;
    this.analysisComplete = true;
    return graph;
  }

  /**
   * Scan directory for files with given extensions
   */
  scanDirectory(dir, extensions, excludeDirs = ['node_modules', '.git', 'tests']) {
    const results = [];

    if (!fs.existsSync(dir)) return results;

    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        if (!excludeDirs.includes(entry.name)) {
          results.push(...this.scanDirectory(fullPath, extensions, excludeDirs));
        }
      } else if (entry.isFile()) {
        const ext = path.extname(entry.name);
        if (extensions.includes(ext)) {
          results.push(fullPath);
        }
      }
    }

    return results;
  }

  /**
   * Detect all circular dependencies using DFS
   */
  detectCircularDependencies() {
    if (!this.analysisComplete) {
      this.buildImportGraph();
    }

    const graph = this.moduleCache;
    const visited = new Set();
    const recursionStack = new Set();
    const cycles = [];

    const dfs = (nodePath, path) => {
      visited.add(nodePath);
      recursionStack.add(nodePath);
      path.push(nodePath);

      const node = graph.get(nodePath);
      if (!node) {
        path.pop();
        recursionStack.delete(nodePath);
        return;
      }

      for (const neighbor of node.imports) {
        if (!visited.has(neighbor)) {
          dfs(neighbor, path);
        } else if (recursionStack.has(neighbor)) {
          // Found a cycle! Extract the cycle path
          const cycleStart = path.indexOf(neighbor);
          const cyclePath = [...path.slice(cycleStart), neighbor];
          cycles.push({
            path: cyclePath,
            length: cyclePath.length - 1,
            nodes: cyclePath.map(p => graph.get(p)?.relativePath || p)
          });
        }
      }

      path.pop();
      recursionStack.delete(nodePath);
    };

    for (const nodePath of graph.keys()) {
      if (!visited.has(nodePath)) {
        dfs(nodePath, []);
      }
    }

    this.circularPaths = cycles;
    return cycles;
  }

  /**
   * Get all modules involved in circular dependencies
   */
  getModulesInCycles() {
    if (this.circularPaths.length === 0) {
      this.detectCircularDependencies();
    }

    const modulesInCycles = new Set();
    for (const cycle of this.circularPaths) {
      for (const node of cycle.nodes) {
        modulesInCycles.add(node);
      }
    }
    return [...modulesInCycles];
  }

  /**
   * Find the shortest cycle involving a specific module
   */
  findCycleForModule(modulePath) {
    if (this.circularPaths.length === 0) {
      this.detectCircularDependencies();
    }

    const normalized = this.normalizePath(modulePath);
    return this.circularPaths.filter(cycle =>
      cycle.path.includes(normalized) || cycle.nodes.includes(modulePath)
    );
  }

  /**
   * Get dependency chain between two modules
   */
  getDependencyChain(fromModule, toModule) {
    if (!this.analysisComplete) {
      this.buildImportGraph();
    }

    const graph = this.moduleCache;
    const from = this.normalizePath(fromModule);
    const to = this.normalizePath(toModule);

    const visited = new Set();
    const parent = new Map();

    const bfs = () => {
      const queue = [from];
      visited.add(from);

      while (queue.length > 0) {
        const current = queue.shift();

        if (current === to) {
          // Reconstruct path
          const path = [];
          let node = to;
          while (node) {
            path.unshift(node);
            node = parent.get(node);
          }
          return path.map(p => graph.get(p)?.relativePath || p);
        }

        const node = graph.get(current);
        if (!node) continue;

        for (const neighbor of node.imports) {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            parent.set(neighbor, current);
            queue.push(neighbor);
          }
        }
      }

      return null; // No path found
    };

    return bfs();
  }

  /**
   * Check if removing a module would break any cycles
   */
  wouldBreakingCycle(modulePath) {
    const cycles = this.findCycleForModule(modulePath);
    return cycles.length > 0;
  }

  /**
   * Get statistics about the import graph
   */
  getGraphStats() {
    if (!this.analysisComplete) {
      this.buildImportGraph();
    }

    const graph = this.moduleCache;
    let totalImports = 0;
    let maxImports = 0;
    let maxImportedBy = 0;
    let mostImportedModule = null;
    let mostImportingModule = null;

    for (const [path, data] of graph) {
      totalImports += data.imports.length;

      if (data.imports.length > maxImports) {
        maxImports = data.imports.length;
        mostImportingModule = data.relativePath;
      }

      if (data.importedBy.length > maxImportedBy) {
        maxImportedBy = data.importedBy.length;
        mostImportedModule = data.relativePath;
      }
    }

    return {
      totalModules: graph.size,
      totalImportStatements: totalImports,
      averageImportsPerModule: (totalImports / graph.size).toFixed(2),
      maxImports,
      mostImportingModule,
      maxImportedBy,
      mostImportedModule,
      modulesInCycles: this.getModulesInCycles().length,
      totalCycles: this.circularPaths.length
    };
  }

  /**
   * Generate a DOT graph for visualization
   */
  generateDotGraph(includeCyclesOnly = false) {
    if (!this.analysisComplete) {
      this.buildImportGraph();
    }

    const graph = this.moduleCache;
    let dot = 'digraph ImportGraph {\n  rankdir=LR;\n  node [shape=box];\n';

    const addEdge = (from, to) => {
      const fromName = path.basename(from, '.js');
      const toName = path.basename(to, '.js');
      dot += `  "${fromName}" -> "${toName}";\n`;
    };

    if (includeCyclesOnly) {
      const cycleModules = new Set();
      for (const cycle of this.circularPaths) {
        for (const node of cycle.path) {
          cycleModules.add(node);
        }
      }

      for (const modulePath of cycleModules) {
        const data = graph.get(modulePath);
        if (!data) continue;

        for (const imp of data.imports) {
          if (cycleModules.has(imp)) {
            addEdge(modulePath, imp);
          }
        }
      }
    } else {
      for (const [modulePath, data] of graph) {
        for (const imp of data.imports) {
          addEdge(modulePath, imp);
        }
      }
    }

    dot += '}';
    return dot;
  }

  /**
   * Clear cache and reset state
   */
  reset() {
    this.moduleCache.clear();
    this.circularPaths = [];
    this.analysisComplete = false;
  }
}

module.exports = CircularDependencyDetector;
