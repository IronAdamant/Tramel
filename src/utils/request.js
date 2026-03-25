'use strict';

const querystring = require('querystring');
const url = require('url');

/**
 * Request body parsing utilities.
 * Replaces body-parser middleware for zero-dependency implementation.
 */

/**
 * Parse URL and extract query parameters
 */
function parseUrl(reqUrl) {
  const parsed = url.parse(reqUrl, true);
  return {
    pathname: parsed.pathname,
    query: parsed.query,
    search: parsed.search
  };
}

/**
 * Parse query string parameters
 */
function parseQuery(queryString) {
  if (!queryString) return {};
  return querystring.parse(queryString);
}

/**
 * Collect request body as a string
 */
function collectBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', chunk => {
      chunks.push(chunk);
    });
    req.on('end', () => {
      resolve(Buffer.concat(chunks).toString('utf8'));
    });
    req.on('error', reject);
  });
}

/**
 * Parse JSON body from request
 * Sets req.body on success, or calls next(err) on failure
 */
async function parseJsonBody(req) {
  const contentType = req.headers['content-type'] || '';

  if (!req.body) {
    const rawBody = await collectBody(req);

    if (!rawBody) {
      req.body = {};
      return;
    }

    // Check content type
    if (!contentType.includes('application/json')) {
      const err = new Error('Content-Type must be application/json');
      err.status = 400;
      throw err;
    }

    try {
      req.body = JSON.parse(rawBody);
    } catch (err) {
      const error = new Error('Invalid JSON body');
      error.status = 400;
      throw error;
    }
  }
}

/**
 * Parse URL-encoded body (form submissions)
 */
async function parseUrlEncodedBody(req) {
  const contentType = req.headers['content-type'] || '';

  if (!req.body) {
    const rawBody = await collectBody(req);

    if (!rawBody) {
      req.body = {};
      return;
    }

    if (contentType.includes('application/x-www-form-urlencoded')) {
      req.body = querystring.parse(rawBody);
    } else {
      req.body = JSON.parse(rawBody);
    }
  }
}

/**
 * Middleware to parse request body
 * Usage: router.post('/path', parseBody, handler);
 */
function parseBody(req, res, next) {
  parseJsonBody(req)
    .then(() => next())
    .catch(next);
}

/**
 * Get client IP address from request
 */
function getClientIp(req) {
  return req.headers['x-forwarded-for'] ||
    req.headers['x-real-ip'] ||
    req.connection.remoteAddress ||
    req.socket.remoteAddress;
}

module.exports = {
  parseUrl,
  parseQuery,
  collectBody,
  parseJsonBody,
  parseUrlEncodedBody,
  parseBody,
  getClientIp
};
