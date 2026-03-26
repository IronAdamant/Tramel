'use strict';

const path = require('path');
const { SQLite, openDatabase } = require('./sqlite');
const { runMigrations } = require('./migrations');

/**
 * Database module - SQLite-based storage.
 * Uses better-sqlite3 for synchronous, thread-safe operations.
 */

let _db = null;
let _initialized = false;

/**
 * Initialize the database (create tables, run migrations)
 * @param {string} dataDir - Directory for database file
 * @returns {SQLite} Database instance
 */
function initializeDatabase(dataDir = 'data') {
  if (_initialized && _db) {
    return _db;
  }

  const dbPath = path.join(dataDir, 'recipelab.db');
  _db = openDatabase(dbPath);

  // Run migrations to create schema
  const result = runMigrations(_db);
  console.log(`Database initialized: ${result.tables.length} tables, version ${result.version}`);

  _initialized = true;
  return _db;
}

/**
 * Get the database instance
 * @param {string} dataDir - Directory for database file (unused, singleton)
 * @returns {SQLite} Database instance
 */
function getDatabase(dataDir = 'data') {
  if (!_initialized) {
    return initializeDatabase(dataDir);
  }
  return _db;
}

/**
 * Check if database is initialized
 * @returns {boolean}
 */
function isInitialized() {
  return _initialized;
}

/**
 * Close database connection
 */
function closeDatabase() {
  if (_db) {
    _db.close();
    _db = null;
    _initialized = false;
  }
}

module.exports = {
  initializeDatabase,
  getDatabase,
  isInitialized,
  closeDatabase
};
