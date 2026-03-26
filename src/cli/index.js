'use strict';

const path = require('path');
const { getDatabase } = require('../db');
const Recipe = require('../models/Recipe');
const Tag = require('../models/Tag');
const MealPlan = require('../models/MealPlan');
const ShoppingList = require('../models/ShoppingList');
const Collection = require('../models/Collection');

/**
 * Simple CLI for RecipeLab
 * Usage: node src/cli/index.js <command> [options]
 */

// Initialize database
const db = getDatabase(path.join(__dirname, '../../data'));
const recipe = new Recipe(db);
const tag = new Tag(db);
const mealPlan = new MealPlan(db);
const shoppingList = new ShoppingList(db);
const collection = new Collection(db);

/**
 * Parse command line arguments
 */
function parseArgs(args) {
  const cmd = args[2] || 'help';
  const subCmd = args[3];
  const options = {};

  for (let i = 4; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const [key, value] = arg.slice(2).split('=');
      options[key] = value;
    } else if (arg.startsWith('-')) {
      options[arg.slice(1)] = true;
    }
  }

  return { cmd, subCmd, options };
}

/**
 * Print help message
 */
function printHelp() {
  console.log(`
RecipeLab CLI

Usage: node src/cli/index.js <command> [options]

Commands:
  recipes list              List all recipes
  recipes get <id>          Get recipe by ID
  recipes create <title>    Create a new recipe
  recipes search <query>    Search recipes
  recipes delete <id>       Delete a recipe

  tags list                 List all tags
  tags create <name>        Create a new tag

  meal-plans list           List all meal plans
  meal-plans create <name>  Create a new meal plan
  meal-plans generate       Generate a weekly plan

  shopping-lists list       List all shopping lists
  shopping-lists generate <planId>  Generate from meal plan

  collections list          List all collections
  collections create <name> Create a new collection

  help                      Show this help message

Options:
  --limit=N                 Limit results (default: 20)
  --format=json             Output format (text or json)

Examples:
  node src/cli/index.js recipes list
  node src/cli/index.js recipes search pasta
  node src/cli/index.js recipes create "My Recipe" --difficulty=medium
  `);
}

/**
 * Format recipe for CLI output
 */
function formatRecipe(r, format = 'text') {
  if (format === 'json') {
    return JSON.stringify(r, null, 2);
  }

  let output = '';
  output += `ID: ${r.id}\n`;
  output += `Title: ${r.title}\n`;
  if (r.description) output += `Description: ${r.description}\n`;
  output += `Prep: ${r.prep_time_minutes || 0} min | Cook: ${r.cook_time_minutes || 0} min\n`;
  output += `Servings: ${r.servings || 1}\n`;
  if (r.ingredients && r.ingredients.length > 0) {
    output += `Ingredients (${r.ingredients.length}):\n`;
    r.ingredients.forEach(ing => {
      const qty = ing.quantity ? `${ing.quantity}` : '';
      output += `  - ${qty} ${ing.unit || ''} ${ing.name}\n`;
    });
  }
  return output;
}

/**
 * Command handlers
 */
const commands = {
  // Recipes
  recipes: {
    list: (subCmd, options) => {
      const result = recipe.getAll({ limit: parseInt(options.limit) || 20 });
      console.log(`Found ${result.total} recipes:\n`);
      result.data.forEach(r => {
        console.log(`[${r.id}] ${r.title}`);
      });
    },
    get: (subCmd, options) => {
      const r = recipe.getById(subCmd);
      if (r) {
        console.log(formatRecipe(r, options.format));
      } else {
        console.log('Recipe not found');
      }
    },
    create: (subCmd, options) => {
      const r = recipe.create({
        title: subCmd || 'Untitled Recipe',
        difficulty: options.difficulty || 'medium',
        servings: parseInt(options.servings) || 1
      });
      console.log('Created recipe:', r.id);
    },
    search: (subCmd, options) => {
      const limit = parseInt(options.limit) || 20;
      const results = recipe.search({ query: subCmd }).slice(0, limit);
      console.log(`Found ${results.length} recipes matching "${subCmd}":\n`);
      results.forEach(r => {
        console.log(`[${r.id}] ${r.title}`);
      });
    },
    delete: (subCmd, options) => {
      const deleted = recipe.delete(subCmd);
      console.log(deleted ? 'Recipe deleted' : 'Recipe not found');
    }
  },

  // Tags
  tags: {
    list: (subCmd, options) => {
      const result = tag.getAll({ limit: 100 });
      console.log(`Found ${result.total} tags:\n`);
      result.data.forEach(t => {
        console.log(`[${t.id}] ${t.name}`);
      });
    },
    create: (subCmd, options) => {
      if (!subCmd) {
        console.log('Tag name required');
        return;
      }
      const t = tag.create({ name: subCmd });
      console.log('Created tag:', t.name);
    }
  },

  // Meal Plans
  'meal-plans': {
    list: (subCmd, options) => {
      const result = mealPlan.getAll({ limit: 20 });
      console.log(`Found ${result.total} meal plans:\n`);
      result.data.forEach(p => {
        console.log(`[${p.id}] ${p.name} (${p.start_date} to ${p.end_date || 'ongoing'})`);
      });
    },
    create: (subCmd, options) => {
      const p = mealPlan.create({
        name: subCmd || 'My Meal Plan',
        start_date: new Date().toISOString().split('T')[0]
      });
      console.log('Created meal plan:', p.id);
    },
    generate: (subCmd, options) => {
      const MealPlannerService = require('../services/mealPlannerService');
      const service = new MealPlannerService(db);
      const plan = service.generateWeeklyPlan({
        servings: parseInt(options.servings) || 2
      });
      console.log('Generated weekly plan:', plan.id);
    }
  },

  // Shopping Lists
  'shopping-lists': {
    list: (subCmd, options) => {
      const result = shoppingList.getAll({ limit: 20 });
      console.log(`Found ${result.total} shopping lists:\n`);
      result.data.forEach(l => {
        console.log(`[${l.id}] ${l.name}`);
      });
    },
    generate: (subCmd, options) => {
      const ShoppingListService = require('../services/shoppingListService');
      const service = new ShoppingListService(db);
      const list = service.generateFromMealPlan(subCmd);
      if (list) {
        console.log('Generated shopping list:', list.id, '-', list.name);
      } else {
        console.log('Meal plan not found');
      }
    }
  },

  // Collections
  collections: {
    list: (subCmd, options) => {
      const result = collection.getAll({ limit: 20 });
      console.log(`Found ${result.total} collections:\n`);
      result.data.forEach(c => {
        console.log(`[${c.id}] ${c.name} (${c.recipe_count || 0} recipes)`);
      });
    },
    create: (subCmd, options) => {
      const c = collection.create({
        name: subCmd || 'My Collection',
        description: options.description || ''
      });
      console.log('Created collection:', c.id);
    }
  },

  // Help
  help: () => printHelp()
};

/**
 * Main entry point
 */
function main() {
  const { cmd, subCmd, options } = parseArgs(process.argv);

  if (commands[cmd]) {
    if (typeof commands[cmd] === 'function') {
      commands[cmd]();
    } else if (commands[cmd][subCmd]) {
      commands[cmd][subCmd](subCmd, options);
    } else {
      // Default to list for known command groups
      if (commands[cmd].list) {
        commands[cmd].list(subCmd, options);
      } else {
        printHelp();
      }
    }
  } else if (cmd === 'help') {
    printHelp();
  } else {
    console.log(`Unknown command: ${cmd}`);
    printHelp();
  }
}

main();
