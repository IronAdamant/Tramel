'use strict';

const { validateRequired, validatePositiveInt, validatePagination, validateDifficulty, validateCuisine, sanitizeString } = require('../utils/validation');

/**
 * Recipe model - main recipe entity
 */
class Recipe {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'recipes';
    this.ingredientsTable = 'ingredients';
    this.recipeTagsTable = 'recipe_tags';
    this.tagsTable = 'tags';
  }

  /**
   * Create a new recipe with ingredients and tags
   */
  create({ title, description, instructions, prep_time_minutes, cook_time_minutes, servings, source, image_url, difficulty, cuisine, ingredients, tags }) {
    validateRequired({ title }, ['title']);

    const recipe = this.store.create(this.table, {
      title: sanitizeString(title),
      description: description || '',
      instructions: instructions || '',
      prep_time_minutes: validatePositiveInt(prep_time_minutes || 0, 'prep_time_minutes'),
      cook_time_minutes: validatePositiveInt(cook_time_minutes || 0, 'cook_time_minutes'),
      servings: validatePositiveInt(servings || 1, 'servings'),
      source: source || '',
      image_url: image_url || '',
      difficulty: validateDifficulty(difficulty, 'difficulty'),
      cuisine: validateCuisine(cuisine, 'cuisine')
    });

    // Add ingredients if provided
    if (ingredients && Array.isArray(ingredients)) {
      for (const ing of ingredients) {
        this.addIngredient(recipe.id, ing);
      }
    }

    // Add tags if provided
    if (tags && Array.isArray(tags)) {
      for (const tagName of tags) {
        this.addTagByName(recipe.id, tagName);
      }
    }

    return this.getById(recipe.id);
  }

  /**
   * Get a recipe by ID with ingredients and tags
   */
  getById(id) {
    const recipe = this.store.readById(this.table, id);
    if (!recipe) return null;

    // Load ingredients
    recipe.ingredients = this.store.findBy(this.ingredientsTable, 'recipe_id', id);

    // Load tags
    recipe.tags = this.getTagsForRecipe(id);

    return recipe;
  }

  /**
   * Get all recipes with pagination
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a recipe
   */
  update(id, fields) {
    const allowedFields = [
      'title', 'description', 'instructions', 'prep_time_minutes',
      'cook_time_minutes', 'servings', 'source', 'image_url', 'difficulty', 'cuisine'
    ];

    const updateData = {};
    for (const field of allowedFields) {
      if (fields[field] !== undefined) {
        updateData[field] = fields[field];
      }
    }

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a recipe and its related data
   */
  delete(id) {
    // Delete ingredients
    const ingredients = this.store.findBy(this.ingredientsTable, 'recipe_id', id);
    ingredients.forEach(ing => this.store.delete(this.ingredientsTable, ing.id));

    // Delete recipe tag associations
    const recipeTags = this.store.findBy(this.recipeTagsTable, 'recipe_id', id);
    recipeTags.forEach(rt => this.store.delete(this.recipeTagsTable, rt.id));

    // Delete recipe
    return this.store.delete(this.table, id);
  }

  /**
   * Search recipes
   */
  search({ query, tags, ingredients, maxTime, minServings, sort = 'title' }) {
    let recipes = this.store.readAll(this.table);

    // Filter by query (title or description)
    if (query) {
      const q = query.toLowerCase();
      recipes = recipes.filter(r =>
        r.title.toLowerCase().includes(q) ||
        (r.description && r.description.toLowerCase().includes(q))
      );
    }

    // Filter by tags
    if (tags && tags.length > 0) {
      recipes = recipes.filter(r => {
        const recipeTags = this.getTagsForRecipe(r.id);
        return tags.some(tagName =>
          recipeTags.some(rt => rt.name.toLowerCase() === tagName.toLowerCase())
        );
      });
    }

    // Filter by max time
    if (maxTime !== undefined) {
      recipes = recipes.filter(r => {
        const totalTime = (r.prep_time_minutes || 0) + (r.cook_time_minutes || 0);
        return totalTime <= maxTime;
      });
    }

    // Filter by min servings
    if (minServings !== undefined) {
      recipes = recipes.filter(r => (r.servings || 0) >= minServings);
    }

    // Sort
    recipes.sort((a, b) => {
      if (sort === 'title') return a.title.localeCompare(b.title);
      if (sort === 'created') return new Date(b.created_at) - new Date(a.created_at);
      if (sort === 'time') {
        const timeA = (a.prep_time_minutes || 0) + (a.cook_time_minutes || 0);
        const timeB = (b.prep_time_minutes || 0) + (b.cook_time_minutes || 0);
        return timeA - timeB;
      }
      return 0;
    });

    return recipes;
  }

  /**
   * Add ingredient to recipe
   */
  addIngredient(recipeId, { name, quantity, unit, notes, sort_order, category, allergens }) {
    return this.store.create(this.ingredientsTable, {
      recipe_id: recipeId,
      name: sanitizeString(name),
      quantity: quantity || null,
      unit: unit || '',
      notes: notes || '',
      sort_order: sort_order || 0,
      category: category || '',
      allergens: allergens || []
    });
  }

  /**
   * Remove ingredient from recipe
   */
  removeIngredient(ingredientId) {
    return this.store.delete(this.ingredientsTable, ingredientId);
  }

  /**
   * Get total cooking time
   */
  getTotalTime(id) {
    const recipe = this.store.readById(this.table, id);
    if (!recipe) return 0;
    return (recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0);
  }

  /**
   * Add tag to recipe
   */
  addTagByName(recipeId, tagName) {
    // Find or create tag
    let tag = this.store.findOneBy(this.tagsTable, 'name', tagName.toLowerCase());
    if (!tag) {
      tag = this.store.create(this.tagsTable, { name: tagName.toLowerCase() });
    }

    // Check if association exists
    const existing = this.store.findOneBy(this.recipeTagsTable, 'recipe_id', recipeId);
    const existingAssoc = existing && this.store.findOneBy(this.recipeTagsTable, 'tag_id', tag.id);

    if (!existingAssoc) {
      this.store.create(this.recipeTagsTable, {
        recipe_id: recipeId,
        tag_id: tag.id
      });
    }

    return tag;
  }

  /**
   * Remove tag from recipe
   */
  removeTagByName(recipeId, tagName) {
    const tag = this.store.findOneBy(this.tagsTable, 'name', tagName.toLowerCase());
    if (!tag) return false;

    const assocs = this.store.findBy(this.recipeTagsTable, 'recipe_id', recipeId);
    const assoc = assocs.find(a => a.tag_id === tag.id);
    if (assoc) {
      return this.store.delete(this.recipeTagsTable, assoc.id);
    }
    return false;
  }

  /**
   * Get tags for a recipe
   */
  getTagsForRecipe(recipeId) {
    const assocs = this.store.findBy(this.recipeTagsTable, 'recipe_id', recipeId);
    return assocs.map(assoc => {
      const tag = this.store.readById(this.tagsTable, assoc.tag_id);
      return tag || null;
    }).filter(Boolean);
  }
}

module.exports = Recipe;
