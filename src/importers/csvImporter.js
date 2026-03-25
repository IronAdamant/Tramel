'use strict';

const Recipe = require('../models/Recipe');

/**
 * CSV importer
 */
class CsvImporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Parse CSV string into array of objects
   */
  parseCsv(csvString) {
    const lines = csvString.split('\n').filter(line => line.trim());
    if (lines.length === 0) return [];

    // Parse header
    const headers = this.parseLine(lines[0]);

    // Parse data rows
    const data = [];
    for (let i = 1; i < lines.length; i++) {
      const values = this.parseLine(lines[i]);
      const row = {};
      headers.forEach((header, index) => {
        row[header.trim()] = values[index] ? values[index].trim() : '';
      });
      data.push(row);
    }

    return data;
  }

  /**
   * Parse a single CSV line, handling quotes
   */
  parseLine(line) {
    const result = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];

      if (char === '"') {
        if (inQuotes && line[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === ',' && !inQuotes) {
        result.push(current);
        current = '';
      } else {
        current += char;
      }
    }

    result.push(current);
    return result;
  }

  /**
   * Import from CSV string
   */
  importFromString(csvString) {
    const data = this.parseCsv(csvString);

    const results = [];
    for (const row of data) {
      try {
        // Map CSV columns to recipe fields
        const recipeData = {
          title: row.title || row.Name || row.recipe_name,
          description: row.description || row.Description || '',
          instructions: row.instructions || row.Instructions || row.Method || '',
          prep_time_minutes: parseInt(row.prep_time || row.PrepTime || row['prep_time_minutes'] || '0', 10),
          cook_time_minutes: parseInt(row.cook_time || row.CookTime || row['cook_time_minutes'] || '0', 10),
          servings: parseInt(row.servings || row.Servings || '1', 10),
          source: row.source || row.Source || '',
          difficulty: row.difficulty || row.Difficulty || 'medium',
          cuisine: row.cuisine || row.Cuisine || '',
          ingredients: this.parseIngredients(row.ingredients || row.Ingredients || ''),
          tags: this.parseTags(row.tags || row.Tags || '')
        };

        const recipe = this.recipe.create(recipeData);
        results.push({ success: true, recipe });
      } catch (err) {
        results.push({ success: false, error: err.message, data: row });
      }
    }

    return results;
  }

  /**
   * Parse ingredients from string (newline or comma separated)
   */
  parseIngredients(str) {
    if (!str) return [];

    // Try JSON array first
    try {
      return JSON.parse(str);
    } catch {}

    // Split by newline or semicolon
    const items = str.split(/[\n;]/).filter(s => s.trim());
    return items.map(item => {
      // Try to parse "quantity unit name" format
      const match = item.match(/^([\d.\/]+)?\s*(\w+)?\s+(.+)$/);
      if (match) {
        return {
          quantity: match[1] ? parseFloat(match[1]) : null,
          unit: match[2] || '',
          name: match[3].trim()
        };
      }
      return { name: item.trim(), quantity: null, unit: '' };
    });
  }

  /**
   * Parse tags from string
   */
  parseTags(str) {
    if (!str) return [];
    return str.split(/[,;|]/).map(t => t.trim()).filter(Boolean);
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

module.exports = CsvImporter;
