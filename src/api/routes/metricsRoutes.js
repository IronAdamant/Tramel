/**
 * Metrics API Routes
 */

const { createRouter } = require('../../utils/router');
const metricsCollector = require('../../services/metrics/MetricsCollector');
const MetricsAggregator = require('../../services/metrics/MetricsAggregator');

const router = createRouter();
const aggregator = new MetricsAggregator(metricsCollector);

// Start snapshot collection interval
let snapshotInterval = null;

function startSnapshotCollection(intervalMs = 5000) {
  if (snapshotInterval) clearInterval(snapshotInterval);
  snapshotInterval = setInterval(() => {
    aggregator.recordSnapshot();
  }, intervalMs);
}

startSnapshotCollection();

/**
 * GET /api/metrics/summary
 * Get summary of all metrics
 */
router.get('/metrics/summary', (req, res) => {
  const summary = metricsCollector.getSummary();
  res.json(summary);
});

/**
 * GET /api/metrics/all
 * Get all raw metrics
 */
router.get('/metrics/all', (req, res) => {
  const metrics = metricsCollector.getAllMetrics();
  res.json(metrics);
});

/**
 * GET /api/metrics/aggregated
 * Get aggregated metrics for a time window
 */
router.get('/metrics/aggregated', (req, res) => {
  const { window = '1m' } = req.query;
  const aggregated = aggregator.getAggregatedMetrics(window);

  if (aggregated.error) {
    return res.status(400).json({ error: aggregated.error });
  }

  res.json(aggregated);
});

/**
 * GET /api/metrics/trends
 * Get trends for a specific metric
 */
router.get('/metrics/trends', (req, res) => {
  const { metric, window = '1m' } = req.query;

  if (!metric) {
    return res.status(400).json({ error: 'metric parameter is required' });
  }

  const trend = aggregator.getTrends(metric, window);
  res.json({ metric, window, ...trend });
});

/**
 * GET /api/metrics/anomalies
 * Detect anomalies in current metrics
 */
router.get('/metrics/anomalies', (req, res) => {
  const { window = '1m', threshold = 2 } = req.query;

  const anomalies = aggregator.detectAnomalies(window, parseFloat(threshold));
  res.json({
    window,
    threshold: parseFloat(threshold),
    anomalyCount: anomalies.length,
    anomalies
  });
});

/**
 * GET /api/metrics/rate
 * Calculate rate of change for a metric
 */
router.get('/metrics/rate', (req, res) => {
  const { metric, window = '1m' } = req.query;

  if (!metric) {
    return res.status(400).json({ error: 'metric parameter is required' });
  }

  const rate = aggregator.calculateRate(metric, window);
  res.json({ metric, window, ratePerSecond: rate });
});

/**
 * GET /api/metrics/windows
 * Get available time windows and their status
 */
router.get('/metrics/windows', (req, res) => {
  const summaries = aggregator.getAllWindowSummaries();
  res.json({
    availableWindows: Object.keys(aggregator.timeWindows),
    summaries
  });
});

/**
 * POST /api/metrics/record
 * Record a custom metric value
 */
router.post('/metrics/record', (req, res) => {
  const { type, name, value } = req.body;

  if (!type || !name || value === undefined) {
    return res.status(400).json({ error: 'type, name, and value are required' });
  }

  switch (type) {
    case 'counter':
      metricsCollector.incrementCounter(name, value);
      break;
    case 'gauge':
      metricsCollector.setGauge(name, value);
      break;
    case 'histogram':
      metricsCollector.recordHistogram(name, value);
      break;
    default:
      return res.status(400).json({ error: 'Invalid type. Use: counter, gauge, or histogram' });
  }

  res.json({ success: true, type, name, value });
});

/**
 * DELETE /api/metrics/cache
 * Clear metrics data (reset)
 */
router.delete('/metrics/all', (req, res) => {
  metricsCollector.reset();
  aggregator.clearAll();
  res.json({ success: true, message: 'All metrics reset' });
});

/**
 * PATCH /api/metrics/enabled
 * Enable/disable metrics collection
 */
router.patch('/metrics/enabled', (req, res) => {
  const { enabled } = req.body;

  if (typeof enabled !== 'boolean') {
    return res.status(400).json({ error: 'enabled must be a boolean' });
  }

  metricsCollector.setEnabled(enabled);
  res.json({ success: true, enabled });
});

/**
 * GET /api/metrics/health
 * Get metrics system health status
 */
router.get('/metrics/health', (req, res) => {
  const isEnabled = metricsCollector.enabled;
  const hasData = Object.keys(metricsCollector.counters).length > 0;

  res.json({
    status: isEnabled ? 'healthy' : 'disabled',
    enabled: isEnabled,
    hasData,
    uptime: process.uptime(),
    memory: process.memoryUsage()
  });
});

module.exports = router;
