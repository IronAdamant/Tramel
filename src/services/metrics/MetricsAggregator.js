/**
 * MetricsAggregator - Aggregates and analyzes metrics over time windows
 *
 * Challenges Stele-context:
 * - Tracks metrics across multiple time windows
 * - Dynamic metric registration and aggregation
 *
 * Challenges Chisel:
 * - Complex time-window calculations
 * - Aggregation algorithm testing
 *
 * Challenges Trammel:
 * - Multi-file planning for aggregation pipeline
 */

const MetricsCollector = require('./MetricsCollector');

class MetricsAggregator {
  constructor(collector = null) {
    this.collector = collector || MetricsCollector;
    this.timeWindows = {
      '1m': { duration: 60 * 1000, buckets: 60 },
      '5m': { duration: 5 * 60 * 1000, buckets: 60 },
      '1h': { duration: 60 * 60 * 1000, buckets: 60 },
      '24h': { duration: 24 * 60 * 60 * 1000, buckets: 96 }
    };

    this.windows = {};
    this.initializeWindows();
  }

  /**
   * Initialize time window buckets
   */
  initializeWindows() {
    for (const [name, config] of Object.entries(this.timeWindows)) {
      this.windows[name] = {
        data: new Array(config.buckets).fill(null).map(() => ({
          timestamp: null,
          metrics: null
        })),
        currentIndex: 0,
        lastUpdate: Date.now()
      };
    }
  }

  /**
   * Record current metrics snapshot to all windows
   */
  recordSnapshot() {
    const metrics = this.collector.getAllMetrics();
    const now = Date.now();

    for (const [name, window] of Object.entries(this.windows)) {
      window.data[window.currentIndex] = {
        timestamp: now,
        metrics: JSON.parse(JSON.stringify(metrics)) // Deep copy
      };
      window.lastUpdate = now;

      // Move to next bucket (circular)
      window.currentIndex = (window.currentIndex + 1) % window.data.length;
    }
  }

  /**
   * Get aggregated metrics for a time window
   */
  getAggregatedMetrics(windowName = '1m') {
    const window = this.windows[windowName];
    if (!window) {
      return { error: `Unknown window: ${windowName}` };
    }

    const snapshots = window.data.filter(s => s.timestamp !== null);
    if (snapshots.length === 0) {
      return { error: 'No data in window' };
    }

    // Aggregate counters (sum)
    const aggregatedCounters = {};
    const counterKeys = new Set();

    for (const snapshot of snapshots) {
      for (const key of Object.keys(snapshot.metrics.counters)) {
        counterKeys.add(key);
      }
    }

    for (const key of counterKeys) {
      aggregatedCounters[key] = snapshots.reduce((sum, s) => {
        return sum + (s.metrics.counters[key] || 0);
      }, 0);
    }

    // Aggregate gauges (latest value)
    const latestSnapshot = snapshots[snapshots.length - 1];
    const aggregatedGauges = { ...latestSnapshot.metrics.gauges };

    // Aggregate histograms (average)
    const histogramKeys = new Set();
    for (const snapshot of snapshots) {
      for (const key of Object.keys(snapshot.metrics.histograms)) {
        histogramKeys.add(key);
      }
    }

    const aggregatedHistograms = {};
    for (const key of histogramKeys) {
      const values = snapshots
        .map(s => s.metrics.histograms[key]?.mean)
        .filter(v => v !== undefined);

      if (values.length > 0) {
        aggregatedHistograms[key] = {
          count: snapshots.reduce((sum, s) => sum + (s.metrics.histograms[key]?.count || 0), 0),
          mean: values.reduce((sum, v) => sum + v, 0) / values.length,
          latest: values[values.length - 1]
        };
      }
    }

    return {
      window: windowName,
      startTime: snapshots[0]?.timestamp,
      endTime: snapshots[snapshots.length - 1]?.timestamp,
      snapshotCount: snapshots.length,
      counters: aggregatedCounters,
      gauges: aggregatedGauges,
      histograms: aggregatedHistograms
    };
  }

  /**
   * Calculate rate of change for a metric
   */
  calculateRate(metricName, windowName = '1m') {
    const window = this.windows[windowName];
    if (!window) return null;

    const snapshots = window.data.filter(s => s.timestamp !== null);
    if (snapshots.length < 2) return 0;

    const oldest = snapshots[0].metrics.counters[metricName] || 0;
    const newest = snapshots[snapshots.length - 1].metrics.counters[metricName] || 0;

    const timeDiff = (snapshots[snapshots.length - 1].timestamp - snapshots[0].timestamp) / 1000;
    if (timeDiff === 0) return 0;

    return (newest - oldest) / timeDiff; // per second
  }

  /**
   * Get trends - increasing/decreasing/stable
   */
  getTrends(metricName, windowName = '1m') {
    const window = this.windows[windowName];
    if (!window) return { trend: 'unknown' };

    const snapshots = window.data.filter(s => s.timestamp !== null && s.metrics.counters[metricName] !== undefined);
    if (snapshots.length < 3) return { trend: 'insufficient_data' };

    const values = snapshots.map(s => s.metrics.counters[metricName]);

    // Simple trend detection
    const firstHalf = values.slice(0, Math.floor(values.length / 2));
    const secondHalf = values.slice(Math.floor(values.length / 2));

    const firstAvg = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
    const secondAvg = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;

    const change = (secondAvg - firstAvg) / (firstAvg || 1);

    if (change > 0.1) return { trend: 'increasing', changePercent: (change * 100).toFixed(2) };
    if (change < -0.1) return { trend: 'decreasing', changePercent: (change * 100).toFixed(2) };
    return { trend: 'stable', changePercent: '0.00' };
  }

  /**
   * Detect anomalies in metrics
   */
  detectAnomalies(windowName = '1m', threshold = 2) {
    const window = this.windows[windowName];
    if (!window) return [];

    const snapshots = window.data.filter(s => s.timestamp !== null);
    if (snapshots.length < 5) return [];

    const anomalies = [];
    const metricNames = Object.keys(snapshots[0].metrics.counters);

    for (const name of metricNames) {
      const values = snapshots.map(s => s.metrics.counters[name] || 0);
      const mean = values.reduce((a, b) => a + b, 0) / values.length;
      const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
      const stdDev = Math.sqrt(variance);

      const latest = values[values.length - 1];
      if (stdDev > 0 && Math.abs(latest - mean) > threshold * stdDev) {
        anomalies.push({
          metric: name,
          latest,
          mean: mean.toFixed(2),
          stdDev: stdDev.toFixed(2),
          deviation: ((latest - mean) / stdDev).toFixed(2) + ' std devs'
        });
      }
    }

    return anomalies;
  }

  /**
   * Get summary across all windows
   */
  getAllWindowSummaries() {
    const summaries = {};

    for (const windowName of Object.keys(this.windows)) {
      const agg = this.getAggregatedMetrics(windowName);
      if (!agg.error) {
        summaries[windowName] = {
          snapshotCount: agg.snapshotCount,
          duration: this.timeWindows[windowName].duration,
          oldestSnapshot: agg.startTime,
          newestSnapshot: agg.endTime
        };
      }
    }

    return summaries;
  }

  /**
   * Clear window data
   */
  clearWindow(windowName) {
    if (this.windows[windowName]) {
      const config = this.timeWindows[windowName];
      this.windows[windowName] = {
        data: new Array(config.buckets).fill(null).map(() => ({
          timestamp: null,
          metrics: null
        })),
        currentIndex: 0,
        lastUpdate: Date.now()
      };
    }
  }

  /**
   * Clear all windows
   */
  clearAll() {
    for (const windowName of Object.keys(this.windows)) {
      this.clearWindow(windowName);
    }
  }
}

module.exports = MetricsAggregator;
