'use strict';

const { createRouter } = require('../../utils/router');
const DietaryProfile = require('../../models/DietaryProfile');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all dietary profiles
router.get('/', (req, res) => {
  const profile = new DietaryProfile(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = profile.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get dietary profile by ID
router.get('/:id', (req, res) => {
  const profile = new DietaryProfile(req.db);
  const item = profile.getById(req.params.id);
  if (!item) return notFound(res, 'Dietary profile not found');
  success(res, item);
});

// Create dietary profile
router.post('/', (req, res) => {
  const profile = new DietaryProfile(req.db);
  const item = profile.create(req.body);
  created(res, item);
});

// Update dietary profile
router.put('/:id', (req, res) => {
  const profile = new DietaryProfile(req.db);
  const existing = profile.getById(req.params.id);
  if (!existing) return notFound(res, 'Dietary profile not found');

  const updated = profile.update(req.params.id, req.body);
  success(res, updated);
});

// Delete dietary profile
router.delete('/:id', (req, res) => {
  const profile = new DietaryProfile(req.db);
  const deleted = profile.delete(req.params.id);
  if (!deleted) return notFound(res, 'Dietary profile not found');
  success(res, { deleted: true });
});

module.exports = router;
