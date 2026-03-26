/**
 * Workflow Automation API Routes
 */

const express = require('express');
const router = express.Router();
const WorkflowAutomationEngine = require('../../services/workflowAutomationEngine');

module.exports = (fileStore) => {
  const engine = new WorkflowAutomationEngine(fileStore);

  /**
   * List all workflows
   */
  router.get('/', (req, res) => {
    try {
      const workflows = engine.getWorkflow();
      res.json({ workflows });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get a specific workflow
   */
  router.get('/:workflowId', (req, res) => {
    try {
      const workflow = engine.getWorkflow(req.params.workflowId);

      if (!workflow) {
        return res.status(404).json({ error: 'Workflow not found' });
      }

      res.json(workflow);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Execute a workflow
   */
  router.post('/:workflowId/execute', async (req, res) => {
    try {
      const { workflowId } = req.params;
      const context = req.body || {};

      const result = await engine.execute(workflowId, context);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Register a new workflow
   */
  router.post('/', (req, res) => {
    try {
      const workflowDef = req.body;

      if (!workflowDef.id || !workflowDef.name || !workflowDef.steps) {
        return res.status(400).json({
          error: 'Missing required fields: id, name, steps'
        });
      }

      engine.registerWorkflow(workflowDef);
      res.json({ success: true, workflowId: workflowDef.id });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get execution history
   */
  router.get('/history/list', (req, res) => {
    try {
      const { limit = 20 } = req.query;
      const history = engine.getHistory(parseInt(limit));
      res.json({ history });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  /**
   * Get active executions
   */
  router.get('/executions/active', (req, res) => {
    try {
      const active = engine.getActiveExecutions();
      res.json({ active });
    } catch (error) {
      res.status(500).json({ error: error.message });
    }
  });

  return router;
};
