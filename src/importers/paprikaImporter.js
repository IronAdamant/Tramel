'use strict';

const Recipe = require('../models/Recipe');

/**
 * Paprika app importer
 * Paprika exports in a specific JSON format
 */
class PaprikaImporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Import from Paprika JSON string
   */
  importFromString(jsonString) {
    const data = JSON.parse(jsonString);

    // Paprika format has "recipes" array
    const recipes = data.recipes || [data];

    const results = [];
    for (const paprikaRecipe of recipes) {
      try {
        const recipe = this.convertPaprikaRecipe(paprikaRecipe);
        const result = this.recipe.create(recipe);
        results.push({ success: true, recipe: result });
      } catch (err) {
        results.push({ success: false, error: err.message, data: paprikaRecipe.name });
      }
    }

    return results;
  }

  /**
   * Convert Paprika format to our format
   */
  convertPaprikaRecipe(paprika) {
    return {
      title: paprika.name || paprika.recipe_name || 'Untitled',
      description: paprika.description || '',
      instructions: this.convertPaprikaInstructions(paprika),
      prep_time_minutes: this.parsePaprikaTime(paprika.prep_time),
      cook_time_minutes: this.parsePaprikaTime(paprika.cook_time),
      servings: parseInt(paprika.servings || paprika.yield || '1', 10),
      source: 'Paprika Import',
      difficulty: 'medium',
      cuisine: paprika.cuisine || '',
      ingredients: this.convertPaprikaIngredients(paprika.ingredients),
      tags: this.convertPaprikaCategories(paprika.categories)
    };
  }

  /**
   * Convert Paprika instructions (may be array or string)
   */
  convertPaprikaInstructions(paprika) {
    if (Array.isArray(paprika.instructions)) {
      return paprika.instructions.join('\n\n');
    }
    return paprika.instructions || paprika.directions || '';
  }

  /**
   * Parse Paprika time string (e.g., "30 mins")
   */
  parsePaprikaTime(timeStr) {
    if (!timeStr) return 0;
    if (typeof timeStr === 'number') return timeStr;

    const match = timeStr.match(/(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  }

  /**
   * Convert Paprika ingredients (may be array or string)
   */
  convertPaprikaIngredients(ingredients) {
    if (!ingredients) return [];
    if (Array.isArray(ingredients)) {
      return ingredients.map(ing => {
        if (typeof ing === 'string') {
          return this.parseIngredientString(ing);
        }
        return {
          name: ing.name || ing.item || 'Unknown',
          quantity: ing.amount ? parseFloat(ing.amount) : null,
          unit: ing.unit || '',
          notes: ing.notes || ''
        };
      });
    }

    // String - split by newlines
    return ingredients.split('\n')
      .filter(s => s.trim())
      .map(s => this.parseIngredientString(s));
  }

  /**
   * Parse ingredient string
   */
  parseIngredientString(str) {
    // Try "1 1/2 cups flour" format
    const match = str.match(/^([\d.\/\s]+)?\s*(cups?|tbsp?|tsp?|oz|lb|g|kg|ml|l|pieces?|cloves?)?\s*(.+)$/i);

    if (match) {
      let quantity = null;
      if (match[1]) {
        const qtyStr = match[1].trim();
        // Handle fractions
        if (qtyStr.includes('/')) {
          const parts = qtyStr.split(' ');
          let total = 0;
          for (const part of parts) {
            if (part.includes('/')) {
              const [num, denom] = part.split('/');
              total += parseFloat(num) / parseFloat(denom);
            } else {
              total += parseFloat(part);
            }
          }
          quantity = total;
        } else {
          quantity = parseFloat(qtyStr);
        }
      }

      return {
        quantity,
        unit: match[2] || '',
        name: match[3].trim()
      };
    }

    return { name: str.trim(), quantity: null, unit: '' };
  }

  /**
   * Convert Paprika categories to tags
   */
  convertPaprikaCategories(categories) {
    if (!categories) return [];
    if (typeof categories === 'string') {
      return categories.split(',').map(c => c.trim().toLowerCase());
    }
    return categories.map(c => c.toLowerCase());
  }

  /**
   * Import from file
   */
  importFromFile(filePath) {
    const fs = require('fs');
    const content = fs.readFileSync(filePath, 'utf8');
    return this.importFromString(content);
  }
}

module.exports = PaprikaImporter;
