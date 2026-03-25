/**
 * onNutrientCalculated hook
 * Fired when nutrition values are calculated for a recipe
 * @param {Object} context - Contains recipe and nutrition data
 */
module.exports = {
  name: 'onNutrientCalculated',
  description: 'Fired when nutrition values are calculated',
  trigger: 'NutritionService.calculate()'
};
