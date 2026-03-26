/**
 * Tests for SimilarityAlgorithms
 *
 * These tests challenge Chisel because:
 * 1. Each algorithm has multiple branches needing coverage
 * 2. Edge cases (empty sets, zero vectors) need tests
 * 3. Composite scoring logic needs thorough testing
 */

const SimilarityAlgorithms = require('../../src/services/similarityEngines/SimilarityAlgorithms');

describe('SimilarityAlgorithms', () => {
  describe('calculateJaccard', () => {
    it('should calculate Jaccard similarity for overlapping sets', () => {
      const setA = new Set(['apple', 'banana', 'cherry']);
      const setB = new Set(['banana', 'cherry', 'date']);

      const similarity = SimilarityAlgorithms.calculateJaccard(setA, setB);

      // Intersection: {banana, cherry} = 2
      // Union: {apple, banana, cherry, date} = 4
      // Jaccard = 2/4 = 0.5
      expect(similarity).toBe(0.5);
    });

    it('should return 1 for identical sets', () => {
      const setA = new Set(['apple', 'banana']);
      const setB = new Set(['apple', 'banana']);

      expect(SimilarityAlgorithms.calculateJaccard(setA, setB)).toBe(1);
    });

    it('should return 0 for disjoint sets', () => {
      const setA = new Set(['apple', 'banana']);
      const setB = new Set(['cherry', 'date']);

      expect(SimilarityAlgorithms.calculateJaccard(setA, setB)).toBe(0);
    });

    it('should return 1 for two empty sets', () => {
      expect(SimilarityAlgorithms.calculateJaccard(new Set(), new Set())).toBe(1);
    });

    it('should return 0 when one set is empty', () => {
      const setA = new Set(['apple']);
      const setB = new Set();

      expect(SimilarityAlgorithms.calculateJaccard(setA, setB)).toBe(0);
      expect(SimilarityAlgorithms.calculateJaccard(setB, setA)).toBe(0);
    });

    it('should handle null/undefined inputs', () => {
      expect(SimilarityAlgorithms.calculateJaccard(null, null)).toBe(0);
      expect(SimilarityAlgorithms.calculateJaccard(undefined, new Set())).toBe(0);
    });
  });

  describe('calculateCosine', () => {
    it('should calculate cosine similarity for identical vectors', () => {
      const vectorA = [1, 2, 3];
      const vectorB = [1, 2, 3];

      expect(SimilarityAlgorithms.calculateCosine(vectorA, vectorB)).toBeCloseTo(1);
    });

    it('should calculate cosine similarity for orthogonal vectors', () => {
      const vectorA = [1, 0, 0];
      const vectorB = [0, 1, 0];

      expect(SimilarityAlgorithms.calculateCosine(vectorA, vectorB)).toBeCloseTo(0);
    });

    it('should calculate cosine similarity for opposite vectors', () => {
      const vectorA = [1, 2, 3];
      const vectorB = [-1, -2, -3];

      expect(SimilarityAlgorithms.calculateCosine(vectorA, vectorB)).toBeCloseTo(-1);
    });

    it('should return 0 for zero vectors', () => {
      const vectorA = [0, 0, 0];
      const vectorB = [1, 2, 3];

      expect(SimilarityAlgorithms.calculateCosine(vectorA, vectorB)).toBe(0);
    });

    it('should handle mismatched lengths', () => {
      const vectorA = [1, 2];
      const vectorB = [1, 2, 3];

      expect(SimilarityAlgorithms.calculateCosine(vectorA, vectorB)).toBe(0);
    });

    it('should handle null/undefined inputs', () => {
      expect(SimilarityAlgorithms.calculateCosine(null, null)).toBe(0);
      expect(SimilarityAlgorithms.calculateCosine(undefined, [1, 2])).toBe(0);
    });
  });

  describe('calculateEuclidean', () => {
    it('should return 1 for identical vectors', () => {
      const vectorA = [1, 2, 3];
      const vectorB = [1, 2, 3];

      expect(SimilarityAlgorithms.calculateEuclidean(vectorA, vectorB)).toBe(1);
    });

    it('should return less than 1 for different vectors', () => {
      const vectorA = [0, 0, 0];
      const vectorB = [10, 10, 10];

      const similarity = SimilarityAlgorithms.calculateEuclidean(vectorA, vectorB);
      expect(similarity).toBeLessThan(1);
      expect(similarity).toBeGreaterThan(0);
    });

    it('should return 0 for max distance', () => {
      const vectorA = [0, 0, 0];
      const vectorB = [100, 100, 100];

      expect(SimilarityAlgorithms.calculateEuclidean(vectorA, vectorB)).toBe(0);
    });

    it('should handle null/undefined inputs', () => {
      expect(SimilarityAlgorithms.calculateEuclidean(null, null)).toBe(0);
    });
  });

  describe('calculateManhattan', () => {
    it('should return 1 for identical vectors', () => {
      const vectorA = [5, 5, 5];
      const vectorB = [5, 5, 5];

      expect(SimilarityAlgorithms.calculateManhattan(vectorA, vectorB)).toBe(1);
    });

    it('should calculate Manhattan distance correctly', () => {
      const vectorA = [1, 2, 3];
      const vectorB = [4, 6, 8];

      // |1-4| + |2-6| + |3-8| = 3 + 4 + 5 = 12
      // Normalized: 1 - 12/(3*100) = 0.96
      const similarity = SimilarityAlgorithms.calculateManhattan(vectorA, vectorB);
      expect(similarity).toBeCloseTo(0.96);
    });
  });

  describe('calculatePearson', () => {
    it('should return 1 for perfectly correlated vectors', () => {
      const vectorA = [1, 2, 3, 4, 5];
      const vectorB = [2, 4, 6, 8, 10];

      expect(SimilarityAlgorithms.calculatePearson(vectorA, vectorB)).toBeCloseTo(1);
    });

    it('should return 0 for uncorrelated vectors', () => {
      const vectorA = [1, 2, 3, 4, 5];
      const vectorB = [5, 4, 3, 2, 1];

      // Perfect negative correlation should give near 0 after normalization
      const similarity = SimilarityAlgorithms.calculatePearson(vectorA, vectorB);
      expect(similarity).toBeLessThan(0.1);
    });

    it('should return 1 for constant vectors', () => {
      const vectorA = [5, 5, 5, 5];
      const vectorB = [1, 2, 3, 4];

      expect(SimilarityAlgorithms.calculatePearson(vectorA, vectorB)).toBe(1);
    });
  });

  describe('calculateDice', () => {
    it('should calculate Dice coefficient', () => {
      const setA = new Set(['apple', 'banana', 'cherry']);
      const setB = new Set(['banana', 'cherry', 'date']);

      // Intersection: {banana, cherry} = 2
      // Dice = 2 * 2 / (3 + 3) = 4/6 = 0.666...
      const similarity = SimilarityAlgorithms.calculateDice(setA, setB);
      expect(similarity).toBeCloseTo(0.666, 2);
    });

    it('should return 1 for identical sets', () => {
      const setA = new Set(['apple', 'banana']);
      expect(SimilarityAlgorithms.calculateDice(setA, setA)).toBe(1);
    });
  });

  describe('calculateOverlap', () => {
    it('should calculate overlap coefficient', () => {
      const setA = new Set(['a', 'b', 'c', 'd']);
      const setB = new Set(['c', 'd', 'e', 'f']);

      // Intersection: {c, d} = 2
      // min(|A|, |B|) = min(4, 4) = 4
      // Overlap = 2/4 = 0.5
      const similarity = SimilarityAlgorithms.calculateOverlap(setA, setB);
      expect(similarity).toBe(0.5);
    });

    it('should handle subset relationships', () => {
      const setA = new Set(['a', 'b', 'c']);
      const setB = new Set(['a', 'b']);

      // Intersection: {a, b} = 2
      // min(3, 2) = 2
      // Overlap = 2/2 = 1
      expect(SimilarityAlgorithms.calculateOverlap(setA, setB)).toBe(1);
      expect(SimilarityAlgorithms.calculateOverlap(setB, setA)).toBe(1);
    });
  });

  describe('calculateTanimoto', () => {
    it('should calculate Tanimoto coefficient', () => {
      const vectorA = [1, 0, 0];
      const vectorB = [1, 0, 0];

      // A·B = 1, ||A||² = 1, ||B||² = 1
      // Tanimoto = 1 / (1 + 1 - 1) = 1
      expect(SimilarityAlgorithms.calculateTanimoto(vectorA, vectorB)).toBe(1);
    });

    it('should handle zero vectors', () => {
      const vectorA = [0, 0, 0];
      const vectorB = [1, 2, 3];

      expect(SimilarityAlgorithms.calculateTanimoto(vectorA, vectorB)).toBe(0);
    });
  });

  describe('calculateComposite', () => {
    it('should combine multiple similarities with weights', () => {
      const results = {
        jaccard: 0.8,
        cosine: 0.9,
        euclidean: 0.7,
        pearson: 0.85
      };

      const weights = {
        jaccard: 0.25,
        cosine: 0.25,
        euclidean: 0.25,
        pearson: 0.25
      };

      const composite = SimilarityAlgorithms.calculateComposite(results, weights);
      const expected = (0.8 + 0.9 + 0.7 + 0.85) / 4;

      expect(composite).toBeCloseTo(expected);
    });

    it('should handle missing similarity values', () => {
      const results = {
        jaccard: 0.8
        // cosine, euclidean, pearson are undefined
      };

      const composite = SimilarityAlgorithms.calculateComposite(results, {
        jaccard: 1
      });

      expect(composite).toBe(0.8);
    });

    it('should clamp result to [0, 1]', () => {
      const results = {
        jaccard: 1.5, // Over 1
        cosine: -0.5  // Under 0
      };

      const composite = SimilarityAlgorithms.calculateComposite(results, {
        jaccard: 0.5,
        cosine: 0.5
      });

      expect(composite).toBeGreaterThanOrEqual(0);
      expect(composite).toBeLessThanOrEqual(1);
    });

    it('should use default weights', () => {
      const results = {
        jaccard: 0.8,
        cosine: 0.8,
        euclidean: 0.8,
        pearson: 0.8
      };

      const composite = SimilarityAlgorithms.calculateComposite(results);
      expect(composite).toBe(0.8);
    });
  });
});
