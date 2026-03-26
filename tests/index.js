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

// Auto-discover all test files
function findTestFiles(dir) {
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory() && entry.name !== 'testRunner.js') {
      results.push(...findTestFiles(path.join(dir, entry.name)));
    } else if (entry.name.endsWith('.test.js')) {
      results.push(path.join(dir, entry.name).replace(__dirname + '/', ''));
    }
  }
  return results;
}

const testFiles = findTestFiles(__dirname);

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
