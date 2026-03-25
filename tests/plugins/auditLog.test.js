'use strict';

const { describe, test, ok, equal } = require('../testRunner');
const auditLog = require('../../src/plugins/plugins/auditLog');

describe('auditLog plugin', () => {
  describe('plugin structure', () => {
    test('should have correct name', () => {
      ok(auditLog.name === 'auditLog');
    });

    test('should subscribe to all CRUD hooks', () => {
      ok(auditLog.hooks.includes('beforeCreate'));
      ok(auditLog.hooks.includes('afterCreate'));
      ok(auditLog.hooks.includes('beforeUpdate'));
      ok(auditLog.hooks.includes('afterUpdate'));
      ok(auditLog.hooks.includes('beforeDelete'));
      ok(auditLog.hooks.includes('afterDelete'));
      ok(auditLog.hooks.length === 6);
    });

    test('should have handler function', () => {
      ok(typeof auditLog.handler === 'function');
    });
  });

  describe('handler', () => {
    test('should log beforeCreate operation', async () => {
      auditLog.clearTrail();
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'beforeCreate', entityType: 'recipe' };

      await auditLog.handler(ctx, { name: 'Test Recipe' });

      console.log = originalLog;
      ok(logged);
    });

    test('should log afterCreate operation', async () => {
      auditLog.clearTrail();
      const originalLog = console.log;
      let logged = false;
      console.log = () => { logged = true; };

      const ctx = { hook: 'afterCreate', entityType: 'recipe', entityId: 123 };

      await auditLog.handler(ctx, { id: 123, name: 'Test Recipe' });

      console.log = originalLog;
      ok(logged);
    });

    test('should include auditEntry in returned context', async () => {
      auditLog.clearTrail();
      const ctx = { hook: 'afterCreate', entityType: 'recipe' };

      const result = await auditLog.handler(ctx, {});

      ok(result.auditEntry !== undefined);
      ok(result.auditEntry.action === 'CREATE');
      ok(result.auditEntry.stage === 'post');
    });
  });

  describe('getAuditTrail', () => {
    test('should return empty array initially', () => {
      auditLog.clearTrail();
      equal(auditLog.getAuditTrail().length, 0);
    });

    test('should return all audit entries', async () => {
      auditLog.clearTrail();
      await auditLog.handler({ hook: 'beforeCreate', entityType: 'recipe' }, {});
      await auditLog.handler({ hook: 'afterCreate', entityType: 'recipe' }, {});
      await auditLog.handler({ hook: 'beforeUpdate', entityType: 'recipe' }, {});

      const trail = auditLog.getAuditTrail();

      ok(trail.length === 3);
      ok(trail[0].action === 'CREATE');
      ok(trail[0].stage === 'pre');
      ok(trail[1].action === 'CREATE');
      ok(trail[1].stage === 'post');
      ok(trail[2].action === 'UPDATE');
    });

    test('should return copy of array', () => {
      auditLog.clearTrail();
      auditLog.getAuditTrail(); // Initialize
      const trail1 = auditLog.getAuditTrail();
      const trail2 = auditLog.getAuditTrail();

      ok(trail1 !== trail2);
    });
  });

  describe('clearTrail', () => {
    test('should clear all audit entries', async () => {
      auditLog.clearTrail();
      await auditLog.handler({ hook: 'beforeCreate', entityType: 'recipe' }, {});
      await auditLog.handler({ hook: 'afterCreate', entityType: 'recipe' }, {});

      auditLog.clearTrail();

      equal(auditLog.getAuditTrail().length, 0);
    });
  });
});
