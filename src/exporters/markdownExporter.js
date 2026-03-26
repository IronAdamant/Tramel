'use strict';

const fs = require('fs');
const path = require('path');
const Recipe = require('../models/Recipe');

/**
 * Markdown exporter - creates nice README-style output
 */
class MarkdownExporter {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Export single recipe to Markdown
   */
  exportRecipe(recipeId) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return null;

    const lines = [];

    // Title
    lines.push(`# ${recipe.title}`);
    lines.push('');

    // Meta info
    const meta = [];
    if (recipe.prep_time_minutes) meta.push(`Prep: ${recipe.prep_time_minutes} min`);
    if (recipe.cook_time_minutes) meta.push(`Cook: ${recipe.cook_time_minutes} min`);
    if (recipe.servings) meta.push(`Servings: ${recipe.servings}`);
    if (recipe.difficulty) meta.push(`Difficulty: ${recipe.difficulty}`);
    if (recipe.cuisine) meta.push(`Cuisine: ${recipe.cuisine}`);

    if (meta.length > 0) {
      lines.push(`**${meta.join(' | ')}**`);
      lines.push('');
    }

    // Description
    if (recipe.description) {
      lines.push(recipe.description);
      lines.push('');
    }

    // Ingredients
    lines.push('## Ingredients');
    lines.push('');

    if (recipe.ingredients && recipe.ingredients.length > 0) {
      for (const ing of recipe.ingredients) {
        let line = '- ';
        if (ing.quantity) line += `${ing.quantity} `;
        if (ing.unit) line += `${ing.unit} `;
        line += ing.name;
        if (ing.notes) line += ` (${ing.notes})`;
        lines.push(line);
      }
    } else {
      lines.push('_No ingredients listed_');
    }
    lines.push('');

    // Instructions
    lines.push('## Instructions');
    lines.push('');

    if (recipe.instructions) {
      const steps = recipe.instructions.split('\n').filter(s => s.trim());
      steps.forEach((step, i) => {
        lines.push(`${i + 1}. ${step.trim()}`);
      });
    } else {
      lines.push('_No instructions provided_');
    }
    lines.push('');

    // Tags
    if (recipe.tags && recipe.tags.length > 0) {
      lines.push('## Tags');
      lines.push('');
      lines.push(recipe.tags.map(t => `\`${t.name || t}\``).join(' '));
      lines.push('');
    }

    // Source
    if (recipe.source) {
      lines.push(`_Source: ${recipe.source}_`);
      lines.push('');
    }

    return lines.join('\n');
  }

  /**
   * Export all recipes to Markdown (multi-file)
   */
  exportAll() {
    const recipes = this.store.readAll('recipes');

    return recipes.map(recipe => ({
      filename: `${this.slugify(recipe.title)}.md`,
      content: this.exportRecipe(recipe.id)
    }));
  }

  /**
   * Export to Markdown file
   */
  exportToFile(recipeId, filePath) {
    const content = this.exportRecipe(recipeId);

    if (!content) {
      return { success: false, error: 'Recipe not found' };
    }

    try {
      fs.writeFileSync(filePath, content, 'utf8');
    } catch (err) {
      return { success: false, error: `Failed to write file: ${err.message}` };
    }
    return { success: true, file: filePath };
  }

  /**
   * Export all to directory
   */
  exportAllToDirectory(directory) {
    if (!fs.existsSync(directory)) {
      try {
        fs.mkdirSync(directory, { recursive: true });
      } catch (err) {
        return { success: false, error: `Failed to create directory: ${err.message}` };
      }
    }

    const recipes = this.store.readAll('recipes');
    const results = [];

    for (const recipe of recipes) {
      const filename = `${this.slugify(recipe.title)}.md`;
      const filePath = path.join(directory, filename);
      const content = this.exportRecipe(recipe.id);

      try {
        fs.writeFileSync(filePath, content, 'utf8');
      } catch (err) {
        return { success: false, error: `Failed to write file ${filename}: ${err.message}` };
      }
      results.push({ recipe: recipe.title, file: filename });
    }

    return { success: true, count: results.length, files: results };
  }

  /**
   * Convert title to filename-safe slug
   */
  slugify(title) {
    return (title || 'untitled')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
  }
}

module.exports = MarkdownExporter;
