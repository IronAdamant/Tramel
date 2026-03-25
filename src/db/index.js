'use strict';

const { FileStore, getFileStore } = require('../utils/fileStore');
const { createSchemaWithDefaults } = require('./schema');

/**
 * Database module - singleton file store initialization.
 * Replaces better-sqlite3 for zero-dependency implementation.
 */

let _initialized = false;

/**
 * Initialize the database (create tables, default data)
 */
function initializeDatabase(dataDir = 'data') {
  const fileStore = getFileStore(dataDir);
  createSchemaWithDefaults(fileStore);
  _initialized = true;
  return fileStore;
}

/**
 * Get the database instance
 */
function getDatabase(dataDir = 'data') {
  if (!_initialized) {
    return initializeDatabase(dataDir);
  }
  return getFileStore(dataDir);
}

/**
 * Check if database is initialized
 */
function isInitialized() {
  return _initialized;
}

module.exports = {
  initializeDatabase,
  getDatabase,
  isInitialized
};
