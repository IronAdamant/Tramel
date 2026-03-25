'use strict';

const { createRouter } = require('../../utils/router');
const Tag = require('../../models/Tag');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all tags
router.get('/', (req, res) => {
  const tag = new Tag(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = tag.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get tag by ID
router.get('/:id', (req, res) => {
  const tag = new Tag(req.db);
  const item = tag.getById(req.params.id);
  if (!item) return notFound(res, 'Tag not found');
  success(res, item);
});

// Create tag
router.post('/', (req, res) => {
  const tag = new Tag(req.db);
  const item = tag.create(req.body);
  created(res, item);
});

// Update tag
router.put('/:id', (req, res) => {
  const tag = new Tag(req.db);
  const existing = tag.getById(req.params.id);
  if (!existing) return notFound(res, 'Tag not found');

  const updated = tag.update(req.params.id, req.body);
  success(res, updated);
});

// Delete tag
router.delete('/:id', (req, res) => {
  const tag = new Tag(req.db);
  const deleted = tag.delete(req.params.id);
  if (!deleted) return notFound(res, 'Tag not found');
  success(res, { deleted: true });
});

module.exports = router;
