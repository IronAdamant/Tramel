/**
 * auditLog plugin
 * Logs all entity CRUD operations for audit purposes
 */

const auditTrail = [];

module.exports = {
  name: 'auditLog',
  hooks: ['beforeCreate', 'afterCreate', 'beforeUpdate', 'afterUpdate', 'beforeDelete', 'afterDelete'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;
    const timestamp = new Date().toISOString();

    const operationMap = {
      beforeCreate: { action: 'CREATE', stage: 'pre' },
      afterCreate: { action: 'CREATE', stage: 'post' },
      beforeUpdate: { action: 'UPDATE', stage: 'pre' },
      afterUpdate: { action: 'UPDATE', stage: 'post' },
      beforeDelete: { action: 'DELETE', stage: 'pre' },
      afterDelete: { action: 'DELETE', stage: 'post' }
    };

    const { action, stage } = operationMap[hook] || {};

    const entry = {
      timestamp,
      action,
      stage,
      hook,
      entityType: ctx.entityType || 'unknown',
      entityId: ctx.entityId || null
    };

    auditTrail.push(entry);
    console.log(`[auditLog] ${action} ${stage} - Entity: ${entry.entityType}, ID: ${entry.entityId}`);

    return { ...ctx, auditEntry: entry };
  },

  /**
   * Get the audit trail
   * @returns {Array} All audit entries
   */
  getAuditTrail: () => [...auditTrail],

  /**
   * Clear the audit trail
   */
  clearTrail: () => {
    auditTrail.length = 0;
  }
};
