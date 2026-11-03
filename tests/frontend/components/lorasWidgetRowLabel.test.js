import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

// The node label preference is a ComfyUI setting, so the widget reads it through
// app.extensionManager.setting. `settingState` is the live value the getter sees.
const { registerExtensionMock, settingState } = vi.hoisted(() => ({
  registerExtensionMock: vi.fn(),
  settingState: { nodeLoraNameDisplay: undefined },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: registerExtensionMock,
    graph: {},
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: {
        get: (id) =>
          id === 'loramanager.node_lora_name_display'
            ? settingState.nodeLoraNameDisplay
            : undefined,
        set: vi.fn(),
      },
    },
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
import {
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

// The cycler list is the only request made: the label preference is read from
// ComfyUI's settings, not fetched from LoRA Manager.
const respondWith = ({ loras = [] } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

// The setting descriptor registered with ComfyUI, which is how a user change
// reaches open graphs.
const nodeLabelSetting = () => {
  const extension = registerExtensionMock.mock.calls
    .map(([registered]) => registered)
    .find((registered) => registered?.name === 'LoraManager.Settings');
  return extension?.settings.find(
    (setting) => setting.id === 'loramanager.node_lora_name_display'
  );
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

const labels = (node) => [...node.container.querySelectorAll('.lm-lora-name')];

describe('addLorasWidget row labels', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    settingState.nodeLoraNameDisplay = undefined;
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('labels rows with the file name by default', async () => {
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget(['abc123def']);
    const label = labels(node)[0];
    expect(label.textContent).toBe('abc123def');
    expect(label.dataset.loraFileName).toBeUndefined();
    expect(node.widget.value).toEqual([{ name: 'abc123def', strength: '1.00', active: true }]);
  });

  it('labels rows with the model name when the setting asks for it', async () => {
    settingState.nodeLoraNameDisplay = 'Model Name';
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget(['abc123def']);
    const label = labels(node)[0];
    expect(label.textContent).toBe('Example model title');
    // The resolved file name stays reachable; the widget value keeps it too.
    expect(label.dataset.loraFileName).toBe('abc123def');
    expect(node.widget.value).toEqual([{ name: 'abc123def', strength: '1.00', active: true }]);
  });

  it('falls back to the file name when the library does not know the entry', async () => {
    settingState.nodeLoraNameDisplay = 'Model Name';
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget(['unknown']);
    expect(labels(node)[0].textContent).toBe('unknown');
  });

  it('relabels open rows when the setting changes', async () => {
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget(['abc123def']);
    expect(labels(node)[0].textContent).toBe('abc123def');

    settingState.nodeLoraNameDisplay = 'Model Name';
    nodeLabelSetting().onChange('Model Name');

    expect(labels(node)[0].textContent).toBe('Example model title');
  });
});

describe('addLorasWidget duplicate titles', () => {
  const title = 'Example model title';

  beforeEach(() => {
    document.body.innerHTML = '';
    settingState.nodeLoraNameDisplay = 'Model Name';
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('prefixes a distinguishing suffix, keeping both file names as values', async () => {
    respondWith({
      loras: [
        { file_name: 'set/abc_v1', model_name: title, version_name: 'Example_v1', folder: 'set' },
        {
          file_name: 'set/abc_v2',
          model_name: title,
          version_name: 'Example_v2 (variant)',
          folder: 'set',
        },
      ],
    });

    const node = await mountWidget(['set/abc_v1', 'set/abc_v2']);

    const all = labels(node).map((el) => el.textContent);
    const rows = all.filter((text) => !text.startsWith('[clip] '));
    expect(rows).toEqual([`[v1] ${title}`, `[v2 (variant)] ${title}`]);
    // The [clip] sub-row mirrors the same disambiguated label.
    expect(all.filter((text) => text.startsWith('[clip] '))).toEqual([
      `[clip] [v1] ${title}`,
      `[clip] [v2 (variant)] ${title}`,
    ]);
    // The widget still stores the file names, so both rows load their own file.
    expect(node.widget.value.map((entry) => entry.name)).toEqual(['set/abc_v1', 'set/abc_v2']);
  });

  it('leaves a unique title unprefixed', async () => {
    respondWith({ loras: [{ file_name: 'set/only', model_name: 'Example sole title' }] });
    const node = await mountWidget(['set/only']);
    expect(labels(node)[0].textContent).toBe('Example sole title');
  });
});
