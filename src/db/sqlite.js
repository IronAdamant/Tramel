'use strict';

const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

/**
 * SQLite wrapper using better-sqlite3.
 * Provides synchronous, thread-safe database operations.
 */
class SQLite {
  /**
   * @param {string} dbPath - Path to SQLite database file
   */
  constructor(dbPath = ':memory:') {
    this.dbPath = dbPath;
    this.db = null;
    this._open();
  }

  /**
   * Open database connection
   */
  _open() {
    const dir = path.dirname(this.dbPath);
    if (dir && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    this.db = new Database(this.dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('foreign_keys = ON');
  }

  /**
   * Close database connection
   */
  close() {
    if (this.db) {
      this.db.close();
      this.db = null;
    }
  }

  /**
   * Run a query (INSERT, UPDATE, DELETE)
   * @param {string} sql - SQL query
   * @param {Array} params - Query parameters
   * @returns {Object} Changes info
   */
  run(sql, params = []) {
    try {
      const stmt = this.db.prepare(sql);
      const result = stmt.run(...params);
      return {
        changes: result.changes,
        lastInsertRowid: result.lastInsertRowid
      };
    } catch (err) {
      throw new Error(`SQL run error: ${err.message}`);
    }
  }

  /**
   * Get a single row
   * @param {string} sql - SQL query
   * @param {Array} params - Query parameters
   * @returns {Object|null} Row object or null
   */
  get(sql, params = []) {
    try {
      const stmt = this.db.prepare(sql);
      return stmt.get(...params) || null;
    } catch (err) {
      throw new Error(`SQL get error: ${err.message}`);
    }
  }

  /**
   * Get all rows
   * @param {string} sql - SQL query
   * @param {Array} params - Query parameters
   * @returns {Array} Array of row objects
   */
  all(sql, params = []) {
    try {
      const stmt = this.db.prepare(sql);
      return stmt.all(...params);
    } catch (err) {
      throw new Error(`SQL all error: ${err.message}`);
    }
  }

  /**
   * Execute multiple statements in a transaction
   * @param {Function} fn - Function that executes statements
   * @returns {*} Result of function
   */
  transaction(fn) {
    return this.db.transaction(fn)();
  }

  /**
   * Create table if not exists
   * @param {string} name - Table name
   * @param {Object} columns - Column definitions { name: type, ... }
   */
  createTable(name, columns) {
    const cols = Object.entries(columns)
      .map(([col, type]) => `${col} ${type}`)
      .join(', ');
    this.run(`CREATE TABLE IF NOT EXISTS ${name} (${cols})`);
  }

  /**
   * Check if table exists
   * @param {string} name - Table name
   * @returns {boolean}
   */
  tableExists(name) {
    const result = this.get(
      "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
      [name]
    );
    return result !== null;
  }

  /**
   * Get all table names
   * @returns {string[]}
   */
  getTableNames() {
    return this.all(
      "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).map(r => r.name);
  }

  /**
   * Drop table if exists
   * @param {string} name - Table name
   */
  dropTable(name) {
    this.run(`DROP TABLE IF EXISTS ${name}`);
  }
}

/**
 * Create a new SQLite instance
 * @param {string} dbPath - Path to database file
 * @returns {SQLite}
 */
function openDatabase(dbPath = ':memory:') {
  return new SQLite(dbPath);
}

module.exports = {
  SQLite,
  openDatabase
};
