/**
 * beforeDelete hook
 * Fired before an entity is deleted
 * @param {Object} context - Contains entity type and id
 */
module.exports = {
  name: 'beforeDelete',
  description: 'Fired before an entity is deleted',
  trigger: 'EntityManager.delete()'
};
