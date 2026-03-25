/**
 * beforeCreate hook
 * Fired before an entity is created
 * @param {Object} context - Contains entity type and data
 */
module.exports = {
  name: 'beforeCreate',
  description: 'Fired before an entity is created',
  trigger: 'EntityManager.create()'
};
