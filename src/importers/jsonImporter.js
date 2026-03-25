'use strict';

const Recipe = require('../models/Recipe');

/**
 * JSON importer
 */
class JsonImporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Import recipes from JSON string
   */
  importFromString(jsonString) {
    const data = JSON.parse(jsonString);

    if (Array.isArray(data)) {
      return this.importBatch(data);
    } else if (data.recipes) {
      return this.importBatch(data.recipes);
    } else {
      return [this.importSingle(data)];
    }
  }

  /**
   * Import a single recipe
   */
  importSingle(recipeData) {
    const { ingredients, tags, ...rest } = recipeData;

    const recipe = this.recipe.create({
      ...rest,
      ingredients: ingredients || [],
      tags: tags || []
    });

    return recipe;
  }

  /**
   * Import multiple recipes
   */
  importBatch(recipes) {
    const results = [];

    for (const recipeData of recipes) {
      try {
        const result = this.importSingle(recipeData);
        results.push({ success: true, recipe: result });
      } catch (err) {
        results.push({ success: false, error: err.message, data: recipeData });
      }
    }

    return results;
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

module.exports = JsonImporter;
