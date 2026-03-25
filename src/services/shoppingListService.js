'use strict';

const ShoppingList = require('../models/ShoppingList');
const MealPlan = require('../models/MealPlan');

/**
 * Shopping list generation service
 */
class ShoppingListService {
  constructor(fileStore) {
    this.store = fileStore;
    this.shoppingList = new ShoppingList(fileStore);
    this.mealPlan = new MealPlan(fileStore);
  }

  /**
   * Generate shopping list from meal plan
   */
  generateFromMealPlan(mealPlanId) {
    const mealPlan = this.mealPlan.getById(mealPlanId);
    if (!mealPlan || !mealPlan.entries) {
      return null;
    }

    // Create shopping list
    const list = this.shoppingList.create({
      name: `Shopping list for ${mealPlan.name}`,
      meal_plan_id: mealPlanId
    });

    // Aggregate ingredients from all recipes
    const ingredientMap = new Map();

    for (const entry of mealPlan.entries) {
      const ingredients = this.store.findBy('ingredients', 'recipe_id', entry.recipe_id);

      for (const ing of ingredients) {
        const key = `${ing.name.toLowerCase()}-${ing.unit || ''}`;

        if (ingredientMap.has(key)) {
          const existing = ingredientMap.get(key);
          existing.quantity = (existing.quantity || 0) + (ing.quantity || 0) * entry.servings;
          existing.recipe_id = existing.recipe_id || ing.recipe_id;
        } else {
          ingredientMap.set(key, {
            ingredient_name: ing.name,
            quantity: (ing.quantity || 0) * entry.servings,
            unit: ing.unit,
            category: ing.category || 'Other',
            recipe_id: ing.recipe_id
          });
        }
      }
    }

    // Add items to shopping list
    for (const [, item] of ingredientMap) {
      this.shoppingList.addItem({
        shopping_list_id: list.id,
        ...item
      });
    }

    return this.shoppingList.getById(list.id);
  }

  /**
   * Categorize ingredients
   */
  categorizeIngredients(items) {
    const categories = {
      Produce: [],
      Dairy: [],
      Meat: [],
      Seafood: [],
      Bakery: [],
      Pantry: [],
      Frozen: [],
      Other: []
    };

    const categoryKeywords = {
      Produce: ['vegetable', 'fruit', 'lettuce', 'tomato', 'onion', 'garlic', 'pepper', 'carrot', 'celery', 'salad', 'herb', 'spice'],
      Dairy: ['milk', 'cheese', 'yogurt', 'cream', 'butter', 'egg'],
      Meat: ['chicken', 'beef', 'pork', 'lamb', 'turkey', 'bacon', 'sausage'],
      Seafood: ['fish', 'salmon', 'shrimp', 'tuna', 'crab', 'lobster', 'scallop'],
      Bakery: ['bread', 'roll', 'bun', 'tortilla', 'pita'],
      Pantry: ['flour', 'sugar', 'salt', 'oil', 'vinegar', 'sauce', 'pasta', 'rice', 'bean', 'lentil'],
      Frozen: ['frozen', 'ice']
    };

    for (const item of items) {
      const name = (item.ingredient_name || '').toLowerCase();
      let categorized = false;

      for (const [category, keywords] of Object.entries(categoryKeywords)) {
        if (keywords.some(kw => name.includes(kw))) {
          categories[category].push(item);
          categorized = true;
          break;
        }
      }

      if (!categorized) {
        categories.Other.push(item);
      }
    }

    return categories;
  }

  /**
   * Get items by category
   */
  getByCategory(shoppingListId) {
    const list = this.shoppingList.getById(shoppingListId);
    if (!list || !list.items) {
      return null;
    }

    return this.categorizeIngredients(list.items);
  }

  /**
   * Estimate quantities (combine similar items)
   */
  estimateQuantities(items) {
    const combined = new Map();

    for (const item of items) {
      const key = `${item.ingredient_name.toLowerCase()}-${item.unit || ''}`;

      if (combined.has(key)) {
        const existing = combined.get(key);
        existing.quantity += item.quantity || 0;
      } else {
        combined.set(key, { ...item });
      }
    }

    return Array.from(combined.values());
  }
}

module.exports = ShoppingListService;
