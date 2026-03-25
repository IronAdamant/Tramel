'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * Simple JSON file-based store with file locking.
 * Replaces SQLite for zero-dependency implementation.
 */
class FileStore {
  constructor(dataDir = 'data') {
    this.dataDir = dataDir;
    this.locks = new Map();
    this.ensureDataDir();
  }

  ensureDataDir() {
    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }
  }

  getFilePath(table) {
    return path.join(this.dataDir, `${table}.json`);
  }

  /**
   * Acquire a simple file lock (best-effort, not fcntl)
   */
  async acquireLock(table) {
    const filePath = this.getFilePath(table);
    const lockKey = filePath;

    // Wait for lock to be available
    while (this.locks.has(lockKey)) {
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    this.locks.set(lockKey, true);
    return lockKey;
  }

  releaseLock(lockKey) {
    this.locks.delete(lockKey);
  }

  /**
   * Read all records from a table
   */
  readAll(table) {
    const filePath = this.getFilePath(table);
    if (!fs.existsSync(filePath)) {
      return [];
    }
    const content = fs.readFileSync(filePath, 'utf8');
    return JSON.parse(content);
  }

  /**
   * Write all records to a table
   */
  writeAll(table, records) {
    const filePath = this.getFilePath(table);
    fs.writeFileSync(filePath, JSON.stringify(records, null, 2), 'utf8');
  }

  /**
   * Read a single record by ID
   */
  readById(table, id) {
    const records = this.readAll(table);
    return records.find(r => r.id === id) || null;
  }

  /**
   * Generate a new ID (UUID v4 using crypto)
   */
  generateId() {
    return crypto.randomUUID();
  }

  /**
   * Create a new record
   */
  create(table, data) {
    const lockKey = this.acquireLock(table);
    try {
      const records = this.readAll(table);
      const newRecord = {
        id: this.generateId(),
        ...data,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      records.push(newRecord);
      this.writeAll(table, records);
      return newRecord;
    } finally {
      this.releaseLock(lockKey);
    }
  }

  /**
   * Update a record by ID
   */
  update(table, id, data) {
    const lockKey = this.acquireLock(table);
    try {
      const records = this.readAll(table);
      const index = records.findIndex(r => r.id === id);
      if (index === -1) return null;

      records[index] = {
        ...records[index],
        ...data,
        id: records[index].id,
        updated_at: new Date().toISOString()
      };
      this.writeAll(table, records);
      return records[index];
    } finally {
      this.releaseLock(lockKey);
    }
  }

  /**
   * Delete a record by ID
   */
  delete(table, id) {
    const lockKey = this.acquireLock(table);
    try {
      const records = this.readAll(table);
      const index = records.findIndex(r => r.id === id);
      if (index === -1) return false;

      records.splice(index, 1);
      this.writeAll(table, records);
      return true;
    } finally {
      this.releaseLock(lockKey);
    }
  }

  /**
   * Find records by a key-value pair
   */
  findBy(table, key, value) {
    const records = this.readAll(table);
    return records.filter(r => r[key] === value);
  }

  /**
   * Find a single record by a key-value pair
   */
  findOneBy(table, key, value) {
    const records = this.readAll(table);
    return records.find(r => r[key] === value) || null;
  }

  /**
   * Initialize tables (create empty JSON files if not exist)
   */
  initializeTable(table) {
    const filePath = this.getFilePath(table);
    if (!fs.existsSync(filePath)) {
      this.writeAll(table, []);
    }
  }

  /**
   * Initialize all standard RecipeLab tables
   */
  initializeAll() {
    const tables = [
      'recipes', 'ingredients', 'tags', 'recipe_tags',
      'meal_plans', 'meal_plan_entries',
      'shopping_lists', 'shopping_list_items',
      'collections', 'collection_recipes',
      'dietary_profiles', 'cooking_logs', 'ingredient_prices'
    ];
    tables.forEach(table => this.initializeTable(table));
  }
}

// Singleton instance
let _fileStore = null;

function getFileStore(dataDir = 'data') {
  if (!_fileStore) {
    _fileStore = new FileStore(dataDir);
  }
  return _fileStore;
}

module.exports = { FileStore, getFileStore };
