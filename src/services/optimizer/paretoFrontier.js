'use strict';

/**
 * ParetoFrontier - Finds non-dominated solutions using Pareto optimization
 * NO TESTS - deliberate gap for Chisel coverage_gap validation
 */
class ParetoFrontier {
  constructor() {
    // No dependencies
  }

  /**
   * Find the Pareto frontier (non-dominated solutions)
   * @param {Array} solutions - Array of solution objects with objective values
   * @param {Array} objectives - [{ name: 'cost', minimize: true }, { name: 'nutrition', minimize: false }]
   * @returns {Array} Non-dominated solutions
   */
  find(solutions, objectives) {
    if (!solutions || solutions.length === 0) return [];
    if (!objectives || objectives.length === 0) return solutions;

    const dominated = new Set();

    // Check each solution against every other
    for (let i = 0; i < solutions.length; i++) {
      for (let j = 0; j < solutions.length; j++) {
        if (i === j) continue;

        // Check if solution i dominates solution j
        if (this.dominates(solutions[i], solutions[j], objectives)) {
          dominated.add(j);
        }
      }
    }

    // Return non-dominated solutions
    return solutions.filter((_, index) => !dominated.has(index));
  }

  /**
   * Check if solution A dominates solution B
   * A dominates B if A is better in at least one objective
   * and not worse in any other objective
   * @param {Object} solutionA - First solution
   * @param {Object} solutionB - Second solution
   * @param {Array} objectives - Objective definitions
   * @returns {boolean} True if A dominates B
   */
  dominates(solutionA, solutionB, objectives) {
    let isBetterInAtLeastOne = false;

    for (const objective of objectives) {
      const valueA = solutionA[objective.name];
      const valueB = solutionB[objective.name];

      if (valueA === undefined || valueB === undefined) continue;

      if (objective.minimize) {
        // Lower is better
        if (valueA > valueB) {
          // A is worse than B in this objective
          return false;
        }
        if (valueA < valueB) {
          // A is better than B in this objective
          isBetterInAtLeastOne = true;
        }
      } else {
        // Higher is better
        if (valueA < valueB) {
          // A is worse than B in this objective
          return false;
        }
        if (valueA > valueB) {
          // A is better than B in this objective
          isBetterInAtLeastOne = true;
        }
      }
    }

    return isBetterInAtLeastOne;
  }

  /**
   * Assign Pareto ranks to solutions
   * Rank 0 = Pareto frontier, Rank 1 = dominated by rank 0, etc.
   * @param {Array} solutions - Array of solutions
   * @param {Array} objectives - Objective definitions
   * @returns {Array} Solutions with pareto_rank added
   */
  rankSolutions(solutions, objectives) {
    if (!solutions || solutions.length === 0) return [];
    if (!objectives || objectives.length === 0) {
      return solutions.map(s => ({ ...s, pareto_rank: 0 }));
    }

    const ranked = [...solutions];
    let currentRank = 0;
    let remaining = [...ranked];

    while (remaining.length > 0) {
      const frontier = this.find(remaining, objectives);

      if (frontier.length === 0) break;

      for (const solution of frontier) {
        solution.pareto_rank = currentRank;
        const idx = remaining.indexOf(solution);
        if (idx !== -1) remaining.splice(idx, 1);
      }

      currentRank++;
    }

    return ranked;
  }

  /**
   * Find the "knee" of the Pareto frontier
   * The knee is the point that offers the best trade-off
   * @param {Array} frontier - Pareto frontier solutions
   * @param {Object} objectives - { xObjective: 'cost', yObjective: 'nutrition' }
   * @returns {Object} The knee point solution
   */
  findKnee(frontier, objectives) {
    if (!frontier || frontier.length === 0) return null;
    if (frontier.length === 1) return frontier[0];

    const { xObjective, yObjective } = objectives;
    const xMin = Math.min(...frontier.map(s => s[xObjective]));
    const xMax = Math.max(...frontier.map(s => s[xObjective]));
    const yMin = Math.min(...frontier.map(s => s[yObjective]));
    const yMax = Math.max(...frontier.map(s => s[yObjective]));

    // Normalize and find point closest to (0, 1) - ideal point
    let knee = null;
    let minDistance = Infinity;

    for (const solution of frontier) {
      const xNorm = xMax === xMin ? 0.5 : (solution[xObjective] - xMin) / (xMax - xMin);
      const yNorm = yMax === yMin ? 0.5 : (solution[yObjective] - yMin) / (yMax - yMin);

      // Distance to ideal point (normalized cost=0, normalized nutrition=1)
      const distance = Math.sqrt(xNorm * xNorm + (1 - yNorm) * (1 - yNorm));

      if (distance < minDistance) {
        minDistance = distance;
        knee = solution;
      }
    }

    return knee;
  }

  /**
   * Filter solutions by a threshold on one objective
   * then return the Pareto frontier of the filtered set
   * @param {Array} solutions - All solutions
   * @param {Array} objectives - Objective definitions
   * @param {string} objectiveName - Name of objective to filter on
   * @param {number} threshold - Maximum (or minimum) value
   * @param {boolean} isMax - If true, keep values <= threshold; if false, keep values >= threshold
   * @returns {Array} Filtered Pareto frontier
   */
  filterThenFindFrontier(solutions, objectives, objectiveName, threshold, isMax = true) {
    const filtered = solutions.filter(s => {
      const value = s[objectiveName];
      if (value === undefined) return true;
      return isMax ? value <= threshold : value >= threshold;
    });

    return this.find(filtered, objectives);
  }
}

module.exports = ParetoFrontier;
