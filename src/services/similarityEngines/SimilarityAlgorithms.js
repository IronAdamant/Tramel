/**
 * SimilarityAlgorithms - Multiple similarity calculation algorithms
 *
 * This module challenges ALL THREE MCPs:
 *
 * STELE-CONTEXT:
 * - Each algorithm is a separate symbol that gets called dynamically
 * - The algorithms cross-reference each other in composite scoring
 * - Method names like 'calculateJaccard', 'calculateCosine' need tracking
 *
 * CHISEL:
 * - Each algorithm branch needs coverage testing
 * - Edge cases (empty sets, zero vectors) need tests
 * - The composite scoring logic needs thorough testing
 *
 * TRAMMEL:
 * - Planning this required understanding algorithm dependencies
 * - Multiple files need coordinated updates
 */

class SimilarityAlgorithms {
  /**
   * Calculate Jaccard similarity between two sets
   * Jaccard = |A ∩ B| / |A ∪ B|
   *
   * Used for: tag overlap, ingredient overlap
   */
  calculateJaccard(setA, setB) {
    if (!setA || !setB) return 0;
    if (setA.size === 0 && setB.size === 0) return 1;
    if (setA.size === 0 || setB.size === 0) return 0;

    const intersection = new Set([...setA].filter(x => setB.has(x)));
    const union = new Set([...setA, ...setB]);

    return intersection.size / union.size;
  }

  /**
   * Calculate Cosine similarity between two vectors
   * Cosine = (A · B) / (||A|| * ||B||)
   *
   * Used for: nutrient vectors, flavor profiles
   */
  calculateCosine(vectorA, vectorB) {
    if (!vectorA || !vectorB) return 0;
    if (vectorA.length !== vectorB.length) return 0;
    if (vectorA.length === 0) return 1;

    // Dot product
    let dotProduct = 0;
    for (let i = 0; i < vectorA.length; i++) {
      dotProduct += vectorA[i] * vectorB[i];
    }

    // Magnitudes
    const magA = Math.sqrt(vectorA.reduce((sum, val) => sum + val * val, 0));
    const magB = Math.sqrt(vectorB.reduce((sum, val) => sum + val * val, 0));

    if (magA === 0 || magB === 0) return 0;

    return dotProduct / (magA * magB);
  }

  /**
   * Calculate Euclidean distance between two vectors
   * Euclidean = sqrt(Σ(a_i - b_i)²)
   *
   * Returns similarity (1 - normalized_distance)
   */
  calculateEuclidean(vectorA, vectorB) {
    if (!vectorA || !vectorB) return 0;
    if (vectorA.length !== vectorB.length) return 0;

    let sumSquaredDiff = 0;
    for (let i = 0; i < vectorA.length; i++) {
      sumSquaredDiff += Math.pow(vectorA[i] - vectorB[i], 2);
    }

    const distance = Math.sqrt(sumSquaredDiff);

    // Normalize to 0-1 similarity (assuming max distance of 100)
    const maxDistance = 100;
    const normalized = Math.min(distance / maxDistance, 1);

    return 1 - normalized;
  }

  /**
   * Calculate Manhattan distance between two vectors
   * Manhattan = Σ|a_i - b_i|
   */
  calculateManhattan(vectorA, vectorB) {
    if (!vectorA || !vectorB) return 0;
    if (vectorA.length !== vectorB.length) return 0;

    let distance = 0;
    for (let i = 0; i < vectorA.length; i++) {
      distance += Math.abs(vectorA[i] - vectorB[i]);
    }

    // Normalize to 0-1 similarity
    const maxDistance = vectorA.length * 100; // Assume max 100 per dimension
    return 1 - Math.min(distance / maxDistance, 1);
  }

  /**
   * Calculate Pearson correlation coefficient
   * Range: -1 to 1, we normalize to 0 to 1
   */
  calculatePearson(vectorA, vectorB) {
    if (!vectorA || !vectorB) return 0;
    if (vectorA.length !== vectorB.length) return 0;
    if (vectorA.length < 2) return 1;

    const n = vectorA.length;

    // Calculate means
    const meanA = vectorA.reduce((sum, val) => sum + val, 0) / n;
    const meanB = vectorB.reduce((sum, val) => sum + val, 0) / n;

    // Calculate correlation
    let numerator = 0;
    let denomA = 0;
    let denomB = 0;

    for (let i = 0; i < n; i++) {
      const diffA = vectorA[i] - meanA;
      const diffB = vectorB[i] - meanB;
      numerator += diffA * diffB;
      denomA += diffA * diffA;
      denomB += diffB * diffB;
    }

    const denominator = Math.sqrt(denomA * denomB);
    if (denominator === 0) return 1; // All same values

    const correlation = numerator / denominator;

    // Normalize from [-1, 1] to [0, 1]
    return (correlation + 1) / 2;
  }

  /**
   * Calculate Dice coefficient
   * Dice = 2 * |A ∩ B| / (|A| + |B|)
   */
  calculateDice(setA, setB) {
    if (!setA || !setB) return 0;
    if (setA.size === 0 && setB.size === 0) return 1;
    if (setA.size === 0 || setB.size === 0) return 0;

    const intersection = new Set([...setA].filter(x => setB.has(x)));

    return (2 * intersection.size) / (setA.size + setB.size);
  }

  /**
   * Calculate overlap coefficient
   * Overlap = |A ∩ B| / min(|A|, |B|)
   */
  calculateOverlap(setA, setB) {
    if (!setA || !setB) return 0;
    if (setA.size === 0 && setB.size === 0) return 1;
    if (setA.size === 0 || setB.size === 0) return 0;

    const intersection = new Set([...setA].filter(x => setB.has(x)));
    const minSize = Math.min(setA.size, setB.size);

    return intersection.size / minSize;
  }

  /**
   * Tanimoto coefficient (generalized Jaccard for vectors)
   * Tanimoto = (A · B) / (||A||² + ||B||² - A · B)
   */
  calculateTanimoto(vectorA, vectorB) {
    if (!vectorA || !vectorB) return 0;
    if (vectorA.length !== vectorB.length) return 0;

    let dotProduct = 0;
    let sumSqA = 0;
    let sumSqB = 0;

    for (let i = 0; i < vectorA.length; i++) {
      dotProduct += vectorA[i] * vectorB[i];
      sumSqA += vectorA[i] * vectorA[i];
      sumSqB += vectorB[i] * vectorB[i];
    }

    const denominator = sumSqA + sumSqB - dotProduct;
    if (denominator === 0) return 1;

    return dotProduct / denominator;
  }

  /**
   * Composite similarity - combines multiple algorithms
   */
  calculateComposite(similarityResults, weights = {}) {
    const {
      jaccard = 0.25,
      cosine = 0.25,
      euclidean = 0.25,
      pearson = 0.25
    } = weights;

    const totalWeight = jaccard + cosine + euclidean + pearson;

    const composite =
      (similarityResults.jaccard || 0) * (jaccard / totalWeight) +
      (similarityResults.cosine || 0) * (cosine / totalWeight) +
      (similarityResults.euclidean || 0) * (euclidean / totalWeight) +
      (similarityResults.pearson || 0) * (pearson / totalWeight);

    return Math.max(0, Math.min(1, composite));
  }
}

module.exports = new SimilarityAlgorithms();
