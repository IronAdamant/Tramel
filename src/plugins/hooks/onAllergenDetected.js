/**
 * onAllergenDetected hook
 * Fired when an allergen is detected in a recipe or ingredient
 * @param {Object} context - Contains allergen info and affected entity
 */
module.exports = {
  name: 'onAllergenDetected',
  description: 'Fired when an allergen is detected',
  trigger: 'DietaryComplianceService.check()'
};
