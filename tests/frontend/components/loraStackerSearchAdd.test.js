import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE, STACKER_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  STACKER_MODULE: new URL('../../../web/comfyui/lora_stacker.js', import.meta.url).pathname,
}));

const { registerExtensionMock, settingState } = vi.hoisted(() => ({
  registerExtensionMock: vi.fn(),
  settingState: { nodeLoraNameDisplay: 'File Name' },
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

vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import {
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';
import { getWidgetSerializedValue } from '../../../web/comfyui/utils.js';

// Synthetic catalogue: every folder, file name and title below is invented and
// corresponds to no real file.
const LIBRARY = [
  {
    file_name: 'portraits/8f3c1a9d2b7e4f60',
    model_name: 'Golden Hour Portrait',
    folder: 'portraits',
    usage_tips: JSON.stringify({ strength: 0.65, strength_range: '0.5-0.8' }),
  },
  {
    file_name: 'styles/watercolour_wash',
    model_name: 'Watercolour Wash',
    folder: 'styles',
  },
  {
    file_name: 'portraits/another-portrait-blend',
    model_name: 'Another Portrait Blend',
    folder: 'portraits',
  },
];

const PORTRAIT_NAME = 'portraits/8f3c1a9d2b7e4f60';

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const getStackerExtension = () => {
  const extension = registerExtensionMock.mock.calls
    .map(([registered]) => registered)
    .find((registered) => registered?.name === 'LoraManager.LoraStacker');
  if (!extension) {
    throw new Error('Lora Stacker extension not registered');
  }
  return extension;
};

const createStackerNode = async ({ loras = [] } = {}) => {
  const extension = getStackerExtension();
  const nodeType = {
    comfyClass: 'Lora Stacker (LoraManager)',
    prototype: {},
  };
  await extension.beforeRegisterNodeDef(
    nodeType,
    { name: 'Lora Stacker (LoraManager)' },
    {}
  );

  const metadataWidget = {
    name: '__lm_autocomplete_meta_text',
    value: { version: 1, textWidgetName: 'text' },
    options: {},
  };
  const textWidget = { name: 'text', value: '', options: {}, callback: null };
  const lorasWidget = { name: 'loras', value: loras, options: {}, callback: null };

  const node = {
    id: 42,
    comfyClass: 'Lora Stacker (LoraManager)',
    widgets: [metadataWidget, textWidget, lorasWidget],
    // What a saved workflow holds: one value per serializable widget.
    widgets_values: [{ version: 1 }, '', loras],
    mode: 0,
    graph: {},
    addInput: vi.fn(),
    addDOMWidget(name, type, container, options) {
      const widget = {
        name,
        type,
        container,
        options,
        value: '',
        serialize: true,
      };
      node.searchContainer = container;
      node.widgets.push(widget);
      return widget;
    },
  };

  nodeType.prototype.onNodeCreated.call(node);
  document.body.appendChild(node.searchContainer);
  await getAvailableLoras();
  await flush();
  return { node, lorasWidget, textWidget, metadataWidget };
};

const typeAndSelect = async (node, query, key = 'Enter') => {
  const input = node.loraSearchWidget.inputEl;
  input.focus();
  input.value = query;
  input.dispatchEvent(new Event('input'));
  await flush();
  input.dispatchEvent(new KeyboardEvent('keydown', { key }));
  await flush();
  return input;
};

describe('Lora Stacker search-and-add wiring', () => {
  beforeEach(async () => {
    registerExtensionMock.mockClear();
    settingState.nodeLoraNameDisplay = 'File Name';
    fetchApiMock.mockReset();
    fetchApiMock.mockImplementation(async (url) => {
      if (url === '/lm/loras/cycler-list') {
        return { ok: true, json: async () => ({ success: true, loras: LIBRARY }) };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    resetAvailableLorasCache();
    document.body.replaceChildren();
    vi.resetModules();
    await import(STACKER_MODULE);
  });

  it('adds a non-serialized search widget between the text and loras widgets', async () => {
    const { node, lorasWidget, textWidget } = await createStackerNode();

    const names = node.widgets.map((widget) => widget.name);
    expect(names).toEqual(['__lm_autocomplete_meta_text', 'text', 'lora_search', 'loras']);

    const searchWidget = node.widgets.find((widget) => widget.name === 'lora_search');
    expect(searchWidget).toBe(node.loraSearchWidget);
    expect(searchWidget.serialize).toBe(false);
    expect(node.loraSearchWidget.inputEl.value).toBe('');

    // widgets_values keeps its three slots: only serializable widgets are
    // counted, so the text and loras values still resolve.
    expect(
      node.widgets.filter((widget) => widget.serialize !== false).map((widget) => widget.name)
    ).toEqual(['__lm_autocomplete_meta_text', 'text', 'loras']);
    expect(getWidgetSerializedValue(node, 'text')).toBe('');
    expect(getWidgetSerializedValue(node, 'loras')).toBe(lorasWidget.value);
    expect(getWidgetSerializedValue(node, 'text')).not.toBe(textWidget.value === '' ? undefined : null);
  });

  it('appends a selected LoRA and notifies the loras widget callback', async () => {
    const { node, lorasWidget } = await createStackerNode();
    const callback = vi.fn();
    lorasWidget.callback = callback;

    const input = await typeAndSelect(node, 'portrait');

    expect(lorasWidget.value).toHaveLength(1);
    expect(lorasWidget.value[0]).toEqual({
      name: PORTRAIT_NAME,
      strength: '0.65',
      clipStrength: '0.65',
      active: true,
      expanded: false,
      selected: false,
      locked: false,
    });
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith(lorasWidget.value);
    expect(input.value).toBe('');
  });

  it('enables a LoRA already in the list instead of adding it twice', async () => {
    const { node, lorasWidget } = await createStackerNode({
      loras: [{ name: PORTRAIT_NAME, strength: '0.90', clipStrength: '0.80', active: false }],
    });
    const callback = vi.fn();
    lorasWidget.callback = callback;

    await typeAndSelect(node, 'portrait');

    expect(lorasWidget.value).toHaveLength(1);
    expect(lorasWidget.value[0]).toEqual({
      name: PORTRAIT_NAME,
      strength: '0.90',
      clipStrength: '0.80',
      active: true,
    });
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('does not notify when the selected LoRA is already active', async () => {
    const { node, lorasWidget } = await createStackerNode({
      loras: [{ name: PORTRAIT_NAME, strength: '1.00', active: true }],
    });
    const callback = vi.fn();
    lorasWidget.callback = callback;

    await typeAndSelect(node, 'portrait');

    expect(lorasWidget.value).toHaveLength(1);
    expect(callback).not.toHaveBeenCalled();
  });

  it('searches titles and file names when the node label setting shows model names', async () => {
    settingState.nodeLoraNameDisplay = 'Model Name';
    const { node, lorasWidget } = await createStackerNode();
    lorasWidget.callback = vi.fn();

    const input = node.loraSearchWidget.inputEl;
    input.focus();
    input.value = 'wash';
    input.dispatchEvent(new Event('input'));
    await flush();

    const rows = Array.from(document.querySelectorAll('.lm-lora-search-result'));
    expect(rows.map((row) => row.dataset.name)).toEqual(['styles/watercolour_wash']);

    // The same entry by its file name: matching covers both fields, so the row
    // stays reachable whichever name the user happens to remember.
    input.value = 'watercolour_wash';
    input.dispatchEvent(new Event('input'));
    await flush();
    expect(
      Array.from(document.querySelectorAll('.lm-lora-search-result')).map(
        (row) => row.dataset.name
      )
    ).toEqual(['styles/watercolour_wash']);
  });

  it('keeps the textarea path intact after adding from the search field', async () => {
    const { node, lorasWidget, textWidget } = await createStackerNode();
    const callback = vi.fn();
    lorasWidget.callback = callback;

    await typeAndSelect(node, 'portrait');

    // The text widget still drives the loras list (text -> loras merge).
    textWidget.callback(
      `<lora:${PORTRAIT_NAME}:0.65> <lora:styles/watercolour_wash:1.00>`
    );

    expect(lorasWidget.value.map((lora) => lora.name)).toEqual([
      PORTRAIT_NAME,
      'styles/watercolour_wash',
    ]);
    expect(lorasWidget.value.every((lora) => lora.active)).toBe(true);
    // The text widget's own value is untouched by the add path.
    expect(textWidget.value).toBe('');
  });
});
