'use strict';

const { describe, test, assert, equal } = require('../testRunner');
const { Router, createRouter } = require('../../src/utils/router');
const { json } = require('../../src/utils/response');

describe('Router', () => {
  let router;
  let mockReq;
  let mockRes;
  let responses;

  beforeEach(() => {
    router = createRouter();
    responses = [];

    mockReq = (method, url) => ({
      method,
      url,
      params: {}
    });

    mockRes = {
      statusCode: 0,
      headers: {},
      setHeader(name, value) { this.headers[name] = value; },
      end(data) {
        responses.push({
          status: this.statusCode,
          body: JSON.parse(data)
        });
      }
    };
  });

  test('should match exact routes', () => {
    router.get('/test', (req, res) => json(res, { ok: true }));

    router.handle(mockReq('GET', '/test'), mockRes);

    equal(responses.length, 1);
    equal(responses[0].status, 200);
    equal(responses[0].body.ok, true);
  });

  test('should extract route parameters', () => {
    router.get('/users/:id', (req, res) => json(res, { userId: req.params.id }));

    router.handle(mockReq('GET', '/users/123'), mockRes);

    equal(responses[0].body.userId, '123');
  });

  test('should return 404 for unmatched routes', () => {
    router.handle(mockReq('GET', '/nonexistent'), mockRes);

    equal(responses[0].status, 404);
    equal(responses[0].body.error, 'Not found');
  });

  test('should match POST routes', () => {
    router.post('/data', (req, res) => json(res, { created: true }));

    router.handle(mockReq('POST', '/data'), mockRes);

    equal(responses[0].status, 200);
    equal(responses[0].body.created, true);
  });

  test('should match DELETE routes', () => {
    router.delete('/items/:id', (req, res) => json(res, { deleted: true }));

    router.handle(mockReq('DELETE', '/items/5'), mockRes);

    equal(responses[0].body.deleted, true);
  });

  test('should handle multiple parameters', () => {
    router.get('/recipes/:id/ingredients/:ingId', (req, res) => {
      json(res, { recipe: req.params.id, ingredient: req.params.ingId });
    });

    router.handle(mockReq('GET', '/recipes/10/ingredients/5'), mockRes);

    equal(responses[0].body.recipe, '10');
    equal(responses[0].body.ingredient, '5');
  });
});
