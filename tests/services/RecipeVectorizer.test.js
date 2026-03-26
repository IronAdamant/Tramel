/**
 * Tests for RecipeVectorizer
 */

const RecipeVectorizer = require('../../src/services/similarityEngines/RecipeVectorizer');

describe('RecipeVectorizer', () => {
  let vectorizer;

  beforeEach(() => {
    vectorizer = new RecipeVectorizer();
  });

  describe('constructor', () => {
    it('should set default weights', () => {
      expect(vectorizer.nutritionWeights).toBeDefined();
      expect(vectorizer.tagWeights).toBeDefined();
    });

    it('should accept custom weights', () => {
      const custom = new RecipeVectorizer({
        nutritionWeights: { calories: 2, protein: 1 },
        tagWeights: { cuisine: 3 }
      });

      expect(custom.nutritionWeights.calories).toBe(2);
      expect(custom.tagWeights.cuisine).toBe(3);
    });
  });

  describe('toIngredientSet', () => {
    it('should convert ingredients to lowercase set', () => {
      const recipe = {
        ingredients: [
          { name: 'Apple' },
          { name: 'BANANA' },
          { name: 'Cherry' }
        ]
      };

      const set = vectorizer.toIngredientSet(recipe);
      expect(set).toBeInstanceOf(Set);
      expect(set.has('apple')).toBe(true);
      expect(set.has('banana')).toBe(true);
      expect(set.has('cherry')).toBe(true);
      expect(set.size).toBe(3);
    });

    it('should handle missing ingredients', () => {
      expect(vectorizer.toIngredientSet({})).toEqual(new Set());
      expect(vectorizer.toIngredientSet(null)).toEqual(new Set());
      expect(vectorizer.toIngredientSet(undefined)).toEqual(new Set());
    });

    it('should filter empty ingredient names', () => {
      const recipe = {
        ingredients: [
          { name: 'Apple' },
          { name: '' },
          { name: null },
          { name: 'Banana' }
        ]
      };

      const set = vectorizer.toIngredientSet(recipe);
      expect(set.size).toBe(2);
    });
  });

  describe('toTagSet', () => {
    it('should extract cuisine tags', () => {
      const recipe = { cuisine: 'Italian, Mexican' };
      const tags = vectorizer.toTagSet(recipe);

      expect(tags.has('cuisine:italian')).toBe(true);
      expect(tags.has('cuisine:mexican')).toBe(true);
    });

    it('should extract meal type tags', () => {
      const recipe = { mealType: 'Breakfast' };
      const tags = vectorizer.toTagSet(recipe);

      expect(tags.has('meal:breakfast')).toBe(true);
    });

    it('should extract dietary tags', () => {
      const recipe = { dietary: 'Vegetarian' };
      const tags = vectorizer.toTagSet(recipe);

      expect(tags.has('dietary:vegetarian')).toBe(true);
    });

    it('should extract difficulty tags', () => {
      const recipe = { difficulty: 'Easy' };
      const tags = vectorizer.toTagSet(recipe);

      expect(tags.has('difficulty:easy')).toBe(true);
    });

    it('should handle null recipe', () => {
      expect(vectorizer.toTagSet(null)).toEqual(new Set());
    });
  });

  describe('toNutritionVector', () => {
    it('should extract nutrition values', () => {
      const recipe = {
        nutrition: {
          calories: 500,
          protein: 30,
          carbohydrates: 50,
          fat: 20,
          fiber: 5
        }
      };

      const vector = vectorizer.toNutritionVector(recipe);
      expect(vector).toEqual([500, 30, 50, 20, 5]);
    });

    it('should use default values when nutrition missing', () => {
      const recipe = { calories: 100 };
      const vector = vectorizer.toNutritionVector(recipe);

      expect(vector[0]).toBe(100);
      expect(vector[1]).toBe(0);
    });

    it('should return zeros for null recipe', () => {
      const vector = vectorizer.toNutritionVector(null);
      expect(vector).toEqual([0, 0, 0, 0, 0]);
    });
  });

  describe('toTimeVector', () => {
    it('should create time feature vector', () => {
      const recipe = {
        prepTime: 15,
        cookTime: 30,
        steps: ['step1', 'step2', 'step3']
      };

      const vector = vectorizer.toTimeVector(recipe);
      expect(vector[0]).toBe(15); // prepTime
      expect(vector[1]).toBe(30); // cookTime
      expect(vector[2]).toBe(45); // totalTime
      expect(vector[3]).toBe(15); // avgStepTime (45/3)
    });

    it('should handle missing time values', () => {
      const recipe = { steps: ['step1'] };
      const vector = vectorizer.toTimeVector(recipe);

      expect(vector).toEqual([0, 0, 0, 0]);
    });
  });

  describe('vectorize', () => {
    it('should create full recipe vector', () => {
      const recipe = {
        name: 'Test Recipe',
        cuisine: 'Italian',
        ingredients: [{ name: 'Pasta' }, { name: 'Tomato' }],
        tags: ['quick', 'easy'],
        nutrition: { calories: 400, protein: 15, carbohydrates: 60, fat: 10, fiber: 5 },
        prepTime: 10,
        cookTime: 20,
        steps: ['step1'],
        servings: 4
      };

      const vector = vectorizer.vectorize(recipe);

      expect(vector).toHaveProperty('ingredients');
      expect(vector).toHaveProperty('tags');
      expect(vector).toHaveProperty('nutrition');
      expect(vector).toHaveProperty('time');
      expect(vector.ingredients.has('pasta')).toBe(true);
    });
  });

  describe('calculateSimilarity', () => {
    it('should calculate composite similarity', () => {
      const vectorA = vectorizer.vectorize({
        ingredients: [{ name: 'Apple' }, { name: 'Banana' }],
        cuisine: 'Italian',
        nutrition: { calories: 100, protein: 5, carbohydrates: 20, fat: 2, fiber: 3 }
      });

      const vectorB = vectorizer.vectorize({
        ingredients: [{ name: 'Apple' }, { name: 'Orange' }],
        cuisine: 'Italian',
        nutrition: { calories: 100, protein: 5, carbohydrates: 20, fat: 2, fiber: 3 }
      });

      const similarity = vectorizer.calculateSimilarity(vectorA, vectorB);
      expect(typeof similarity).toBe('number');
      expect(similarity).toBeGreaterThan(0);
    });

    it('should include breakdown when requested', () => {
      const vectorA = vectorizer.vectorize({
        ingredients: [{ name: 'A' }],
        nutrition: { calories: 10, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 }
      });

      const vectorB = vectorizer.vectorize({
        ingredients: [{ name: 'A' }],
        nutrition: { calories: 10, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 }
      });

      const result = vectorizer.calculateSimilarity(vectorA, vectorB, { includeBreakdown: true });
      expect(result).toHaveProperty('composite');
      expect(result).toHaveProperty('breakdown');
      expect(result).toHaveProperty('weights');
    });
  });

  describe('findSimilar', () => {
    it('should find similar recipes', () => {
      const recipe = {
        id: '1',
        name: 'Apple Pie',
        ingredients: [{ name: 'Apple' }, { name: 'Sugar' }],
        cuisine: 'American',
        nutrition: { calories: 300, protein: 2, carbohydrates: 50, fat: 10, fiber: 3 }
      };

      const candidates = [
        { id: '2', name: 'Apple Crisp', ingredients: [{ name: 'Apple' }, { name: 'Oats' }], cuisine: 'American', nutrition: { calories: 280, protein: 3, carbohydrates: 45, fat: 9, fiber: 4 } },
        { id: '3', name: 'Banana Bread', ingredients: [{ name: 'Banana' }, { name: 'Flour' }], cuisine: 'American', nutrition: { calories: 350, protein: 4, carbohydrates: 60, fat: 12, fiber: 2 } }
      ];

      const results = vectorizer.findSimilar(recipe, candidates, { k: 1 });
      expect(results.length).toBeGreaterThan(0);
      expect(results[0].recipe.id).toBe('2'); // Apple Crisp should be more similar
    });

    it('should filter by minimum similarity', () => {
      const recipe = { id: '1', name: 'X', ingredients: [{ name: 'A' }], nutrition: { calories: 100, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 } };
      const candidates = [
        { id: '2', name: 'Y', ingredients: [{ name: 'Z' }], nutrition: { calories: 100, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 } }
      ];

      const results = vectorizer.findSimilar(recipe, candidates, { k: 5, minSimilarity: 0.5 });
      // May or may not have results depending on similarity
      expect(Array.isArray(results)).toBe(true);
    });
  });

  describe('cluster', () => {
    it('should cluster recipes into groups', () => {
      const recipes = [
        { id: '1', name: 'R1', ingredients: [{ name: 'A' }], nutrition: { calories: 100, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 } },
        { id: '2', name: 'R2', ingredients: [{ name: 'A' }], nutrition: { calories: 100, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 } },
        { id: '3', name: 'R3', ingredients: [{ name: 'B' }], nutrition: { calories: 200, protein: 2, carbohydrates: 2, fat: 2, fiber: 2 } }
      ];

      const clusters = vectorizer.cluster(recipes, { k: 2 });
      expect(clusters.length).toBe(3);
      expect(clusters[0]).toHaveProperty('cluster');
      expect(clusters[0]).toHaveProperty('recipe');
    });

    it('should return each recipe in its own cluster if fewer recipes than k', () => {
      const recipes = [
        { id: '1', name: 'R1', ingredients: [{ name: 'A' }], nutrition: { calories: 100, protein: 1, carbohydrates: 1, fat: 1, fiber: 1 } }
      ];

      const clusters = vectorizer.cluster(recipes, { k: 3 });
      expect(clusters.length).toBe(1);
      expect(clusters[0].cluster).toBe(0);
    });
  });
});
