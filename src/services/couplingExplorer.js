/**
 * DynamicImportGraphCouplingExplorer - Import relationship analysis
 *
 * CHALLENGES CHISEL:
 * - Dynamic module loading creates runtime-only dependencies
 * - Circular dependencies detected and managed
 * - Import-graph coupling metrics (static analysis based)
 * - Partial coverage scenarios (some paths tested, others not)
 *
 * This module demonstrates how import relationships create coupling
 * that chisel's coupling analysis should track but currently doesn't
 * (chisel relies on co-change history, not import edges).
 */

const fs = require('fs');
const path = require('path');

class DynamicImportGraphCouplingExplorer {
  constructor(basePath = null) {
    this.basePath = basePath || process.cwd();
    this.modules = new Map();
    this.dependencyGraph = new Map();
    this.couplingScores = new Map();
    this.circularDependencies = [];
    this.moduleCache = new Map();
  }

  /**
   * Register a module with its dependencies
   * Creates coupling relationships
   */
  registerModule(moduleId, { path: modulePath, dependencies = [], exports = [] }) {
    this.modules.set(moduleId, {
      id: moduleId,
      path: modulePath,
      dependencies: [...dependencies],
      exports,
      registeredAt: Date.now()
    });

    // Update dependency graph
    this.dependencyGraph.set(moduleId, new Set(dependencies));

    // Calculate coupling for this module
    this.calculateModuleCoupling(moduleId);

    return this;
  }

  /**
   * Register a dynamic dependency (loaded at runtime)
   * These are NOT visible through static import analysis
   */
  registerDynamicDependency(moduleId, dynamicDep) {
    const module = this.modules.get(moduleId);
    if (!module) return;

    // Track dynamic dependency separately
    if (!module.dynamicDependencies) {
      module.dynamicDependencies = [];
    }
    module.dynamicDependencies.push(dynamicDep);

    // Add to dependency graph
    const deps = this.dependencyGraph.get(moduleId);
    if (deps) {
      deps.add(dynamicDep);
    }

    // Recalculate coupling
    this.calculateModuleCoupling(moduleId);

    return this;
  }

  /**
   * Calculate coupling score for a module
   * Based on import graph metrics
   */
  calculateModuleCoupling(moduleId) {
    const module = this.modules.get(moduleId);
    if (!module) return null;

    const directImports = module.dependencies.length;
    const dynamicImports = module.dynamicDependencies?.length || 0;

    // Fan-in: how many modules depend on this one
    const fanIn = this.getFanIn(moduleId);

    // Fan-out: how many modules this one depends on
    const fanOut = directImports + dynamicImports;

    // Coupling metrics
    const coupling = {
      fanIn,
      fanOut,
      directImports,
      dynamicImports,
      instability: fanOut / (fanIn + fanOut + 1), // 0 = stable, 1 = unstable
      abstractness: module.exports.length / Math.max(1, directImports + 1),
      // Import-graph based coupling (NOT co-change based!)
      importCoupling: this.calculateImportGraphCoupling(moduleId),
      // Transitive coupling through import chain
      transitiveCoupling: this.calculateTransitiveCoupling(moduleId)
    };

    this.couplingScores.set(moduleId, coupling);
    return coupling;
  }

  /**
   * Calculate coupling based on import graph structure
   * This is what CHISEL SHOULD do but currently relies on co-change instead
   */
  calculateImportGraphCoupling(moduleId) {
    const visited = new Set();
    const importChain = [];

    this.walkImportGraph(moduleId, visited, importChain, 0, 3);

    // Coupling score based on how interconnected this module is
    // through import chains
    const uniqueImports = new Set(importChain).size;
    const maxPossible = this.modules.size - 1;

    return uniqueImports / Math.max(1, maxPossible);
  }

  /**
   * Walk import graph to find all reachable modules
   */
  walkImportGraph(moduleId, visited, chain, depth, maxDepth) {
    if (visited.has(moduleId) || depth > maxDepth) return;

    visited.add(moduleId);
    chain.push(moduleId);

    const deps = this.dependencyGraph.get(moduleId);
    if (deps) {
      for (const dep of deps) {
        this.walkImportGraph(dep, visited, chain, depth + 1, maxDepth);
      }
    }
  }

  /**
   * Calculate transitive coupling
   */
  calculateTransitiveCoupling(moduleId) {
    const visited = new Set();
    const transitiveDeps = new Set();

    this.collectTransitiveDependencies(moduleId, visited, transitiveDeps);

    return {
      count: transitiveDeps.size,
      modules: Array.from(transitiveDeps),
      ratio: transitiveDeps.size / Math.max(1, this.modules.size - 1)
    };
  }

  /**
   * Collect all transitive dependencies
   */
  collectTransitiveDependencies(moduleId, visited, collection) {
    if (visited.has(moduleId)) return;
    visited.add(moduleId);

    const deps = this.dependencyGraph.get(moduleId);
    if (deps) {
      for (const dep of deps) {
        collection.add(dep);
        this.collectTransitiveDependencies(dep, visited, collection);
      }
    }
  }

  /**
   * Get fan-in for a module (how many modules depend on it)
   */
  getFanIn(moduleId) {
    let fanIn = 0;

    for (const [, deps] of this.dependencyGraph) {
      if (deps.has(moduleId)) {
        fanIn++;
      }
    }

    return fanIn;
  }

  /**
   * Detect circular dependencies
   */
  detectCircularDependencies() {
    const cycles = [];
    const visited = new Set();
    const recursionStack = new Set();

    const detectCycle = (moduleId, path = []) => {
      if (recursionStack.has(moduleId)) {
        // Found cycle
        const cycleStart = path.indexOf(moduleId);
        const cycle = path.slice(cycleStart);
        cycle.push(moduleId);
        cycles.push(cycle);
        return;
      }

      if (visited.has(moduleId)) return;

      visited.add(moduleId);
      recursionStack.add(moduleId);
      path.push(moduleId);

      const deps = this.dependencyGraph.get(moduleId);
      if (deps) {
        for (const dep of deps) {
          detectCycle(dep, [...path]);
        }
      }

      recursionStack.delete(moduleId);
    };

    for (const moduleId of this.modules.keys()) {
      detectCycle(moduleId, []);
    }

    this.circularDependencies = cycles;
    return cycles;
  }

  /**
   * Find strongly connected components
   */
  findStronglyConnectedComponents() {
    // Tarjan's algorithm for SCCs
    const indices = new Map();
    const lowlinks = new Map();
    const onStack = new Set();
    const stack = [];
    const sccs = [];
    let index = 0;

    const strongConnect = (moduleId) => {
      indices.set(moduleId, index);
      lowlinks.set(moduleId, index);
      index++;
      stack.push(moduleId);
      onStack.add(moduleId);

      const deps = this.dependencyGraph.get(moduleId);
      if (deps) {
        for (const dep of deps) {
          if (!indices.has(dep)) {
            strongConnect(dep);
            lowlinks.set(moduleId, Math.min(lowlinks.get(moduleId), lowlinks.get(dep)));
          } else if (onStack.has(dep)) {
            lowlinks.set(moduleId, Math.min(lowlinks.get(moduleId), indices.get(dep)));
          }
        }
      }

      if (lowlinks.get(moduleId) === indices.get(moduleId)) {
        const scc = [];
        let w;
        do {
          w = stack.pop();
          onStack.delete(w);
          scc.push(w);
        } while (w !== moduleId);
        sccs.push(scc);
      }
    };

    for (const moduleId of this.modules.keys()) {
      if (!indices.has(moduleId)) {
        strongConnect(moduleId);
      }
    }

    return sccs;
  }

  /**
   * Calculate overall system coupling metrics
   */
  getSystemCouplingMetrics() {
    const totalModules = this.modules.size;

    let totalFanIn = 0;
    let totalFanOut = 0;
    let totalInstability = 0;
    let totalImportCoupling = 0;

    for (const [moduleId, scores] of this.couplingScores) {
      totalFanIn += scores.fanIn;
      totalFanOut += scores.fanOut;
      totalInstability += scores.instability;
      totalImportCoupling += scores.importCoupling;
    }

    const avgInstability = totalInstability / Math.max(1, totalModules);
    const avgImportCoupling = totalImportCoupling / Math.max(1, totalModules);

    // System-level metrics
    const systemCoupling = {
      totalModules,
      totalDependencies: Array.from(this.dependencyGraph.values())
        .reduce((sum, deps) => sum + deps.size, 0),
      averageFanIn: totalFanIn / Math.max(1, totalModules),
      averageFanOut: totalFanOut / Math.max(1, totalModules),
      averageInstability: avgInstability,
      averageImportCoupling: avgImportCoupling,
      // Architectural metrics
      isStable: avgInstability < 0.5,
      hasHighCoupling: avgImportCoupling > 0.5,
      // Module with highest coupling
      mostCoupledModule: this.findMostCoupledModule(),
      // Module with highest fan-in (most depended upon)
      mostCentralModule: this.findMostCentralModule()
    };

    return systemCoupling;
  }

  /**
   * Find module with highest coupling
   */
  findMostCoupledModule() {
    let maxCoupling = -1;
    let mostCoupled = null;

    for (const [moduleId, scores] of this.couplingScores) {
      const combinedCoupling = scores.importCoupling + scores.transitiveCoupling.ratio;
      if (combinedCoupling > maxCoupling) {
        maxCoupling = combinedCoupling;
        mostCoupled = moduleId;
      }
    }

    return mostCoupled ? { moduleId: mostCoupled, coupling: maxCoupling } : null;
  }

  /**
   * Find module with highest fan-in (most depended upon)
   */
  findMostCentralModule() {
    let maxFanIn = -1;
    let mostCentral = null;

    for (const [moduleId, scores] of this.couplingScores) {
      if (scores.fanIn > maxFanIn) {
        maxFanIn = scores.fanIn;
        mostCentral = moduleId;
      }
    }

    return mostCentral ? { moduleId: mostCentral, fanIn: maxFanIn } : null;
  }

  /**
   * Analyze a file and extract its import dependencies
   * This simulates what static analysis SHOULD do
   */
  analyzeFileImports(filePath) {
    try {
      const content = fs.readFileSync(filePath, 'utf-8');
      const lines = content.split('\n');

      const imports = [];
      const dynamicImports = [];

      for (const line of lines) {
        // Static imports
        const requireMatch = line.match(/require\s*\(\s*['"]([^'"]+)['"]\s*\)/);
        if (requireMatch) {
          imports.push({
            type: 'require',
            source: requireMatch[1],
            line: line.trim()
          });
        }

        // Dynamic imports (require with variables)
        const dynamicMatch = line.match(/require\s*\(\s*(\w+)/);
        if (dynamicMatch && !requireMatch) {
          dynamicImports.push({
            type: 'dynamic',
            variable: dynamicMatch[1],
            line: line.trim()
          });
        }

        // Import statements
        const importMatch = line.match(/import\s+.*?from\s+['"]([^'"]+)['"]/);
        if (importMatch) {
          imports.push({
            type: 'import',
            source: importMatch[1],
            line: line.trim()
          });
        }
      }

      return {
        file: filePath,
        imports,
        dynamicImports,
        importCount: imports.length,
        isDynamic: dynamicImports.length > 0
      };
    } catch (error) {
      return {
        file: filePath,
        error: error.message,
        imports: [],
        dynamicImports: []
      };
    }
  }

  /**
   * Build import graph from directory
   */
  buildImportGraphFromDirectory(dirPath, extensions = ['.js']) {
    const files = this.findFiles(dirPath, extensions);
    const graph = new Map();

    for (const file of files) {
      const analysis = this.analyzeFileImports(file);
      const moduleId = this.relativePath(dirPath, file);

      graph.set(moduleId, {
        id: moduleId,
        file,
        imports: analysis.imports.map(i => i.source),
        dynamicImports: analysis.dynamicImports.length,
        importCount: analysis.importCount
      });
    }

    return graph;
  }

  /**
   * Find files with extension
   */
  findFiles(dirPath, extensions) {
    const results = [];

    const walk = (currentPath) => {
      try {
        const entries = fs.readdirSync(currentPath, { withFileTypes: true });

        for (const entry of entries) {
          const fullPath = path.join(currentPath, entry.name);

          if (entry.isDirectory()) {
            // Skip node_modules, .git, etc.
            if (!entry.name.startsWith('.') && entry.name !== 'node_modules') {
              walk(fullPath);
            }
          } else if (entry.isFile()) {
            const ext = path.extname(entry.name);
            if (extensions.includes(ext)) {
              results.push(fullPath);
            }
          }
        }
      } catch {
        // Skip inaccessible directories
      }
    };

    walk(dirPath);
    return results;
  }

  relativePath(base, target) {
    return path.relative(base, target);
  }

  /**
   * Get all modules that would be affected by changing a module
   * (transitive dependents)
   */
  getAffectedModules(moduleId) {
    const affected = new Set();
    this.collectTransitiveDependents(moduleId, affected);
    return Array.from(affected);
  }

  /**
   * Collect transitive dependents (modules that depend on this one, directly or indirectly)
   */
  collectTransitiveDependents(moduleId, collection) {
    for (const [otherId, deps] of this.dependencyGraph) {
      if (deps.has(moduleId)) {
        collection.add(otherId);
        this.collectTransitiveDependents(otherId, collection);
      }
    }
  }

  /**
   * Get coupling report for a module
   */
  getModuleCouplingReport(moduleId) {
    const module = this.modules.get(moduleId);
    if (!module) {
      return { error: 'Module not found' };
    }

    const scores = this.couplingScores.get(moduleId) ||
      this.calculateModuleCoupling(moduleId);

    return {
      module: moduleId,
      path: module.path,
      ...module,
      coupling: scores,
      affectedModules: this.getAffectedModules(moduleId),
      // Is this module in a circular dependency?
      inCycle: this.circularDependencies.some(c => c.includes(moduleId))
    };
  }

  /**
   * Get complete system analysis
   */
  getSystemAnalysis() {
    return {
      systemCoupling: this.getSystemCouplingMetrics(),
      circularDependencies: this.circularDependencies,
      stronglyConnectedComponents: this.findStronglyConnectedComponents(),
      highCouplingModules: this.getHighCouplingModules(),
      unstableModules: this.getUnstableModules()
    };
  }

  /**
   * Get modules with high coupling
   */
  getHighCouplingModules(threshold = 0.5) {
    const highCoupling = [];

    for (const [moduleId, scores] of this.couplingScores) {
      if (scores.importCoupling > threshold) {
        highCoupling.push({
          moduleId,
          coupling: scores.importCoupling,
          fanIn: scores.fanIn,
          fanOut: scores.fanOut
        });
      }
    }

    return highCoupling.sort((a, b) => b.coupling - a.coupling);
  }

  /**
   * Get unstable modules
   */
  getUnstableModules(threshold = 0.5) {
    const unstable = [];

    for (const [moduleId, scores] of this.couplingScores) {
      if (scores.instability > threshold) {
        unstable.push({
          moduleId,
          instability: scores.instability,
          fanIn: scores.fanIn,
          fanOut: scores.fanOut
        });
      }
    }

    return unstable.sort((a, b) => b.instability - a.instability);
  }

  /**
   * Reset all state
   */
  reset() {
    this.modules.clear();
    this.dependencyGraph.clear();
    this.couplingScores.clear();
    this.circularDependencies = [];
    this.moduleCache.clear();
    return this;
  }
}

module.exports = DynamicImportGraphCouplingExplorer;
