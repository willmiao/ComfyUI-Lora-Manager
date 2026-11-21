/**
 * Regression tests for the LoRA list scroll position across re-renders.
 *
 * Every widget value change rebuilds the whole list. In a real browser the
 * rebuild starts by emptying the scroll container, which removes the control
 * the user just clicked; the focus fixup that follows flushes layout while the
 * container has no content, and the browser clamps its scrollTop to 0. The
 * rebuilt rows do not restore the offset, so toggling a row near the bottom
 * used to jump the list back to the top.
 *
 * jsdom has no layout and therefore never clamps anything, so the harness
 * emulates the clamp: the container's scrollTop is a plain property that an
 * emptied container resets to 0, exactly like the browser does.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
    canvas: { ds: { scale: 1 }, emitBeforeChange: vi.fn(), emitAfterChange: vi.fn() },
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

const mountWidget = async (entries) => {
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
      node.container = container;
      node.widget = widget;
      return widget;
    },
  };
  addLorasWidget(node, 'loras', { defaultVal: entries });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

const entry = (name, active = true) => ({
  name,
  strength: '1.00',
  clipStrength: '1.00',
  active,
  expanded: false,
});

const rows = (node) => [...node.container.querySelectorAll('.lm-lora-entry')];

/**
 * Give the container a real scroll offset and make an emptied container reset
 * it to 0 the way a browser clamps a scroll container that lost its content.
 */
const installScrollClamp = (node) => {
  let offset = 0;
  Object.defineProperty(node.container, 'scrollTop', {
    configurable: true,
    get: () => offset,
    set: (value) => {
      offset = Number(value) || 0;
    },
  });
  const originalRemoveChild = node.container.removeChild.bind(node.container);
  node.container.removeChild = (child) => {
    const removed = originalRemoveChild(child);
    if (node.container.childNodes.length === 0) {
      offset = 0;
    }
    return removed;
  };
  return {
    get: () => offset,
    set: (value) => {
      offset = value;
    },
  };
};

const manyEntries = (count = 24) =>
  Array.from({ length: count }, (_, i) => entry(`lora_${i}`, i % 2 === 0));

describe('addLorasWidget scroll position', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('keeps the list where the user left it when a row toggle rebuilds it', async () => {
    respondWith();
    const node = await mountWidget(manyEntries());
    const scroll = installScrollClamp(node);
    scroll.set(400);

    const target = rows(node).at(-2);
    const name = target.dataset.loraName;
    const wasActive = target.dataset.active === 'true';

    target.querySelector('.lm-lora-toggle').click();

    expect(rows(node).at(-2).dataset.loraName).toBe(name);
    expect(rows(node).at(-2).dataset.active).toBe(String(!wasActive));
    expect(node.container.scrollTop).toBe(400);
  });

  it('keeps the list in place when the header toggle-all rebuilds it', async () => {
    respondWith();
    const node = await mountWidget(manyEntries());
    const scroll = installScrollClamp(node);
    scroll.set(512);

    node.container.querySelector('.lm-toggle-container .lm-lora-toggle').click();

    expect(node.widget.value.every((lora) => lora.active === true)).toBe(true);
    expect(node.container.scrollTop).toBe(512);
  });

  it('keeps the list in place when the value is replaced from outside', async () => {
    respondWith();
    const node = await mountWidget(manyEntries());
    const scroll = installScrollClamp(node);
    scroll.set(256);

    node.widget.value = [...node.widget.value, entry('appended', true)];

    expect(rows(node)).toHaveLength(25);
    expect(node.container.scrollTop).toBe(256);
  });
});
