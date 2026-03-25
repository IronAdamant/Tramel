'use strict';

const { createRouter } = require('../../utils/router');
const DietaryComplianceService = require('../../services/dietaryComplianceService');
const { success, notFound } = require('../../utils/response');

const router = createRouter();

// Check dietary compliance for a recipe
router.get('/check/:recipeId', (req, res) => {
  const service = new DietaryComplianceService(req.db);
  const { profileId } = req.query;

  const result = service.checkRecipeCompliance(req.params.recipeId, profileId);

  if (result.error) {
    return notFound(res, result.error);
  }

  success(res, result);
});

module.exports = router;
