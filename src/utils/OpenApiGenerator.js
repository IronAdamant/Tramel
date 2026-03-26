/**
 * OpenApiGenerator - Generates OpenAPI 3.0 specifications from route definitions
 *
 * This module challenges Trammel because:
 * 1. It reads multiple existing files to understand route structure
 * 2. It generates multiple output files with specific naming
 * 3. It has complex dependencies between parse → generate → write
 * 4. Planning requires understanding both input patterns and output schema
 */

const fs = require('fs');
const path = require('path');

class OpenApiGenerator {
  constructor(options = {}) {
    this.projectRoot = options.projectRoot || process.cwd();
    this.srcDir = path.join(this.projectRoot, 'src');
    this.outputDir = options.outputDir || path.join(this.projectRoot, 'docs', 'openapi');
    this.specVersion = options.version || '3.0.0';
    this.title = options.title || 'RecipeLab API';
    this.description = options.description || 'Recipe and Meal Planning API';
    this.host = options.host || 'localhost:3000';
    this.basePath = options.basePath || '/api';

    this.routePatterns = [];
    this.schemas = new Map();
    this.securitySchemes = new Map();
  }

  /**
   * Scan and parse all route files
   */
  async parseRoutes() {
    const routesDir = path.join(this.srcDir, 'api', 'routes');
    const routeFiles = this.getJsFiles(routesDir);

    for (const file of routeFiles) {
      await this.parseRouteFile(file);
    }

    return this.routePatterns;
  }

  /**
   * Get all JavaScript files in a directory recursively
   */
  getJsFiles(dir, files = []) {
    if (!fs.existsSync(dir)) return files;

    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        this.getJsFiles(fullPath, files);
      } else if (entry.isFile() && entry.name.endsWith('.js')) {
        files.push(fullPath);
      }
    }
    return files;
  }

  /**
   * Parse a single route file to extract route patterns
   */
  async parseRouteFile(filePath) {
    const content = fs.readFileSync(filePath, 'utf-8');
    const relativePath = path.relative(this.srcDir, filePath);

    // Extract route patterns from apiRouter calls
    // Pattern: apiRouter.METHOD(PATH, handler)
    const routerCallRegex = /apiRouter\s*\.\s*(get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]\s*,/gi;

    let match;
    while ((match = routerCallRegex.exec(content)) !== null) {
      const method = match[1].toUpperCase();
      const routePath = match[2];

      // Extract parameter names from paths like /recipes/:id
      const params = [];
      const paramRegex = /:([a-zA-Z_][a-zA-Z0-9_]*)/g;
      let paramMatch;
      while ((paramMatch = paramRegex.exec(routePath)) !== null) {
        params.push(paramMatch[1]);
      }

      // Infer tags from file name
      const fileName = path.basename(filePath, '.js');
      const tag = this.inferTag(fileName);

      this.routePatterns.push({
        method,
        path: routePath,
        params,
        tag,
        file: relativePath,
        summary: this.generateSummary(method, routePath, tag),
        operationId: this.generateOperationId(method, routePath)
      });
    }

    // Also look for DynamicRegistry patterns
    const dynamicRegex = /registerRoute\s*\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\s*,/gi;
    while ((match = dynamicRegex.exec(content)) !== null) {
      const pluginName = match[1];
      const routePath = match[2];

      this.routePatterns.push({
        method: 'GET', // Default for dynamic routes
        path: routePath,
        params: [],
        tag: 'Dynamic',
        file: relativePath,
        summary: `Dynamic route from plugin: ${pluginName}`,
        operationId: `dynamic_${pluginName}_${routePath.replace(/\//g, '_')}`
      });
    }
  }

  /**
   * Infer tag name from file name
   */
  inferTag(fileName) {
    const tagMap = {
      'recipes': 'Recipes',
      'ingredients': 'Ingredients',
      'tags': 'Tags',
      'mealPlans': 'Meal Plans',
      'shoppingLists': 'Shopping Lists',
      'collections': 'Collections',
      'dietaryProfiles': 'Dietary Profiles',
      'cookingLogs': 'Cooking Logs',
      'search': 'Search',
      'mealPlannerRoutes': 'Meal Planner',
      'shoppingListServiceRoutes': 'Shopping List',
      'nutritionRoutes': 'Nutrition',
      'recommendationRoutes': 'Recommendations',
      'costRoutes': 'Cost',
      'dietaryRoutes': 'Dietary',
      'conversionRoutes': 'Conversion',
      'scalingRoutes': 'Scaling',
      'substitutionRoutes': 'Substitution'
    };

    return tagMap[fileName] || 'Miscellaneous';
  }

  /**
   * Generate a summary for the operation
   */
  generateSummary(method, routePath, tag) {
    const actions = {
      'GET': 'Get',
      'POST': 'Create',
      'PUT': 'Update',
      'PATCH': 'Patch',
      'DELETE': 'Delete'
    };

    const action = actions[method] || method;
    const resource = routePath.split('/').filter(Boolean).pop() || tag;
    const cleanResource = resource.replace(/:/g, '').replace(/_/g, ' ');

    return `${action} ${cleanResource}`;
  }

  /**
   * Generate unique operation ID
   */
  generateOperationId(method, routePath) {
    const cleanPath = routePath.replace(/[:\/]/g, '_').replace(/^_/, '');
    return `${method.toLowerCase()}_${cleanPath}`.replace(/__/g, '_');
  }

  /**
   * Generate the complete OpenAPI specification
   */
  generateSpec() {
    const spec = {
      openapi: this.specVersion,
      info: {
        title: this.title,
        version: '1.0.0',
        description: this.description,
        contact: {
          name: 'RecipeLab Support'
        }
      },
      servers: [
        {
          url: `http://${this.host}${this.basePath}`,
          description: 'Development server'
        }
      ],
      paths: this.generatePaths(),
      components: this.generateComponents(),
      tags: this.generateTags()
    };

    return spec;
  }

  /**
   * Generate paths object from route patterns
   */
  generatePaths() {
    const paths = {};

    for (const route of this.routePatterns) {
      // Normalize path to OpenAPI format
      const openApiPath = route.path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '{$1}');

      if (!paths[openApiPath]) {
        paths[openApiPath] = {};
      }

      paths[openApiPath][route.method.toLowerCase()] = {
        summary: route.summary,
        operationId: route.operationId,
        tags: [route.tag],
        parameters: this.generateParameters(route),
        responses: this.generateResponses(route),
        security: route.tag === 'Dynamic' ? [] : undefined
      };

      // Add POST/PUT body schemas for mutation methods
      if (['POST', 'PUT', 'PATCH'].includes(route.method)) {
        const schemaName = this.getSchemaNameForRoute(openApiPath, route.method);
        paths[openApiPath][route.method.toLowerCase()].requestBody = {
          required: true,
          content: {
            'application/json': {
              schema: { $ref: `#/components/schemas/${schemaName}` }
            }
          }
        };
      }
    }

    return paths;
  }

  /**
   * Generate parameters for a route
   */
  generateParameters(route) {
    const params = [];

    // Check for path parameters
    const pathMatch = route.path.match(/:([a-zA-Z_][a-zA-Z0-9_]*)/g);
    if (pathMatch) {
      for (const param of pathMatch) {
        const name = param.replace(':', '');
        params.push({
          name,
          in: 'path',
          required: true,
          schema: {
            type: 'string'
          },
          description: `The ${name} identifier`
        });
      }
    }

    return params;
  }

  /**
   * Generate responses for a route
   */
  generateResponses(route) {
    const responses = {
      '200': {
        description: 'Successful response',
        content: {
          'application/json': {
            schema: {
              type: 'object'
            }
          }
        }
      },
      '400': {
        description: 'Bad request',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/Error' }
          }
        }
      },
      '404': {
        description: 'Not found',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/Error' }
          }
        }
      },
      '500': {
        description: 'Internal server error',
        content: {
          'application/json': {
            schema: { $ref: '#/components/schemas/Error' }
          }
        }
      }
    };

    // For DELETE, add 204
    if (route.method === 'DELETE') {
      responses['204'] = { description: 'Deleted successfully' };
      delete responses['200'];
    }

    return responses;
  }

  /**
   * Get schema name for a route
   */
  getSchemaNameForRoute(openApiPath, method) {
    const pathParts = openApiPath.split('/').filter(Boolean);
    const resource = pathParts[pathParts.length - 1] || pathParts[pathParts.length - 2];

    if (method === 'POST') {
      return `Create${resource.charAt(0).toUpperCase() + resource.slice(1)}Input`;
    }
    if (method === 'PUT' || method === 'PATCH') {
      return `Update${resource.charAt(0).toUpperCase() + resource.slice(1)}Input`;
    }
    return resource.charAt(0).toUpperCase() + resource.slice(1);
  }

  /**
   * Generate components (schemas, security schemes, etc.)
   */
  generateComponents() {
    return {
      schemas: this.generateSchemas(),
      securitySchemes: this.generateSecuritySchemes()
    };
  }

  /**
   * Generate schema definitions
   */
  generateSchemas() {
    const schemas = {
      Error: {
        type: 'object',
        properties: {
          error: { type: 'string' },
          message: { type: 'string' },
          status: { type: 'integer' }
        }
      },
      Recipe: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          description: { type: 'string' },
          cuisine: { type: 'string' },
          totalTime: { type: 'integer' },
          servings: { type: 'integer' },
          ingredients: {
            type: 'array',
            items: { $ref: '#/components/schemas/Ingredient' }
          },
          steps: {
            type: 'array',
            items: { type: 'string' }
          },
          tags: {
            type: 'array',
            items: { type: 'string' }
          }
        }
      },
      Ingredient: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          amount: { type: 'number' },
          unit: { type: 'string' }
        }
      },
      MealPlan: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          startDate: { type: 'string', format: 'date' },
          endDate: { type: 'string', format: 'date' },
          entries: {
            type: 'array',
            items: { $ref: '#/components/schemas/MealPlanEntry' }
          }
        }
      },
      MealPlanEntry: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          recipeId: { type: 'string' },
          date: { type: 'string', format: 'date' },
          mealType: { type: 'string', enum: ['breakfast', 'lunch', 'dinner', 'snack'] }
        }
      },
      ShoppingList: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          items: {
            type: 'array',
            items: { $ref: '#/components/schemas/ShoppingListItem' }
          }
        }
      },
      ShoppingListItem: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          amount: { type: 'number' },
          unit: { type: 'string' },
          checked: { type: 'boolean' }
        }
      },
      Collection: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          description: { type: 'string' },
          recipeIds: { type: 'array', items: { type: 'string' } }
        }
      },
      DietaryProfile: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          name: { type: 'string' },
          restrictions: { type: 'array', items: { type: 'string' } },
          preferences: { type: 'object' }
        }
      },
      NutritionInfo: {
        type: 'object',
        properties: {
          calories: { type: 'number' },
          protein: { type: 'number' },
          carbohydrates: { type: 'number' },
          fat: { type: 'number' },
          fiber: { type: 'number' }
        }
      }
    };

    // Add input schemas for POST/PUT
    for (const [name, schema] of Object.entries(schemas)) {
      schemas[`Create${name}Input`] = { ...schema, required: Object.keys(schema.properties).slice(0, 3) };
      schemas[`Update${name}Input`] = { ...schema, required: [] };
    }

    return schemas;
  }

  /**
   * Generate security schemes
   */
  generateSecuritySchemes() {
    return {
      ApiKeyAuth: {
        type: 'apiKey',
        in: 'header',
        name: 'X-API-Key',
        description: 'API key authentication'
      }
    };
  }

  /**
   * Generate tags for grouping
   */
  generateTags() {
    const tags = new Set(this.routePatterns.map(r => r.tag));

    return [...tags].map(tag => ({
      name: tag,
      description: `Operations for ${tag}`
    }));
  }

  /**
   * Write the generated spec to a file
   */
  async writeSpec(filename = 'openapi.json') {
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }

    const spec = this.generateSpec();
    const filePath = path.join(this.outputDir, filename);

    fs.writeFileSync(filePath, JSON.stringify(spec, null, 2));
    return filePath;
  }

  /**
   * Write separate spec files for each tag
   */
  async writeTagSpecs() {
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }

    const tags = [...new Set(this.routePatterns.map(r => r.tag))];
    const files = [];

    for (const tag of tags) {
      const tagRoutes = this.routePatterns.filter(r => r.tag === tag);
      const tagSpec = {
        openapi: this.specVersion,
        info: {
          title: `${this.title} - ${tag}`,
          version: '1.0.0',
          description: `OpenAPI specification for ${tag} operations`
        },
        servers: [
          { url: `http://${this.host}${this.basePath}`, description: 'Development server' }
        ],
        paths: this.generatePathsForTag(tag),
        components: {
          schemas: this.generateSchemas()
        },
        tags: [{ name: tag, description: `Operations for ${tag}` }]
      };

      const filename = `${tag.toLowerCase().replace(/ /g, '-')}.json`;
      const filePath = path.join(this.outputDir, filename);

      fs.writeFileSync(filePath, JSON.stringify(tagSpec, null, 2));
      files.push({ tag, filePath });
    }

    return files;
  }

  /**
   * Generate paths filtered by tag
   */
  generatePathsForTag(tag) {
    const routes = this.routePatterns.filter(r => r.tag === tag);
    const paths = {};

    for (const route of routes) {
      const openApiPath = route.path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '{$1}');

      if (!paths[openApiPath]) {
        paths[openApiPath] = {};
      }

      paths[openApiPath][route.method.toLowerCase()] = {
        summary: route.summary,
        operationId: route.operationId,
        tags: [route.tag],
        parameters: this.generateParameters(route),
        responses: this.generateResponses(route)
      };
    }

    return paths;
  }

  /**
   * Generate markdown documentation
   */
  async writeMarkdownDocs(filename = 'api-docs.md') {
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }

    let markdown = `# ${this.title}\n\n`;
    markdown += `${this.description}\n\n`;
    markdown += `## Base URL\n\n`;
    markdown += `\`http://${this.host}${this.basePath}\`\n\n`;
    markdown += `## Tags\n\n`;

    const tags = [...new Set(this.routePatterns.map(r => r.tag))];
    for (const tag of tags) {
      markdown += `- [${tag}](#${tag.toLowerCase().replace(/ /g, '-')})\n`;
    }

    markdown += `\n---\n\n`;

    for (const tag of tags) {
      markdown += `## ${tag}\n\n`;
      const routes = this.routePatterns.filter(r => r.tag === tag);

      for (const route of routes) {
        markdown += `### ${route.summary}\n\n`;
        markdown += `\`${route.method} ${route.path}\`\n\n`;
        markdown += `**Operation ID:** \`${route.operationId}\`\n\n`;

        if (route.params.length > 0) {
          markdown += `**Parameters:**\n`;
          for (const param of route.params) {
            markdown += `- \`${param}\` (path)\n`;
          }
          markdown += `\n`;
        }

        markdown += `---\n\n`;
      }
    }

    const filePath = path.join(this.outputDir, filename);
    fs.writeFileSync(filePath, markdown);
    return filePath;
  }
}

module.exports = OpenApiGenerator;
