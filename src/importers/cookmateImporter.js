'use strict';

const Recipe = require('../models/Recipe');

/**
 * Cookmate app importer
 * Cookmate uses a different JSON format
 */
class CookmateImporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Import from Cookmate JSON string
   */
  importFromString(jsonString) {
    const data = JSON.parse(jsonString);

    // Cookmate may have different structures
    let recipes = [];

    if (Array.isArray(data)) {
      recipes = data;
    } else if (data.recipe) {
      recipes = [data.recipe];
    } else if (data.data) {
      recipes = Array.isArray(data.data) ? data.data : [data.data];
    } else {
      recipes = [data];
    }

    const results = [];
    for (const cookmateRecipe of recipes) {
      try {
        const recipe = this.convertCookmateRecipe(cookmateRecipe);
        const result = this.recipe.create(recipe);
        results.push({ success: true, recipe: result });
      } catch (err) {
        results.push({ success: false, error: err.message, data: cookmateRecipe.title || cookmateRecipe.name });
      }
    }

    return results;
  }

  /**
   * Convert Cookmate format to our format
   */
  convertCookmateRecipe(cookmate) {
    return {
      title: cookmate.title || cookmate.name || 'Untitled',
      description: cookmate.description || cookmate.summary || '',
      instructions: this.convertCookmateInstructions(cookmate),
      prep_time_minutes: parseInt(cookmate.prep_time || cookmate.prepTime || '0', 10),
      cook_time_minutes: parseInt(cookmate.cook_time || cookmate.cookTime || '0', 10),
      servings: parseInt(cookmate.servings || cookmate.yield || cookmate.serving || '1', 10),
      source: 'Cookmate Import',
      difficulty: cookmate.difficulty || 'medium',
      cuisine: cookmate.cuisine || '',
      ingredients: this.convertCookmateIngredients(cookmate.ingredients),
      tags: this.convertCookmateTags(cookmate.tags || cookmate.categories)
    };
  }

  /**
   * Convert Cookmate instructions
   */
  convertCookmateInstructions(cookmate) {
    if (Array.isArray(cookmate.steps)) {
      return cookmate.steps.map((s, i) => `${i + 1}. ${s}`).join('\n');
    }
    if (Array.isArray(cookmate.instructions)) {
      return cookmate.instructions.join('\n\n');
    }
    return cookmate.instructions || cookmate.directions || cookmate.method || '';
  }

  /**
   * Convert Cookmate ingredients
   */
  convertCookmateIngredients(ingredients) {
    if (!ingredients) return [];
    if (Array.isArray(ingredients)) {
      return ingredients.map(ing => {
        if (typeof ing === 'string') {
          return { name: ing, quantity: null, unit: '' };
        }
        return {
          name: ing.name || ing.item || 'Unknown',
          quantity: ing.quantity ? parseFloat(ing.quantity) : (ing.amount ? parseFloat(ing.amount) : null),
          unit: ing.unit || ing.measurement || '',
          notes: ing.notes || ''
        };
      });
    }
    return [];
  }

  /**
   * Convert Cookmate tags
   */
  convertCookmateTags(tags) {
    if (!tags) return [];
    if (typeof tags === 'string') {
      return tags.split(',').map(t => t.trim().toLowerCase());
    }
    if (Array.isArray(tags)) {
      return tags.map(t => (typeof t === 'string' ? t : t.name).toLowerCase());
    }
    return [];
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

module.exports = CookmateImporter;
