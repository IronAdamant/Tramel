'use strict';

const { validateRequired, validatePositiveInt, validateDate } = require('../utils/validation');

/**
 * CookingLog model
 */
class CookingLog {
  constructor(fileStore) {
    this.store = fileStore;
    this.table = 'cooking_logs';
  }

  /**
   * Create a new cooking log entry
   */
  create({ recipe_id, date, rating, notes, servings_made }) {
    validateRequired({ recipe_id, date }, ['recipe_id', 'date']);

    return this.store.create(this.table, {
      recipe_id,
      date: validateDate(date, 'date'),
      rating: rating !== undefined ? validatePositiveInt(rating, 'rating') : null,
      notes: notes || '',
      servings_made: validatePositiveInt(servings_made || 1, 'servings_made')
    });
  }

  /**
   * Get cooking log by ID
   */
  getById(id) {
    return this.store.readById(this.table, id);
  }

  /**
   * Get all cooking logs with pagination
   */
  getAll({ limit = 20, offset = 0 } = {}) {
    const records = this.store.readAll(this.table);
    return {
      data: records.slice(offset, offset + limit),
      total: records.length
    };
  }

  /**
   * Update a cooking log
   */
  update(id, { date, rating, notes, servings_made }) {
    const updateData = {};

    if (date !== undefined) updateData.date = validateDate(date, 'date');
    if (rating !== undefined) updateData.rating = validatePositiveInt(rating, 'rating');
    if (notes !== undefined) updateData.notes = notes;
    if (servings_made !== undefined) updateData.servings_made = validatePositiveInt(servings_made, 'servings_made');

    return this.store.update(this.table, id, updateData);
  }

  /**
   * Delete a cooking log
   */
  delete(id) {
    return this.store.delete(this.table, id);
  }

  /**
   * Get cooking logs for a recipe
   */
  getByRecipeId(recipeId) {
    return this.store.findBy(this.table, 'recipe_id', recipeId);
  }

  /**
   * Get frequently cooked recipes
   */
  getFrequent({ limit = 10 } = {}) {
    const logs = this.store.readAll(this.table);

    // Count cooking frequency per recipe
    const frequencyMap = {};
    logs.forEach(log => {
      if (!frequencyMap[log.recipe_id]) {
        frequencyMap[log.recipe_id] = 0;
      }
      frequencyMap[log.recipe_id]++;
    });

    // Convert to array and sort
    const sorted = Object.entries(frequencyMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit);

    // Get recipe details
    return sorted.map(([recipeId, count]) => {
      const recipe = this.store.readById('recipes', recipeId);
      return {
        recipe,
        cooking_count: count
      };
    }).filter(entry => entry.recipe !== null);
  }

  /**
   * Get ratings for recipes
   */
  getRatings(recipeId) {
    const logs = this.store.findBy(this.table, 'recipe_id', recipeId);
    const ratings = logs.filter(log => log.rating !== null).map(log => log.rating);

    if (ratings.length === 0) return null;

    const avg = ratings.reduce((a, b) => a + b, 0) / ratings.length;

    return {
      average: avg,
      count: ratings.length,
      ratings
    };
  }

  /**
   * Get cooking statistics
   */
  getStats() {
    const logs = this.store.readAll(this.table);

    const totalCookings = logs.length;
    const recipesCooked = new Set(logs.map(l => l.recipe_id)).size;
    const ratedCookings = logs.filter(l => l.rating !== null).length;
    const avgRating = logs
      .filter(l => l.rating !== null)
      .reduce((sum, l) => sum + l.rating, 0) / (ratedCookings || 1);

    return {
      total_cookings: totalCookings,
      unique_recipes: recipesCooked,
      rated_cookings: ratedCookings,
      average_rating: avgRating || null
    };
  }
}

module.exports = CookingLog;
