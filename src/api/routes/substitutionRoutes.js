'use strict';

const { createRouter } = require('../../utils/router');
const SubstitutionEngine = require('../../services/substitutionEngine');
const { success, notFound, badRequest } = require('../../utils/response');

const router = createRouter();
const engine = new SubstitutionEngine();

/**
 * GET /substitutions/find
 * Find substitutes for an ingredient
 *
 * Query params:
 * - ingredient: ingredient name (required)
 * - avoidAllergens: comma-separated list of allergens to avoid
 * - constraint: constraint string (e.g., 'nut-free', 'vegan')
 */
router.get('/find', (req, res) => {
  const { ingredient, avoidAllergens, constraint } = req.query;

  if (!ingredient) {
    return badRequest(res, 'Ingredient name is required');
  }

  // Parse avoidAllergens from query param
  const allergens = avoidAllergens
    ? avoidAllergens.split(',').map(a => a.trim().toLowerCase())
    : [];

  // Parse constraint if provided
  let parsedConstraint = {};
  if (constraint) {
    parsedConstraint = engine._parseConstraint(constraint);
  }

  const constraints = {
    avoidAllergens: allergens.length > 0 ? allergens : parsedConstraint.avoidAllergens,
    targetNutrition: parsedConstraint.targetNutrition || {}
  };

  const substitutes = engine.findSubstitutes(ingredient, constraints);

  success(res, {
    ingredient,
    constraints,
    count: substitutes.length,
    substitutes
  });
});

/**
 * GET /substitutions/swap
 * Suggest a swap for a recipe ingredient
 *
 * Query params:
 * - recipeId: recipe ID (optional, for future recipe integrity checking)
 * - ingredient: ingredient to replace
 * - constraint: constraint to satisfy (e.g., 'nut-free', 'vegan', 'low-carb')
 */
router.get('/swap', (req, res) => {
  const { recipeId, ingredient, constraint } = req.query;

  if (!ingredient) {
    return badRequest(res, 'Ingredient name is required');
  }

  if (!constraint) {
    return badRequest(res, 'Constraint is required (e.g., "nut-free", "vegan", "low-carb")');
  }

  const result = engine.suggestSwap(recipeId || null, ingredient, constraint);

  if (!result.found) {
    return notFound(res, result.message);
  }

  success(res, result);
});

/**
 * GET /substitutions/compatibility
 * Get compatibility score between two ingredients
 *
 * Query params:
 * - original: original ingredient name
 * - substitute: substitute ingredient name
 */
router.get('/compatibility', (req, res) => {
  const { original, substitute } = req.query;

  if (!original || !substitute) {
    return badRequest(res, 'Both original and substitute ingredient names are required');
  }

  const originalNutrition = require('../../data/nutritionData').getNutrition(original);
  const substituteNutrition = require('../../data/nutritionData').getNutrition(substitute);
  const originalDensity = require('../../data/densityData').getDensity(original);
  const substituteDensity = require('../../data/densityData').getDensity(substitute);

  const score = engine.getCompatibilityScore(
    original,
    substitute,
    originalNutrition,
    substituteNutrition,
    originalDensity,
    substituteDensity
  );

  success(res, {
    original,
    substitute,
    score,
    nutrition: {
      original: originalNutrition,
      substitute: substituteNutrition
    },
    density: {
      original: originalDensity,
      substitute: substituteDensity
    }
  });
});

/**
 * GET /substitutions/parse-constraint
 * Parse a constraint string and return structured constraints
 *
 * Query params:
 * - constraint: constraint string to parse
 */
router.get('/parse-constraint', (req, res) => {
  const { constraint } = req.query;

  if (!constraint) {
    return badRequest(res, 'Constraint string is required');
  }

  const parsed = engine._parseConstraint(constraint);

  success(res, {
    input: constraint,
    parsed
  });
});

module.exports = router;
