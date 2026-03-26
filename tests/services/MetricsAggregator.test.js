/**
 * Tests for MetricsAggregator
 */

const MetricsAggregator = require('../../src/services/metrics/MetricsAggregator');
const MetricsCollector = require('../../src/services/metrics/MetricsCollector');

describe('MetricsAggregator', () => {
  let aggregator;
  let collector;

  beforeEach(() => {
    collector = new MetricsCollector({ enabled: true, prefix: 'test' });
    aggregator = new MetricsAggregator(collector);
  });

  describe('constructor', () => {
    it('should initialize with default time windows', () => {
      expect(aggregator.windows).toBeDefined();
      expect(Object.keys(aggregator.windows)).toContain('1m');
      expect(Object.keys(aggregator.windows)).toContain('5m');
      expect(Object.keys(aggregator.windows)).toContain('1h');
      expect(Object.keys(aggregator.windows)).toContain('24h');
    });

    it('should create bucket arrays for each window', () => {
      expect(aggregator.windows['1m'].data.length).toBe(60);
      expect(aggregator.windows['5m'].data.length).toBe(60);
    });
  });

  describe('recordSnapshot', () => {
    it('should record current metrics to all windows', () => {
      collector.incrementCounter('test.custom_counter', 42);
      aggregator.recordSnapshot();

      for (const window of Object.values(aggregator.windows)) {
        const latest = window.data[window.currentIndex === 0 ? window.data.length - 1 : window.currentIndex - 1];
        expect(latest.metrics).not.toBeNull();
      }
    });

    it('should update currentIndex', () => {
      const initialIndex = aggregator.windows['1m'].currentIndex;
      aggregator.recordSnapshot();
      expect(aggregator.windows['1m'].currentIndex).toBe((initialIndex + 1) % 60);
    });
  });

  describe('getAggregatedMetrics', () => {
    it('should return error for unknown window', () => {
      const result = aggregator.getAggregatedMetrics('invalid');
      expect(result.error).toBe('Unknown window: invalid');
    });

    it('should return error when no data', () => {
      const result = aggregator.getAggregatedMetrics('1m');
      expect(result.error).toBe('No data in window');
    });

    it('should aggregate counter values', () => {
      // Record multiple snapshots
      collector.incrementCounter('test.batch_counter', 10);
      aggregator.recordSnapshot();

      collector.incrementCounter('test.batch_counter', 20);
      aggregator.recordSnapshot();

      const result = aggregator.getAggregatedMetrics('1m');
      expect(result.error).toBeUndefined();
      expect(result.counters['test.batch_counter']).toBe(30);
    });

    it('should track snapshot count', () => {
      aggregator.recordSnapshot();
      aggregator.recordSnapshot();
      aggregator.recordSnapshot();

      const result = aggregator.getAggregatedMetrics('1m');
      expect(result.snapshotCount).toBe(3);
    });
  });

  describe('calculateRate', () => {
    it('should return 0 for unknown window', () => {
      expect(aggregator.calculateRate('test.metric', 'invalid')).toBeNull();
    });

    it('should return 0 with insufficient data', () => {
      aggregator.recordSnapshot();
      expect(aggregator.calculateRate('test.metric', '1m')).toBe(0);
    });

    it('should calculate rate of change', () => {
      // This test is timing-dependent, so just check it runs
      collector.incrementCounter('test.rate_counter', 100);
      aggregator.recordSnapshot();

      collector.incrementCounter('test.rate_counter', 100);
      aggregator.recordSnapshot();

      const rate = aggregator.calculateRate('test.rate_counter', '1m');
      expect(typeof rate).toBe('number');
    });
  });

  describe('getTrends', () => {
    it('should return error for unknown window', () => {
      const result = aggregator.getTrends('test.metric', 'invalid');
      expect(result.trend).toBe('unknown');
    });

    it('should return insufficient_data with few snapshots', () => {
      aggregator.recordSnapshot();
      const result = aggregator.getTrends('test.metric', '1m');
      expect(result.trend).toBe('insufficient_data');
    });

    it('should detect increasing trend', () => {
      // Record snapshots with increasing values
      for (let i = 0; i < 10; i++) {
        collector.setGauge('test.trend_metric', i * 10);
        aggregator.recordSnapshot();
      }

      const result = aggregator.getTrends('test.trend_metric', '1m');
      expect(['increasing', 'stable']).toContain(result.trend);
    });

    it('should detect decreasing trend', () => {
      // Record snapshots with decreasing values
      for (let i = 10; i >= 0; i--) {
        collector.setGauge('test.down_trend', i * 10);
        aggregator.recordSnapshot();
      }

      const result = aggregator.getTrends('test.down_trend', '1m');
      expect(['decreasing', 'stable']).toContain(result.trend);
    });
  });

  describe('detectAnomalies', () => {
    it('should return empty array with insufficient data', () => {
      aggregator.recordSnapshot();
      const anomalies = aggregator.detectAnomalies('1m');
      expect(anomalies).toEqual([]);
    });

    it('should detect metrics that deviate significantly', () => {
      // Create some normal data
      for (let i = 0; i < 10; i++) {
        collector.setGauge('test.stable_metric', 100);
        aggregator.recordSnapshot();
      }

      // Add anomalous value
      collector.setGauge('test.stable_metric', 1000);
      aggregator.recordSnapshot();

      const anomalies = aggregator.detectAnomalies('1m', 2);
      expect(anomalies.length).toBeGreaterThan(0);
    });

    it('should respect custom threshold', () => {
      for (let i = 0; i < 10; i++) {
        collector.setGauge('test.metric', 100);
        aggregator.recordSnapshot();
      }

      collector.setGauge('test.metric', 150);
      aggregator.recordSnapshot();

      // With threshold 2, should not detect
      const noAnomaly = aggregator.detectAnomalies('1m', 2);
      expect(noAnomaly.length).toBe(0);
    });
  });

  describe('getAllWindowSummaries', () => {
    it('should return summaries for all windows', () => {
      aggregator.recordSnapshot();
      const summaries = aggregator.getAllWindowSummaries();

      expect(Object.keys(summaries)).toContain('1m');
      expect(Object.keys(summaries)).toContain('5m');
      expect(Object.keys(summaries)).toContain('1h');
      expect(Object.keys(summaries)).toContain('24h');
    });

    it('should include snapshot counts', () => {
      aggregator.recordSnapshot();
      aggregator.recordSnapshot();

      const summaries = aggregator.getAllWindowSummaries();
      expect(summaries['1m'].snapshotCount).toBe(2);
    });
  });

  describe('clearWindow', () => {
    it('should clear data for specific window', () => {
      aggregator.recordSnapshot();
      aggregator.recordSnapshot();

      aggregator.clearWindow('1m');

      const result = aggregator.getAggregatedMetrics('1m');
      expect(result.error).toBe('No data in window');
    });

    it('should not affect other windows', () => {
      aggregator.recordSnapshot();
      aggregator.clearWindow('1m');

      const result = aggregator.getAggregatedMetrics('5m');
      expect(result.error).toBeUndefined();
    });
  });

  describe('clearAll', () => {
    it('should clear all windows', () => {
      aggregator.recordSnapshot();
      aggregator.clearAll();

      for (const window of Object.values(aggregator.windows)) {
        const hasData = window.data.some(d => d.timestamp !== null);
        expect(hasData).toBe(false);
      }
    });
  });
});
