/**
 * afterDelete hook
 * Fired after an entity is deleted
 * @param {Object} context - Contains entity type and id
 */
module.exports = {
  name: 'afterDelete',
  description: 'Fired after an entity is deleted',
  trigger: 'EntityManager.delete()'
};
