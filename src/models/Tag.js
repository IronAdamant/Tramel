'use strict';

const { validateRequired, sanitizeString } = require('../utils/validation');

/**
 * Tag model
 */
class Tag {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'tags';
    this.recipeTagsTable = 'recipe_tags';
  }

  /**
   * Create a new tag
   */
  create({ name }) {
    validateRequired({ name }, ['name']);

    // Normalize name to lowercase
    const normalizedName = sanitizeString(name).toLowerCase();

    // Check if tag already exists
    const existing = this.store.findOneBy(this.table, 'name', normalizedName);
    if (existing) {
      return existing;
    }

    return this.store.create(this.table, {
      name: normalizedName
    });
  }

  /**
   * Get tag by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get tag by name
   */
  getByName(name) {
    return this.store.findOneBy(this.table, 'name', name.toLowerCase());
  }

  /**
   * Get all tags
   */
  getAll({ limit = 50, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a tag
   */
  update(id, { name }) {
    if (name) {
      name = sanitizeString(name).toLowerCase();
    }
    return this.store.update(this.table, id, { name });
  }

  /**
   * Delete a tag
   */
  delete(id) {
    // Delete all recipe associations first
    const assocs = this.store.findBy(this.recipeTagsTable, 'tag_id', id);
    for (const assoc of assocs) {
      this.store.delete(this.recipeTagsTable, assoc.id);
    }
    return this.store.delete(this.table, id);
  }

  /**
   * Add tag to recipe
   */
  addToRecipe(tagId, recipeId) {
    // Check if association exists
    const existing = this.store.findOneBy(this.recipeTagsTable, 'recipe_id', recipeId);
    const assocs = existing ? [existing] : this.store.findBy(this.recipeTagsTable, 'recipe_id', recipeId);
    const existingAssoc = assocs.find(a => a.tag_id === tagId);

    if (existingAssoc) {
      return existingAssoc;
    }

    return this.store.create(this.recipeTagsTable, {
      recipe_id: recipeId,
      tag_id: tagId
    });
  }

  /**
   * Remove tag from recipe
   */
  removeFromRecipe(tagId, recipeId) {
    const assocs = this.store.findBy(this.recipeTagsTable, 'recipe_id', recipeId);
    const assoc = assocs.find(a => a.tag_id === tagId);
    if (assoc) {
      return this.store.delete(this.recipeTagsTable, assoc.id);
    }
    return false;
  }

  /**
   * Get recipes with this tag
   */
  getRecipes(tagId) {
    const assocs = this.store.findBy(this.recipeTagsTable, 'tag_id', tagId);
    return assocs.map(assoc => this.store.readById('recipes', assoc.recipe_id)).filter(Boolean);
  }
}

module.exports = Tag;
