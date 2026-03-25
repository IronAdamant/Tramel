'use strict';

const { createRouter } = require('../../utils/router');
const CookingLog = require('../../models/CookingLog');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all cooking logs
router.get('/', (req, res) => {
  const cookingLog = new CookingLog(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = cookingLog.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get cooking log by ID
router.get('/:id', (req, res) => {
  const cookingLog = new CookingLog(req.db);
  const item = cookingLog.getById(req.params.id);
  if (!item) return notFound(res, 'Cooking log not found');
  success(res, item);
});

// Create cooking log
router.post('/', (req, res) => {
  const cookingLog = new CookingLog(req.db);
  const item = cookingLog.create(req.body);
  created(res, item);
});

// Update cooking log
router.put('/:id', (req, res) => {
  const cookingLog = new CookingLog(req.db);
  const existing = cookingLog.getById(req.params.id);
  if (!existing) return notFound(res, 'Cooking log not found');

  const updated = cookingLog.update(req.params.id, req.body);
  success(res, updated);
});

// Delete cooking log
router.delete('/:id', (req, res) => {
  const cookingLog = new CookingLog(req.db);
  const deleted = cookingLog.delete(req.params.id);
  if (!deleted) return notFound(res, 'Cooking log not found');
  success(res, { deleted: true });
});

module.exports = router;
