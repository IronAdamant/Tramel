'use strict';

/**
 * Seasonal availability data for ingredients
 * Based on Northern Hemisphere seasons
 */
const SEASONAL_DATA = {
  // Spring (March-May)
  spring: [
    'asparagus', 'artichoke', 'peas', 'radish', 'spinach',
    'lettuce', 'arugula', 'mint', 'parsley', 'chive',
    'rhubarb', 'strawberry', 'cherry', 'lemon'
  ],

  // Summer (June-August)
  summer: [
    'tomato', 'zucchini', 'corn', 'eggplant', 'pepper',
    'cucumber', 'squash', 'watermelon', 'peach', 'nectarine',
    'blueberry', 'raspberry', 'blackberry', 'fig', 'melon',
    'basil', 'oregano', 'thyme', 'rosemary', 'sage'
  ],

  // Fall (September-November)
  fall: [
    'pumpkin', 'squash', 'butternut squash', 'sweet potato',
    'brussels sprouts', 'cabbage', 'kale', 'cauliflower',
    'apple', 'pear', 'grape', 'cranberry', 'pomegranate',
    'persimmon', 'hazelnut', 'walnut'
  ],

  // Winter (December-February)
  winter: [
    'potato', 'carrot', 'onion', 'garlic', 'leek',
    'turnip', 'parsnip', 'beet', 'celery', 'cabbage',
    'citrus', 'orange', 'grapefruit', 'tangerine', 'lemon',
    'lime', 'kale', 'swiss chard'
  ]
};

/**
 * Get current season based on month
 */
function getCurrentSeason() {
  const month = new Date().getMonth();

  if (month >= 2 && month <= 4) return 'spring';
  if (month >= 5 && month <= 7) return 'summer';
  if (month >= 8 && month <= 10) return 'fall';
  return 'winter';
}

/**
 * Get ingredients that are in season
 */
function getInSeason(season = null) {
  const targetSeason = season || getCurrentSeason();
  return SEASONAL_DATA[targetSeason] || [];
}

/**
 * Check if an ingredient is in season
 */
function isInSeason(ingredientName, season = null) {
  const targetSeason = season || getCurrentSeason();
  const seasonal = SEASONAL_DATA[targetSeason] || [];
  const key = ingredientName.toLowerCase();

  return seasonal.some(item => key.includes(item));
}

/**
 * Get peak season for an ingredient
 */
function getPeakSeason(ingredientName) {
  const key = ingredientName.toLowerCase();
  const seasons = [];

  for (const [season, ingredients] of Object.entries(SEASONAL_DATA)) {
    if (ingredients.some(item => key.includes(item))) {
      seasons.push(season);
    }
  }

  return seasons;
}

module.exports = {
  SEASONAL_DATA,
  getCurrentSeason,
  getInSeason,
  isInSeason,
  getPeakSeason
};
