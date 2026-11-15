import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { STYLES_MODULE } = vi.hoisted(() => ({
  STYLES_MODULE: new URL(
    '../../../web/comfyui/lm_styles_loader.js',
    import.meta.url,
  ).pathname,
}));

vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));

import { PreviewTooltip } from '../../../web/comfyui/preview_tooltip.js';

function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

let tooltip;

beforeEach(() => {
  document.body.innerHTML = '';
  vi.useFakeTimers();
  // jsdom does not provide rAF; run the callback inline so positioning is
  // deterministic.
  vi.stubGlobal('requestAnimationFrame', vi.fn((callback) => {
    callback();
    return 1;
  }));
});

afterEach(() => {
  tooltip?.cleanup();
  tooltip = null;
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('PreviewTooltip', () => {
  it('applies the caller class so a panel preview can clear its layer', () => {
    tooltip = new PreviewTooltip({ className: 'lm-tooltip--elevated' });

    expect(tooltip.element.classList.contains('lm-tooltip')).toBe(true);
    expect(tooltip.element.classList.contains('lm-tooltip--elevated')).toBe(true);
  });

  it('shows the resolved preview with its display name', async () => {
    tooltip = new PreviewTooltip({
      previewUrlResolver: vi.fn(async () => '/previews/astral.png'),
    });

    const shown = tooltip.show('characters/astral', 10, 20);
    await vi.advanceTimersByTimeAsync(1000);
    await shown;

    expect(tooltip.element.style.display).toBe('block');
    expect(tooltip.element.querySelector('img')?.getAttribute('src'))
      .toBe('/previews/astral.png');
    expect(tooltip.element.querySelector('.lm-tooltip__label')?.textContent)
      .toBe('characters/astral');
  });

  it('does not show a preview that resolves after the pointer left', async () => {
    const pending = deferred();
    tooltip = new PreviewTooltip({
      previewUrlResolver: vi.fn(() => pending.promise),
    });

    const shown = tooltip.show('a', 10, 20);
    tooltip.hide();
    pending.resolve('/previews/a.png');
    await shown;

    expect(tooltip.element.style.display).not.toBe('block');
    expect(tooltip.element.children).toHaveLength(0);
  });

  it('stays quiet when the resolver has nothing to show', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    tooltip = new PreviewTooltip({ previewUrlResolver: vi.fn(async () => null) });

    await tooltip.show('a', 0, 0);

    expect(tooltip.element.style.display).not.toBe('block');
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it('keeps the preview inside the caller pane instead of the detail column', async () => {
    tooltip = new PreviewTooltip({
      previewUrlResolver: vi.fn(async () => '/previews/a.png'),
      positionBoundary: () => ({
        left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600,
      }),
    });
    tooltip.element.getBoundingClientRect = () => ({ width: 300, height: 200 });

    const shown = tooltip.show('a', 900, 40);
    await vi.advanceTimersByTimeAsync(1000);
    await shown;

    // The row's right edge is the pane's right edge: flip left of it.
    expect(tooltip.element.style.left).toBe('590px');
  });

  it('does not push a wide preview past the pane into negative space', async () => {
    tooltip = new PreviewTooltip({
      previewUrlResolver: vi.fn(async () => '/previews/a.png'),
      positionBoundary: () => ({
        left: 0, top: 0, right: 280, bottom: 600, width: 280, height: 600,
      }),
    });
    tooltip.element.getBoundingClientRect = () => ({ width: 320, height: 200 });

    const shown = tooltip.show('a', 280, 40);
    await vi.advanceTimersByTimeAsync(1000);
    await shown;

    expect(tooltip.element.style.left).toBe('10px');
  });

  it('hides the current preview when the next item has none', async () => {
    tooltip = new PreviewTooltip({
      previewUrlResolver: vi.fn(async (name) => (
        name === 'a' ? '/previews/a.png' : null
      )),
    });

    const first = tooltip.show('a', 0, 0);
    await vi.advanceTimersByTimeAsync(1000);
    await first;
    expect(tooltip.element.style.display).toBe('block');

    await tooltip.show('b', 0, 0);

    expect(tooltip.element.style.opacity).toBe('0');
    vi.advanceTimersByTime(150);
    expect(tooltip.element.style.display).toBe('none');
  });
});
