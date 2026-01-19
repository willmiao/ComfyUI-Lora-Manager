import { afterEach, beforeEach } from 'vitest';
import { resetDom } from './utils/domFixtures.js';

// Polyfill fetch for jsdom environment
if (typeof window !== 'undefined' && !window.fetch) {
  window.fetch = async function(url, options) {
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
      text: async () => '',
      blob: async () => new Blob(),
      arrayBuffer: async () => new ArrayBuffer(8),
      headers: new Headers(),
      clone: () => this
    };
  };
}

// Polyfill PointerEvent for jsdom environment
if (typeof window !== 'undefined' && !window.PointerEvent) {
  class PointerEvent extends MouseEvent {
    constructor(type, eventInit = {}) {
      super(type, eventInit);
      this.pointerId = eventInit.pointerId || 0;
      this.pointerType = eventInit.pointerType || 'mouse';
      this.isPrimary = eventInit.isPrimary !== undefined ? eventInit.isPrimary : true;
    }
  }
  window.PointerEvent = PointerEvent;
}

// Polyfill setPointerCapture and releasePointerCapture for jsdom elements
if (typeof Element !== 'undefined') {
  const capturedPointers = new Map();

  Element.prototype.setPointerCapture = function(pointerId) {
    capturedPointers.set(pointerId, this);
  };

  Element.prototype.releasePointerCapture = function(pointerId) {
    capturedPointers.delete(pointerId);
  };

  // Store captured pointers for potential use in tests
  window.__testCapturedPointers = capturedPointers;
}

beforeEach(() => {
  // Ensure storage is clean before each test to avoid cross-test pollution
  localStorage.clear();
  sessionStorage.clear();

  // Reset DOM state for modules that rely on body attributes
  resetDom();
});

afterEach(() => {
  // Clean any dynamically attached globals by tests
  resetDom();
});
