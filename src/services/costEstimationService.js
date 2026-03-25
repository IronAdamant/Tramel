'use strict';

const Recipe = require('../models/Recipe');

/**
 * Cost estimation service
 */
class CostEstimationService {
  constructor(fileStore) {
    this.store = fileStore;
    this.recipe = new Recipe(fileStore);
  }

  /**
   * Estimate cost for a recipe
   */
  estimateRecipeCost(recipeId) {
    const recipe = this.recipe.getById(recipeId);
    if (!recipe || !recipe.ingredients) {
      return null;
    }

    const ingredients = recipe.ingredients;
    let totalCost = 0;
    const itemCosts = [];

    for (const ingredient of ingredients) {
      const itemCost = this.estimateIngredientCost(ingredient);
      totalCost += itemCost.cost;
      itemCosts.push(itemCost);
    }

    const servings = recipe.servings || 1;

    return {
      recipe_id: recipeId,
      recipe_title: recipe.title,
      currency: 'USD',
      total_cost: Math.round(totalCost * 100) / 100,
      per_serving: Math.round((totalCost / servings) * 100) / 100,
      servings,
      item_costs: itemCosts
    };
  }

  /**
   * Estimate cost for a single ingredient
   */
  estimateIngredientCost(ingredient) {
    const name = ingredient.name || '';
    const quantity = ingredient.quantity || 100;
    const unit = ingredient.unit || 'unit';

    // Try to find price in price data
    const prices = this.store.readAll('ingredient_prices');
    const priceEntry = prices.find(p =>
      name.toLowerCase().includes(p.ingredient_name.toLowerCase())
    );

    let costPerUnit = 0;
    let priceSource = 'estimated';

    if (priceEntry) {
      costPerUnit = priceEntry.price_per_unit;
      priceSource = 'database';
    } else {
      // Estimate based on category
      costPerUnit = this.estimatePriceByCategory(name, unit);
    }

    return {
      ingredient: name,
      quantity,
      unit,
      estimated_cost: Math.round(costPerUnit * quantity * 100) / 100,
      cost_per_unit: costPerUnit,
      price_source: priceSource
    };
  }

  /**
   * Estimate price by ingredient category
   */
  estimatePriceByCategory(name, unit) {
    const nameLower = name.toLowerCase();

    // Meat proteins (per 100g)
    if (nameLower.includes('chicken')) return 0.15;
    if (nameLower.includes('beef')) return 0.25;
    if (nameLower.includes('pork')) return 0.18;
    if (nameLower.includes('fish') || nameLower.includes('salmon')) return 0.35;
    if (nameLower.includes('shrimp')) return 0.40;

    // Vegetables (per 100g)
    if (nameLower.includes('tomato')) return 0.05;
    if (nameLower.includes('onion')) return 0.03;
    if (nameLower.includes('garlic')) return 0.10;
    if (nameLower.includes('carrot')) return 0.04;
    if (nameLower.includes('potato')) return 0.03;
    if (nameLower.includes('lettuce') || nameLower.includes('salad')) return 0.08;

    // Dairy (per unit)
    if (nameLower.includes('milk')) return 0.05;
    if (nameLower.includes('cheese')) return 0.25;
    if (nameLower.includes('butter')) return 0.20;
    if (nameLower.includes('egg')) return 0.25;

    // Grains (per 100g)
    if (nameLower.includes('flour')) return 0.02;
    if (nameLower.includes('rice')) return 0.03;
    if (nameLower.includes('pasta')) return 0.03;
    if (nameLower.includes('bread')) return 0.05;

    // Default
    return 0.10;
  }

  /**
   * Estimate cost for a meal plan
   */
  estimateMealPlanCost(mealPlanId) {
    const entries = this.store.findBy('meal_plan_entries', 'meal_plan_id', mealPlanId);

    let totalCost = 0;
    const recipeCosts = [];

    for (const entry of entries) {
      const cost = this.estimateRecipeCost(entry.recipe_id);
      if (cost) {
        const adjustedCost = cost.total_cost * (entry.servings || 1) / (cost.servings || 1);
        totalCost += adjustedCost;
        recipeCosts.push({
          recipe_id: entry.recipe_id,
          cost: adjustedCost,
          servings: entry.servings
        });
      }
    }

    return {
      meal_plan_id: mealPlanId,
      currency: 'USD',
      total_cost: Math.round(totalCost * 100) / 100,
      recipe_costs: recipeCosts
    };
  }

  /**
   * Compare recipe costs
   */
  compareCosts(recipeIds) {
    return recipeIds.map(id => {
      const cost = this.estimateRecipeCost(id);
      return cost;
    }).filter(Boolean)
      .sort((a, b) => a.per_serving - b.per_serving);
  }
}

module.exports = CostEstimationService;
