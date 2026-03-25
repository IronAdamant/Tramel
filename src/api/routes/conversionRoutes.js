'use strict';

const { createRouter } = require('../../utils/router');
const ConversionEngine = require('../../utils/conversionEngine');
const { success, badRequest } = require('../../utils/response');

const router = createRouter();

// Convert units
router.get('/', (req, res) => {
  const { value, from, to } = req.query;

  if (!value || !from || !to) {
    return badRequest(res, 'Missing required parameters: value, from, to');
  }

  const engine = new ConversionEngine();
  const result = engine.convert(parseFloat(value), from, to);

  if (result.error) {
    return badRequest(res, result.error);
  }

  success(res, result);
});

module.exports = router;
