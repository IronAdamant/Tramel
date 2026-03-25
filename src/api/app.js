'use strict';

const http = require('http');
const path = require('path');
const fs = require('fs');
const { createRouter } = require('../utils/router');
const { parseBody } = require('../utils/request');
const { getDatabase, initializeDatabase } = require('../db');
const { json, success, error, notFound, badRequest } = require('../utils/response');
const { ValidationError } = require('../utils/validation');

/**
 * Main API application.
 * Replaces Express app for zero-dependency implementation.
 */

const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, '../../public');

// Create routers
const apiRouter = createRouter();

// Initialize database
let db;
function getDb() {
  if (!db) {
    db = initializeDatabase(path.join(__dirname, '../../data'));
  }
  return db;
}

// Attach database to request
function attachDb(req, res, next) {
  req.db = getDb();
  next();
}

// Error handler middleware
function errorHandler(err, req, res) {
  console.error('Error:', err.message);

  if (err instanceof ValidationError) {
    return badRequest(res, err.message, { field: err.field });
  }

  error(res, err.message || 'Internal server error', err.status || 500);
}

// Import routes
const recipesRouter = require('./routes/recipes');
const ingredientsRouter = require('./routes/ingredients');
const tagsRouter = require('./routes/tags');
const mealPlansRouter = require('./routes/mealPlans');
const shoppingListsRouter = require('./routes/shoppingLists');
const collectionsRouter = require('./routes/collections');
const dietaryProfilesRouter = require('./routes/dietaryProfiles');
const cookingLogsRouter = require('./routes/cookingLogs');
const searchRouter = require('./routes/search');
const mealPlannerRouter = require('./routes/mealPlannerRoutes');
const shoppingListServiceRouter = require('./routes/shoppingListServiceRoutes');
const nutritionRouter = require('./routes/nutritionRoutes');
const recommendationRouter = require('./routes/recommendationRoutes');
const costRouter = require('./routes/costRoutes');
const dietaryRouter = require('./routes/dietaryRoutes');
const conversionRouter = require('./routes/conversionRoutes');
const scalingRouter = require('./routes/scalingRoutes');

// Mount routes
apiRouter.get('/health', (req, res) => {
  json(res, { status: 'ok', timestamp: new Date().toISOString() });
});

// Recipe CRUD
apiRouter.get('/recipes', attachDb, recipesRouter.handle.bind(recipesRouter));
apiRouter.get('/recipes/:id', attachDb, recipesRouter.handle.bind(recipesRouter));
apiRouter.post('/recipes', attachDb, parseBody, recipesRouter.handle.bind(recipesRouter));
apiRouter.put('/recipes/:id', attachDb, parseBody, recipesRouter.handle.bind(recipesRouter));
apiRouter.delete('/recipes/:id', attachDb, recipesRouter.handle.bind(recipesRouter));

// Ingredients
apiRouter.get('/ingredients', attachDb, ingredientsRouter.handle.bind(ingredientsRouter));
apiRouter.get('/ingredients/:id', attachDb, ingredientsRouter.handle.bind(ingredientsRouter));
apiRouter.post('/ingredients', attachDb, parseBody, ingredientsRouter.handle.bind(ingredientsRouter));
apiRouter.put('/ingredients/:id', attachDb, parseBody, ingredientsRouter.handle.bind(ingredientsRouter));
apiRouter.delete('/ingredients/:id', attachDb, ingredientsRouter.handle.bind(ingredientsRouter));

// Tags
apiRouter.get('/tags', attachDb, tagsRouter.handle.bind(tagsRouter));
apiRouter.get('/tags/:id', attachDb, tagsRouter.handle.bind(tagsRouter));
apiRouter.post('/tags', attachDb, parseBody, tagsRouter.handle.bind(tagsRouter));
apiRouter.put('/tags/:id', attachDb, parseBody, tagsRouter.handle.bind(tagsRouter));
apiRouter.delete('/tags/:id', attachDb, tagsRouter.handle.bind(tagsRouter));

// Meal Plans
apiRouter.get('/meal-plans', attachDb, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.get('/meal-plans/:id', attachDb, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.post('/meal-plans', attachDb, parseBody, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.put('/meal-plans/:id', attachDb, parseBody, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.delete('/meal-plans/:id', attachDb, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.post('/meal-plans/:id/entries', attachDb, parseBody, mealPlansRouter.handle.bind(mealPlansRouter));
apiRouter.delete('/meal-plans/:id/entries/:entryId', attachDb, mealPlansRouter.handle.bind(mealPlansRouter));

// Shopping Lists
apiRouter.get('/shopping-lists', attachDb, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.get('/shopping-lists/:id', attachDb, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.post('/shopping-lists', attachDb, parseBody, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.put('/shopping-lists/:id', attachDb, parseBody, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.delete('/shopping-lists/:id', attachDb, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.post('/shopping-lists/:id/items', attachDb, parseBody, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.patch('/shopping-lists/:id/items/:itemId', attachDb, parseBody, shoppingListsRouter.handle.bind(shoppingListsRouter));
apiRouter.delete('/shopping-lists/:id/items/:itemId', attachDb, shoppingListsRouter.handle.bind(shoppingListsRouter));

// Collections
apiRouter.get('/collections', attachDb, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.get('/collections/:id', attachDb, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.post('/collections', attachDb, parseBody, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.put('/collections/:id', attachDb, parseBody, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.delete('/collections/:id', attachDb, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.post('/collections/:id/recipes/:recipeId', attachDb, collectionsRouter.handle.bind(collectionsRouter));
apiRouter.delete('/collections/:id/recipes/:recipeId', attachDb, collectionsRouter.handle.bind(collectionsRouter));

// Dietary Profiles
apiRouter.get('/dietary-profiles', attachDb, dietaryProfilesRouter.handle.bind(dietaryProfilesRouter));
apiRouter.get('/dietary-profiles/:id', attachDb, dietaryProfilesRouter.handle.bind(dietaryProfilesRouter));
apiRouter.post('/dietary-profiles', attachDb, parseBody, dietaryProfilesRouter.handle.bind(dietaryProfilesRouter));
apiRouter.put('/dietary-profiles/:id', attachDb, parseBody, dietaryProfilesRouter.handle.bind(dietaryProfilesRouter));
apiRouter.delete('/dietary-profiles/:id', attachDb, dietaryProfilesRouter.handle.bind(dietaryProfilesRouter));

// Cooking Logs
apiRouter.get('/cooking-logs', attachDb, cookingLogsRouter.handle.bind(cookingLogsRouter));
apiRouter.get('/cooking-logs/:id', attachDb, cookingLogsRouter.handle.bind(cookingLogsRouter));
apiRouter.post('/cooking-logs', attachDb, parseBody, cookingLogsRouter.handle.bind(cookingLogsRouter));
apiRouter.put('/cooking-logs/:id', attachDb, parseBody, cookingLogsRouter.handle.bind(cookingLogsRouter));
apiRouter.delete('/cooking-logs/:id', attachDb, cookingLogsRouter.handle.bind(cookingLogsRouter));

// Search
apiRouter.get('/search', attachDb, searchRouter.handle.bind(searchRouter));

// Meal Planner Service
apiRouter.get('/meal-planner/generate', attachDb, mealPlannerRouter.handle.bind(mealPlannerRouter));
apiRouter.get('/meal-planner/suggest', attachDb, mealPlannerRouter.handle.bind(mealPlannerRouter));

// Shopping List Service
apiRouter.get('/shopping-list/generate/:mealPlanId', attachDb, shoppingListServiceRouter.handle.bind(shoppingListServiceRouter));

// Nutrition
apiRouter.get('/nutrition/estimate/:recipeId', attachDb, nutritionRouter.handle.bind(nutritionRouter));

// Recommendations
apiRouter.get('/recommendations', attachDb, recommendationRouter.handle.bind(recommendationRouter));

// Cost
apiRouter.get('/cost/estimate/:recipeId', attachDb, costRouter.handle.bind(costRouter));

// Dietary Compliance
apiRouter.get('/dietary/check/:recipeId', attachDb, dietaryRouter.handle.bind(dietaryRouter));

// Conversion
apiRouter.get('/convert', attachDb, conversionRouter.handle.bind(conversionRouter));

// Scaling
apiRouter.post('/scale/:recipeId', attachDb, parseBody, scalingRouter.handle.bind(scalingRouter));

// Static file serving
function serveStatic(req, res) {
  let filePath = req.url.pathname;

  // Remove query string
  filePath = filePath.split('?')[0];

  // Default to index.html
  if (filePath === '/') {
    filePath = '/index.html';
  }

  const fullPath = path.join(PUBLIC_DIR, filePath);

  // Security: prevent directory traversal
  if (!fullPath.startsWith(PUBLIC_DIR)) {
    return notFound(res, 'Not found');
  }

  // Check if file exists
  if (!fs.existsSync(fullPath)) {
    return notFound(res, 'Not found');
  }

  // Determine content type
  const ext = path.extname(fullPath);
  const contentTypes = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
  };

  const contentType = contentTypes[ext] || 'text/plain';

  res.setHeader('Content-Type', contentType);
  const content = fs.readFileSync(fullPath);
  res.end(content);
}

// Create HTTP server
const server = http.createServer((req, res) => {
  const parsedUrl = require('url').parse(req.url, true);
  req.url = req.url; // Keep original for route matching

  try {
    // API routes
    if (parsedUrl.pathname.startsWith('/api')) {
      apiRouter.handle(req, res);
    } else {
      // Static files
      serveStatic(req, res);
    }
  } catch (err) {
    errorHandler(err, req, res);
  }
});

// Start server
server.listen(PORT, () => {
  console.log(`RecipeLab API server running on http://localhost:${PORT}`);
  console.log(`API available at http://localhost:${PORT}/api`);
});

module.exports = { app: server };
