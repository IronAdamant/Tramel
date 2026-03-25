'use strict';

const { createRouter } = require('../../utils/router');
const MealPlannerService = require('../../services/mealPlannerService');
const { success } = require('../../utils/response');

const router = createRouter();

// Generate weekly meal plan
router.get('/generate', (req, res) => {
  const service = new MealPlannerService(req.db);
  const { startDate, endDate, servings } = req.query;

  const plan = service.generateWeeklyPlan({
    startDate,
    endDate,
    servings: servings ? parseInt(servings, 10) : 2
  });

  success(res, plan);
});

// Suggest meals
router.get('/suggest', (req, res) => {
  const service = new MealPlannerService(req.db);
  const { count } = req.query;

  const suggestions = service.suggestMeals({
    count: count ? parseInt(count, 10) : 7
  });

  success(res, suggestions);
});

module.exports = router;
