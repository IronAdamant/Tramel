'use strict';

const Collection = require('../models/Collection');

/**
 * Collection management service
 */
class CollectionService {
  constructor(fileStore) {
    this.store = fileStore;
    this.collection = new Collection(fileStore);
  }

  /**
   * Create a new collection
   */
  createCollection({ name, description }) {
    return this.collection.create({ name, description });
  }

  /**
   * Add multiple recipes to a collection
   */
  addRecipes(collectionId, recipeIds) {
    const results = [];

    for (const recipeId of recipeIds) {
      const result = this.collection.addRecipe(collectionId, recipeId);
      results.push(result);
    }

    return results;
  }

  /**
   * Get collection with full recipe details
   */
  getCollectionWithRecipes(collectionId) {
    const collection = this.collection.getById(collectionId);
    if (!collection) {
      return null;
    }

    return {
      ...collection,
      recipes: collection.recipes.map(recipe => ({
        ...recipe,
        tags: this.getRecipeTags(recipe.id)
      }))
    };
  }

  /**
   * Get tags for a recipe
   */
  getRecipeTags(recipeId) {
    const assocs = this.store.findBy('recipe_tags', 'recipe_id', recipeId);
    return assocs.map(assoc => {
      const tag = this.store.readById('tags', assoc.tag_id);
      return tag ? tag.name : null;
    }).filter(Boolean);
  }

  /**
   * Find collections by name
   */
  findByName(name) {
    const collections = this.store.readAll('collections');
    const searchTerm = name.toLowerCase();

    return collections.filter(c =>
      c.name.toLowerCase().includes(searchTerm)
    );
  }

  /**
   * Get collections containing a specific recipe
   */
  getCollectionsForRecipe(recipeId) {
    const assocs = this.store.findBy('collection_recipes', 'recipe_id', recipeId);
    return assocs.map(assoc => {
      return this.store.readById('collections', assoc.collection_id);
    }).filter(Boolean);
  }

  /**
   * Copy a collection
   */
  copyCollection(sourceId, newName) {
    const source = this.collection.getById(sourceId);
    if (!source) {
      return null;
    }

    const newCollection = this.collection.create({
      name: newName || `${source.name} (Copy)`,
      description: source.description
    });

    // Copy recipes
    if (source.recipes) {
      for (const recipe of source.recipes) {
        this.collection.addRecipe(newCollection.id, recipe.id);
      }
    }

    return this.collection.getById(newCollection.id);
  }

  /**
   * Merge multiple collections
   */
  mergeCollections(sourceIds, newName) {
    const newCollection = this.collection.create({
      name: newName || 'Merged Collection'
    });

    const addedRecipeIds = new Set();

    for (const sourceId of sourceIds) {
      const source = this.collection.getById(sourceId);
      if (source && source.recipes) {
        for (const recipe of source.recipes) {
          if (!addedRecipeIds.has(recipe.id)) {
            this.collection.addRecipe(newCollection.id, recipe.id);
            addedRecipeIds.add(recipe.id);
          }
        }
      }
    }

    return this.collection.getById(newCollection.id);
  }
}

module.exports = CollectionService;
