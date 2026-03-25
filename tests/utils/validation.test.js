'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const {
  ValidationError,
  validateRequired,
  validatePositiveInt,
  validatePositiveNumber,
  validateDate,
  validateMealType,
  validateUUID
} = require('../../src/utils/validation');

describe('Validation', () => {
  test('validateRequired should throw for missing fields', () => {
    assert.throws(
      () => validateRequired({ name: 'test' }, ['name', 'description']),
      ValidationError
    );
  });

  test('validateRequired should pass with all fields present', () => {
    const result = validateRequired({ name: 'test', description: 'desc' }, ['name', 'description']);
    equal(result, undefined); // No error thrown
  });

  test('validatePositiveInt should accept valid integers', () => {
    equal(validatePositiveInt(0, 'test'), 0);
    equal(validatePositiveInt(1, 'test'), 1);
    equal(validatePositiveInt(100, 'test'), 100);
  });

  test('validatePositiveInt should reject decimal values', () => {
    assert.throws(() => validatePositiveInt(1.5, 'test'), ValidationError);
  });

  test('validatePositiveInt should reject negative values', () => {
    assert.throws(() => validatePositiveInt(-1, 'test'), ValidationError);
  });

  test('validatePositiveInt should reject non-numeric strings', () => {
    assert.throws(() => validatePositiveInt('abc', 'test'), ValidationError);
  });

  test('validatePositiveNumber should accept valid numbers', () => {
    equal(validatePositiveNumber(0, 'test'), 0);
    equal(validatePositiveNumber(1.5, 'test'), 1.5);
    equal(validatePositiveNumber(0.001, 'test'), 0.001);
  });

  test('validatePositiveNumber should reject negative numbers', () => {
    assert.throws(() => validatePositiveNumber(-1, 'test'), ValidationError);
  });

  test('validateDate should accept valid date strings', () => {
    const result = validateDate('2024-01-15', 'test');
    equal(result, '2024-01-15');
  });

  test('validateDate should reject invalid dates', () => {
    assert.throws(() => validateDate('not-a-date', 'test'), ValidationError);
    assert.throws(() => validateDate(null, 'test'), ValidationError);
  });

  test('validateMealType should accept valid meal types', () => {
    equal(validateMealType('breakfast'), 'breakfast');
    equal(validateMealType('lunch'), 'lunch');
    equal(validateMealType('dinner'), 'dinner');
    equal(validateMealType('snack'), 'snack');
  });

  test('validateMealType should reject invalid meal types', () => {
    assert.throws(() => validateMealType('brunch'), ValidationError);
    assert.throws(() => validateMealType(''), ValidationError);
  });

  test('validateUUID should accept valid UUIDs', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    equal(validateUUID(uuid), uuid);
  });

  test('validateUUID should reject invalid UUIDs', () => {
    assert.throws(() => validateUUID('not-a-uuid'), ValidationError);
    assert.throws(() => validateUUID('123'), ValidationError);
  });
});
