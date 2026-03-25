/**
 * Plugin System - Public API
 */

const { PluginManager, HOOKS } = require('./PluginManager');

// Load all built-in plugins
const nutritionLogger = require('./plugins/nutritionLogger');
const allergenChecker = require('./plugins/allergenChecker');
const auditLog = require('./plugins/auditLog');
const priceTagger = require('./plugins/priceTagger');
const seasonalRecommender = require('./plugins/seasonalRecommender');
const ratingPredictor = require('./plugins/ratingPredictor');

// Load all hooks
const hooks = {
  beforeCreate: require('./hooks/beforeCreate'),
  afterCreate: require('./hooks/afterCreate'),
  beforeUpdate: require('./hooks/beforeUpdate'),
  afterUpdate: require('./hooks/afterUpdate'),
  beforeDelete: require('./hooks/beforeDelete'),
  afterDelete: require('./hooks/afterDelete'),
  beforeSearch: require('./hooks/beforeSearch'),
  afterSearch: require('./hooks/afterSearch'),
  beforeScale: require('./hooks/beforeScale'),
  afterScale: require('./hooks/afterScale'),
  beforeExport: require('./hooks/beforeExport'),
  afterExport: require('./hooks/afterExport'),
  onAllergenDetected: require('./hooks/onAllergenDetected'),
  onNutrientCalculated: require('./hooks/onNutrientCalculated'),
  onMealPlanGenerated: require('./hooks/onMealPlanGenerated'),
  onShoppingListGenerated: require('./hooks/onShoppingListGenerated'),
  onRecipeRated: require('./hooks/onRecipeRated'),
  onError: require('./hooks/onError')
};

/**
 * Create a PluginManager with all built-in plugins registered
 * @returns {PluginManager}
 */
function createManager() {
  const manager = new PluginManager();

  // Register all built-in plugins
  manager.registerPlugin(nutritionLogger);
  manager.registerPlugin(allergenChecker);
  manager.registerPlugin(auditLog);
  manager.registerPlugin(priceTagger);
  manager.registerPlugin(seasonalRecommender);
  manager.registerPlugin(ratingPredictor);

  return manager;
}

module.exports = {
  PluginManager,
  HOOKS,
  hooks,
  createManager,
  // Export individual plugins for custom registration
  plugins: {
    nutritionLogger,
    allergenChecker,
    auditLog,
    priceTagger,
    seasonalRecommender,
    ratingPredictor
  }
};
