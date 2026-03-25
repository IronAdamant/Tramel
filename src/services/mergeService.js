/**
 * MergeService
 * 3-way merge with conflict detection
 */

const DiffService = require('./diffService');

class MergeService {
  constructor() {
    this.diffService = new DiffService();
  }

  /**
   * Find the base version (common ancestor) for 3-way merge
   * In a real implementation, this would use commit history
   * For this simplified version, we assume base is provided
   * @param {Object} base - Base recipe state
   * @param {Object} target - Target branch state
   * @param {Object} source - Source branch state
   * @returns {Object} { success, result, conflicts }
   */
  threeWayMerge(base, target, source) {
    if (!base || !target || !source) {
      return {
        success: false,
        error: 'base, target, and source are all required',
        conflicts: []
      };
    }

    const conflicts = [];
    const result = JSON.parse(JSON.stringify(target)); // Start with target as base

    // Merge ingredients
    const ingredientResult = this.mergeIngredients(
      base.ingredients || [],
      target.ingredients || [],
      source.ingredients || [],
      conflicts
    );
    result.ingredients = ingredientResult;

    // Merge fields
    this.mergeFields(base, target, source, result, conflicts);

    // Merge instructions
    const instructionResult = this.mergeInstructions(
      base.instructions || [],
      target.instructions || [],
      source.instructions || [],
      conflicts
    );
    result.instructions = instructionResult;

    return {
      success: conflicts.length === 0,
      result,
      conflicts
    };
  }

  /**
   * Merge ingredients using 3-way diff
   */
  mergeIngredients(baseIngredients, targetIngredients, sourceIngredients, conflicts) {
    const baseDiff = this.diffService.diff(baseIngredients, targetIngredients);
    const sourceDiff = this.diffService.diff(baseIngredients, sourceIngredients);

    // Check for conflicts in modified items
    const conflictItems = this.findConflictingModifications(
      baseDiff.modified,
      sourceDiff.modified
    );

    for (const conflict of conflictItems) {
      conflicts.push({
        type: 'ingredient',
        fieldPath: `ingredients.${conflict.index}`,
        baseValue: baseIngredients[conflict.index],
        targetValue: conflict.targetItem,
        sourceValue: conflict.sourceItem
      });
    }

    // Auto-merge non-conflicting changes
    const merged = this.autoMergeIngredients(baseIngredients, targetIngredients, sourceIngredients);

    return merged;
  }

  /**
   * Find conflicting modifications between target and source
   */
  findConflictingModifications(targetMods, sourceMods) {
    const conflicts = [];

    // Create maps by ingredient name
    const targetMap = new Map();
    const sourceMap = new Map();

    targetMods.forEach(m => {
      targetMap.set(m.before.name.toLowerCase(), m);
    });

    sourceMods.forEach(m => {
      sourceMap.set(m.before.name.toLowerCase(), m);
    });

    // Check each target modification against source modifications
    for (const [name, targetMod] of targetMap) {
      const sourceMod = sourceMap.get(name);

      if (sourceMod) {
        // Both modified the same ingredient differently
        conflicts.push({
          index: targetMod.before._index || 0,
          targetItem: targetMod.after,
          sourceItem: sourceMod.after,
          baseItem: targetMod.before
        });
      } else {
        // Check if source removed this ingredient that target modified
        const sourceRemoved = sourceMods.find(m => m.before.name.toLowerCase() === name);
        if (sourceRemoved) {
          conflicts.push({
            index: targetMod.before._index || 0,
            targetItem: targetMod.after,
            sourceItem: null, // removed
            baseItem: targetMod.before
          });
        }
      }
    }

    // Check if source modified something target removed
    for (const sourceMod of sourceMods) {
      const targetRemoved = targetMods.find(m => m.before.name.toLowerCase() === sourceMod.before.name.toLowerCase());
      if (targetRemoved) {
        // Already caught above
      } else if (!targetMap.has(sourceMod.before.name.toLowerCase())) {
        // Source modified something not in target modifications
        // This would be caught in the reverse check above
      }
    }

    return conflicts;
  }

  /**
   * Auto-merge ingredients (non-conflicting changes)
   */
  autoMergeIngredients(baseIngredients, targetIngredients, sourceIngredients) {
    const baseSet = new Set(baseIngredients.map(i => i.name.toLowerCase()));
    const targetSet = new Set(targetIngredients.map(i => i.name.toLowerCase()));
    const sourceSet = new Set(sourceIngredients.map(i => i.name.toLowerCase()));

    const result = [];

    // Add all target ingredients not removed in source
    for (const ing of targetIngredients) {
      const key = ing.name.toLowerCase();
      if (sourceSet.has(key)) {
        // In source, check if modified
        const sourceIng = sourceIngredients.find(i => i.name.toLowerCase() === key);
        const baseIng = baseIngredients.find(i => i.name.toLowerCase() === key);

        if (baseIng) {
          // Check if source changed it differently than target
          const targetChanged = this.ingredientChanged(ing, baseIng);
          const sourceChanged = this.ingredientChanged(sourceIng, baseIng);

          if (!targetChanged && !sourceChanged) {
            result.push(ing); // Neither changed, use target
          } else if (targetChanged && !sourceChanged) {
            result.push(ing); // Only target changed
          } else if (!targetChanged && sourceChanged) {
            result.push(sourceIng); // Only source changed
          } else if (JSON.stringify(ing) === JSON.stringify(sourceIng)) {
            result.push(ing); // Same change in both
          }
          // If different changes, it's a conflict (already handled)
        } else {
          result.push(ing);
        }
      } else {
        // Not in source, target keeps it
        result.push(ing);
      }
    }

    // Add new ingredients from source not in target
    for (const ing of sourceIngredients) {
      const key = ing.name.toLowerCase();
      if (!targetSet.has(key) && !baseSet.has(key)) {
        result.push(ing);
      }
    }

    return result;
  }

  /**
   * Check if an ingredient was modified from base
   */
  ingredientChanged(ing, baseIng) {
    return ing.quantity !== baseIng.quantity ||
           ing.unit !== baseIng.unit ||
           ing.notes !== baseIng.notes ||
           ing.prep !== baseIng.prep;
  }

  /**
   * Merge scalar fields (title, description, etc.)
   */
  mergeFields(base, target, source, result, conflicts) {
    const scalarFields = ['title', 'description', 'servings', 'prepTime', 'cookTime',
                          'totalTime', 'difficulty', 'cuisine', 'mealType', 'source', 'notes'];

    for (const field of scalarFields) {
      const baseVal = base[field];
      const targetVal = target[field];
      const sourceVal = source[field];

      if (targetVal === sourceVal) {
        // Both made the same change or both unchanged
        result[field] = targetVal;
      } else if (targetVal === baseVal) {
        // Only source changed
        result[field] = sourceVal;
      } else if (sourceVal === baseVal) {
        // Only target changed
        result[field] = targetVal;
      } else {
        // Both changed differently - CONFLICT
        conflicts.push({
          type: 'field',
          fieldPath: field,
          baseValue: baseVal,
          targetValue: targetVal,
          sourceValue: sourceVal
        });
        // Use target as default resolution
        result[field] = targetVal;
      }
    }

    // Merge tags (array)
    result.tags = this.mergeArrays(base.tags, target.tags, source.tags);

    // Merge dietary flags
    result.dietaryFlags = this.mergeObjects(base.dietaryFlags, target.dietaryFlags, source.dietaryFlags);
  }

  /**
   * Merge instructions
   */
  mergeInstructions(baseInstructions, targetInstructions, sourceInstructions, conflicts) {
    const baseSet = new Set(baseInstructions);
    const targetSet = new Set(targetInstructions);
    const sourceSet = new Set(sourceInstructions);

    const result = [];

    // Add all target instructions
    for (const instr of targetInstructions) {
      if (sourceSet.has(instr)) {
        // In both - no conflict
        result.push(instr);
      } else if (!baseSet.has(instr)) {
        // New in target
        result.push(instr);
      }
      // If removed in source but exists in target - potential conflict
      else if (baseSet.has(instr) && !sourceSet.has(instr)) {
        // Check if target modified vs base
        const baseIdx = baseInstructions.indexOf(instr);
        const targetIdx = targetInstructions.indexOf(instr);

        if (targetIdx !== baseIdx) {
          // Position changed - conflict
          conflicts.push({
            type: 'instruction',
            fieldPath: `instructions`,
            baseValue: instr,
            targetValue: instr,
            sourceValue: null
          });
        }
        result.push(instr);
      }
    }

    // Add new instructions from source not in target
    for (const instr of sourceInstructions) {
      if (!targetSet.has(instr) && !baseSet.has(instr)) {
        result.push(instr);
      }
    }

    return result;
  }

  /**
   * Merge arrays (for tags)
   */
  mergeArrays(baseArr, targetArr, sourceArr) {
    const baseSet = new Set(baseArr || []);
    const targetSet = new Set(targetArr || []);
    const sourceSet = new Set(sourceArr || []);

    const result = new Set();

    // Add target items
    for (const item of targetArr || []) {
      result.add(item);
    }

    // Add source items
    for (const item of sourceArr || []) {
      result.add(item);
    }

    return Array.from(result);
  }

  /**
   * Merge objects (for dietaryFlags)
   */
  mergeObjects(baseObj, targetObj, sourceObj) {
    const base = baseObj || {};
    const target = targetObj || {};
    const source = sourceObj || {};

    const allKeys = new Set([...Object.keys(base), ...Object.keys(target), ...Object.keys(source)]);
    const result = {};

    for (const key of allKeys) {
      const baseVal = base[key];
      const targetVal = target[key];
      const sourceVal = source[key];

      if (targetVal === sourceVal) {
        result[key] = targetVal;
      } else if (targetVal === baseVal) {
        result[key] = sourceVal;
      } else if (sourceVal === baseVal) {
        result[key] = targetVal;
      } else {
        // Conflict - prefer target
        result[key] = targetVal;
      }
    }

    return result;
  }

  /**
   * Detect if a specific conflict exists between target and source
   */
  detectConflict(targetItem, sourceItem, baseItem) {
    if (!baseItem) return false;
    if (!targetItem && !sourceItem) return false;
    if (targetItem && !sourceItem) return true;
    if (!targetItem && sourceItem) return true;

    // Both modified differently
    return JSON.stringify(targetItem) !== JSON.stringify(sourceItem);
  }

  /**
   * Resolve a conflict with a specific value
   * @param {Object} conflict - Conflict object
   * @param {string} resolution - 'target', 'source', or 'manual'
   * @param {*} manualValue - Value for manual resolution
   * @returns {*} Resolved value
   */
  resolveConflict(conflict, resolution, manualValue = null) {
    switch (resolution) {
      case 'target':
        return conflict.targetValue;
      case 'source':
        return conflict.sourceValue;
      case 'manual':
        return manualValue;
      default:
        return conflict.targetValue; // Default to target
    }
  }
}

module.exports = MergeService;
