'use strict';

const { UNITS, normalizeUnit, getUnitInfo } = require('./units');

/**
 * Simple unit conversion
 */
function convert(value, fromUnit, toUnit) {
  const from = normalizeUnit(fromUnit);
  const to = normalizeUnit(toUnit);

  if (from === to) {
    return { value, unit: to };
  }

  const fromInfo = getUnitInfo(from);
  const toInfo = getUnitInfo(to);

  // Check compatibility
  if (fromInfo.type !== toInfo.type) {
    return { error: `Cannot convert between ${fromInfo.type} and ${toInfo.type}` };
  }

  // Convert to base unit, then to target
  let baseValue;

  // Volume to ml
  if (fromInfo.type === 'volume') {
    baseValue = value * fromInfo.toMl;
    return { value: baseValue / toInfo.toMl, unit: to };
  }

  // Weight to grams
  if (fromInfo.type === 'weight') {
    baseValue = value * fromInfo.toGrams;
    return { value: baseValue / toInfo.toGrams, unit: to };
  }

  // Length to mm
  if (fromInfo.type === 'length') {
    baseValue = value * fromInfo.toMm;
    return { value: baseValue / toInfo.toMm, unit: to };
  }

  // Count
  return { value, unit: to };
}

/**
 * Convert to common serving units
 */
function convertToCommonServings(quantity, unit) {
  const normalized = normalizeUnit(unit);
  const info = getUnitInfo(normalized);

  if (info.type === 'volume') {
    // Prefer cups or tablespoons
    const inCups = (quantity * info.toMl) / UNITS.cup.toMl;
    if (inCups >= 0.25) {
      return { quantity: Math.round(inCups * 100) / 100, unit: 'cup' };
    }
    const inTbsp = (quantity * info.toMl) / UNITS.tablespoon.toMl;
    return { quantity: Math.round(inTbsp * 100) / 100, unit: 'tablespoon' };
  }

  if (info.type === 'weight') {
    const inGrams = quantity * info.toGrams;
    if (inGrams >= 1000) {
      return { quantity: Math.round((inGrams / 1000) * 100) / 100, unit: 'kilogram' };
    }
    return { quantity: Math.round(inGrams * 100) / 100, unit: 'gram' };
  }

  return { quantity, unit: normalized };
}

module.exports = {
  convert,
  convertToCommonServings
};
