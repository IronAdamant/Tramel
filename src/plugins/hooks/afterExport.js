/**
 * afterExport hook
 * Fired after an export operation completes
 * @param {Object} context - Contains export format, data, and output
 */
module.exports = {
  name: 'afterExport',
  description: 'Fired after an export operation completes',
  trigger: 'ExporterService.export()'
};
