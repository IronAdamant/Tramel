'use strict';

const assert = require('assert');

/**
 * Minimal test runner using Node's built-in assert module.
 * Replaces Jest for zero-dependency testing.
 */

const tests = [];
let currentDescribe = '';
let passed = 0;
let failed = 0;

/**
 * Describe a test suite
 */
function describe(name, fn) {
  currentDescribe = name;
  fn();
  currentDescribe = '';
}

/**
 * Test case
 */
function test(name, fn) {
  tests.push({ name: `${currentDescribe} > ${name}`, fn });
}

/**
 * Run all tests
 */
async function runTests() {
  console.log('\n========================================');
  console.log('RecipeLab Test Suite');
  console.log('========================================\n');

  for (const t of tests) {
    try {
      await t.fn();
      passed++;
      console.log(`  ✓ ${t.name}`);
    } catch (err) {
      failed++;
      console.log(`  ✗ ${t.name}`);
      console.log(`    Error: ${err.message}`);
    }
  }

  console.log('\n----------------------------------------');
  console.log(`Results: ${passed} passed, ${failed} failed, ${tests.length} total`);
  console.log('----------------------------------------\n');

  if (failed > 0) {
    process.exit(1);
  }
}

// Export test utilities
module.exports = {
  describe,
  test,
  assert,
  runTests,
  // Re-export assert functions for convenience
  equal: assert.strictEqual,
  deepEqual: assert.deepStrictEqual,
  ok: assert.ok,
  throws: assert.throws,
  doesNotThrow: assert.doesNotThrow,
  fail: assert.fail
};
