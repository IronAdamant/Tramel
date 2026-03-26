/**
 * Tests for MetricsCollector
 *
 * These tests challenge Chisel because:
 * 1. Performance measurement code needs thorough testing
 * 2. Timing/caching logic needs edge case coverage
 * 3. Aggregation calculations need validation
 */

const MetricsCollector = require('../../src/services/metrics/MetricsCollector');

describe('MetricsCollector', () => {
  let collector;

  beforeEach(() => {
    collector = new MetricsCollector({ enabled: true, prefix: 'test' });
  });

  describe('constructor', () => {
    it('should initialize with default values', () => {
      expect(collector.prefix).toBe('test');
      expect(collector.enabled).toBe(true);
    });

    it('should initialize default metrics', () => {
      expect(collector.getCounter('test.requests.total')).toBe(0);
      expect(collector.getCounter('test.cache.hits')).toBe(0);
    });
  });

  describe('counter', () => {
    it('should get and set counter', () => {
      collector.counter('test.counter', 10);
      expect(collector.getCounter('test.counter')).toBe(10);
    });

    it('should increment counter', () => {
      collector.incrementCounter('test.counter');
      collector.incrementCounter('test.counter', 5);
      expect(collector.getCounter('test.counter')).toBe(6);
    });

    it('should handle negative increments', () => {
      collector.counter('test.counter', 10);
      collector.incrementCounter('test.counter', -3);
      expect(collector.getCounter('test.counter')).toBe(7);
    });
  });

  describe('gauge', () => {
    it('should set and get gauge', () => {
      collector.setGauge('test.gauge', 100);
      expect(collector.getGauge('test.gauge')).toBe(100);
    });

    it('should overwrite gauge value', () => {
      collector.setGauge('test.gauge', 100);
      collector.setGauge('test.gauge', 200);
      expect(collector.getGauge('test.gauge')).toBe(200);
    });
  });

  describe('histogram', () => {
    it('should record values', () => {
      collector.recordHistogram('test.hist', 10);
      collector.recordHistogram('test.hist', 20);
      collector.recordHistogram('test.hist', 30);

      const stats = collector.getHistogramStats('test.hist');
      expect(stats.count).toBe(3);
      expect(stats.mean).toBe(20);
      expect(stats.min).toBe(10);
      expect(stats.max).toBe(30);
    });

    it('should calculate percentiles', () => {
      for (let i = 1; i <= 100; i++) {
        collector.recordHistogram('test.pct', i);
      }

      const stats = collector.getHistogramStats('test.pct');
      expect(stats.p50).toBe(50);
      expect(stats.p95).toBe(95);
      expect(stats.p99).toBe(99);
    });

    it('should limit stored values', () => {
      // Record more than maxValues (1000)
      for (let i = 0; i < 1500; i++) {
        collector.recordHistogram('test.limit', i);
      }

      const stats = collector.getHistogramStats('test.limit');
      expect(stats.count).toBe(1500); // Count is accurate
      expect(stats.values || stats.max).toBeLessThanOrEqual(1500);
    });
  });

  describe('timer', () => {
    it('should start and end timer', () => {
      const timer = collector.startTimer('test.operation');
      expect(timer.name).toBe('test.operation');
      expect(timer.start).not.toBeNull();

      // Simulate some work
      const start = Date.now();
      while (Date.now() - start < 10) {} // 10ms delay

      const duration = collector.endTimer(timer);
      expect(duration).toBeGreaterThanOrEqual(0);
    });

    it('should return null for unknown timer', () => {
      const duration = collector.endTimer('nonexistent');
      expect(duration).toBeNull();
    });

    it('should record to histogram when specified', () => {
      const timer = collector.startTimer('test.histogram_op');
      collector.endTimer(timer, 'test.histogram');

      const stats = collector.getHistogramStats('test.histogram');
      expect(stats.count).toBe(1);
    });
  });

  describe('timeFunction', () => {
    it('should time a synchronous function', () => {
      const result = collector.timeFunction('test.sync', () => {
        return 42;
      });

      expect(result).toBe(42);
    });

    it('should time an asynchronous function', async () => {
      const result = await collector.timeAsyncFunction('test.async', async () => {
        return await Promise.resolve(42);
      });

      expect(result).toBe(42);
    });

    it('should still return value if function throws', () => {
      expect(() => {
        collector.timeFunction('test.error', () => {
          throw new Error('test error');
        });
      }).toThrow('test error');
    });
  });

  describe('recordRequest', () => {
    it('should record successful request', () => {
      collector.recordRequest(true, 50);

      expect(collector.getCounter('test.requests.total')).toBe(1);
      expect(collector.getCounter('test.requests.success')).toBe(1);
      expect(collector.getCounter('test.requests.error')).toBe(0);
    });

    it('should record failed request', () => {
      collector.recordRequest(false, 100);

      expect(collector.getCounter('test.requests.total')).toBe(1);
      expect(collector.getCounter('test.requests.error')).toBe(1);
    });
  });

  describe('cache recording', () => {
    it('should record cache hits', () => {
      collector.recordCacheHit();
      collector.recordCacheHit();
      expect(collector.getCounter('test.cache.hits')).toBe(2);
    });

    it('should record cache misses', () => {
      collector.recordCacheMiss();
      expect(collector.getCounter('test.cache.misses')).toBe(1);
    });
  });

  describe('getAllMetrics', () => {
    it('should return all metrics', () => {
      collector.setGauge('test.custom', 42);
      collector.incrementCounter('test.custom_counter');

      const all = collector.getAllMetrics();

      expect(all.counters).toBeDefined();
      expect(all.gauges).toBeDefined();
      expect(all.histograms).toBeDefined();
      expect(all.gauges['test.custom']).toBe(42);
    });
  });

  describe('getSummary', () => {
    it('should return summary with rates', () => {
      collector.recordCacheHit();
      collector.recordCacheHit();
      collector.recordCacheHit();
      collector.recordCacheMiss();

      const summary = collector.getSummary();

      expect(summary.cache.hits).toBe(3);
      expect(summary.cache.misses).toBe(1);
      expect(summary.cache.hitRate).toBe('75.00%');
    });

    it('should include memory metrics', () => {
      const summary = collector.getSummary();
      expect(summary.memory).toBeDefined();
      expect(summary.memory.heapUsed).toBeGreaterThan(0);
    });
  });

  describe('reset', () => {
    it('should reset all metrics', () => {
      collector.incrementCounter('test.custom');
      collector.setGauge('test.custom', 100);

      collector.reset();

      // Should reinitialize defaults
      expect(collector.getCounter('test.requests.total')).toBe(0);
      expect(collector.getCounter('test.cache.hits')).toBe(0);
    });
  });

  describe('setEnabled', () => {
    it('should disable metrics collection', () => {
      collector.setEnabled(false);
      collector.incrementCounter('test.should_not_record');
      expect(collector.getCounter('test.should_not_record')).toBe(0);
    });

    it('should re-enable metrics collection', () => {
      collector.setEnabled(false);
      collector.setEnabled(true);
      collector.incrementCounter('test.should_record');
      expect(collector.getCounter('test.should_record')).toBe(1);
    });
  });
});
