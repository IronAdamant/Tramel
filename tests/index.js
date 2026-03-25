'use strict';

/**
 * Test entry point - runs all test files
 */

const fs = require('fs');
const path = require('path');

// Load and run testRunner
const { runTests } = require('./testRunner');

// Load all test files
const testDir = __dirname;

const testFiles = [
  'utils/fileStore.test.js',
  'utils/router.test.js',
  'utils/validation.test.js',
  'models/recipe.test.js',
  'models/tag.test.js',
  'models/mealPlan.test.js',
  'services/searchService.test.js',
  'services/shoppingListService.test.js'
];

console.log('Loading test files...');

for (const testFile of testFiles) {
  const filePath = path.join(testDir, testFile);
  if (fs.existsSync(filePath)) {
    try {
      require('./' + testFile);
      console.log(`  Loaded: ${testFile}`);
    } catch (err) {
      console.log(`  Failed to load ${testFile}: ${err.message}`);
    }
  }
}

// Run all tests
runTests();
