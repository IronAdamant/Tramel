'use strict';

const { createRouter } = require('../../utils/router');
const Recipe = require('../../models/Recipe');
const { success, created, notFound, badRequest, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all recipes
router.get('/', (req, res) => {
  const recipe = new Recipe(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = recipe.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get recipe by ID
router.get('/:id', (req, res) => {
  const recipe = new Recipe(req.db);
  const item = recipe.getById(req.params.id);
  if (!item) return notFound(res, 'Recipe not found');
  success(res, item);
});

// Create recipe
router.post('/', (req, res) => {
  const recipe = new Recipe(req.db);
  const item = recipe.create(req.body);
  created(res, item);
});

// Update recipe
router.put('/:id', (req, res) => {
  const recipe = new Recipe(req.db);
  const existing = recipe.getById(req.params.id);
  if (!existing) return notFound(res, 'Recipe not found');

  const updated = recipe.update(req.params.id, req.body);
  success(res, updated);
});

// Delete recipe
router.delete('/:id', (req, res) => {
  const recipe = new Recipe(req.db);
  const deleted = recipe.delete(req.params.id);
  if (!deleted) return notFound(res, 'Recipe not found');
  success(res, { deleted: true });
});

module.exports = router;
