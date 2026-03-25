/**
 * afterScale hook
 * Fired after a recipe is scaled
 * @param {Object} context - Contains original recipe, scaling factor, and scaled recipe
 */
module.exports = {
  name: 'afterScale',
  description: 'Fired after a recipe is scaled',
  trigger: 'RecipeScalingService.scale()'
};
