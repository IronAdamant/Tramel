'use strict';

const Recipe = require('../models/Recipe');

/**
 * Recipe scaling service
 */
class RecipeScalingService {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Scale a recipe by factor or target servings
   */
  scaleRecipe(recipeId, { scaleFactor, targetServings }) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe) {
      return null;
    }

    let factor;

    if (targetServings !== undefined && recipe.servings) {
      factor = targetServings / recipe.servings;
    } else if (scaleFactor !== undefined) {
      factor = scaleFactor;
    } else {
      factor = 1;
    }

    // Scale ingredient quantities
    const scaledIngredients = (recipe.ingredients || []).map(ing => ({
      ...ing,
      quantity: ing.quantity ? ing.quantity * factor : null,
      original_quantity: ing.quantity
    }));

    return {
      id: recipe.id,
      title: recipe.title,
      original_servings: recipe.servings,
      scaled_servings: Math.round((recipe.servings || 1) * factor),
      scale_factor: factor,
      ingredients: scaledIngredients,
      prep_time_minutes: recipe.prep_time_minutes,
      cook_time_minutes: recipe.cook_time_minutes,
      instructions: recipe.instructions
    };
  }

  /**
   * Scale recipe for a specific number of servings
   */
  scaleForServings(recipeId, targetServings) {
    return this.scaleRecipe(recipeId, { targetServings });
  }

  /**
   * Scale recipe by a multiplication factor
   */
  scaleByFactor(recipeId, factor) {
    return this.scaleRecipe(recipeId, { scaleFactor: factor });
  }

  /**
   * Scale all ingredients in a recipe by half (common need)
   */
  scaleHalf(recipeId) {
    return this.scaleRecipe(recipeId, { scaleFactor: 0.5 });
  }

  /**
   * Scale recipe to double
   */
  scaleDouble(recipeId) {
    return this.scaleRecipe(recipeId, { scaleFactor: 2 });
  }
}

module.exports = RecipeScalingService;
