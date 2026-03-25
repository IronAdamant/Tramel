/**
 * afterUpdate hook
 * Fired after an entity is updated
 * @param {Object} context - Contains entity type, id, and updated entity
 */
module.exports = {
  name: 'afterUpdate',
  description: 'Fired after an entity is updated',
  trigger: 'EntityManager.update()'
};
