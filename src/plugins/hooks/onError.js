/**
 * onError hook
 * Fired when an error occurs in the system
 * @param {Object} context - Contains error info and original hook
 */
module.exports = {
  name: 'onError',
  description: 'Fired when an error occurs',
  trigger: 'PluginManager.dispatch()'
};
