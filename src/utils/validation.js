'use strict';

const assert = require('assert');

/**
 * Validation utilities for input validation.
 * Replaces express-validator for zero-dependency implementation.
 */

class ValidationError extends Error {
  constructor(message, field) {
    super(message);
    this.name = 'ValidationError';
    this.field = field;
    this.status = 400;
  }
}

/**
 * Validate that required fields are present
 */
function validateRequired(obj, fields) {
  const missing = [];
  for (const field of fields) {
    if (obj[field] === undefined || obj[field] === null || obj[field] === '') {
      missing.push(field);
    }
  }
  if (missing.length > 0) {
    throw new ValidationError(`Missing required fields: ${missing.join(', ')}`, missing);
  }
}

/**
 * Validate that a value is a positive integer
 */
function validatePositiveInt(value, name = 'value') {
  const num = parseFloat(value);
  if (isNaN(num) || num < 0 || !Number.isInteger(num)) {
    throw new ValidationError(`${name} must be a positive integer`, name);
  }
  return Math.floor(num);
}

/**
 * Validate that a value is a positive number
 */
function validatePositiveNumber(value, name = 'value') {
  const num = parseFloat(value);
  if (isNaN(num) || num < 0) {
    throw new ValidationError(`${name} must be a positive number`, name);
  }
  return num;
}

/**
 * Validate that a value is a valid date string
 */
function validateDate(value, name = 'value') {
  if (typeof value !== 'string') {
    throw new ValidationError(`${name} must be a date string`, name);
  }
  const date = new Date(value);
  if (isNaN(date.getTime())) {
    throw new ValidationError(`${name} must be a valid date`, name);
  }
  return value;
}

/**
 * Validate meal type
 */
function validateMealType(value, name = 'meal_type') {
  const validTypes = ['breakfast', 'lunch', 'dinner', 'snack'];
  if (!validTypes.includes(value)) {
    throw new ValidationError(
      `${name} must be one of: ${validTypes.join(', ')}`,
      name
    );
  }
  return value;
}

/**
 * Validate difficulty level
 */
function validateDifficulty(value, name = 'difficulty') {
  const validLevels = ['easy', 'medium', 'hard'];
  if (value && !validLevels.includes(value)) {
    throw new ValidationError(
      `${name} must be one of: ${validLevels.join(', ')}`,
      name
    );
  }
  return value;
}

/**
 * Validate cuisine type
 */
function validateCuisine(value, name = 'cuisine') {
  // Allow any string for cuisine, just validate it's a string if provided
  if (value !== undefined && typeof value !== 'string') {
    throw new ValidationError(`${name} must be a string`, name);
  }
  return value;
}

/**
 * Validate array of strings
 */
function validateStringArray(value, name = 'array') {
  if (!Array.isArray(value)) {
    throw new ValidationError(`${name} must be an array`, name);
  }
  for (let i = 0; i < value.length; i++) {
    if (typeof value[i] !== 'string') {
      throw new ValidationError(`${name} must contain only strings`, name);
    }
  }
  return value;
}

/**
 * Validate pagination parameters
 */
function validatePagination(query, defaultLimit = 20, maxLimit = 100) {
  const limit = query.limit !== undefined ? validatePositiveInt(query.limit, 'limit') : defaultLimit;
  const offset = query.offset !== undefined ? validatePositiveInt(query.offset, 'offset') : 0;
  return {
    limit: Math.min(limit, maxLimit),
    offset
  };
}

/**
 * Sanitize a string (trim whitespace)
 */
function sanitizeString(value) {
  if (typeof value !== 'string') return value;
  return value.trim();
}

/**
 * Validate UUID format
 */
function validateUUID(value, name = 'id') {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!uuidRegex.test(value)) {
    throw new ValidationError(`${name} must be a valid UUID`, name);
  }
  return value;
}

module.exports = {
  ValidationError,
  validateRequired,
  validatePositiveInt,
  validatePositiveNumber,
  validateDate,
  validateMealType,
  validateDifficulty,
  validateCuisine,
  validateStringArray,
  validatePagination,
  sanitizeString,
  validateUUID
};
