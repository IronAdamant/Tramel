/**
 * beforeExport hook
 * Fired before an export operation
 * @param {Object} context - Contains export format and data
 */
module.exports = {
  name: 'beforeExport',
  description: 'Fired before an export operation',
  trigger: 'ExporterService.export()'
};
