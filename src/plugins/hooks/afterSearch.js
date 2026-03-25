/**
 * afterSearch hook
 * Fired after a search operation completes
 * @param {Object} context - Contains search query, options, and results
 */
module.exports = {
  name: 'afterSearch',
  description: 'Fired after a search operation completes',
  trigger: 'SearchService.search()'
};
