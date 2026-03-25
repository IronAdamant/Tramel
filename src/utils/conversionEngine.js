'use strict';

const { UNITS, normalizeUnit, getUnitInfo } = require('./units');

/**
 * Advanced conversion engine with scaling and formatting
 */
class ConversionEngine {
  constructor() {
    this.precision = 2;
  }

  /**
   * Convert value from one unit to another
   */
  convert(value, fromUnit, toUnit) {
    const from = normalizeUnit(fromUnit);
    const to = normalizeUnit(toUnit);

    if (from === to) {
      return {
        value: this.round(value),
        from: fromUnit,
        to: toUnit
      };
    }

    const fromInfo = getUnitInfo(from);
    const toInfo = getUnitInfo(to);

    if (fromInfo.type !== toInfo.type) {
      return {
        error: `Cannot convert ${fromInfo.type} to ${toInfo.type}`,
        from: fromUnit,
        to: toUnit
      };
    }

    let result;

    switch (fromInfo.type) {
      case 'volume':
        result = this.convertVolume(value, from, to);
        break;
      case 'weight':
        result = this.convertWeight(value, from, to);
        break;
      case 'length':
        result = this.convertLength(value, from, to);
        break;
      default:
        result = value;
    }

    return {
      value: this.round(result),
      from: fromUnit,
      to: toUnit,
      original: value
    };
  }

  /**
   * Convert volume units
   */
  convertVolume(value, from, to) {
    // Convert to ml first
    const ml = value * UNITS[from].toMl;
    return ml / UNITS[to].toMl;
  }

  /**
   * Convert weight units
   */
  convertWeight(value, from, to) {
    // Convert to grams first
    const grams = value * UNITS[from].toGrams;
    return grams / UNITS[to].toGrams;
  }

  /**
   * Convert length units
   */
  convertLength(value, from, to) {
    // Convert to mm first
    const mm = value * UNITS[from].toMm;
    return mm / UNITS[to].toMm;
  }

  /**
   * Round to precision
   */
  round(value) {
    const multiplier = Math.pow(10, this.precision);
    return Math.round(value * multiplier) / multiplier;
  }

  /**
   * Scale ingredient quantity
   */
  scaleQuantity(quantity, unit, scaleFactor) {
    const converted = this.convert(quantity, unit, unit);
    return {
      quantity: this.round(converted.value * scaleFactor),
      unit: converted.to || unit
    };
  }

  /**
   * Format quantity for display
   */
  formatQuantity(quantity, unit) {
    // Handle fractions
    const formatted = this.toFraction(quantity);
    return `${formatted} ${unit}`;
  }

  /**
   * Convert decimal to fraction string
   */
  toFraction(decimal) {
    if (!decimal || decimal === 0) return '0';

    const whole = Math.floor(decimal);
    const remainder = decimal - whole;

    if (remainder < 0.05) return String(whole);

    // Common fractions
    const fractions = [
      [0.125, '1/8'],
      [0.25, '1/4'],
      [0.333, '1/3'],
      [0.375, '3/8'],
      [0.5, '1/2'],
      [0.625, '5/8'],
      [0.666, '2/3'],
      [0.75, '3/4'],
      [0.875, '7/8']
    ];

    for (const [dec, frac] of fractions) {
      if (Math.abs(remainder - dec) < 0.05) {
        return whole > 0 ? `${whole} ${frac}` : frac;
      }
    }

    return decimal.toFixed(2).replace(/\.?0+$/, '');
  }

  /**
   * Temperature conversion (bonus)
   */
  convertTemperature(value, fromUnit, toUnit) {
    const from = fromUnit.toLowerCase();
    const to = toUnit.toLowerCase();

    // Convert to Celsius first
    let celsius;
    if (from === 'f' || from === 'fahrenheit') {
      celsius = (value - 32) * 5 / 9;
    } else if (from === 'c' || from === 'celsius') {
      celsius = value;
    } else if (from === 'k' || from === 'kelvin') {
      celsius = value - 273.15;
    } else {
      return { error: 'Unknown temperature unit' };
    }

    // Convert from Celsius to target
    if (to === 'f' || to === 'fahrenheit') {
      return { value: this.round((celsius * 9 / 5) + 32), unit: 'F' };
    } else if (to === 'c' || to === 'celsius') {
      return { value: this.round(celsius), unit: 'C' };
    } else if (to === 'k' || to === 'kelvin') {
      return { value: this.round(celsius + 273.15), unit: 'K' };
    }

    return { error: 'Unknown temperature unit' };
  }
}

module.exports = ConversionEngine;
