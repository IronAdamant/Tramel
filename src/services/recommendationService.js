'use strict';

const Recipe = require('../models/Recipe');
const CookingLog = require('../models/CookingLog');

/**
 * Recipe recommendation service
 */
class RecommendationService {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
    this.cookingLog = new CookingLog(fileStore);
  }

  /**
   * Get recommendations based on cooking history
   */
  getRecommendations({ limit = 10, userId }) {
    const recommendations = [];
    const recipes = this.store.readAll('recipes');

    if (recipes.length === 0) {
      return [];
    }

    // Get cooking history
    const frequent = this.cookingLog.getFrequent({ limit: 5 });
    const recentlyCookedIds = frequent.map(f => f.recipe ? f.recipe.id : null).filter(Boolean);

    // Get tags from frequently cooked recipes
    const preferredTags = new Set();
    for (const item of frequent) {
      if (item.recipe) {
        const tags = this.recipe.getTagsForRecipe(item.recipe.id);
        tags.forEach(tag => preferredTags.add(tag.name));
      }
    }

    // Score recipes
    const scored = recipes.map(recipe => {
      let score = 0;

      // Boost recently cooked (makes it less likely to recommend)
      if (!recentlyCookedIds.includes(recipe.id)) {
        score += 5;
      }

      // Boost recipes with preferred tags
      const recipeTags = this.recipe.getTagsForRecipe(recipe.id);
      for (const tag of recipeTags) {
        if (preferredTags.has(tag.name)) {
          score += 3;
        }
      }

      // Boost quick recipes
      const totalTime = (recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0);
      if (totalTime <= 30) score += 2;
      if (totalTime <= 15) score += 2;

      // Boost highly rated (if we have ratings)
      const ratings = this.cookingLog.getRatings(recipe.id);
      if (ratings && ratings.average >= 4) score += 3;

      return {
        recipe,
        score,
        total_time: totalTime
      };
    });

    // Sort by score descending
    scored.sort((a, b) => b.score - a.score);

    return scored.slice(0, limit).map(s => ({
      recipe: s.recipe,
      reason: this.getReason(s.score, s.total_time),
      total_time: s.total_time
    }));
  }

  /**
   * Get recommendation reason
   */
  getReason(score, totalTime) {
    if (totalTime <= 15) return 'Quick and easy';
    if (totalTime <= 30) return 'Moderate prep time';
    if (score >= 10) return 'Matches your preferences';
    return 'Recommended for you';
  }

  /**
   * Get "what's for dinner" suggestions
   */
  whatsForDinner({ maxTime = 60, count = 5 }) {
    const recipes = this.recipe.search({ maxTime });

    return recipes
      .slice(0, count * 2)
      .sort(() => Math.random() - 0.5)
      .slice(0, count)
      .map(recipe => ({
        recipe,
        meal_type: 'dinner',
        total_time: (recipe.prep_time_minutes || 0) + (recipe.cook_time_minutes || 0)
      }));
  }

  /**
   * Get similar recipes
   */
  findSimilar(recipeId, { limit = 5 }) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe) return [];

    const recipeTags = this.recipe.getTagsForRecipe(recipeId);
    const recipeTagNames = new Set(recipeTags.map(t => t.name));

    const allRecipes = this.store.readAll('recipes');

    const similar = allRecipes
      .filter(r => r.id !== recipeId)
      .map(r => {
        const tags = this.recipe.getTagsForRecipe(r.id);
        const matchingTags = tags.filter(t => recipeTagNames.has(t.name));

        return {
          recipe: r,
          similarity_score: matchingTags.length,
          matching_tags: matchingTags.map(t => t.name)
        };
      })
      .filter(s => s.similarity_score > 0)
      .sort((a, b) => b.similarity_score - a.similarity_score)
      .slice(0, limit);

    return similar;
  }

  /**
   * Get seasonal recommendations
   */
  getSeasonal({ count = 5 }) {
    const recipes = this.store.readAll('recipes');

    // Simple seasonal logic based on current month
    const month = new Date().getMonth();
    const seasonalKeywords = {
      spring: ['salad', 'fresh', 'asparagus', 'peas'],
      summer: ['grill', 'barbecue', 'cold', 'salad', 'bbq'],
      fall: ['pumpkin', 'squash', 'apple', 'harvest'],
      winter: ['soup', 'stew', 'roast', 'warm']
    };

    let keywords = [];
    if (month >= 2 && month <= 4) keywords = seasonalKeywords.spring;
    else if (month >= 5 && month <= 7) keywords = seasonalKeywords.summer;
    else if (month >= 8 && month <= 10) keywords = seasonalKeywords.fall;
    else keywords = seasonalKeywords.winter;

    const seasonal = recipes.filter(r => {
      const title = (r.title || '').toLowerCase();
      const desc = (r.description || '').toLowerCase();
      return keywords.some(kw => title.includes(kw) || desc.includes(kw));
    });

    // If no seasonal matches, return random
    if (seasonal.length === 0) {
      return recipes.slice(0, count).map(recipe => ({
        recipe,
        reason: 'Try something new'
      }));
    }

    return seasonal.slice(0, count).map(recipe => ({
      recipe,
      reason: 'In season now'
    }));
  }
}

module.exports = RecommendationService;
