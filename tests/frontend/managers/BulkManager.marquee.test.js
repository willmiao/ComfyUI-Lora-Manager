import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { state } from '../../../static/js/state/index.js';
import { MODEL_TYPES } from '../../../static/js/api/apiConfig.js';
import { eventManager } from '../../../static/js/utils/EventManager.js';
import { BulkManager } from '../../../static/js/managers/BulkManager.js';

function fire(type, init = {}) {
  return new MouseEvent(type, { bubbles: true, cancelable: true, ...init });
}

describe('BulkManager marquee guards', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom may not provide requestAnimationFrame; stub it so the auto-scroll loop is a no-op.
    window.requestAnimationFrame = vi.fn();
    window.cancelAnimationFrame = vi.fn();

    eventManager.cleanup();
    state.currentPageType = MODEL_TYPES.LORA;
    state.bulkMode = false;
    state.selectedModels.clear();

    document.body.innerHTML = '<div class="page-content"></div>';
    const pageContent = document.querySelector('.page-content');
    pageContent.getBoundingClientRect = () => ({
      top: 0,
      left: 0,
      right: 1000,
      bottom: 1000,
      width: 1000,
      height: 1000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    pageContent.scrollBy = vi.fn();
  });

  afterEach(() => {
    eventManager.cleanup();
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  function createBulkManager() {
    const bulk = new BulkManager();
    bulk.initialize();
    return bulk;
  }

  it('never starts a marquee when the left button is not held', () => {
    const bulk = createBulkManager();
    const pageContent = document.querySelector('.page-content');

    pageContent.dispatchEvent(fire('mousedown', { button: 0, clientX: 10, clientY: 10 }));
    document.dispatchEvent(fire('mousemove', { buttons: 0, clientX: 50, clientY: 50 }));

    expect(bulk.mouseDownTime).toBe(0);
    expect(bulk.isMarqueeActive).toBe(false);
    expect(state.bulkMode).toBe(false);
    expect(document.querySelector('.marquee-selection')).toBeNull();
  });

  it('requires holding the left button for the drag delay before starting a marquee', () => {
    const bulk = createBulkManager();
    const pageContent = document.querySelector('.page-content');

    pageContent.dispatchEvent(fire('mousedown', { button: 0, clientX: 10, clientY: 10 }));

    // Fast movement: far enough, but too soon after mousedown.
    document.dispatchEvent(fire('mousemove', { buttons: 1, clientX: 30, clientY: 10 }));
    expect(state.bulkMode).toBe(false);
    expect(bulk.isMarqueeActive).toBe(false);

    // Once the hold time has elapsed, the same drag qualifies.
    vi.advanceTimersByTime(100);
    document.dispatchEvent(fire('mousemove', { buttons: 1, clientX: 35, clientY: 12 }));
    expect(state.bulkMode).toBe(true);
    expect(bulk.isMarqueeActive).toBe(true);
    expect(document.querySelector('.marquee-selection')).not.toBeNull();
  });

  it('ends an active marquee if the left button is released without a mouseup event', () => {
    const bulk = createBulkManager();
    bulk.mouseDownPosition = { x: 10, y: 10 };
    bulk.startMarqueeSelection({}, true);
    expect(state.bulkMode).toBe(true);
    expect(document.querySelector('.marquee-selection')).not.toBeNull();

    // No mouseup was dispatched; a plain move with the button released finalizes it.
    document.dispatchEvent(fire('mousemove', { buttons: 0, clientX: 50, clientY: 50 }));

    expect(bulk.isMarqueeActive).toBe(false);
    expect(document.querySelector('.marquee-selection')).toBeNull();
    expect(state.bulkMode).toBe(false); // zero selected -> auto-exit
  });

  it('treats a tiny marquee as an accidental click: clears selection and exits bulk mode', () => {
    const bulk = createBulkManager();
    const card = document.createElement('div');
    card.className = 'model-card selected';
    card.dataset.filepath = '/models/test.safetensors';
    document.body.appendChild(card);
    state.selectedModels.add('/models/test.safetensors');

    bulk.mouseDownPosition = { x: 100, y: 100 };
    bulk.startMarqueeSelection({}, true);
    expect(state.bulkMode).toBe(true);

    bulk.endMarqueeSelection({ clientX: 103, clientY: 104 });

    expect(state.bulkMode).toBe(false);
    expect(state.selectedModels.size).toBe(0);
    expect(card.classList.contains('selected')).toBe(false);
  });

  it('keeps selection and bulk mode when the marquee is large enough', () => {
    const bulk = createBulkManager();
    const card = document.createElement('div');
    card.className = 'model-card selected';
    card.dataset.filepath = '/models/test.safetensors';
    document.body.appendChild(card);
    state.selectedModels.add('/models/test.safetensors');

    bulk.mouseDownPosition = { x: 100, y: 100 };
    bulk.startMarqueeSelection({}, true);

    bulk.endMarqueeSelection({ clientX: 130, clientY: 140 });

    expect(state.bulkMode).toBe(true);
    expect(state.selectedModels.has('/models/test.safetensors')).toBe(true);
    expect(card.classList.contains('selected')).toBe(true);
  });

  it('keeps auto-scroll marquee selections when the pointer only moved a few pixels', () => {
    const bulk = createBulkManager();
    const pageContent = document.querySelector('.page-content');

    // Card just below the press point in document coordinates.
    const card = document.createElement('div');
    card.className = 'model-card';
    card.dataset.filepath = '/models/off-screen.safetensors';
    card.getBoundingClientRect = () => ({
      top: 950,
      left: 400,
      right: 600,
      bottom: 1050,
      width: 200,
      height: 100,
      x: 400,
      y: 950,
      toJSON: () => ({}),
    });
    document.body.appendChild(card);

    pageContent.dispatchEvent(fire('mousedown', { button: 0, clientX: 500, clientY: 900 }));
    vi.advanceTimersByTime(100);

    // Small pointer move: enough to start the marquee, but under minMarqueeSize.
    document.dispatchEvent(fire('mousemove', { buttons: 1, clientX: 506, clientY: 906 }));
    expect(bulk.isMarqueeActive).toBe(true);

    // Auto-scroll grows the document-space box while the pointer stays nearly still.
    pageContent.scrollTop = 200;
    card.getBoundingClientRect = () => ({
      top: 750,
      left: 400,
      right: 600,
      bottom: 850,
      width: 200,
      height: 100,
      x: 400,
      y: 750,
      toJSON: () => ({}),
    });
    document.dispatchEvent(fire('mousemove', { buttons: 1, clientX: 506, clientY: 906 }));

    expect(state.selectedModels.has('/models/off-screen.safetensors')).toBe(true);

    // Release: the client-space box is tiny, but the document-space box is not.
    document.dispatchEvent(fire('mouseup', { button: 0, clientX: 506, clientY: 906 }));

    expect(state.selectedModels.has('/models/off-screen.safetensors')).toBe(true);
    expect(state.bulkMode).toBe(true);
  });
});
