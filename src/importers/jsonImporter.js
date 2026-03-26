'use strict';

const Recipe = require('../models/Recipe');

const fs = require('fs');

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
    let data;
    try {
      data = JSON.parse(jsonString);
    } catch (err) {
      return [{ success: false, error: `Invalid JSON: ${err.message}` }];
    }

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
    let content;
    try {
      content = fs.readFileSync(filePath, 'utf8');
    } catch (err) {
      return [{ success: false, error: `Failed to read file: ${err.message}` }];
    }
    return this.importFromString(content);
  }
}

module.exports = JsonImporter;
