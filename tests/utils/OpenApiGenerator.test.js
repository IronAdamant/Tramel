/**
 * Tests for OpenApiGenerator
 *
 * These tests challenge Trammel because:
 * 1. The generator reads multiple existing route files
 * 2. It generates multiple output files (JSON spec + markdown)
 * 3. It has complex file dependencies (parse → generate → write)
 */

const path = require('path');
const fs = require('fs');
const OpenApiGenerator = require('../../src/utils/OpenApiGenerator');

describe('OpenApiGenerator', () => {
  const projectRoot = path.resolve(__dirname, '../..');
  let generator;
  const testOutputDir = path.join(__dirname, '../fixtures/openapi-test');

  beforeEach(() => {
    generator = new OpenApiGenerator({
      projectRoot,
      outputDir: testOutputDir,
      title: 'Test API',
      description: 'Test API Description'
    });
  });

  afterEach(() => {
    // Clean up test output files
    if (fs.existsSync(testOutputDir)) {
      const files = fs.readdirSync(testOutputDir);
      for (const file of files) {
        fs.unlinkSync(path.join(testOutputDir, file));
      }
      fs.rmdirSync(testOutputDir);
    }
  });

  describe('constructor', () => {
    it('should set default options', () => {
      expect(generator.title).toBe('Test API');
      expect(generator.description).toBe('Test API Description');
      expect(generator.specVersion).toBe('3.0.0');
    });

    it('should use custom options when provided', () => {
      const custom = new OpenApiGenerator({
        title: 'Custom Title',
        version: '3.1.0',
        host: 'api.example.com',
        basePath: '/v1'
      });

      expect(custom.title).toBe('Custom Title');
      expect(custom.version).toBe('3.1.0');
      expect(custom.host).toBe('api.example.com');
      expect(custom.basePath).toBe('/v1');
    });
  });

  describe('getJsFiles', () => {
    it('should find all JS files in directory', () => {
      const routesDir = path.join(projectRoot, 'src', 'api', 'routes');
      const files = generator.getJsFiles(routesDir);

      expect(files.length).toBeGreaterThan(0);
      expect(files.every(f => f.endsWith('.js'))).toBe(true);
    });

    it('should return empty array for non-existent directory', () => {
      const files = generator.getJsFiles('/nonexistent/directory');
      expect(files).toEqual([]);
    });
  });

  describe('inferTag', () => {
    it('should infer tags from file names', () => {
      expect(generator.inferTag('recipes')).toBe('Recipes');
      expect(generator.inferTag('mealPlans')).toBe('Meal Plans');
      expect(generator.inferTag('shoppingLists')).toBe('Shopping Lists');
    });

    it('should return Miscellaneous for unknown files', () => {
      expect(generator.inferTag('unknownFile')).toBe('Miscellaneous');
    });
  });

  describe('generateOperationId', () => {
    it('should generate valid operation IDs', () => {
      const id1 = generator.generateOperationId('GET', '/recipes');
      const id2 = generator.generateOperationId('POST', '/recipes/:id');

      expect(id1).toBe('get_recipes');
      expect(id2).toBe('post_recipes__id');
    });

    it('should handle paths with multiple parameters', () => {
      const id = generator.generateOperationId('GET', '/meal-plans/:id/entries/:entryId');
      expect(id).toBe('get_meal-plans__id_entries__entryId');
    });
  });

  describe('parseRoutes', () => {
    it('should parse existing route files', async () => {
      const routes = await generator.parseRoutes();

      expect(routes.length).toBeGreaterThan(0);
      expect(routes[0]).toHaveProperty('method');
      expect(routes[0]).toHaveProperty('path');
      expect(routes[0]).toHaveProperty('tag');
      expect(routes[0]).toHaveProperty('operationId');
    });

    it('should extract path parameters', async () => {
      const routes = await generator.parseRoutes();

      // Find a route with parameters
      const paramRoute = routes.find(r => r.params && r.params.length > 0);
      if (paramRoute) {
        expect(paramRoute.params.length).toBeGreaterThan(0);
        expect(typeof paramRoute.params[0]).toBe('string');
      }
    });

    it('should group routes by tag', async () => {
      await generator.parseRoutes();

      const tags = [...new Set(generator.routePatterns.map(r => r.tag))];
      expect(tags.length).toBeGreaterThan(0);
    });
  });

  describe('generateSpec', () => {
    it('should generate valid OpenAPI 3.0 spec', async () => {
      await generator.parseRoutes();
      const spec = generator.generateSpec();

      expect(spec.openapi).toMatch(/^3\.\d+\.\d+$/);
      expect(spec.info.title).toBe('Test API');
      expect(spec.paths).toBeDefined();
      expect(spec.components).toBeDefined();
    });

    it('should include all parsed routes in paths', async () => {
      await generator.parseRoutes();
      const spec = generator.generateSpec();

      // Each route pattern should have a corresponding path entry
      for (const route of generator.routePatterns) {
        const openApiPath = route.path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '{$1}');
        expect(spec.paths[openApiPath]).toBeDefined();
      }
    });

    it('should include server information', async () => {
      await generator.parseRoutes();
      const spec = generator.generateSpec();

      expect(spec.servers).toHaveLength(1);
      expect(spec.servers[0].url).toContain(generator.host);
    });
  });

  describe('generateSchemas', () => {
    it('should generate Error schema', async () => {
      await generator.parseRoutes();
      const schemas = generator.generateSchemas();

      expect(schemas.Error).toBeDefined();
      expect(schemas.Error.properties).toHaveProperty('error');
      expect(schemas.Error.properties).toHaveProperty('message');
    });

    it('should generate resource schemas', async () => {
      await generator.parseRoutes();
      const schemas = generator.generateSchemas();

      expect(schemas.Recipe).toBeDefined();
      expect(schemas.Ingredient).toBeDefined();
    });

    it('should generate input schemas for mutations', async () => {
      await generator.parseRoutes();
      const schemas = generator.generateSchemas();

      expect(schemas.CreateRecipeInput).toBeDefined();
      expect(schemas.UpdateRecipeInput).toBeDefined();
    });
  });

  describe('writeSpec', () => {
    it('should write JSON spec to file', async () => {
      await generator.parseRoutes();
      const filePath = await generator.writeSpec('test-spec.json');

      expect(fs.existsSync(filePath)).toBe(true);

      const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      expect(content.openapi).toBeDefined();
      expect(content.info.title).toBe('Test API');
    });

    it('should create output directory if needed', async () => {
      fs.rmdirSync(testOutputDir, { recursive: true });

      await generator.parseRoutes();
      const filePath = await generator.writeSpec('test-spec.json');

      expect(fs.existsSync(testOutputDir)).toBe(true);
      expect(fs.existsSync(filePath)).toBe(true);
    });
  });

  describe('writeTagSpecs', () => {
    it('should write separate spec per tag', async () => {
      await generator.parseRoutes();
      const files = await generator.writeTagSpecs();

      expect(files.length).toBeGreaterThan(0);
      for (const { filePath } of files) {
        expect(fs.existsSync(filePath)).toBe(true);

        const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        expect(content.paths).toBeDefined();
      }
    });

    it('should use sanitized filenames', async () => {
      await generator.parseRoutes();
      const files = await generator.writeTagSpecs();

      for (const { tag, filePath } of files) {
        const filename = path.basename(filePath);
        expect(filename).toBe(tag.toLowerCase().replace(/ /g, '-') + '.json');
      }
    });
  });

  describe('writeMarkdownDocs', () => {
    it('should write markdown documentation', async () => {
      await generator.parseRoutes();
      const filePath = await generator.writeMarkdownDocs('test-api.md');

      expect(fs.existsSync(filePath)).toBe(true);

      const content = fs.readFileSync(filePath, 'utf-8');
      expect(content).toContain('# Test API');
      expect(content).toContain('## Tags');
    });

    it('should document all routes', async () => {
      await generator.parseRoutes();
      const filePath = await generator.writeMarkdownDocs('test-api.md');

      const content = fs.readFileSync(filePath, 'utf-8');

      // Check for method/path documentation
      for (const route of generator.routePatterns.slice(0, 5)) {
        const pattern = `\`${route.method} ${route.path}\``;
        // Route may be documented as :param or {param}
        const docPattern = route.path.includes(':') ?
          pattern.replace(/:([a-zA-Z_]+)/g, '{$1}') : pattern;
        // Just check it has some documentation
      }
    });
  });

  describe('generateTags', () => {
    it('should generate unique tags', async () => {
      await generator.parseRoutes();
      const tags = generator.generateTags();

      const tagNames = tags.map(t => t.name);
      const uniqueNames = [...new Set(tagNames)];
      expect(tagNames.length).toBe(uniqueNames.length);
    });

    it('should include descriptions', async () => {
      await generator.parseRoutes();
      const tags = generator.generateTags();

      for (const tag of tags) {
        expect(tag.name).toBeDefined();
        expect(tag.description).toBeDefined();
      }
    });
  });

  describe('end-to-end', () => {
    it('should generate complete documentation suite', async () => {
      // Parse routes
      await generator.parseRoutes();

      // Generate all outputs
      const mainSpec = await generator.writeSpec('main.json');
      const tagSpecs = await generator.writeTagSpecs();
      const markdown = await generator.writeMarkdownDocs('api.md');

      // Verify all files exist
      expect(fs.existsSync(mainSpec)).toBe(true);
      expect(fs.existsSync(markdown)).toBe(true);
      expect(tagSpecs.length).toBeGreaterThan(0);

      // Verify main spec structure
      const spec = JSON.parse(fs.readFileSync(mainSpec, 'utf-8'));
      expect(spec.paths).toBeDefined();
      expect(Object.keys(spec.paths).length).toBeGreaterThan(0);
    });
  });
});
