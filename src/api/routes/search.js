'use strict';

const { createRouter } = require('../../utils/router');
const Recipe = require('../../models/Recipe');
const { success } = require('../../utils/response');

const router = createRouter();

// Search recipes
router.get('/', (req, res) => {
  const recipe = new Recipe(req.db);

  const { query, tags, ingredients, maxTime, minServings, sort } = req.query;

  const results = recipe.search({
    query,
    tags: tags ? tags.split(',').map(t => t.trim()) : undefined,
    ingredients,
    maxTime: maxTime ? parseInt(maxTime, 10) : undefined,
    minServings: minServings ? parseInt(minServings, 10) : undefined,
    sort
  });

  success(res, { results, count: results.length });
});

module.exports = router;
