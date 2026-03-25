'use strict';

const http = require('http');
const url = require('url');

/**
 * Simple pattern-matching HTTP router.
 * Replaces Express Router for zero-dependency implementation.
 */
class Router {
  constructor() {
    this.routes = [];
  }

  /**
   * Parse URL and extract path parameters
   */
  parseUrl(reqUrl) {
    const parsed = url.parse(reqUrl, true);
    return {
      pathname: parsed.pathname,
      query: parsed.query,
      search: parsed.search
    };
  }

  /**
   * Match a route pattern against a path
   * Supports: /users/:id, /recipes/:id/ingredients
   */
  matchRoute(pattern, path) {
    const patternParts = pattern.split('/');
    const pathParts = path.split('/');

    if (patternParts.length !== pathParts.length) {
      return null;
    }

    const params = {};

    for (let i = 0; i < patternParts.length; i++) {
      const patternPart = patternParts[i];
      const pathPart = pathParts[i];

      if (patternPart.startsWith(':')) {
        // Parameter (e.g., :id)
        params[patternPart.slice(1)] = pathPart;
      } else if (patternPart !== pathPart) {
        return null;
      }
    }

    return params;
  }

  /**
   * Register a route
   */
  addRoute(method, pattern, handler) {
    this.routes.push({ method: method.toUpperCase(), pattern, handler });
  }

  /**
   * Register GET route
   */
  get(pattern, handler) {
    this.addRoute('GET', pattern, handler);
  }

  /**
   * Register POST route
   */
  post(pattern, handler) {
    this.addRoute('POST', pattern, handler);
  }

  /**
   * Register PUT route
   */
  put(pattern, handler) {
    this.addRoute('PUT', pattern, handler);
  }

  /**
   * Register DELETE route
   */
  delete(pattern, handler) {
    this.addRoute('DELETE', pattern, handler);
  }

  /**
   * Register PATCH route
   */
  patch(pattern, handler) {
    this.addRoute('PATCH', pattern, handler);
  }

  /**
   * Handle an incoming HTTP request
   */
  handle(req, res, ...args) {
    const { pathname } = this.parseUrl(req.url);
    const method = req.method.toUpperCase();

    for (const route of this.routes) {
      if (route.method !== method) continue;

      const params = this.matchRoute(route.pattern, pathname);
      if (params !== null) {
        req.params = params;
        return route.handler(req, res, ...args);
      }
    }

    // No route matched
    res.statusCode = 404;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ error: 'Not found' }));
  }
}

/**
 * Create a new router instance
 */
function createRouter() {
  return new Router();
}

module.exports = { Router, createRouter };
