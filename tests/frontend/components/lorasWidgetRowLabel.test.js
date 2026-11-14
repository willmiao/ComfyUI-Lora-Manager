import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE, QUICK_PANEL_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
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

const { fetchApiMock, openLoraQuickPanelMock } = vi.hoisted(() => ({
  fetchApiMock: vi.fn(),
  openLoraQuickPanelMock: vi.fn(),
}));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock, addEventListener: vi.fn() },
}));
vi.mock(QUICK_PANEL_MODULE, () => ({
  openLoraQuickPanel: openLoraQuickPanelMock,
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
  addLorasWidget(node, 'loras', {
    defaultVal: entries.map((entry) => typeof entry === 'string'
      ? { name: entry, strength: '1.00', active: true }
      : { strength: '1.00', active: true, ...entry }),
  });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

const labels = (node) => [...node.container.querySelectorAll('.lm-lora-name')];

beforeEach(() => {
  openLoraQuickPanelMock.mockReset();
});

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
    expect(node.widget.value).toEqual([
      expect.objectContaining({ name: 'abc123def', strength: '1.00', active: true }),
    ]);
  });

  it('labels rows with the model name when the setting asks for it', async () => {
    settingState.nodeLoraNameDisplay = 'Model Name';
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget(['abc123def']);
    const label = labels(node)[0];
    expect(label.textContent).toBe('Example model title');
    // The resolved file name stays reachable; the widget value keeps it too.
    expect(label.dataset.loraFileName).toBe('abc123def');
    expect(node.widget.value).toEqual([
      expect.objectContaining({ name: 'abc123def', strength: '1.00', active: true }),
    ]);
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

  it('selects the row when its info button is clicked', async () => {
    respondWith({ loras: [{ file_name: 'one' }, { file_name: 'two' }] });
    const node = await mountWidget(['one', 'two']);
    const infoButtons = node.container.querySelectorAll('.lm-lora-info-button');

    infoButtons[1].click();

    const rows = [...node.container.querySelectorAll('.lm-lora-entry')];
    expect(rows.map((entry) => entry.dataset.selected)).toEqual(['false', 'true']);
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
    expect(all).toEqual([`[v1] ${title}`, `[v2 (variant)] ${title}`]);
    // The widget still stores the file names, so both rows load their own file.
    expect(node.widget.value.map((entry) => entry.name)).toEqual(['set/abc_v1', 'set/abc_v2']);
  });

  it('leaves a unique title unprefixed', async () => {
    respondWith({ loras: [{ file_name: 'set/only', model_name: 'Example sole title' }] });
    const node = await mountWidget(['set/only']);
    expect(labels(node)[0].textContent).toBe('Example sole title');
  });
});

describe('addLorasWidget header and strength controls', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    settingState.nodeLoraNameDisplay = undefined;
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('shows the enabled count and a mixed state while toggling all LoRAs', async () => {
    respondWith({ loras: [{ file_name: 'one' }, { file_name: 'two' }, { file_name: 'three' }] });
    const node = await mountWidget([
      { name: 'one', active: true },
      { name: 'two', active: false },
      { name: 'three', active: true },
    ]);
    const toggleAll = () => node.container.querySelector('.lm-toggle-container .lm-lora-toggle');
    const toggleLabel = () => node.container.querySelector('.lm-toggle-label');

    expect(toggleLabel().textContent).toBe('2/3 on');
    expect(toggleAll().getAttribute('aria-checked')).toBe('mixed');
    expect(toggleAll().classList.contains('lm-lora-toggle--mixed')).toBe(true);
    expect(toggleAll().title).toContain('Click to enable all');

    toggleAll().click();
    expect(node.widget.value.every((entry) => entry.active)).toBe(true);
    expect(toggleLabel().textContent).toBe('3/3 on');
    expect(toggleAll().getAttribute('aria-checked')).toBe('true');
    expect(toggleAll().classList.contains('lm-lora-toggle--mixed')).toBe(false);
    expect(toggleAll().title).toContain('Click to disable all');

    toggleAll().click();
    expect(node.widget.value.every((entry) => !entry.active)).toBe(true);
    expect(toggleLabel().textContent).toBe('0/3 on');
    expect(toggleAll().getAttribute('aria-checked')).toBe('false');
  });

  it('opens the quick picker for the current node without starting header drag', async () => {
    respondWith({ loras: [{ file_name: 'one' }] });
    const node = await mountWidget(['one']);
    const addButton = node.container.querySelector('.lm-lora-add-button');
    const strengthDragHandle = node.container.querySelector('.lm-lora-strength-drag-handle');

    expect(node.container.querySelector('.lm-loras-header').textContent).not.toContain('Strength');
    expect(strengthDragHandle.title).toBe('Drag to scale all strengths');
    expect(addButton.title).toBe('Add LoRA · Quick Picker (Alt+L)');
    addButton.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true,
      button: 0,
      pointerId: 1,
    }));
    expect(node.widget.__dragActive).not.toBe(true);

    addButton.click();
    expect(openLoraQuickPanelMock).toHaveBeenCalledOnce();
    expect(openLoraQuickPanelMock).toHaveBeenCalledWith({ node });
  });

  it('keeps add available in the empty state and disables toggle all', async () => {
    respondWith();
    const node = await mountWidget([]);
    const toggleAll = node.container.querySelector('.lm-toggle-container .lm-lora-toggle');

    expect(node.container.querySelector('.lm-toggle-label').textContent).toBe('0 LoRAs');
    expect(node.container.querySelector('.lm-lora-empty-state')).not.toBeNull();
    expect(node.container.querySelector('.lm-lora-strength-drag-handle')).toBeNull();
    expect(toggleAll.getAttribute('aria-disabled')).toBe('true');
    expect(toggleAll.getAttribute('aria-checked')).toBe('false');
    expect(toggleAll.tabIndex).toBe(-1);

    toggleAll.click();
    expect(node.widget.value).toEqual([]);
    node.container.querySelector('.lm-lora-add-button').click();
    expect(openLoraQuickPanelMock).toHaveBeenCalledWith({ node });
  });

  it('keeps model and CLIP strength controls in the same expanded card', async () => {
    settingState.nodeLoraNameDisplay = 'Model Name';
    respondWith({ loras: [{ file_name: 'set/abc123def', model_name: 'Example model title' }] });
    const node = await mountWidget([{
      name: 'set/abc123def',
      clipStrength: '0.60',
      expanded: true,
    }]);
    const mainRow = node.container.querySelector('.lm-lora-entry');
    const strengthRows = mainRow.querySelectorAll('.lm-lora-strength-row');
    const strengthLabels = mainRow.querySelectorAll('.lm-lora-strength-label');
    const modelInput = mainRow.querySelector('.lm-lora-model-strength-input');
    const clipInput = mainRow.querySelector('.lm-lora-clip-strength-input');

    expect(node.container.querySelectorAll('.lm-lora-entry')).toHaveLength(1);
    expect(node.container.querySelector('.lm-lora-clip-entry')).toBeNull();
    expect(mainRow.classList.contains('lm-lora-entry--expanded')).toBe(true);
    expect(strengthRows).toHaveLength(2);
    expect([...strengthLabels].map((label) => label.textContent)).toEqual(['M', 'C']);
    expect(strengthLabels[0].title).toBe('Model strength: Example model title');
    expect(strengthLabels[1].title).toBe('CLIP strength: Example model title');
    expect(modelInput.value).toBe('1.00');
    expect(clipInput.value).toBe('0.60');
    expect(modelInput.getAttribute('aria-label')).toBe('Model strength: Example model title');
    expect(clipInput.getAttribute('aria-label')).toBe('CLIP strength: Example model title');

    mainRow.querySelector('.lm-lora-info-button').click();
    expect(mainRow.dataset.selected).toBe('true');
    mainRow.click();
    expect(mainRow.dataset.selected).toBe('false');
  });

  it('drags CLIP strength without also changing model strength', async () => {
    respondWith({ loras: [{ file_name: 'one' }] });
    const node = await mountWidget([{
      name: 'one',
      strength: '1.00',
      clipStrength: '0.60',
      expanded: true,
    }]);
    const mainRow = node.container.querySelector('.lm-lora-entry');
    const clipLabel = [...mainRow.querySelectorAll('.lm-lora-strength-label')]
      .find((label) => label.textContent === 'C');

    clipLabel.dispatchEvent(new PointerEvent('pointerdown', {
      clientX: 100,
      bubbles: true,
      button: 0,
      pointerId: 12,
    }));
    clipLabel.dispatchEvent(new PointerEvent('pointermove', {
      clientX: 140,
      bubbles: true,
      pointerId: 12,
    }));
    clipLabel.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true,
      pointerId: 12,
    }));

    expect(Number(node.widget.value[0].strength)).toBe(1);
    expect(Number(node.widget.value[0].clipStrength)).toBeCloseTo(0.64, 2);
  });

  it('keeps a collapsed LoRA on one unlabeled strength control', async () => {
    respondWith({ loras: [{ file_name: 'one' }] });
    const node = await mountWidget(['one']);
    const mainRow = node.container.querySelector('.lm-lora-entry');

    expect(mainRow.querySelectorAll('.lm-lora-strength-row')).toHaveLength(1);
    expect(mainRow.querySelector('.lm-lora-strength-label')).toBeNull();
    expect(mainRow.querySelector('.lm-lora-model-strength-input')).not.toBeNull();
    expect(mainRow.querySelector('.lm-lora-clip-strength-input')).toBeNull();
  });
});
