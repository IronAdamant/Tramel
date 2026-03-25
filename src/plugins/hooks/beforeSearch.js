/**
 * beforeSearch hook
 * Fired before a search operation is executed
 * @param {Object} context - Contains search query and options
 */
module.exports = {
  name: 'beforeSearch',
  description: 'Fired before a search operation is executed',
  trigger: 'SearchService.search()'
};
