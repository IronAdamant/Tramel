'use strict';

/**
 * Explicit substitution rules for ingredients.
 * Maps ingredients to their valid substitutes with quality scores and reasons.
 *
 * Structure:
 * ingredient -> [
 *   { substitute: 'name', score: 0-100, reason: 'why it works', constraints: { avoidAllergens: [], targetNutrition: {} } }
 * ]
 */
const SUBSTITUTION_RULES = {
  // Butter substitutions
  'butter': [
    { substitute: 'olive oil', score: 75, reason: 'Good for savory dishes, similar fat content', constraints: { avoidAllergens: ['dairy'] } },
    { substitute: 'coconut oil', score: 70, reason: 'Solid at room temperature, similar texture', constraints: { avoidAllergens: [] } },
    { substitute: 'vegetable oil', score: 65, reason: 'Neutral flavor, good for baking', constraints: { avoidAllergens: [] } },
    { substitute: 'applesauce', score: 60, reason: 'Reduces fat in baking, adds moisture', constraints: { avoidAllergens: [], targetNutrition: { lowerFat: true } } },
    { substitute: 'greek yogurt', score: 70, reason: 'Creamy texture, protein boost', constraints: { avoidAllergens: ['dairy'] } },
    { substitute: 'avocado', score: 65, reason: 'Healthy fats, creamy texture', constraints: { avoidAllergens: [] } }
  ],

  // Egg substitutions
  'egg': [
    { substitute: 'flax egg', score: 75, reason: '1 tbsp flax + 3 tbsp water per egg, good for binding', constraints: { avoidAllergens: ['eggs'] } },
    { substitute: 'chia egg', score: 75, reason: '1 tbsp chia + 3 tbsp water per egg, similar binding', constraints: { avoidAllergens: [] } },
    { substitute: 'applesauce', score: 60, reason: 'Good for moisture in baking', constraints: { avoidAllergens: [] } },
    { substitute: 'banana', score: 55, reason: 'Adds sweetness, good for pancakes', constraints: { avoidAllergens: [] } },
    { substitute: 'tofu', score: 65, reason: 'Good for savory dishes, adds protein', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'aquafaba', score: 80, reason: 'Chickpea liquid, great for meringues and binding', constraints: { avoidAllergens: ['legumes'] } }
  ],

  // Milk substitutions
  'milk': [
    { substitute: 'almond milk', score: 85, reason: 'Neutral flavor, widely available', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'oat milk', score: 85, reason: 'Creamy texture, good for coffee', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'soy milk', score: 80, reason: 'High protein, good for baking', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'coconut milk', score: 75, reason: 'Rich flavor, good for curries', constraints: { avoidAllergens: [] } },
    { substitute: 'rice milk', score: 70, reason: 'Hypoallergenic, mild flavor', constraints: { avoidAllergens: [] } },
    { substitute: 'water', score: 40, reason: 'Use in emergencies, affects texture', constraints: { avoidAllergens: [] } }
  ],

  // Flour substitutions (for gluten-free)
  'flour': [
    { substitute: 'almond flour', score: 80, reason: 'Gluten-free, high protein, nutty flavor', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'coconut flour', score: 75, reason: 'Gluten-free, high fiber, absorbs more liquid', constraints: { avoidAllergens: [] } },
    { substitute: 'rice flour', score: 70, reason: 'Gluten-free, light texture', constraints: { avoidAllergens: [] } },
    { substitute: 'oat flour', score: 78, reason: 'Gluten-free (if certified), good texture', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'quinoa flour', score: 75, reason: 'High protein, slightly bitter', constraints: { avoidAllergens: [] } }
  ],

  // Sugar substitutions
  'sugar': [
    { substitute: 'honey', score: 80, reason: 'Natural sweetener, adds moisture', constraints: { avoidAllergens: [] } },
    { substitute: 'maple syrup', score: 80, reason: 'Distinctive flavor, liquid sweetener', constraints: { avoidAllergens: [] } },
    { substitute: 'stevia', score: 70, reason: 'Zero calorie, very sweet', constraints: { avoidAllergens: [] } },
    { substitute: 'coconut sugar', score: 75, reason: 'Lower glycemic index', constraints: { avoidAllergens: [] } },
    { substitute: 'dates', score: 72, reason: 'Natural, adds fiber', constraints: { avoidAllergens: [] } }
  ],

  // Cream substitutions
  'cream': [
    { substitute: 'coconut cream', score: 85, reason: 'Rich, creamy, dairy-free', constraints: { avoidAllergens: [] } },
    { substitute: 'cashew cream', score: 82, reason: 'Creamy, neutral flavor', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'silken tofu', score: 70, reason: 'Smooth texture for sauces', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'greek yogurt', score: 78, reason: 'Thick, tangy, high protein', constraints: { avoidAllergens: ['dairy'] } }
  ],

  // Cheese substitutions
  'cheese': [
    { substitute: 'nutritional yeast', score: 75, reason: 'Cheesy flavor, vegan', constraints: { avoidAllergens: [] } },
    { substitute: 'cashew cheese', score: 78, reason: 'Creamy, similar texture', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'tofu ricotta', score: 70, reason: 'Good for Italian dishes', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'vegan cheese', score: 72, reason: 'Direct substitute, varies in quality', constraints: { avoidAllergens: [] } }
  ],

  // Chicken substitutions
  'chicken': [
    { substitute: 'tofu', score: 75, reason: 'High protein, absorbs flavors', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'seitan', score: 85, reason: 'Meat-like texture, high protein', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'tempeh', score: 78, reason: 'Firm texture, nutty flavor', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'chickpeas', score: 70, reason: 'Good for curries and salads', constraints: { avoidAllergens: ['legumes'] } },
    { substitute: 'portobello mushroom', score: 72, reason: 'Meaty texture, umami flavor', constraints: { avoidAllergens: [] } }
  ],

  // Beef substitutions
  'beef': [
    { substitute: 'mushrooms', score: 78, reason: 'Umami-rich, meaty texture', constraints: { avoidAllergens: [] } },
    { substitute: 'lentils', score: 75, reason: 'Hearty texture, high protein', constraints: { avoidAllergens: ['legumes'] } },
    { substitute: 'tempeh', score: 72, reason: 'Firm, nutty, good for tacos', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'seitan', score: 82, reason: 'Closest texture to meat', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'eggplant', score: 65, reason: 'Absorbs flavors, good for lasagna', constraints: { avoidAllergens: [] } }
  ],

  // Soy sauce substitutions
  'soy sauce': [
    { substitute: 'coconut aminos', score: 82, reason: 'Soy-free, slightly sweeter', constraints: { avoidAllergens: [] } },
    { substitute: 'tamari', score: 90, reason: 'Gluten-free soy sauce', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'worcestershire sauce', score: 70, reason: 'Similar umami, contains fish', constraints: { avoidAllergens: ['fish'] } },
    { substitute: 'liquid aminos', score: 85, reason: 'Similar flavor profile', constraints: { avoidAllergens: ['soy'] } }
  ],

  // Honey substitutions
  'honey': [
    { substitute: 'maple syrup', score: 88, reason: 'Similar sweetness, distinct flavor', constraints: { avoidAllergens: [] } },
    { substitute: 'agave nectar', score: 82, reason: 'Very sweet, mild flavor', constraints: { avoidAllergens: [] } },
    { substitute: 'molasses', score: 70, reason: 'Strong flavor, less sweet', constraints: { avoidAllergens: [] } },
    { substitute: 'brown rice syrup', score: 72, reason: 'Mild sweetness, gluten-free', constraints: { avoidAllergens: [] } }
  ],

  // Yogurt substitutions
  'yogurt': [
    { substitute: 'coconut yogurt', score: 85, reason: 'Creamy, dairy-free', constraints: { avoidAllergens: [] } },
    { substitute: 'almond yogurt', score: 80, reason: 'Light, dairy-free', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'silken tofu', score: 72, reason: 'Smooth texture for sauces', constraints: { avoidAllergens: ['soy'] } },
    { substitute: 'sour cream', score: 75, reason: 'Similar tanginess', constraints: { avoidAllergens: ['dairy'] } }
  ],

  // Bread crumb substitutions
  'bread crumbs': [
    { substitute: 'rolled oats', score: 78, reason: 'Good binding, gluten-free if certified', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'crushed rice crackers', score: 72, reason: 'Crispy coating', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'almond meal', score: 75, reason: 'Nutty flavor, gluten-free', constraints: { avoidAllergens: ['tree nuts'] } },
    { substitute: 'cornmeal', score: 70, reason: 'Crispy texture', constraints: { avoidAllergens: [] } }
  ],

  // Olive oil substitutions
  'olive oil': [
    { substitute: 'vegetable oil', score: 80, reason: 'Neutral flavor, similar smoke point', constraints: { avoidAllergens: [] } },
    { substitute: 'avocado oil', score: 85, reason: 'High smoke point, neutral flavor', constraints: { avoidAllergens: [] } },
    { substitute: 'coconut oil', score: 75, reason: 'Good for high heat', constraints: { avoidAllergens: [] } },
    { substitute: 'butter', score: 70, reason: 'Rich flavor, lower smoke point', constraints: { avoidAllergens: ['dairy'] } }
  ],

  // All-purpose flour specific
  'all-purpose flour': [
    { substitute: 'whole wheat flour', score: 78, reason: 'More fiber and nutrients', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'bread flour', score: 90, reason: 'Higher protein for bread', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'cake flour', score: 85, reason: 'Lower protein for tender baked goods', constraints: { avoidAllergens: ['gluten'] } },
    { substitute: 'gluten-free flour blend', score: 75, reason: 'Direct substitute for gluten-free', constraints: { avoidAllergens: [] } }
  ],

  // Salt substitutions
  'salt': [
    { substitute: 'soy sauce', score: 60, reason: 'Adds saltiness and umami', constraints: { avoidAllergens: ['soy', 'gluten'] } },
    { substitute: 'coconut aminos', score: 62, reason: 'Saltiness with sweetness', constraints: { avoidAllergens: [] } },
    { substitute: 'herbs', score: 40, reason: 'Enhances flavor without salt', constraints: { avoidAllergens: [] } },
    { substitute: 'lemon juice', score: 45, reason: 'Brightens flavors, reduces salt need', constraints: { avoidAllergens: [] } }
  ]
};

/**
 * Get substitution rules for an ingredient
 */
function getSubstitutionRules(ingredientName) {
  const key = ingredientName.toLowerCase();
  return SUBSTITUTION_RULES[key] || null;
}

/**
 * Check if an ingredient has substitution rules
 */
function hasSubstitutionRules(ingredientName) {
  const key = ingredientName.toLowerCase();
  return SUBSTITUTION_RULES.hasOwnProperty(key);
}

/**
 * Get all ingredients that can be substituted
 */
function getSubstitutableIngredients() {
  return Object.keys(SUBSTITUTION_RULES);
}

module.exports = {
  SUBSTITUTION_RULES,
  getSubstitutionRules,
  hasSubstitutionRules,
  getSubstitutableIngredients
};
