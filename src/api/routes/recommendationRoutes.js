'use strict';

const { createRouter } = require('../../utils/router');
const RecommendationService = require('../../services/recommendationService');
const { success } = require('../../utils/response');

const router = createRouter();

// Get recommendations
router.get('/', (req, res) => {
  const service = new RecommendationService(req.db);
  const { limit } = req.query;

  const recommendations = service.getRecommendations({
    limit: limit ? parseInt(limit, 10) : 10
  });

  success(res, recommendations);
});

module.exports = router;
