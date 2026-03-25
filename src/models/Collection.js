'use strict';

const { validateRequired, sanitizeString } = require('../utils/validation');

/**
 * Collection model
 */
class Collection {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'collections';
    this.collectionRecipesTable = 'collection_recipes';
  }

  /**
   * Create a new collection
   */
  create({ name, description }) {
    validateRequired({ name }, ['name']);

    return this.store.create(this.table, {
      name: sanitizeString(name),
      description: description || ''
    });
  }

  /**
   * Get collection by ID with recipes
   */
  getById(id) {
    const collection = this.store.readById(this.table, id);
    if (!collection) return null;

    // Load recipe associations
    const assocs = this.store.findBy(this.collectionRecipesTable, 'collection_id', id);
    collection.recipes = assocs.map(assoc => {
      const recipe = this.store.readById('recipes', assoc.recipe_id);
      return recipe;
    }).filter(Boolean);

    collection.recipe_count = collection.recipes.length;

    return collection;
  }

  /**
   * Get all collections
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);

    // Add recipe counts
    const withCounts = records.map(collection => {
      const assocs = this.store.findBy(this.collectionRecipesTable, 'collection_id', collection.id);
      return {
        ...collection,
        recipe_count: assocs.length
      };
    });

    return {
      data: withCounts.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a collection
   */
  update(id, { name, description }) {
    const updateData = {};
    if (name !== undefined) updateData.name = sanitizeString(name);
    if (description !== undefined) updateData.description = sanitizeString(description);

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a collection and its recipe associations
   */
  delete(id) {
    // Delete recipe associations
    const assocs = this.store.findBy(this.collectionRecipesTable, 'collection_id', id);
    assocs.forEach(assoc => this.store.delete(this.collectionRecipesTable, assoc.id));

    return this.store.delete(this.table, id);
  }

  /**
   * Add recipe to collection
   */
  addRecipe(collectionId, recipeId) {
    // Check for duplicate
    const existing = this.store.findBy(this.collectionRecipesTable, 'collection_id', collectionId);
    const duplicate = existing.find(a => a.recipe_id === recipeId);

    if (duplicate) {
      return duplicate;
    }

    return this.store.create(this.collectionRecipesTable, {
      collection_id: collectionId,
      recipe_id: recipeId
    });
  }

  /**
   * Remove recipe from collection
   */
  removeRecipe(collectionId, recipeId) {
    const assocs = this.store.findBy(this.collectionRecipesTable, 'collection_id', collectionId);
    const assoc = assocs.find(a => a.recipe_id === recipeId);

    if (assoc) {
      return this.store.delete(this.collectionRecipesTable, assoc.id);
    }
    return false;
  }
}

module.exports = Collection;
