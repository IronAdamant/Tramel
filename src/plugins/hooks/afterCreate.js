/**
 * afterCreate hook
 * Fired after an entity is created
 * @param {Object} context - Contains entity type, data, and created entity
 */
module.exports = {
  name: 'afterCreate',
  description: 'Fired after an entity is created',
  trigger: 'EntityManager.create()'
};
