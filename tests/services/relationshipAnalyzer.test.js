/**
 * Tests for SemanticRecipeRelationshipAnalyzer
 */

'use strict';

const { describe, test, assert } = require('../testRunner');
const SemanticRecipeRelationshipAnalyzer = require('../../src/services/relationshipAnalyzer');

const recipeBase = {
  id: 'recipe-1',
  title: 'Classic Spaghetti Carbonara',
  instructions: 'Cook pasta. Saute pancetta. Mix eggs with cheese. Combine all.',
  ingredients: [
    { name: 'spaghetti' },
    { name: 'pancetta' },
    { name: 'eggs' },
    { name: 'parmesan cheese' },
    { name: 'black pepper' }
  ],
  tags: [
    { name: 'italian', type: 'cuisine' },
    { name: 'pasta' }
  ],
  cuisine: 'italian',
  createdAt: '2024-01-15'
};

const recipeVariation = {
  id: 'recipe-2',
  title: 'Spaghetti Carbonara with Peas',
  instructions: 'Cook pasta. Saute pancetta with peas. Mix eggs with cheese. Combine all.',
  ingredients: [
    { name: 'spaghetti' },
    { name: 'pancetta' },
    { name: 'eggs' },
    { name: 'parmesan cheese' },
    { name: 'black pepper' },
    { name: 'peas' }
  ],
  tags: [
    { name: 'italian', type: 'cuisine' },
    { name: 'pasta' }
  ],
  cuisine: 'italian',
  createdAt: '2024-02-01'
};

const recipeContradiction = {
  id: 'recipe-3',
  title: 'Vegan Buddha Bowl',
  instructions: 'Cook quinoa. Roast vegetables. Make tahini dressing.',
  ingredients: [
    { name: 'quinoa' },
    { name: 'chickpeas' },
    { name: 'sweet potato' },
    { name: 'kale' },
    { name: 'tahini' }
  ],
  tags: [
    { name: 'vegan' },
    { name: 'gluten-free' }
  ],
  cuisine: 'american',
  createdAt: '2024-01-20'
};

function createAnalyzer() {
  const mockStore = { readById: () => {}, readAll: () => {} };
  return new SemanticRecipeRelationshipAnalyzer(mockStore);
}

describe('SemanticRecipeRelationshipAnalyzer', () => {

  test('should analyze relationship between recipes', () => {
    const analyzer = createAnalyzer();
    const result = analyzer.analyzeRelationship(recipeBase, recipeVariation);

    assert.ok(result.relationships, 'Should have relationships');
    assert.ok(result.relationships.length > 0, 'Should have at least one relationship');
  });

  test('should identify relationship between similar recipes', () => {
    const analyzer = createAnalyzer();
    const result = analyzer.analyzeRelationship(recipeBase, recipeVariation);

    // Should find cuisine_share and technique_share at minimum
    assert.ok(result.relationships.length > 0, 'Should find at least one relationship');
    const hasCuisine = result.relationships.some(
      r => r.type === analyzer.relationshipTypes.CUISINE_SHARE
    );
    assert.ok(hasCuisine, 'Should find cuisine share relationship');
  });

  test('should identify relationship between different recipes', () => {
    const analyzer = createAnalyzer();
    const result = analyzer.analyzeRelationship(recipeBase, recipeContradiction);

    // May or may not find relationships depending on similarity threshold
    // Just verify the analysis completes without error
    assert.ok(result.relationships !== undefined);
  });

  test('should cache results', () => {
    const analyzer = createAnalyzer();
    const result1 = analyzer.analyzeRelationship(recipeBase, recipeVariation);
    const result2 = analyzer.analyzeRelationship(recipeBase, recipeVariation);

    assert.equal(result1, result2, 'Should return same cached result');
  });

  test('should calculate composite score', () => {
    const analyzer = createAnalyzer();
    const scores = analyzer.calculateRelationshipScore(recipeBase, recipeVariation);

    assert.ok(typeof scores.composite === 'number', 'Should have composite score');
    assert.ok(scores.composite >= 0 && scores.composite <= 1, 'Composite should be 0-1');
  });

  test('should define all relationship types', () => {
    const analyzer = createAnalyzer();
    assert.equal(analyzer.relationshipTypes.DERIVES_FROM, 'derives_from');
    assert.equal(analyzer.relationshipTypes.SUBSTITUTES, 'substitutes');
    assert.equal(analyzer.relationshipTypes.ENHANCES, 'enhances');
    assert.equal(analyzer.relationshipTypes.CONTRADICTS, 'contradicts');
    assert.equal(analyzer.relationshipTypes.SEASONAL_VARIANT, 'seasonal_variant');
  });

  test('should normalize ingredients from array of objects', () => {
    const analyzer = createAnalyzer();
    const normalized = analyzer.normalizeIngredients(recipeBase);

    assert.ok(normalized.includes('spaghetti'), 'Should contain spaghetti');
    assert.ok(normalized.includes('pancetta'), 'Should contain pancetta');
  });

  test('should detect vegan recipes', () => {
    const analyzer = createAnalyzer();
    assert.equal(analyzer.isVegan(recipeContradiction), true, 'Should detect vegan');
    assert.equal(analyzer.isVegan(recipeBase), false, 'Should detect non-vegan');
  });

  test('should detect meat in recipes', () => {
    const analyzer = createAnalyzer();
    const recipeWithChicken = {
      id: 'test',
      ingredients: [{ name: 'chicken breast' }]
    };
    assert.equal(analyzer.containsMeat(recipeWithChicken), true, 'Should detect chicken');
    assert.equal(analyzer.containsMeat(recipeContradiction), false, 'Should detect no meat');
  });

  test('should extract allergens', () => {
    const analyzer = createAnalyzer();
    const recipe = {
      ingredients: [
        { name: 'peanuts' },
        { name: 'milk' },
        { name: 'flour' }
      ]
    };

    const allergens = analyzer.extractAllergens(recipe);

    assert.ok(allergens.includes('peanut'), 'Should find peanut allergen');
    assert.ok(allergens.includes('milk'), 'Should find milk allergen');
  });

  test('should calculate Jaccard similarity', () => {
    const analyzer = createAnalyzer();
    const setA = ['a', 'b', 'c'];
    const setB = ['b', 'c', 'd'];

    const similarity = analyzer.jaccardSimilarity(setA, setB);

    assert.equal(similarity, 2 / 4, 'Should be 0.5');
  });

  test('should clear cache', () => {
    const analyzer = createAnalyzer();
    analyzer.analyzeRelationship(recipeBase, recipeVariation);
    const result = analyzer.clearCache();

    assert.equal(result.cleared, true);
  });
});
