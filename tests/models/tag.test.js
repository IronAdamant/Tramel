'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const Tag = require('../../src/models/Tag');
const { FileStore } = require('../../src/utils/fileStore');
const path = require('path');

describe('Tag Model', () => {
  const testDir = path.join(__dirname, '../../data/test');
  const store = new FileStore(testDir);
  const tag = new Tag(store);

  test('should create a tag', () => {
    const created = tag.create({ name: 'Vegetarian' });

    assert.ok(created.id !== undefined);
    equal(created.name, 'vegetarian'); // Normalized to lowercase
  });

  test('should return existing tag if duplicate', () => {
    tag.create({ name: 'Vegan' });
    const duplicate = tag.create({ name: 'VEGAN' });

    equal(duplicate.name, 'vegan');
  });

  test('should get tag by name', () => {
    tag.create({ name: 'Gluten-Free' });

    const found = tag.getByName('gluten-free');
    assert.ok(found !== null);
    equal(found.name, 'gluten-free');
  });

  test('should get all tags with pagination', () => {
    tag.create({ name: 'Tag1' });
    tag.create({ name: 'Tag2' });

    const result = tag.getAll({ limit: 10 });

    assert.ok(Array.isArray(result.data));
    assert.ok(result.total >= 2);
  });

  test('should delete tag and its associations', () => {
    const created = tag.create({ name: 'ToDelete' });

    const result = tag.delete(created.id);
    equal(result, true);

    const found = tag.getById(created.id);
    equal(found, null);
  });
});
