'use strict';

const { createRouter } = require('../../utils/router');
const Ingredient = require('../../models/Ingredient');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all ingredients
router.get('/', (req, res) => {
  const ingredient = new Ingredient(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = ingredient.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get ingredient by ID
router.get('/:id', (req, res) => {
  const ingredient = new Ingredient(req.db);
  const item = ingredient.getById(req.params.id);
  if (!item) return notFound(res, 'Ingredient not found');
  success(res, item);
});

// Create ingredient
router.post('/', (req, res) => {
  const ingredient = new Ingredient(req.db);
  const item = ingredient.create(req.body);
  created(res, item);
});

// Update ingredient
router.put('/:id', (req, res) => {
  const ingredient = new Ingredient(req.db);
  const existing = ingredient.getById(req.params.id);
  if (!existing) return notFound(res, 'Ingredient not found');

  const updated = ingredient.update(req.params.id, req.body);
  success(res, updated);
});

// Delete ingredient
router.delete('/:id', (req, res) => {
  const ingredient = new Ingredient(req.db);
  const deleted = ingredient.delete(req.params.id);
  if (!deleted) return notFound(res, 'Ingredient not found');
  success(res, { deleted: true });
});

module.exports = router;
