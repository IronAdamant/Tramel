/**
 * DiffService
 * LCS-based text diff algorithm for ingredients
 */

const crypto = require('crypto');

class DiffService {
  constructor() {
    this.ingredientKeyExtractor = (ing) => ing.name.toLowerCase();
  }

  /**
   * Compute LCS (Longest Common Subsequence) table
   * @param {Array} a - First array
   * @param {Array} b - Second array
   * @param {Function} keyExtractor - Function to extract comparison key
   * @returns {Array} 2D LCS table
   */
  computeLCSTable(a, b, keyExtractor = null) {
    const m = a.length;
    const n = b.length;
    const table = Array(m + 1).fill(null).map(() => Array(n + 1).fill(0));
    const extractor = keyExtractor || ((item) => item);

    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        if (extractor(a[i - 1]) === extractor(b[j - 1])) {
          table[i][j] = table[i - 1][j - 1] + 1;
        } else {
          table[i][j] = Math.max(table[i - 1][j], table[i][j - 1]);
        }
      }
    }

    return table;
  }

  /**
   * Backtrack through LCS table to find diff
   * @param {Array} a - First array
   * @param {Array} b - Second array
   * @param {Array} table - LCS table
   * @param {Function} keyExtractor - Function to extract comparison key
   * @returns {Object} { lcs, added, removed }
   */
  backtrack(a, b, table, keyExtractor = null) {
    const lcs = [];
    const added = [];
    const removed = [];
    const extractor = keyExtractor || ((item) => item);
    let i = a.length;
    let j = b.length;

    while (i > 0 || j > 0) {
      if (i > 0 && j > 0 && extractor(a[i - 1]) === extractor(b[j - 1])) {
        lcs.push({ indexA: i - 1, indexB: j - 1, item: a[i - 1] });
        i--;
        j--;
      } else if (j > 0 && (i === 0 || table[i][j - 1] >= table[i - 1][j])) {
        added.push({ indexB: j - 1, item: b[j - 1] });
        j--;
      } else if (i > 0) {
        removed.push({ indexA: i - 1, item: a[i - 1] });
        i--;
      }
    }

    return { lcs: lcs.reverse(), added: added.reverse(), removed: removed.reverse() };
  }

  /**
   * Diff two sets of ingredients
   * @param {Array} ingredients1 - First set of ingredients
   * @param {Array} ingredients2 - Second set of ingredients
   * @returns {Object} { added, removed, modified }
   */
  diff(ingredients1, ingredients2) {
    const empty1 = !ingredients1 || ingredients1.length === 0;
    const empty2 = !ingredients2 || ingredients2.length === 0;

    if (empty1 && empty2) {
      return { added: [], removed: [], modified: [] };
    }

    if (empty1) {
      return { added: ingredients2, removed: [], modified: [] };
    }

    if (empty2) {
      return { added: [], removed: ingredients1, modified: [] };
    }

    const table = this.computeLCSTable(ingredients1, ingredients2, this.ingredientKeyExtractor);
    const { lcs, added, removed } = this.backtrack(ingredients1, ingredients2, table, this.ingredientKeyExtractor);

    // Find modified items by comparing items at LCS positions that are different
    const modified = [];
    for (const lcsItem of lcs) {
      const item1 = lcsItem.item;
      const item2 = ingredients2[lcsItem.indexB];
      if (this.ingredientsAreDifferent(item1, item2)) {
        modified.push({ before: item1, after: item2 });
      }
    }

    return {
      added: added.map(a => a.item),
      removed: removed.map(r => r.item),
      modified
    };
  }

  /**
   * Check if two ingredients have meaningful differences
   */
  ingredientsAreDifferent(ing1, ing2) {
    if (this.ingredientKeyExtractor(ing1) !== this.ingredientKeyExtractor(ing2)) {
      return false; // Different ingredients shouldn't be in modified
    }
    return ing1.quantity !== ing2.quantity ||
           ing1.unit !== ing2.unit ||
           ing1.notes !== ing2.notes ||
           ing1.prep !== ing2.prep;
  }

  /**
   * Compute field-level diff for recipe properties
   * @param {Object} recipe1 - First recipe state
   * @param {Object} recipe2 - Second recipe state
   * @returns {Object} { changedFields, added, removed, modified }
   */
  diffRecipeFields(recipe1, recipe2) {
    const fieldsToCompare = [
      'title', 'description', 'servings', 'prepTime', 'cookTime',
      'totalTime', 'difficulty', 'cuisine', 'mealType', 'tags',
      'source', 'notes'
    ];

    const changedFields = [];
    const allFields = new Set([...Object.keys(recipe1 || {}), ...Object.keys(recipe2 || {})]);

    for (const field of allFields) {
      const val1 = recipe1?.[field];
      const val2 = recipe2?.[field];

      if (JSON.stringify(val1) !== JSON.stringify(val2)) {
        if (!(val1 === undefined || val1 === null || val1 === '') &&
            !(val2 === undefined || val2 === null || val2 === '')) {
          changedFields.push({
            field,
            before: val1,
            after: val2
          });
        } else if (val1 === undefined || val1 === null || val1 === '') {
          changedFields.push({
            field,
            before: null,
            after: val2,
            type: 'added'
          });
        } else {
          changedFields.push({
            field,
            before: val1,
            after: null,
            type: 'removed'
          });
        }
      }
    }

    return changedFields;
  }

  /**
   * Diff instructions (list of strings)
   * @param {Array} instructions1 - First instructions array
   * @param {Array} instructions2 - Second instructions array
   * @returns {Object} { added, removed, modified }
   */
  diffInstructions(instructions1, instructions2) {
    const empty1 = !instructions1 || instructions1.length === 0;
    const empty2 = !instructions2 || instructions2.length === 0;

    if (empty1 && empty2) {
      return { added: [], removed: [], modified: [] };
    }

    if (empty1) {
      return { added: instructions2.map((text, i) => ({ step: i + 1, text })), removed: [], modified: [] };
    }

    if (empty2) {
      return { added: [], removed: instructions1.map((text, i) => ({ step: i + 1, text })), modified: [] };
    }

    // For strings, use null keyExtractor (default returns item directly)
    const table = this.computeLCSTable(instructions1, instructions2, null);
    const { lcs, added, removed } = this.backtrack(instructions1, instructions2, table, null);

    const modified = [];
    for (const lcsItem of lcs) {
      const text1 = instructions1[lcsItem.indexA];
      const text2 = instructions2[lcsItem.indexB];
      if (text1 !== text2) {
        modified.push({
          step: lcsItem.indexB + 1,
          before: text1,
          after: text2
        });
      }
    }

    return {
      added: added.map(a => ({ step: a.indexB + 1, text: instructions2[a.indexB] })),
      removed: removed.map(r => ({ step: r.indexA + 1, text: instructions1[r.indexA] })),
      modified
    };
  }

  /**
   * Format diff for output
   * @param {Object} diff - Diff result
   * @param {string} format - 'text' or 'json'
   * @returns {string|Object}
   */
  formatDiff(diff, format = 'text') {
    if (format === 'json') {
      return diff;
    }

    const lines = [];
    lines.push('Changes:');

    if (diff.added.length > 0) {
      lines.push(`\n+ Added (${diff.added.length}):`);
      diff.added.forEach(ing => {
        lines.push(`  + ${ing.name}: ${ing.quantity || ''} ${ing.unit || ''}`.trim());
      });
    }

    if (diff.removed.length > 0) {
      lines.push(`\n- Removed (${diff.removed.length}):`);
      diff.removed.forEach(ing => {
        lines.push(`  - ${ing.name}: ${ing.quantity || ''} ${ing.unit || ''}`.trim());
      });
    }

    if (diff.modified.length > 0) {
      lines.push(`\n~ Modified (${diff.modified.length}):`);
      diff.modified.forEach(m => {
        lines.push(`  ~ ${m.before.name}:`);
        lines.push(`    before: ${m.before.quantity || ''} ${m.before.unit || ''}`.trim());
        lines.push(`    after: ${m.after.quantity || ''} ${m.after.unit || ''}`.trim());
      });
    }

    if (diff.added.length === 0 && diff.removed.length === 0 && diff.modified.length === 0) {
      lines.push('  (no changes)');
    }

    return lines.join('\n');
  }

  /**
   * Generate a hash for a diff (for caching/comparison)
   */
  hashDiff(diff) {
    // Sort keys at all levels for consistent hashing
    const sortKeys = (obj) => {
      if (Array.isArray(obj)) {
        return obj.map(sortKeys);
      }
      if (obj !== null && typeof obj === 'object') {
        return Object.keys(obj).sort().reduce((acc, key) => {
          acc[key] = sortKeys(obj[key]);
          return acc;
        }, {});
      }
      return obj;
    };
    const normalized = JSON.stringify(sortKeys(diff));
    return crypto.createHash('md5').update(normalized).digest('hex');
  }
}

module.exports = DiffService;
