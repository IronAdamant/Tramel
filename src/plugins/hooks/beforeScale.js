/**
 * beforeScale hook
 * Fired before a recipe is scaled
 * @param {Object} context - Contains recipe and scaling factor
 */
module.exports = {
  name: 'beforeScale',
  description: 'Fired before a recipe is scaled',
  trigger: 'RecipeScalingService.scale()'
};
