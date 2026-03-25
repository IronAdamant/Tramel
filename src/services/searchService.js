'use strict';

const Recipe = require('../models/Recipe');

/**
 * Search service for recipe discovery
 */
class SearchService {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Full-text search across recipes
   */
  search({ query, tags, ingredients, maxTime, minServings, sort, limit = 50 }) {
    return this.recipe.search({ query, tags, ingredients, maxTime, minServings, sort }).slice(0, limit);
  }

  /**
   * Find recipes by ingredient
   */
  findByIngredient(ingredientName) {
    const ingredients = this.store.findBy('ingredients', 'name', ingredientName.toLowerCase());
    const recipeIds = [...new Set(ingredients.map(i => i.recipe_id))];

    return recipeIds.map(id => this.store.readById('recipes', id)).filter(Boolean);
  }

  /**
   * Find recipes by multiple ingredients (what's in my fridge)
   */
  findByIngredients(ingredientNames, matchAll = false) {
    const allIngredients = this.store.readAll('ingredients');

    // Group ingredients by recipe
    const recipeIngredients = {};
    allIngredients.forEach(ing => {
      if (!recipeIngredients[ing.recipe_id]) {
        recipeIngredients[ing.recipe_id] = [];
      }
      recipeIngredients[ing.recipe_id].push(ing.name.toLowerCase());
    });

    const namesLower = ingredientNames.map(n => n.toLowerCase());

    return Object.entries(recipeIngredients)
      .map(([recipeId, ingredients]) => {
        const matched = ingredients.filter(ing =>
          namesLower.some(name => ing.includes(name))
        );

        const matchResult = {
          recipe: this.store.readById('recipes', recipeId),
          matched_ingredients: matched,
          match_count: matched.length
        };

        if (matchAll) {
          matchResult.matches_all = namesLower.every(name =>
            ingredients.some(ing => ing.includes(name))
          );
        }

        return matchResult;
      })
      .filter(r => r.recipe && (matchAll ? r.matches_all : r.match_count > 0))
      .sort((a, b) => b.match_count - a.match_count);
  }

  /**
   * Get recipes by cuisine
   */
  findByCuisine(cuisine) {
    const recipes = this.store.readAll('recipes');
    return recipes.filter(r =>
      r.cuisine && r.cuisine.toLowerCase() === cuisine.toLowerCase()
    );
  }

  /**
   * Get quick recipes (under specified minutes)
   */
  findQuickRecipes(maxMinutes = 30) {
    return this.recipe.search({ maxTime: maxMinutes, sort: 'time' });
  }
}

module.exports = SearchService;
