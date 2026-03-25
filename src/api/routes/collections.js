'use strict';

const { createRouter } = require('../../utils/router');
const Collection = require('../../models/Collection');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all collections
router.get('/', (req, res) => {
  const collection = new Collection(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = collection.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get collection by ID
router.get('/:id', (req, res) => {
  const collection = new Collection(req.db);
  const item = collection.getById(req.params.id);
  if (!item) return notFound(res, 'Collection not found');
  success(res, item);
});

// Create collection
router.post('/', (req, res) => {
  const collection = new Collection(req.db);
  const item = collection.create(req.body);
  created(res, item);
});

// Update collection
router.put('/:id', (req, res) => {
  const collection = new Collection(req.db);
  const existing = collection.getById(req.params.id);
  if (!existing) return notFound(res, 'Collection not found');

  const updated = collection.update(req.params.id, req.body);
  success(res, updated);
});

// Delete collection
router.delete('/:id', (req, res) => {
  const collection = new Collection(req.db);
  const deleted = collection.delete(req.params.id);
  if (!deleted) return notFound(res, 'Collection not found');
  success(res, { deleted: true });
});

// Add recipe to collection
router.post('/:id/recipes/:recipeId', (req, res) => {
  const collection = new Collection(req.db);
  const item = collection.addRecipe(req.params.id, req.params.recipeId);
  created(res, item);
});

// Remove recipe from collection
router.delete('/:id/recipes/:recipeId', (req, res) => {
  const collection = new Collection(req.db);
  const removed = collection.removeRecipe(req.params.id, req.params.recipeId);
  if (!removed) return notFound(res, 'Recipe not in collection');
  success(res, { removed: true });
});

module.exports = router;
