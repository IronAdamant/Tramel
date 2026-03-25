/**
 * onRecipeRated hook
 * Fired when a recipe is rated
 * @param {Object} context - Contains recipe and rating
 */
module.exports = {
  name: 'onRecipeRated',
  description: 'Fired when a recipe is rated',
  trigger: 'Recipe.rate()'
};
