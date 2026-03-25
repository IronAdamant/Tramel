/**
 * onShoppingListGenerated hook
 * Fired when a shopping list is generated
 * @param {Object} context - Contains shopping list data
 */
module.exports = {
  name: 'onShoppingListGenerated',
  description: 'Fired when a shopping list is generated',
  trigger: 'ShoppingListService.generate()'
};
