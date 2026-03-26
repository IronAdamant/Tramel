'use strict';

const fs = require('fs');
const Recipe = require('../models/Recipe');

/**
 * CSV exporter
 */
class CsvExporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Escape CSV field
   */
  escapeField(value) {
    if (value === null || value === undefined) return '';
    const str = String(value);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  }

  /**
   * Convert recipe to CSV row
   */
  recipeToRow(recipe) {
    const fields = [
      recipe.title || '',
      recipe.description || '',
      recipe.instructions || '',
      recipe.prep_time_minutes || 0,
      recipe.cook_time_minutes || 0,
      recipe.servings || 1,
      recipe.source || '',
      recipe.difficulty || '',
      recipe.cuisine || '',
      this.escapeField(recipe.ingredients ? JSON.stringify(recipe.ingredients) : ''),
      this.escapeField(recipe.tags ? recipe.tags.map(t => t.name || t).join(';') : '')
    ];

    return fields.join(',');
  }

  /**
   * Export recipes to CSV string
   */
  exportToString(recipeIds) {
    const header = 'title,description,instructions,prep_time_minutes,cook_time_minutes,servings,source,difficulty,cuisine,ingredients,tags';

    let recipes;
    if (recipeIds && recipeIds.length > 0) {
      recipes = recipeIds.map(id => this.recipe.getById(id)).filter(Boolean);
    } else {
      recipes = this.store.readAll('recipes').map(r => this.recipe.getById(r.id));
    }

    const rows = recipes.map(r => this.recipeToRow(r));
    return [header, ...rows].join('\n');
  }

  /**
   * Export recipes to CSV file
   */
  exportToFile(recipeIds, filePath) {
    const csv = this.exportToString(recipeIds);
    try {
      fs.writeFileSync(filePath, csv, 'utf8');
    } catch (err) {
      return { success: false, error: `Failed to write file: ${err.message}` };
    }

    return { success: true, count: recipeIds ? recipeIds.length : 0, file: filePath };
  }
}

module.exports = CsvExporter;
