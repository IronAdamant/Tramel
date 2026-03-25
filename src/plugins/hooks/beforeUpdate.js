/**
 * beforeUpdate hook
 * Fired before an entity is updated
 * @param {Object} context - Contains entity type, id, and changes
 */
module.exports = {
  name: 'beforeUpdate',
  description: 'Fired before an entity is updated',
  trigger: 'EntityManager.update()'
};
