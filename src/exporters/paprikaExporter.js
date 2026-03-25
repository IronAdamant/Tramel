'use strict';

const Recipe = require('../models/Recipe');

/**
 * Paprika format exporter
 */
class PaprikaExporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Convert recipe to Paprika format
   */
  toPaprikaFormat(recipe) {
    const paprika = {
      name: recipe.title,
      description: recipe.description || '',
      prep_time: recipe.prep_time_minutes ? `${recipe.prep_time_minutes} mins` : '',
      cook_time: recipe.cook_time_minutes ? `${recipe.cook_time_minutes} mins` : '',
      servings: String(recipe.servings || 1),
      servings_unit: 'servings',
      categories: (recipe.tags || []).map(t => t.name || t),
      difficulty: recipe.difficulty || 'medium',
      cuisine: recipe.cuisine || '',
      source: recipe.source || '',
      ingredients: this.formatIngredients(recipe.ingredients),
      instructions: this.formatInstructions(recipe.instructions),
      notes: '',
      rating: 0,
      created_at: recipe.created_at,
      image_url: recipe.image_url || ''
    };

    return paprika;
  }

  /**
   * Format ingredients for Paprika
   */
  formatIngredients(ingredients) {
    if (!ingredients || !Array.isArray(ingredients)) return '';

    return ingredients.map(ing => {
      let str = '';
      if (ing.quantity) {
        str += this.formatQuantity(ing.quantity);
        if (ing.unit) str += ' ';
      }
      if (ing.unit) str += ing.unit;
      if (str) str += ' ';
      str += ing.name;
      if (ing.notes) str += ` (${ing.notes})`;
      return str;
    }).join('\n');
  }

  /**
   * Format quantity (handle fractions)
   */
  formatQuantity(num) {
    if (!num) return '';
    if (Number.isInteger(num)) return String(num);

    // Common fractions
    const fractions = {
      0.25: '1/4',
      0.33: '1/3',
      0.5: '1/2',
      0.66: '2/3',
      0.75: '3/4'
    };

    const decimal = num % 1;
    const whole = Math.floor(num);

    for (const [dec, frac] of Object.entries(fractions)) {
      if (Math.abs(decimal - parseFloat(dec)) < 0.05) {
        return whole > 0 ? `${whole} ${frac}` : frac;
      }
    }

    return num.toFixed(2).replace(/\.?0+$/, '');
  }

  /**
   * Format instructions for Paprika
   */
  formatInstructions(instructions) {
    if (!instructions) return '';
    // Paprika uses newline-separated steps
    return instructions.split('\n').filter(s => s.trim()).join('\n');
  }

  /**
   * Export recipe to Paprika JSON string
   */
  exportRecipe(recipeId) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return null;

    return JSON.stringify(this.toPaprikaFormat(recipe), null, 2);
  }

  /**
   * Export all recipes to Paprika format
   */
  exportAll() {
    const recipes = this.store.readAll('recipes');
    const paprikaRecipes = recipes.map(r => {
      const full = this.recipe.getById(r.id);
      return this.toPaprikaFormat(full);
    });

    return JSON.stringify({ recipes: paprikaRecipes }, null, 2);
  }

  /**
   * Export to file
   */
  exportToFile(recipeId, filePath) {
    const fs = require('fs');
    const content = this.exportRecipe(recipeId);

    if (!content) {
      return { success: false, error: 'Recipe not found' };
    }

    fs.writeFileSync(filePath, content, 'utf8');
    return { success: true, file: filePath };
  }
}

module.exports = PaprikaExporter;
