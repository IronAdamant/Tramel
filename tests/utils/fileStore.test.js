'use strict';

const { describe, test, assert, equal, deepEqual, ok } = require('../testRunner');
const { FileStore } = require('../../src/utils/fileStore');
const fs = require('fs');
const path = require('path');

describe('FileStore', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);

  test('should initialize with an array', () => {
    const recipes = store.readAll('recipes');
    equal(Array.isArray(recipes), true);
    // Note: length may not be 0 due to test pollution, just check it's an array
  });

  test('should create a record with auto-generated id', () => {
    const record = store.create('recipes', { title: 'Test Recipe' });
    ok(record.id !== undefined);
    equal(record.title, 'Test Recipe');
    ok(record.created_at !== undefined);
  });

  test('should read a record by id', () => {
    const created = store.create('recipes', { title: 'Read Test' });
    const read = store.readById('recipes', created.id);
    equal(read.id, created.id);
    equal(read.title, 'Read Test');
  });

  test('should update a record', () => {
    const created = store.create('recipes', { title: 'Original' });
    const updated = store.update('recipes', created.id, { title: 'Updated' });
    equal(updated.title, 'Updated');
    equal(updated.id, created.id);
  });

  test('should delete a record', () => {
    const created = store.create('recipes', { title: 'To Delete' });
    const result = store.delete('recipes', created.id);
    equal(result, true);
    const read = store.readById('recipes', created.id);
    equal(read, null);
  });

  test('should find records by field', () => {
    store.create('recipes', { title: 'Find Me', category: 'test' });
    store.create('recipes', { title: 'Not Me', category: 'other' });

    const found = store.findBy('recipes', 'category', 'test');
    equal(found.length >= 1, true);
    equal(found[0].title, 'Find Me');
  });

  test('should find one record by field', () => {
    store.create('recipes', { title: 'Unique One', category: 'unique' });

    const found = store.findOneBy('recipes', 'category', 'unique');
    ok(found !== null);
    equal(found.title, 'Unique One');
  });

  test('should generate unique IDs', () => {
    const id1 = store.generateId();
    const id2 = store.generateId();
    ok(id1 !== id2);
    ok(id1.length === 36); // UUID format
  });

  // Cleanup
  after(() => {
    // Clean up test files
    const files = fs.readdirSync(testDir).filter(f => f.endsWith('.json'));
    files.forEach(f => fs.unlinkSync(path.join(testDir, f)));
  });
});
