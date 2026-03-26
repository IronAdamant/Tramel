'use strict';

const fs = require('fs');
const Recipe = require('../models/Recipe');

/**
 * JSON exporter
 */
class JsonExporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Export recipe to JSON string
   */
  exportRecipe(recipeId) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return null;

    return JSON.stringify(recipe, null, 2);
  }

  /**
   * Export all recipes to JSON string
   */
  exportAll() {
    const recipes = this.store.readAll('recipes');
    const fullRecipes = recipes.map(r => this.recipe.getById(r.id));

    return JSON.stringify({ recipes: fullRecipes }, null, 2);
  }

  /**
   * Export recipes to file
   */
  exportToFile(recipeIds, filePath) {
    const data = recipeIds
      ? recipeIds.map(id => this.recipe.getById(id)).filter(Boolean)
      : this.store.readAll('recipes').map(r => this.recipe.getById(r.id));

    const json = JSON.stringify({ recipes: data }, null, 2);
    try {
      fs.writeFileSync(filePath, json, 'utf8');
    } catch (err) {
      return { success: false, error: `Failed to write file: ${err.message}` };
    }

    return { success: true, count: data.length, file: filePath };
  }
}

module.exports = JsonExporter;
