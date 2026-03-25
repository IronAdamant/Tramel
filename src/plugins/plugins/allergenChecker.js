/**
 * allergenChecker plugin
 * Checks recipes for allergens and triggers onAllergenDetected when found
 */

const ALLERGENS = ['peanuts', 'tree nuts', 'milk', 'eggs', 'fish', 'shellfish', 'soy', 'wheat', 'sesame'];

module.exports = {
  name: 'allergenChecker',
  hooks: ['beforeCreate', 'beforeUpdate', 'onAllergenDetected'],
  handler: async (ctx, ...args) => {
    const { hook } = ctx;

    if (hook === 'beforeCreate' || hook === 'beforeUpdate') {
      const [entity] = args;
      const detectedAllergens = [];

      if (entity && entity.ingredients) {
        const ingredientList = Array.isArray(entity.ingredients)
          ? entity.ingredients
          : [entity.ingredients];

        ingredientList.forEach(ingredient => {
          const name = (ingredient.name || '').toLowerCase();
          ALLERGENS.forEach(allergen => {
            if (name.includes(allergen)) {
              detectedAllergens.push({ ingredient: ingredient.name, allergen });
            }
          });
        });
      }

      if (detectedAllergens.length > 0) {
        console.log(`[allergenChecker] Detected ${detectedAllergens.length} potential allergen(s)`);
        return { ...ctx, allergens: detectedAllergens };
      }
    }

    if (hook === 'onAllergenDetected') {
      const [allergenInfo] = args;
      console.log(`[allergenChecker] Allergen alert: ${JSON.stringify(allergenInfo)}`);
    }

    return ctx;
  }
};
