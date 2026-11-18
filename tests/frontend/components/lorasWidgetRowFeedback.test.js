/**
 * Tests for the list's transient row feedback.
 *
 * A LoRA added or enabled from a surface outside the list (the prompt
 * autocomplete, the quick picker) flashes its row and brings it into view
 * inside the list. The cue is purely visual: it must never select the row,
 * never emit the selection callback and never write the widget value, so the
 * row the user is inspecting stays selected. It fades out on its own.
 *
 * The widget mount mirrors ComfyUI's real addDOMWidget: `value` is wired to
 * options.getValue/setValue, and setValue() re-renders the list, so a value
 * written by another surface produces the row before the flash is requested.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
    canvas: { ds: { scale: 1 } },
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: { get: () => undefined, set: vi.fn() },
    },
  },
}));

const { fetchApiMock } = vi.hoisted(() => ({ fetchApiMock: vi.fn() }));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock, addEventListener: vi.fn() },
}));

// The styles loader fetches the stylesheet over a relative URL, which jsdom's
// fetch cannot resolve; styles are irrelevant to the classes under test.
vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import { addLorasWidget } from '../../../web/comfyui/loras_widget.js';
import {
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

const respondWith = ({ loras = [] } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

const entry = (name, active, strength = '1.00', extra = {}) => ({
  name,
  strength,
  active,
  ...extra,
});

const mountWidget = async (entries, opts = {}) => {
  const node = {
    id: 1,
    comfyClass: 'Lora Stacker (LoraManager)',
    addDOMWidget(name, type, container, options) {
      const widget = {
        get value() {
          return options.getValue();
        },
        set value(nextValue) {
          options.setValue(nextValue);
        },
      };
      widget.getValue = () => options.getValue();
      node.container = container;
      node.widget = widget;
      return widget;
    },
  };
  addLorasWidget(node, 'loras', { defaultVal: entries, ...opts }, opts.callback);
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

const rows = (node) => [...node.container.querySelectorAll('.lm-lora-entry')];
const rowFor = (node, name) => rows(node).find((row) => row.dataset.loraName === name);
const flashing = (node) =>
  rows(node)
    .filter(
      (row) =>
        row.classList.contains('lm-lora-entry--flash-added') ||
        row.classList.contains('lm-lora-entry--flash-enabled'),
    )
    .map((row) => row.dataset.loraName);
const selectedNames = (node) =>
  node.widget.getValue().filter((lora) => lora.selected).map((lora) => lora.name);

describe('addLorasWidget transient row feedback', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('flashes an appended row without selecting it', async () => {
    const onSelectionChange = vi.fn();
    respondWith();
    const node = await mountWidget([entry('set/kept', true)], { onSelectionChange });

    node.widget.value = [...node.widget.getValue(), entry('set/added_row', true)];
    const flashed = node.widget.flashLoraEntry('set/added_row.safetensors', 'added');

    expect(flashed).toBe(true);
    expect(rowFor(node, 'set/added_row').classList.contains('lm-lora-entry--flash-added')).toBe(true);
    // Pure visual feedback: no row becomes selected and no selection event fires.
    expect(rowFor(node, 'set/added_row').dataset.selected).toBe('false');
    expect(selectedNames(node)).toEqual([]);
    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it('rings an enabled row with the enabled cue only', async () => {
    respondWith();
    const node = await mountWidget([entry('set/on', true), entry('set/off', false)]);

    node.widget.flashLoraEntry('set/off', 'enabled');

    expect(rowFor(node, 'set/off').classList.contains('lm-lora-entry--flash-enabled')).toBe(true);
    expect(rowFor(node, 'set/off').classList.contains('lm-lora-entry--flash-added')).toBe(false);
    expect(flashing(node)).toEqual(['set/off']);
  });

  it('resolves a bare-name row from a picked relative path', async () => {
    respondWith();
    const node = await mountWidget([entry('bare_entry', true)]);

    const flashed = node.widget.flashLoraEntry('folder/bare_entry.safetensors', 'added');

    expect(flashed).toBe(true);
    expect(rowFor(node, 'bare_entry').classList.contains('lm-lora-entry--flash-added')).toBe(true);
  });

  it('ignores a name that is not in the list', async () => {
    respondWith();
    const node = await mountWidget([entry('set/known', true)]);

    expect(node.widget.flashLoraEntry('set/missing.safetensors', 'added')).toBe(false);
    expect(node.widget.flashLoraEntry('', 'added')).toBe(false);
    expect(flashing(node)).toEqual([]);
  });

  it('keeps one cue at a time and clears it after the animation', async () => {
    respondWith();
    const node = await mountWidget([entry('set/first', true), entry('set/second', true)]);

    node.widget.flashLoraEntry('set/first', 'added');
    node.widget.flashLoraEntry('set/second', 'enabled');

    // The second pick restarts the cue rather than leaving two rows glowing.
    expect(flashing(node)).toEqual(['set/second']);

    vi.useFakeTimers();
    node.widget.flashLoraEntry('set/second', 'enabled');
    expect(flashing(node)).toEqual(['set/second']);
    vi.advanceTimersByTime(1200);
    expect(flashing(node)).toEqual([]);
  });

  it('scrolls the list only when the row is out of view', async () => {
    respondWith();
    const node = await mountWidget([entry('set/first', true), entry('set/last', true)]);
    const container = node.container;
    let scrollTop = 0;
    Object.defineProperty(container, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value;
      },
    });
    container.getBoundingClientRect = () => ({
      top: 100, bottom: 140, height: 40, left: 0, right: 300, width: 300,
      x: 0, y: 100, toJSON: () => ({}),
    });
    const visibleRow = rowFor(node, 'set/first');
    visibleRow.getBoundingClientRect = () => ({
      top: 104, bottom: 130, height: 26, left: 0, right: 300, width: 300,
      x: 0, y: 104, toJSON: () => ({}),
    });
    const hiddenRow = rowFor(node, 'set/last');
    hiddenRow.getBoundingClientRect = () => ({
      top: 160, bottom: 186, height: 26, left: 0, right: 300, width: 300,
      x: 0, y: 160, toJSON: () => ({}),
    });

    node.widget.flashLoraEntry('set/first', 'added');
    expect(scrollTop).toBe(0);

    node.widget.flashLoraEntry('set/last', 'added');
    // Just enough to clear the bottom edge plus the breathing room.
    expect(scrollTop).toBe(186 - 140 + 4);
  });

  it('leaves values and callbacks alone', async () => {
    respondWith();
    const callback = vi.fn();
    const node = await mountWidget([entry('set/on', true), entry('set/off', false)], { callback });
    const before = JSON.stringify(node.widget.getValue());
    callback.mockClear();

    node.widget.flashLoraEntry('set/off', 'enabled');

    expect(callback).not.toHaveBeenCalled();
    expect(JSON.stringify(node.widget.getValue())).toBe(before);
  });
});
