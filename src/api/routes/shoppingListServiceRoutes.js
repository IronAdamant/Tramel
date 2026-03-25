'use strict';

const { createRouter } = require('../../utils/router');
const ShoppingListService = require('../../services/shoppingListService');
const { success, notFound } = require('../../utils/response');

const router = createRouter();

// Generate shopping list from meal plan
router.get('/generate/:mealPlanId', (req, res) => {
  const service = new ShoppingListService(req.db);

  const shoppingList = service.generateFromMealPlan(req.params.mealPlanId);

  if (!shoppingList) {
    return notFound(res, 'Meal plan not found');
  }

  success(res, shoppingList);
});

module.exports = router;
