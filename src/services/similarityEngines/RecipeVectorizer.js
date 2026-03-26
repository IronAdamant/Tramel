/**
 * RecipeVectorizer - Converts recipes into vectors for similarity comparison
 *
 * This challenges Stele-context because:
 * - Creates complex transformation chains: recipe -> sets -> vectors -> similarity scores
 * - Uses multiple data sources (ingredients, nutrition, tags) for vectorization
 * - Dynamic weight configuration affects calculations
 */

const SimilarityAlgorithms = require('./SimilarityAlgorithms');

class RecipeVectorizer {
  constructor(options = {}) {
    this.algorithms = SimilarityAlgorithms;
    this.nutritionWeights = options.nutritionWeights || {
      calories: 1,
      protein: 1,
      carbohydrates: 1,
      fat: 1,
      fiber: 1
    };
    this.tagWeights = options.tagWeights || {
      cuisine: 2,
      mealType: 1.5,
      dietary: 1,
      difficulty: 1
    };
  }

  /**
   * Convert recipe to ingredient set
   */
  toIngredientSet(recipe) {
    if (!recipe || !recipe.ingredients) return new Set();

    return new Set(
      recipe.ingredients
        .map(i => i.name?.toLowerCase().trim())
        .filter(Boolean)
    );
  }

  /**
   * Convert recipe to tag set
   */
  toTagSet(recipe) {
    if (!recipe) return new Set();

    const tags = new Set();

    // Add cuisine tags
    if (recipe.cuisine) {
      recipe.cuisine.split(',').forEach(c => tags.add(`cuisine:${c.trim().toLowerCase()}`));
    }

    // Add meal type tags
    if (recipe.mealType) {
      if (Array.isArray(recipe.mealType)) {
        recipe.mealType.forEach(m => tags.add(`meal:${m.toLowerCase()}`));
      } else {
        tags.add(`meal:${recipe.mealType.toLowerCase()}`);
      }
    }

    // Add dietary tags
    if (recipe.dietary) {
      if (Array.isArray(recipe.dietary)) {
        recipe.dietary.forEach(d => tags.add(`dietary:${d.toLowerCase()}`));
      } else {
        tags.add(`dietary:${recipe.dietary.toLowerCase()}`);
      }
    }

    // Add explicit tags
    if (recipe.tags) {
      if (Array.isArray(recipe.tags)) {
        recipe.tags.forEach(t => tags.add(t.toLowerCase()));
      } else {
        tags.add(recipe.tags.toLowerCase());
      }
    }

    // Add difficulty
    if (recipe.difficulty) {
      tags.add(`difficulty:${recipe.difficulty.toLowerCase()}`);
    }

    return tags;
  }

  /**
   * Convert recipe to nutrition vector
   */
  toNutritionVector(recipe) {
    if (!recipe || !recipe.nutrition) {
      // Default weights for standard nutrition
      return [
        recipe?.calories || 0,
        recipe?.protein || 0,
        recipe?.carbohydrates || 0,
        recipe?.fat || 0,
        recipe?.fiber || 0
      ];
    }

    const n = recipe.nutrition;
    return [
      (n.calories || 0) * this.nutritionWeights.calories,
      (n.protein || 0) * this.nutritionWeights.protein,
      (n.carbohydrates || 0) * this.nutritionWeights.carbohydrates,
      (n.fat || 0) * this.nutritionWeights.fat,
      (n.fiber || 0) * this.nutritionWeights.fiber
    ];
  }

  /**
   * Convert recipe to time feature vector
   * [prepTime, cookTime, totalTime, avgStepTime]
   */
  toTimeVector(recipe) {
    const prepTime = recipe.prepTime || 0;
    const cookTime = recipe.cookTime || 0;
    const totalTime = recipe.totalTime || (prepTime + cookTime);
    const stepCount = recipe.steps?.length || 1;
    const avgStepTime = totalTime / stepCount;

    return [prepTime, cookTime, totalTime, avgStepTime];
  }

  /**
   * Convert recipe to serving size vector
   */
  toServingVector(recipe) {
    return [recipe.servings || 1, recipe.yield || 1];
  }

  /**
   * Full vectorization of a recipe
   */
  vectorize(recipe) {
    return {
      ingredients: this.toIngredientSet(recipe),
      tags: this.toTagSet(recipe),
      nutrition: this.toNutritionVector(recipe),
      time: this.toTimeVector(recipe),
      servings: this.toServingVector(recipe),
      raw: {
        name: recipe.name,
        cuisine: recipe.cuisine,
        totalTime: recipe.totalTime
      }
    };
  }

  /**
   * Calculate similarity between two vectorized recipes
   */
  calculateSimilarity(vectorA, vectorB, options = {}) {
    const {
      includeBreakdown = false,
      weights = {
        ingredients: 0.4,
        tags: 0.2,
        nutrition: 0.25,
        time: 0.1,
        servings: 0.05
      }
    } = options;

    const results = {};

    // Ingredient similarity (Jaccard)
    results.ingredients = this.algorithms.calculateJaccard(
      vectorA.ingredients,
      vectorB.ingredients
    );

    // Tag similarity (Dice - better for asymmetric sets)
    results.tags = this.algorithms.calculateDice(
      vectorA.tags,
      vectorB.tags
    );

    // Nutrition similarity (Cosine)
    results.nutrition = this.algorithms.calculateCosine(
      vectorA.nutrition,
      vectorB.nutrition
    );

    // Time similarity (Euclidean)
    results.time = this.algorithms.calculateEuclidean(
      vectorA.time,
      vectorB.time
    );

    // Serving similarity (Overlap)
    results.servings = this.algorithms.calculateOverlap(
      new Set(vectorA.servings),
      new Set(vectorB.servings)
    );

    // Calculate weighted composite
    const composite = Object.entries(weights).reduce((sum, [key, weight]) => {
      return sum + (results[key] || 0) * weight;
    }, 0);

    if (includeBreakdown) {
      return {
        composite,
        breakdown: results,
        weights
      };
    }

    return composite;
  }

  /**
   * Find k most similar recipes to a given recipe
   */
  findSimilar(recipe, candidateRecipes, options = {}) {
    const {
      k = 5,
      minSimilarity = 0,
      includeBreakdown = false
    } = options;

    const sourceVector = this.vectorize(recipe);
    const similarities = [];

    for (const candidate of candidateRecipes) {
      if (candidate.id === recipe.id) continue;

      const candidateVector = this.vectorize(candidate);
      const similarity = this.calculateSimilarity(
        sourceVector,
        candidateVector,
        { includeBreakdown }
      );

      if (similarity.composite !== undefined) {
        if (similarity.composite >= minSimilarity) {
          similarities.push({
            recipe: candidate,
            similarity: similarity.composite,
            breakdown: similarity.breakdown
          });
        }
      } else if (similarity >= minSimilarity) {
        similarities.push({
          recipe: candidate,
          similarity,
          breakdown: null
        });
      }
    }

    // Sort by similarity descending
    similarities.sort((a, b) => b.similarity - a.similarity);

    return similarities.slice(0, k);
  }

  /**
   * Cluster recipes by similarity
   */
  cluster(recipes, options = {}) {
    const {
      k = 3, // Number of clusters
      maxIterations = 10
    } = options;

    if (recipes.length <= k) {
      return recipes.map((recipe, i) => ({
        cluster: i,
        recipe,
        centroid: this.vectorize(recipe)
      }));
    }

    // Simple k-means clustering using similarity
    // Initialize centroids randomly
    let centroids = [];
    const usedIndices = new Set();
    while (centroids.length < k) {
      const idx = Math.floor(Math.random() * recipes.length);
      if (!usedIndices.has(idx)) {
        usedIndices.add(idx);
        centroids.push(this.vectorize(recipes[idx]));
      }
    }

    const assignments = new Array(recipes.length);

    for (let iter = 0; iter < maxIterations; iter++) {
      // Assign each recipe to nearest centroid
      for (let i = 0; i < recipes.length; i++) {
        const vector = this.vectorize(recipes[i]);
        let maxSim = -1;
        let cluster = 0;

        for (let c = 0; c < centroids.length; c++) {
          const sim = this.calculateSimilarity(vector, centroids[c]);
          if (sim > maxSim) {
            maxSim = sim;
            cluster = c;
          }
        }

        assignments[i] = cluster;
      }

      // Update centroids (average of cluster members)
      const newCentroids = centroids.map((_, c) => {
        const clusterVectors = recipes
          .map((r, i) => assignments[i] === c ? this.vectorize(r) : null)
          .filter(Boolean);

        if (clusterVectors.length === 0) return centroids[c];

        // Average the vectors
        return this.averageVectors(clusterVectors);
      });

      centroids = newCentroids;
    }

    return recipes.map((recipe, i) => ({
      cluster: assignments[i],
      recipe,
      centroid: centroids[assignments[i]]
    }));
  }

  /**
   * Average multiple vectors
   */
  averageVectors(vectors) {
    if (vectors.length === 0) return null;

    const ingredientSets = vectors.map(v => v.ingredients);
    const tagSets = vectors.map(v => v.tags);
    const avgNutrition = this.averageNumericVectors(vectors.map(v => v.nutrition));
    const avgTime = this.averageNumericVectors(vectors.map(v => v.time));

    return {
      ingredients: this.mergeSets(ingredientSets),
      tags: this.mergeSets(tagSets),
      nutrition: avgNutrition,
      time: avgTime
    };
  }

  averageNumericVectors(vectors) {
    if (vectors.length === 0) return [];
    const len = vectors[0].length;
    const result = new Array(len).fill(0);

    for (const v of vectors) {
      for (let i = 0; i < len; i++) {
        result[i] += (v[i] || 0) / vectors.length;
      }
    }

    return result;
  }

  mergeSets(sets) {
    const merged = new Set();
    for (const set of sets) {
      if (set instanceof Set) {
        for (const item of set) {
          merged.add(item);
        }
      }
    }
    return merged;
  }
}

module.exports = RecipeVectorizer;
