'use strict';

const { createRouter } = require('../../utils/router');
const ShoppingList = require('../../models/ShoppingList');
const { success, created, notFound, paginated } = require('../../utils/response');
const { validatePagination } = require('../../utils/validation');

const router = createRouter();

// List all shopping lists
router.get('/', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const { limit, offset } = validatePagination(req.query);
  const result = shoppingList.getAll({ limit, offset });
  paginated(res, result.data, result.total, limit, offset);
});

// Get shopping list by ID
router.get('/:id', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const item = shoppingList.getById(req.params.id);
  if (!item) return notFound(res, 'Shopping list not found');
  success(res, item);
});

// Create shopping list
router.post('/', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const item = shoppingList.create(req.body);
  created(res, item);
});

// Update shopping list
router.put('/:id', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const existing = shoppingList.getById(req.params.id);
  if (!existing) return notFound(res, 'Shopping list not found');

  const updated = shoppingList.update(req.params.id, req.body);
  success(res, updated);
});

// Delete shopping list
router.delete('/:id', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const deleted = shoppingList.delete(req.params.id);
  if (!deleted) return notFound(res, 'Shopping list not found');
  success(res, { deleted: true });
});

// Add item to shopping list
router.post('/:id/items', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const item = shoppingList.addItem({
    ...req.body,
    shopping_list_id: req.params.id
  });
  created(res, item);
});

// Toggle item checked status
router.patch('/:id/items/:itemId', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const updated = shoppingList.toggleItem(req.params.itemId);
  if (!updated) return notFound(res, 'Item not found');
  success(res, updated);
});

// Remove item from shopping list
router.delete('/:id/items/:itemId', (req, res) => {
  const shoppingList = new ShoppingList(req.db);
  const deleted = shoppingList.removeItem(req.params.itemId);
  if (!deleted) return notFound(res, 'Item not found');
  success(res, { deleted: true });
});

module.exports = router;
