import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { initTooltips, hideTooltip } from '../../../static/js/utils/tooltip.js';

const TOOLTIP_WIDTH = 200;
const TOOLTIP_HEIGHT = 60;

function makeRect({ top = 0, left = 0, width = 0, height = 0 } = {}) {
  return {
    top,
    left,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON() { return this; }
  };
}

/**
 * Mount a trigger inside a scrollable container so the tooltip can be asserted
 * to escape the clipping ancestor.
 */
function mountTrigger({ id = 'helpIcon', tooltip = 'Help text', rect } = {}) {
  const scroller = document.createElement('div');
  scroller.className = 'settings-content';
  scroller.style.overflowY = 'auto';

  const icon = document.createElement('i');
  icon.id = id;
  icon.className = 'fas fa-info-circle info-icon';
  if (tooltip !== null) {
    icon.setAttribute('data-tooltip', tooltip);
  }
  // Own-property override so a test can move the trigger (scroll) later.
  icon.getBoundingClientRect = () => rectByElement.get(icon) || makeRect();
  rectByElement.set(icon, rect);

  scroller.appendChild(icon);
  document.body.appendChild(scroller);
  return icon;
}

let rectByElement;

beforeEach(() => {
  rectByElement = new Map();
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function () {
    if (this.id === 'lm-tooltip') {
      return makeRect({ width: TOOLTIP_WIDTH, height: TOOLTIP_HEIGHT });
    }
    return rectByElement.get(this) || makeRect();
  });
  initTooltips();
});

afterEach(() => {
  hideTooltip();
  vi.restoreAllMocks();
});

describe('tooltip', () => {
  it('renders the tooltip in the body, outside the scrollable container', () => {
    const icon = mountTrigger({
      tooltip: 'First line. Second line.',
      rect: makeRect({ top: 400, left: 100, width: 16, height: 16 })
    });

    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip).not.toBeNull();
    expect(tooltip.parentElement).toBe(document.body);
    expect(tooltip.closest('.settings-content')).toBeNull();
    expect(tooltip.textContent).toBe('First line. Second line.');
    expect(tooltip.classList.contains('visible')).toBe(true);
    expect(icon.getAttribute('aria-describedby')).toBe('lm-tooltip');
  });

  it('places the tooltip above the trigger when it fits', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 500, left: 100, width: 16, height: 16 }) });

    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip.style.top).toBe(`${500 - TOOLTIP_HEIGHT - 8}px`);
  });

  it('flips below the trigger when there is no room above', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 20, left: 100, width: 16, height: 16 }) });

    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip.style.top).toBe(`${20 + 16 + 8}px`);
  });

  it('clamps the tooltip inside the viewport', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 400, left: 0, width: 16, height: 16 }) });

    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(parseFloat(tooltip.style.left)).toBe(8);
  });

  it('hides the tooltip when the pointer leaves the trigger', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 400, left: 100, width: 16, height: 16 }) });
    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    icon.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip.classList.contains('visible')).toBe(false);
    expect(icon.hasAttribute('aria-describedby')).toBe(false);
  });

  it('keeps the tooltip open while moving between children of the trigger', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 400, left: 100, width: 16, height: 16 }) });
    const child = document.createElement('span');
    icon.appendChild(child);
    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    icon.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: child }));

    expect(document.getElementById('lm-tooltip').classList.contains('visible')).toBe(true);
  });

  it('hides the tooltip on Escape', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 400, left: 100, width: 16, height: 16 }) });
    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(document.getElementById('lm-tooltip').classList.contains('visible')).toBe(false);
  });

  it('follows the trigger while the settings pane scrolls', () => {
    const icon = mountTrigger({ rect: makeRect({ top: 500, left: 100, width: 16, height: 16 }) });
    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    rectByElement.set(icon, makeRect({ top: 20, left: 100, width: 16, height: 16 }));
    window.dispatchEvent(new Event('scroll'));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip.style.top).toBe(`${20 + 16 + 8}px`);
    expect(tooltip.classList.contains('visible')).toBe(true);
  });

  it('ignores triggers without tooltip text', () => {
    const icon = mountTrigger({ tooltip: null, rect: makeRect({ top: 400, left: 100, width: 16, height: 16 }) });

    icon.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

    const tooltip = document.getElementById('lm-tooltip');
    expect(tooltip === null || !tooltip.classList.contains('visible')).toBe(true);
  });
});
