'use strict';

/**
 * Density data for volume-to-weight conversions
 * Values are grams per cup unless otherwise specified
 */
const DENSITY_DATA = {
  // Flours
  'flour': 125,
  'all-purpose flour': 125,
  'whole wheat flour': 128,
  'bread flour': 127,
  'cake flour': 114,
  'almond flour': 96,
  'coconut flour': 112,

  // Sugars
  'sugar': 200,
  'white sugar': 200,
  'brown sugar': 220,
  'powdered sugar': 120,
  'honey': 340,
  'maple syrup': 315,

  // Liquids
  'water': 236,
  'milk': 244,
  'cream': 238,
  'butter': 227,
  'olive oil': 216,
  'vegetable oil': 218,
  'coconut oil': 218,

  // Dairy
  'yogurt': 245,
  'sour cream': 242,
  'cream cheese': 232,

  // Grains
  'rice': 185,
  'oats': 80,
  'quinoa': 170,

  // Nuts
  'almonds': 143,
  'walnuts': 120,
  'peanuts': 146,

  // Leavening
  'baking powder': 230,
  'baking soda': 220,
  'salt': 288,

  // Cocoa
  'cocoa powder': 85,
  'chocolate chips': 168
};

/**
 * Get density for an ingredient
 */
function getDensity(ingredientName) {
  const key = ingredientName.toLowerCase();
  return DENSITY_DATA[key] || null;
}

/**
 * Convert volume to weight using density
 */
function volumeToWeight(volumeMl, unit, ingredientName) {
  // Convert ml to cups (1 cup = 236.588 ml)
  const cups = volumeMl / 236.588;

  const density = getDensity(ingredientName);
  if (!density) {
    return { error: 'Unknown density for ingredient' };
  }

  return {
    grams: cups * density,
    cups: cups,
    density: density
  };
}

module.exports = {
  DENSITY_DATA,
  getDensity,
  volumeToWeight
};
