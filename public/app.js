'use strict';

/**
 * RecipeLab Web UI JavaScript
 * API client and utility functions
 */

const API_BASE = '/api';

// Simple API client
const api = {
  async request(method, endpoint, data = null) {
    const url = `${API_BASE}${endpoint}`;
    const options = {
      method,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    try {
      const response = await fetch(url, options);
      const json = await response.json();

      if (!response.ok) {
        throw new Error(json.error || 'Request failed');
      }

      return json;
    } catch (err) {
      throw err;
    }
  },

  get(endpoint) {
    return this.request('GET', endpoint);
  },

  post(endpoint, data) {
    return this.request('POST', endpoint, data);
  },

  put(endpoint, data) {
    return this.request('PUT', endpoint, data);
  },

  delete(endpoint) {
    return this.request('DELETE', endpoint);
  }
};

// Utility functions
const utils = {
  /**
   * Format time in minutes to human readable
   */
  formatTime(minutes) {
    if (!minutes) return '-';
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  },

  /**
   * Format date
   */
  formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString();
  },

  /**
   * Escape HTML
   */
  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  /**
   * Create element with classes
   */
  createElement(tag, classes = [], content = '') {
    const el = document.createElement(tag);
    if (classes.length) {
      el.className = classes.join(' ');
    }
    if (content) {
      el.innerHTML = content;
    }
    return el;
  },

  /**
   * Show loading indicator
   */
  showLoading(el) {
    el.innerHTML = '<div class="loading">Loading...</div>';
  },

  /**
   * Show error message
   */
  showError(el, message) {
    el.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;
  }
};

// Initialize page scripts
document.addEventListener('DOMContentLoaded', () => {
  console.log('RecipeLab initialized');
});
