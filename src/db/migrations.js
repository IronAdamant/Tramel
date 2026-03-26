'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Database migration system.
 * Manages schema versions and applies migrations.
 */
class MigrationRunner {
  /**
   * @param {Object} db - Database wrapper with run/get/all methods
   */
  constructor(db) {
    this.db = db;
    this._ensureMigrationsTable();
  }

  /**
   * Create migrations tracking table
   */
  _ensureMigrationsTable() {
    this.db.run(`
      CREATE TABLE IF NOT EXISTS _migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        applied_at TEXT DEFAULT (datetime('now'))
      )
    `);
  }

  /**
   * Check if migration is applied
   * @param {string} name - Migration name
   * @returns {boolean}
   */
  _isApplied(name) {
    const row = this.db.get(
      'SELECT id FROM _migrations WHERE name = ?',
      [name]
    );
    return row !== null;
  }

  /**
   * Mark migration as applied
   * @param {string} name - Migration name
   */
  _markApplied(name) {
    this.db.run(
      'INSERT OR IGNORE INTO _migrations (name) VALUES (?)',
      [name]
    );
  }

  /**
   * Get applied migrations
   * @returns {Array} Array of migration names
   */
  getApplied() {
    return this.db.all(
      'SELECT name, applied_at FROM _migrations ORDER BY id'
    );
  }

  /**
   * Run a migration
   * @param {string} name - Migration name
   * @param {Function} up - Migration up function
   */
  migrate(name, up) {
    if (this._isApplied(name)) {
      return false;
    }

    this.db.transaction(() => {
      up(this.db);
      this._markApplied(name);
    });

    return true;
  }

  /**
   * Get current schema version
   * @returns {number}
   */
  getVersion() {
    const result = this.db.get(
      'SELECT COUNT(*) as count FROM _migrations'
    );
    return result ? result.count : 0;
  }
}

/**
 * Default schema migration
 * Creates all application tables.
 */
function migrateSchema(db) {
  // Recipes table
  db.run(`
    CREATE TABLE IF NOT EXISTS recipes (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      description TEXT,
      instructions TEXT,
      prep_time INTEGER,
      cook_time INTEGER,
      servings INTEGER DEFAULT 1,
      difficulty TEXT,
      cuisine TEXT,
      ingredients TEXT,
      tags TEXT,
      nutrition TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Ingredients table
  db.run(`
    CREATE TABLE IF NOT EXISTS ingredients (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      category TEXT,
      unit TEXT,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Tags table
  db.run(`
    CREATE TABLE IF NOT EXISTS tags (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL UNIQUE,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Recipe-Tags junction
  db.run(`
    CREATE TABLE IF NOT EXISTS recipe_tags (
      recipe_id TEXT,
      tag_id TEXT,
      PRIMARY KEY (recipe_id, tag_id),
      FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
      FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    )
  `);

  // Meal plans table
  db.run(`
    CREATE TABLE IF NOT EXISTS meal_plans (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      start_date TEXT,
      end_date TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Meal plan entries
  db.run(`
    CREATE TABLE IF NOT EXISTS meal_plan_entries (
      id TEXT PRIMARY KEY,
      meal_plan_id TEXT NOT NULL,
      recipe_id TEXT,
      date TEXT,
      meal_type TEXT,
      servings INTEGER DEFAULT 1,
      notes TEXT,
      FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE CASCADE,
      FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE SET NULL
    )
  `);

  // Shopping lists
  db.run(`
    CREATE TABLE IF NOT EXISTS shopping_lists (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      meal_plan_id TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id) ON DELETE SET NULL
    )
  `);

  // Shopping list items
  db.run(`
    CREATE TABLE IF NOT EXISTS shopping_list_items (
      id TEXT PRIMARY KEY,
      shopping_list_id TEXT NOT NULL,
      ingredient_id TEXT,
      name TEXT NOT NULL,
      quantity REAL,
      unit TEXT,
      checked INTEGER DEFAULT 0,
      FOREIGN KEY (shopping_list_id) REFERENCES shopping_lists(id) ON DELETE CASCADE,
      FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE SET NULL
    )
  `);

  // Collections
  db.run(`
    CREATE TABLE IF NOT EXISTS collections (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      description TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Collection recipes junction
  db.run(`
    CREATE TABLE IF NOT EXISTS collection_recipes (
      collection_id TEXT,
      recipe_id TEXT,
      added_at TEXT DEFAULT (datetime('now')),
      PRIMARY KEY (collection_id, recipe_id),
      FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
      FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
    )
  `);

  // Dietary profiles
  db.run(`
    CREATE TABLE IF NOT EXISTS dietary_profiles (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      restrictions TEXT,
      allergens TEXT,
      nutrition_goals TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
    )
  `);

  // Cooking logs
  db.run(`
    CREATE TABLE IF NOT EXISTS cooking_logs (
      id TEXT PRIMARY KEY,
      recipe_id TEXT,
      cooked_at TEXT,
      rating INTEGER,
      notes TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE SET NULL
    )
  `);

  // Create indexes
  db.run('CREATE INDEX IF NOT EXISTS idx_recipes_name ON recipes(name)');
  db.run('CREATE INDEX IF NOT EXISTS idx_ingredients_name ON ingredients(name)');
  db.run('CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)');
  db.run('CREATE INDEX IF NOT EXISTS idx_meal_plans_dates ON meal_plans(start_date, end_date)');
  db.run('CREATE INDEX IF NOT EXISTS idx_meal_plan_entries_date ON meal_plan_entries(date)');
  db.run('CREATE INDEX IF NOT EXISTS idx_shopping_lists_meal_plan ON shopping_lists(meal_plan_id)');
}

/**
 * Run all migrations
 * @param {Object} db - Database wrapper
 * @returns {Object} Migration result
 */
function runMigrations(db) {
  const runner = new MigrationRunner(db);
  let applied = 0;

  // Run schema migration
  if (runner.migrate('001_schema', migrateSchema)) {
    applied++;
  }

  return {
    applied,
    version: runner.getVersion(),
    tables: db.getTableNames()
  };
}

module.exports = {
  MigrationRunner,
  migrateSchema,
  runMigrations
};
