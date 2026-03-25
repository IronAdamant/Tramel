/**
 * onMealPlanGenerated hook
 * Fired when a meal plan is generated
 * @param {Object} context - Contains meal plan data
 */
module.exports = {
  name: 'onMealPlanGenerated',
  description: 'Fired when a meal plan is generated',
  trigger: 'MealPlannerService.generate()'
};
