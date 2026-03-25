'use strict';

/**
 * Price data per standard unit (USD)
 */
const PRICE_DATA = {
  // Proteins (per pound)
  'chicken breast': { price: 3.49, unit: 'lb', category: 'meat' },
  'chicken thigh': { price: 2.49, unit: 'lb', category: 'meat' },
  'ground beef': { price: 4.99, unit: 'lb', category: 'meat' },
  'ground turkey': { price: 4.29, unit: 'lb', category: 'meat' },
  'pork chop': { price: 3.99, unit: 'lb', category: 'meat' },
  'bacon': { price: 6.99, unit: 'lb', category: 'meat' },
  'sausage': { price: 5.49, unit: 'lb', category: 'meat' },
  'salmon': { price: 9.99, unit: 'lb', category: 'seafood' },
  'tuna': { price: 7.99, unit: 'lb', category: 'seafood' },
  'shrimp': { price: 12.99, unit: 'lb', category: 'seafood' },

  // Dairy (per unit)
  'milk': { price: 3.49, unit: 'gallon', category: 'dairy' },
  'butter': { price: 4.29, unit: 'lb', category: 'dairy' },
  'eggs': { price: 3.99, unit: 'dozen', category: 'dairy' },
  'cheese': { price: 5.99, unit: 'lb', category: 'dairy' },
  'yogurt': { price: 4.49, unit: '32oz', category: 'dairy' },

  // Vegetables (per pound unless noted)
  'tomato': { price: 2.99, unit: 'lb', category: 'produce' },
  'onion': { price: 0.79, unit: 'lb', category: 'produce' },
  'garlic': { price: 0.25, unit: 'head', category: 'produce' },
  'potato': { price: 0.69, unit: 'lb', category: 'produce' },
  'carrot': { price: 0.99, unit: 'lb', category: 'produce' },
  'lettuce': { price: 2.49, unit: 'head', category: 'produce' },
  'spinach': { price: 3.99, unit: 'bunch', category: 'produce' },
  'broccoli': { price: 1.99, unit: 'lb', category: 'produce' },
  'bell pepper': { price: 1.29, unit: 'each', category: 'produce' },
  'cucumber': { price: 0.79, unit: 'each', category: 'produce' },
  'zucchini': { price: 1.49, unit: 'lb', category: 'produce' },

  // Fruits (per pound unless noted)
  'apple': { price: 1.99, unit: 'lb', category: 'produce' },
  'banana': { price: 0.59, unit: 'lb', category: 'produce' },
  'orange': { price: 1.29, unit: 'lb', category: 'produce' },
  'lemon': { price: 0.50, unit: 'each', category: 'produce' },
  'strawberry': { price: 3.99, unit: 'pint', category: 'produce' },
  'blueberry': { price: 4.99, unit: 'pint', category: 'produce' },

  // Pantry (per standard unit)
  'flour': { price: 0.35, unit: 'lb', category: 'pantry' },
  'sugar': { price: 0.45, unit: 'lb', category: 'pantry' },
  'rice': { price: 0.79, unit: 'lb', category: 'pantry' },
  'pasta': { price: 1.29, unit: 'lb', category: 'pantry' },
  'bread': { price: 2.99, unit: 'loaf', category: 'pantry' },
  'olive oil': { price: 9.99, unit: '500ml', category: 'pantry' },
  'vegetable oil': { price: 2.99, unit: '32oz', category: 'pantry' }
};

/**
 * Get price for an ingredient
 */
function getPrice(ingredientName) {
  const key = ingredientName.toLowerCase();
  return PRICE_DATA[key] || null;
}

/**
 * Estimate total recipe cost
 */
function estimateRecipeCost(ingredients) {
  let total = 0;
  const itemCosts = [];

  for (const ing of ingredients) {
    const price = getPrice(ing.name);
    if (price) {
      // Simple estimation: assume quantity is in same unit
      const cost = (ing.quantity || 1) * price.price;
      total += cost;
      itemCosts.push({
        ingredient: ing.name,
        price: price.price,
        unit: price.unit,
        estimatedCost: Math.round(cost * 100) / 100
      });
    }
  }

  return {
    total: Math.round(total * 100) / 100,
    currency: 'USD',
    items: itemCosts
  };
}

module.exports = {
  PRICE_DATA,
  getPrice,
  estimateRecipeCost
};
