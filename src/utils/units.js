'use strict';

/**
 * Unit definitions and conversions
 */
const UNITS = {
  // Volume
  teaspoon: { type: 'volume', toMl: 4.92892 },
  tablespoon: { type: 'volume', toMl: 14.7868 },
  cup: { type: 'volume', toMl: 236.588 },
  fluid_ounce: { type: 'volume', toMl: 29.5735 },
  pint: { type: 'volume', toMl: 473.176 },
  quart: { type: 'volume', toMl: 946.353 },
  gallon: { type: 'volume', toMl: 3785.41 },
  liter: { type: 'volume', toMl: 1000 },
  milliliter: { type: 'volume', toMl: 1 },

  // Weight
  ounce: { type: 'weight', toGrams: 28.3495 },
  pound: { type: 'weight', toGrams: 453.592 },
  gram: { type: 'weight', toGrams: 1 },
  kilogram: { type: 'weight', toGrams: 1000 },

  // Length
  inch: { type: 'length', toMm: 25.4 },
  centimeter: { type: 'length', toMm: 10 },
  millimeter: { type: 'length', toMm: 1 },

  // Count
  piece: { type: 'count', toCount: 1 },
  whole: { type: 'count', toCount: 1 },
  clove: { type: 'count', toCount: 1 },
  slice: { type: 'count', toCount: 1 },
  pinch: { type: 'count', toCount: 1 },
  dash: { type: 'count', toCount: 1 }
};

// Aliases
const UNIT_ALIASES = {
  'tsp': 'teaspoon',
  'tbsp': 'tablespoon',
  'tbs': 'tablespoon',
  'fl oz': 'fluid_ounce',
  'pt': 'pint',
  'qt': 'quart',
  'gal': 'gallon',
  'l': 'liter',
  'ml': 'milliliter',
  'oz': 'ounce',
  'lb': 'pound',
  'lbs': 'pound',
  'g': 'gram',
  'kg': 'kilogram',
  'in': 'inch',
  'cm': 'centimeter',
  'mm': 'millimeter',
  'pc': 'piece',
  'pcs': 'piece',
  'cl': 'clove',
  'clv': 'clove'
};

/**
 * Normalize unit name to standard form
 */
function normalizeUnit(unit) {
  if (!unit) return 'piece';

  const lower = unit.toLowerCase().trim();
  return UNIT_ALIASES[lower] || lower.replace(/\s+/g, '_');
}

/**
 * Get unit info
 */
function getUnitInfo(unit) {
  const normalized = normalizeUnit(unit);
  return UNITS[normalized] || { type: 'count', toCount: 1 };
}

/**
 * Check if two units are compatible
 */
function areUnitsCompatible(unit1, unit2) {
  const info1 = getUnitInfo(unit1);
  const info2 = getUnitInfo(unit2);
  return info1.type === info2.type;
}

module.exports = {
  UNITS,
  UNIT_ALIASES,
  normalizeUnit,
  getUnitInfo,
  areUnitsCompatible
};
