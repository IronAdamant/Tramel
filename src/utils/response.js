'use strict';

/**
 * Response helpers for JSON API responses.
 * Replaces Express response methods for zero-dependency implementation.
 */

/**
 * Send a JSON response
 */
function json(res, data, statusCode = 200) {
  res.statusCode = statusCode;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(data));
}

/**
 * Send a success response with data
 */
function success(res, data, statusCode = 200) {
  json(res, { success: true, data }, statusCode);
}

/**
 * Send an error response
 */
function error(res, message, statusCode = 500, details = null) {
  const response = {
    success: false,
    error: message
  };
  if (details) {
    response.details = details;
  }
  json(res, response, statusCode);
}

/**
 * Send a 201 Created response
 */
function created(res, data) {
  success(res, data, 201);
}

/**
 * Send a 204 No Content response
 */
function noContent(res) {
  res.statusCode = 204;
  res.end();
}

/**
 * Send a 400 Bad Request response
 */
function badRequest(res, message, details = null) {
  error(res, message, 400, details);
}

/**
 * Send a 404 Not Found response
 */
function notFound(res, message = 'Resource not found') {
  error(res, message, 404);
}

/**
 * Send a 500 Internal Server Error response
 */
function serverError(res, message = 'Internal server error') {
  error(res, message, 500);
}

/**
 * Send a paginated response
 */
function paginated(res, data, total, limit, offset) {
  json(res, {
    success: true,
    data,
    pagination: {
      total,
      limit,
      offset,
      hasMore: offset + limit < total
    }
  });
}

module.exports = {
  json,
  success,
  error,
  created,
  noContent,
  badRequest,
  notFound,
  serverError,
  paginated
};
