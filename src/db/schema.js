'use strict';

const { v4: uuidv4 } = require('uuid');

/**
 * Initialize database schema (creates SQLite tables).
 * Called by migrations system via runMigrations().
 */
function initializeSchema(db) {
  // Note: Tables are created via migrations.js:migrateSchema()
  // This function is kept for compatibility but schema creation
  // is now handled by the migration system.
}

/**
 * Create schema with default data
 */
function createSchemaWithDefaults(db) {
  // Initialize schema via migrations (already done in db/index.js)
  initializeSchema(db);

  // Add some default tags if empty
  const tags = db.all('SELECT COUNT(*) as count FROM tags');
  if (tags[0].count === 0) {
    const defaultTags = [
      'breakfast', 'lunch', 'dinner', 'snack',
      'vegetarian', 'vegan', 'gluten-free', 'dairy-free',
      'quick', 'easy', 'healthy', 'comfort-food'
    ];
    const insert = db.prepare('INSERT INTO tags (id, name) VALUES (?, ?)');
    defaultTags.forEach(name => {
      insert.run(uuidv4(), name);
    });
  }

  // Add default dietary profile if none exist
  const profiles = db.all('SELECT COUNT(*) as count FROM dietary_profiles');
  if (profiles[0].count === 0) {
    const id = uuidv4();
    db.run(
      `INSERT INTO dietary_profiles (id, name, restrictions, allergens, nutrition_goals)
       VALUES (?, ?, ?, ?, ?)`,
      [
        id,
        'Default',
        JSON.stringify([]),
        JSON.stringify([]),
        JSON.stringify({ calories: 2000, protein: 50, carbs: 250, fat: 65 })
      ]
    );
  }
}

/**
 * Legacy alias for compatibility
 */
const createSchema = createSchemaWithDefaults;

module.exports = {
  initializeSchema,
  createSchemaWithDefaults,
  createSchema
};
