import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
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
// fetch cannot resolve; styles are irrelevant to the selection under test.
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
    addDOMWidget(name, type, container) {
      const widget = { value: undefined };
      node.container = container;
      node.widget = widget;
      return widget;
    },
  };
  addLorasWidget(node, 'loras', {
    defaultVal: entries.map((name) => ({ name, strength: '1.00', active: true })),
  });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

const rows = (node) => [...node.container.querySelectorAll('.lm-lora-entry')];
const rowFor = (node, name) => rows(node).find((row) => row.dataset.loraName === name);

describe('addLorasWidget selectLoraByName', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('marks the row selected and scrolls it into view', async () => {
    respondWith();
    const node = await mountWidget(['abc123def', 'set/xyz789ghi']);

    node.widget.selectLoraByName('set/xyz789ghi');

    expect(rowFor(node, 'set/xyz789ghi').dataset.selected).toBe('true');
    expect(rowFor(node, 'abc123def').dataset.selected).toBe('false');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it('moves the selection when another LoRA is picked', async () => {
    respondWith();
    const node = await mountWidget(['abc123def', 'set/xyz789ghi']);

    node.widget.selectLoraByName('abc123def');
    node.widget.selectLoraByName('set/xyz789ghi');

    expect(rowFor(node, 'abc123def').dataset.selected).toBe('false');
    expect(rowFor(node, 'set/xyz789ghi').dataset.selected).toBe('true');
  });

  it('ignores an empty name', async () => {
    respondWith();
    const node = await mountWidget(['abc123def']);

    node.widget.selectLoraByName('');

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(rowFor(node, 'abc123def').dataset.selected).toBe('false');
  });
});
