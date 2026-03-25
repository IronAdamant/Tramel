'use strict';

const { FileStore } = require('../utils/fileStore');

/**
 * Initialize database schema (creates JSON store files).
 * Called by FileStore.initializeAll() or can be called directly.
 */
function initializeSchema(fileStore) {
  const tables = [
    'recipes',
    'ingredients',
    'tags',
    'recipe_tags',
    'meal_plans',
    'meal_plan_entries',
    'shopping_lists',
    'shopping_list_items',
    'collections',
    'collection_recipes',
    'dietary_profiles',
    'cooking_logs',
    'ingredient_prices'
  ];

  tables.forEach(table => fileStore.initializeTable(table));
}

/**
 * Create schema with default data
 */
function createSchemaWithDefaults(fileStore) {
  // Initialize all tables
  initializeSchema(fileStore);

  // Add some default tags if empty
  const tags = fileStore.readAll('tags');
  if (tags.length === 0) {
    const defaultTags = [
      'breakfast', 'lunch', 'dinner', 'snack',
      'vegetarian', 'vegan', 'gluten-free', 'dairy-free',
      'quick', 'easy', 'healthy', 'comfort-food'
    ];
    defaultTags.forEach(name => {
      fileStore.create('tags', { name });
    });
  }

  // Add default dietary profile if none exist
  const profiles = fileStore.readAll('dietary_profiles');
  if (profiles.length === 0) {
    fileStore.create('dietary_profiles', {
      name: 'Default',
      restrictions: [],
      allergens: [],
      nutrition_goals: {
        calories: 2000,
        protein: 50,
        carbs: 250,
        fat: 65
      }
    });
  }
}

module.exports = {
  initializeSchema,
  createSchemaWithDefaults
};
