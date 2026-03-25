'use strict';

const { createRouter } = require('../../utils/router');
const MealPlan = require('../../models/MealPlan');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all meal plans
router.get('/', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = mealPlan.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get meal plan by ID
router.get('/:id', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const item = mealPlan.getById(req.params.id);
  if (!item) return notFound(res, 'Meal plan not found');
  success(res, item);
});

// Create meal plan
router.post('/', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const item = mealPlan.create(req.body);
  created(res, item);
});

// Update meal plan
router.put('/:id', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const existing = mealPlan.getById(req.params.id);
  if (!existing) return notFound(res, 'Meal plan not found');

  const updated = mealPlan.update(req.params.id, req.body);
  success(res, updated);
});

// Delete meal plan
router.delete('/:id', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const deleted = mealPlan.delete(req.params.id);
  if (!deleted) return notFound(res, 'Meal plan not found');
  success(res, { deleted: true });
});

// Add entry to meal plan
router.post('/:id/entries', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const item = mealPlan.addEntry({
    ...req.body,
    meal_plan_id: req.params.id
  });
  created(res, item);
});

// Remove entry from meal plan
router.delete('/:id/entries/:entryId', (req, res) => {
  const mealPlan = new MealPlan(req.db);
  const deleted = mealPlan.removeEntry(req.params.entryId);
  if (!deleted) return notFound(res, 'Entry not found');
  success(res, { deleted: true });
});

module.exports = router;
