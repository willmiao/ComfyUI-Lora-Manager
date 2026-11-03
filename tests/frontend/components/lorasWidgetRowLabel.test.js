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
    extensionManager: { setting: { get: () => undefined, set: vi.fn() } },
  },
}));

const { fetchApiMock } = vi.hoisted(() => ({ fetchApiMock: vi.fn() }));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock, addEventListener: vi.fn() },
}));

// The styles loader fetches the stylesheet over a relative URL, which jsdom's
// fetch cannot resolve; styles are irrelevant to the row labels under test.
vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import { addLorasWidget } from '../../../web/comfyui/loras_widget.js';
import { getAvailableLoras, resetAvailableLorasCache } from '../../../web/comfyui/loras_widget_utils.js';

const respondWith = ({ loras = [], settings = {} } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    if (url === '/lm/settings') {
      return { ok: true, json: async () => ({ success: true, settings }) };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  });
};

const mountWidget = async (options, entryName) => {
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
    ...options,
    defaultVal: [{ name: entryName, strength: '1.00', active: true }],
  });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

describe('addLorasWidget row labels', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('labels rows with the model name', async () => {
    respondWith({
      loras: [{ file_name: 'krea2/abc123def', model_name: 'Example title' }],
      settings: { model_name_display: 'model_name' },
    });
    const node = await mountWidget({}, 'abc123def');
    const label = node.container.querySelector('.lm-lora-name');
    expect(label.textContent).toBe('Example title');
    expect(label.dataset.loraFileName).toBe('abc123def');
    expect(node.widget.value).toEqual([{ name: 'abc123def', strength: '1.00', active: true }]);
  });

  it('keeps the file name when the preference asks for it', async () => {
    respondWith({
      loras: [{ file_name: 'krea2/abc123def', model_name: 'Example title' }],
      settings: { model_name_display: 'file_name' },
    });
    const node = await mountWidget({}, 'abc123def');
    expect(node.container.querySelector('.lm-lora-name').textContent).toBe('abc123def');
  });
});
