'use strict';

/**
 * Allergen data - maps ingredients to allergens
 */
const ALLERGEN_DATA = {
  // Dairy
  'milk': ['dairy'],
  'cheese': ['dairy'],
  'butter': ['dairy'],
  'yogurt': ['dairy'],
  'cream': ['dairy'],
  'sour cream': ['dairy'],
  'cream cheese': ['dairy'],

  // Eggs
  'egg': ['eggs'],
  'eggs': ['eggs'],
  'egg white': ['eggs'],
  'egg yolk': ['eggs'],

  // Fish
  'fish': ['fish'],
  'salmon': ['fish', 'seafood'],
  'tuna': ['fish', 'seafood'],
  'cod': ['fish', 'seafood'],

  // Shellfish
  'shrimp': ['shellfish', 'seafood'],
  'crab': ['shellfish', 'seafood'],
  'lobster': ['shellfish', 'seafood'],
  'scallop': ['shellfish', 'seafood'],
  'clam': ['shellfish', 'seafood'],
  'mussel': ['shellfish', 'seafood'],

  // Tree nuts
  'almond': ['tree nuts'],
  'walnut': ['tree nuts'],
  'cashew': ['tree nuts'],
  'pecan': ['tree nuts'],
  'pistachio': ['tree nuts'],
  'hazelnut': ['tree nuts'],

  // Peanuts
  'peanut': ['peanuts'],
  'peanuts': ['peanuts'],

  // Wheat/Gluten
  'wheat': ['gluten'],
  'flour': ['gluten'],
  'bread': ['gluten'],
  'pasta': ['gluten'],
  'bread crumbs': ['gluten'],
  'soy sauce': ['gluten', 'soy'],

  // Soy
  'soy': ['soy'],
  'tofu': ['soy'],
  'edamame': ['soy'],
  'soy sauce': ['soy', 'gluten'],
  'tempeh': ['soy'],

  // Sesame
  'sesame': ['sesame'],
  'sesame oil': ['sesame'],
  'tahini': ['sesame']
};

/**
 * Get allergens for an ingredient
 */
function getAllergens(ingredientName) {
  const key = ingredientName.toLowerCase();
  return ALLERGEN_DATA[key] || [];
}

/**
 * Check if ingredient contains any of the specified allergens
 */
function containsAllergen(ingredientName, allergenList) {
  const ingredientAllergens = getAllergens(ingredientName);
  return allergenList.some(allergen =>
    ingredientAllergens.includes(allergen.toLowerCase())
  );
}

/**
 * Allergen categories
 */
const ALLERGEN_CATEGORIES = [
  'dairy',
  'eggs',
  'fish',
  'shellfish',
  'tree nuts',
  'peanuts',
  'gluten',
  'soy',
  'sesame'
];

module.exports = {
  ALLERGEN_DATA,
  getAllergens,
  containsAllergen,
  ALLERGEN_CATEGORIES
};
