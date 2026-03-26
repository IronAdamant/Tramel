/**
 * MetricsCollector - Collects runtime metrics for API monitoring
 *
 * This challenges ALL THREE MCPs:
 *
 * STEFE-CONTEXT:
 * - Dynamic metric collection without static imports
 * - Runtime symbol tracking for metric aggregations
 * - Cross-module metric references
 *
 * CHISEL:
 * - Performance measurement code needs thorough testing
 * - Timing/caching logic needs edge case coverage
 * - Aggregation calculations need validation
 *
 * TRAMMEL:
 * - Multi-file planning for metrics pipeline
 * - Service -> Aggregator -> API -> Web UI coordination
 */

class MetricsCollector {
  constructor(options = {}) {
    this.metrics = new Map();
    this.counters = new Map();
    this.gauges = new Map();
    this.histograms = new Map();
    this.timers = new Map();
    this.enabled = options.enabled !== false;
    this.prefix = options.prefix || 'recipelab';

    // Initialize default metrics
    this.initializeDefaultMetrics();
  }

  /**
   * Initialize default system metrics
   */
  initializeDefaultMetrics() {
    // Request counters
    this.counter(`${this.prefix}.requests.total`, 0);
    this.counter(`${this.prefix}.requests.success`, 0);
    this.counter(`${this.prefix}.requests.error`, 0);

    // Timing gauges
    this.gauge(`${this.prefix}.request.duration.ms`, 0);
    this.gauge(`${this.prefix}.db.query.duration.ms`, 0);

    // Cache metrics
    this.counter(`${this.prefix}.cache.hits`, 0);
    this.counter(`${this.prefix}.cache.misses`, 0);

    // Memory metrics (will be updated periodically)
    this.gauge(`${this.prefix}.memory.heap_used`, 0);
    this.gauge(`${this.prefix}.memory.heap_total`, 0);

    // Recipe metrics
    this.counter(`${this.prefix}.recipes.created`, 0);
    this.counter(`${this.prefix}.recipes.updated`, 0);
    this.counter(`${this.prefix}.recipes.deleted`, 0);
    this.counter(`${this.prefix}.recipes.searched`, 0);
  }

  /**
   * Counter - monotonically increasing value
   */
  counter(name, initialValue = 0) {
    if (!this.counters.has(name)) {
      this.counters.set(name, initialValue);
    }
    return this.counters.get(name);
  }

  /**
   * Increment a counter
   */
  incrementCounter(name, delta = 1) {
    if (!this.enabled) return;

    const current = this.counter(name);
    this.counters.set(name, current + delta);
  }

  /**
   * Get counter value
   */
  getCounter(name) {
    return this.counters.get(name) || 0;
  }

  /**
   * Gauge - point-in-time value
   */
  gauge(name, value) {
    this.gauges.set(name, value);
  }

  /**
   * Set gauge value
   */
  setGauge(name, value) {
    if (!this.enabled) return;
    this.gauges.set(name, value);
  }

  /**
   * Get gauge value
   */
  getGauge(name) {
    return this.gauges.get(name) || 0;
  }

  /**
   * Histogram - distribution of values
   */
  histogram(name) {
    if (!this.histograms.has(name)) {
      this.histograms.set(name, {
        count: 0,
        sum: 0,
        min: Infinity,
        max: -Infinity,
        values: []
      });
    }
    return this.histograms.get(name);
  }

  /**
   * Record a value in histogram
   */
  recordHistogram(name, value, maxValues = 1000) {
    if (!this.enabled) return;

    const hist = this.histogram(name);
    hist.count++;
    hist.sum += value;
    hist.min = Math.min(hist.min, value);
    hist.max = Math.max(hist.max, value);

    // Keep last N values for percentile calculation
    hist.values.push(value);
    if (hist.values.length > maxValues) {
      hist.values.shift();
    }
  }

  /**
   * Get histogram stats
   */
  getHistogramStats(name) {
    const hist = this.histograms.get(name);
    if (!hist || hist.count === 0) {
      return { count: 0, mean: 0, min: 0, max: 0, p50: 0, p95: 0, p99: 0 };
    }

    const sorted = [...hist.values].sort((a, b) => a - b);
    const p = (percentile) => {
      const idx = Math.ceil((percentile / 100) * sorted.length) - 1;
      return sorted[Math.max(0, idx)];
    };

    return {
      count: hist.count,
      mean: hist.sum / hist.count,
      min: hist.min,
      max: hist.max,
      p50: p(50),
      p95: p(95),
      p99: p(99)
    };
  }

  /**
   * Timer - measure duration
   */
  startTimer(name) {
    if (!this.enabled) return { name, start: null };

    const start = process.hrtime.bigint();
    this.timers.set(name, start);
    return { name, start };
  }

  /**
   * End timer and record duration
   */
  endTimer(timerOrName, histogramName = null) {
    if (!this.enabled) return null;

    let name;
    let start;

    if (typeof timerOrName === 'object') {
      name = timerOrName.name;
      start = timerOrName.start;
    } else {
      name = timerOrName;
      start = this.timers.get(name);
    }

    if (!start) return null;

    const end = process.hrtime.bigint();
    const durationNs = Number(end - start);
    const durationMs = durationNs / 1e6;

    // Record in histogram if specified
    if (histogramName) {
      this.recordHistogram(histogramName, durationMs);
    }

    // Also set as gauge
    this.setGauge(`${this.prefix}.timer.${name}.ms`, durationMs);

    this.timers.delete(name);

    return durationMs;
  }

  /**
   * Convenience: time a function execution
   */
  timeFunction(name, fn, histogramName = null) {
    const timer = this.startTimer(name);
    try {
      const result = fn();
      this.endTimer(timer, histogramName);
      return result;
    } catch (error) {
      this.endTimer(timer, histogramName);
      throw error;
    }
  }

  /**
   * Convenience: time an async function
   */
  async timeAsyncFunction(name, fn, histogramName = null) {
    const timer = this.startTimer(name);
    try {
      const result = await fn();
      this.endTimer(timer, histogramName);
      return result;
    } catch (error) {
      this.endTimer(timer, histogramName);
      throw error;
    }
  }

  /**
   * Update memory metrics
   */
  updateMemoryMetrics() {
    if (!this.enabled) return;

    const mem = process.memoryUsage();
    this.setGauge(`${this.prefix}.memory.heap_used`, mem.heapUsed);
    this.setGauge(`${this.prefix}.memory.heap_total`, mem.heapTotal);
    this.setGauge(`${this.prefix}.memory.rss`, mem.rss);
    this.setGauge(`${this.prefix}.memory.external`, mem.external);
  }

  /**
   * Record API request
   */
  recordRequest(success = true, durationMs = 0) {
    this.incrementCounter(`${this.prefix}.requests.total`);
    this.incrementCounter(success ? `${this.prefix}.requests.success` : `${this.prefix}.requests.error`);
    this.recordHistogram(`${this.prefix}.request.duration`, durationMs);
    this.setGauge(`${this.prefix}.request.duration.ms`, durationMs);
  }

  /**
   * Record database query
   */
  recordDbQuery(durationMs) {
    this.incrementCounter(`${this.prefix}.db.queries`);
    this.recordHistogram(`${this.prefix}.db.query.duration`, durationMs);
    this.setGauge(`${this.prefix}.db.query.duration.ms`, durationMs);
  }

  /**
   * Record cache operation
   */
  recordCacheHit() {
    this.incrementCounter(`${this.prefix}.cache.hits`);
  }

  recordCacheMiss() {
    this.incrementCounter(`${this.prefix}.cache.misses`);
  }

  /**
   * Get all metrics as object
   */
  getAllMetrics() {
    const result = {
      counters: {},
      gauges: {},
      histograms: {}
    };

    // Counters
    for (const [name, value] of this.counters) {
      result.counters[name] = value;
    }

    // Gauges
    for (const [name, value] of this.gauges) {
      result.gauges[name] = value;
    }

    // Histograms
    for (const name of this.histograms.keys()) {
      result.histograms[name] = this.getHistogramStats(name);
    }

    return result;
  }

  /**
   * Get metrics summary for API response
   */
  getSummary() {
    this.updateMemoryMetrics();

    const cacheHits = this.getCounter(`${this.prefix}.cache.hits`);
    const cacheMisses = this.getCounter(`${this.prefix}.cache.misses`);
    const totalCacheOps = cacheHits + cacheMisses;
    const cacheHitRate = totalCacheOps > 0 ? (cacheHits / totalCacheOps * 100).toFixed(2) + '%' : '0%';

    const requestDuration = this.getHistogramStats(`${this.prefix}.request.duration`);
    const dbDuration = this.getHistogramStats(`${this.prefix}.db.query.duration`);

    return {
      requests: {
        total: this.getCounter(`${this.prefix}.requests.total`),
        success: this.getCounter(`${this.prefix}.requests.success`),
        error: this.getCounter(`${this.prefix}.requests.error`),
        duration: requestDuration
      },
      cache: {
        hits: cacheHits,
        misses: cacheMisses,
        hitRate: cacheHitRate
      },
      database: {
        queries: this.getCounter(`${this.prefix}.db.queries`) || 0,
        duration: dbDuration
      },
      memory: {
        heapUsed: this.getGauge(`${this.prefix}.memory.heap_used`),
        heapTotal: this.getGauge(`${this.prefix}.memory.heap_total`),
        rss: this.getGauge(`${this.prefix}.memory.rss`)
      },
      recipes: {
        created: this.getCounter(`${this.prefix}.recipes.created`),
        updated: this.getCounter(`${this.prefix}.recipes.updated`),
        deleted: this.getCounter(`${this.prefix}.recipes.deleted`),
        searched: this.getCounter(`${this.prefix}.recipes.searched`)
      },
      uptime: process.uptime()
    };
  }

  /**
   * Reset all metrics
   */
  reset() {
    this.counters.clear();
    this.gauges.clear();
    this.histograms.clear();
    this.timers.clear();
    this.initializeDefaultMetrics();
  }

  /**
   * Enable/disable metrics collection
   */
  setEnabled(enabled) {
    this.enabled = enabled;
  }
}

// Singleton instance
const collector = new MetricsCollector();

module.exports = collector;
