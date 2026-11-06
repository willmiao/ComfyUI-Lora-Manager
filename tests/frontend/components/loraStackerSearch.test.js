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

vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import {
  addLoraSearchWidget,
  applyLoraSelection,
  filterLoraCandidates,
  getLoraSearchField,
} from '../../../web/comfyui/lora_stacker_search.js';
import {
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

// Synthetic catalogue: every folder, file name and title below is invented and
// corresponds to no real file. The fixtures keep one property that matters for
// the tests: a title that appears nowhere in its file name.
const LIBRARY = [
  {
    file_name: 'portraits/8f3c1a9d2b7e4f60',
    model_name: 'Golden Hour Portrait',
    folder: 'portraits',
    usage_tips: JSON.stringify({ strength: 0.65 }),
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

const respondWithLibrary = () => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras: LIBRARY }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const mountSearch = async ({ displayMode = 'file_name', onSelect = vi.fn() } = {}) => {
  const state = { displayMode };
  const node = {
    id: 11,
    widgets: [],
    addDOMWidget(name, type, container, options) {
      const widget = {
        name,
        type,
        container,
        options,
        value: '',
        serialize: true,
        computeSize: undefined,
      };
      node.container = container;
      node.widget = widget;
      node.widgets.push(widget);
      return widget;
    },
  };
  const widget = addLoraSearchWidget(node, {
    onSelect,
    getDisplayMode: () => state.displayMode,
  });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await flush();
  const input = widget.inputEl;
  return { node, widget, input, state, onSelect };
};

const typeQuery = async (input, query) => {
  input.focus();
  input.value = query;
  input.dispatchEvent(new Event('input'));
  await flush();
};

const resultRows = () =>
  Array.from(document.querySelectorAll('.lm-lora-search-result'));
const resultLabels = () =>
  resultRows().map((row) => row.querySelector('.lm-lora-search-result-label').textContent);

const entry = (name, label, strength = null) => ({ name, label, strength });

describe('getLoraSearchField', () => {
  it('returns the title in model-name mode and the file name otherwise', () => {
    const candidate = entry('portraits/8f3c1a9d2b7e4f60', 'Golden Hour Portrait');
    expect(getLoraSearchField(candidate, 'model_name')).toBe('Golden Hour Portrait');
    expect(getLoraSearchField(candidate, 'file_name')).toBe('portraits/8f3c1a9d2b7e4f60');
  });

  it('falls back to the file name when the library has no title', () => {
    const candidate = entry('folder/untitled', '');
    expect(getLoraSearchField(candidate, 'model_name')).toBe('folder/untitled');
  });
});

describe('filterLoraCandidates', () => {
  const candidates = [
    entry('portraits/8f3c1a9d2b7e4f60', 'Golden Hour Portrait'),
    entry('styles/watercolour_wash', 'Watercolour Wash'),
    entry('portraits/another-portrait-blend', 'Another Portrait Blend'),
    entry('portraits/portrait-studio', 'Portrait Studio Light'),
  ];

  it('matches titles in model-name mode', () => {
    expect(filterLoraCandidates(candidates, 'golden', 'model_name')).toHaveLength(1);
    expect(filterLoraCandidates(candidates, 'golden', 'model_name')[0].name).toBe(
      'portraits/8f3c1a9d2b7e4f60'
    );
  });

  it('does not match a title in file-name mode', () => {
    expect(filterLoraCandidates(candidates, 'golden', 'file_name')).toEqual([]);
  });

  it('matches file names in file-name mode and not in model-name mode', () => {
    expect(filterLoraCandidates(candidates, '8f3c1a9d', 'file_name')).toHaveLength(1);
    expect(filterLoraCandidates(candidates, '8f3c1a9d', 'model_name')).toEqual([]);
  });

  it('is case-insensitive and substring-based', () => {
    expect(filterLoraCandidates(candidates, 'PORTRAIT', 'model_name')).toHaveLength(3);
    expect(filterLoraCandidates(candidates, 'atercol', 'model_name')).toHaveLength(1);
  });

  it('requires every whitespace separated token to match', () => {
    expect(filterLoraCandidates(candidates, 'portrait blend', 'model_name')).toHaveLength(1);
    expect(filterLoraCandidates(candidates, 'portrait wash', 'model_name')).toEqual([]);
  });

  it('ranks prefix matches above later substring matches', () => {
    const ranked = filterLoraCandidates(candidates, 'portrait', 'model_name');
    expect(ranked.map((candidate) => candidate.label)).toEqual([
      'Portrait Studio Light',
      'Another Portrait Blend',
      'Golden Hour Portrait',
    ]);
  });

  it('returns nothing for an empty query', () => {
    expect(filterLoraCandidates(candidates, '   ', 'model_name')).toEqual([]);
  });
});

describe('applyLoraSelection', () => {
  it('appends a new LoRA active, using the recommended strength', () => {
    const { loras, changed } = applyLoraSelection([], {
      name: 'portraits/8f3c1a9d2b7e4f60.safetensors',
      strength: 0.65,
    });
    expect(changed).toBe(true);
    expect(loras).toEqual([
      {
        name: 'portraits/8f3c1a9d2b7e4f60',
        strength: '0.65',
        clipStrength: '0.65',
        active: true,
        expanded: false,
        selected: false,
        locked: false,
      },
    ]);
  });

  it('defaults to 1.00 when the library has no recommended strength', () => {
    const { loras } = applyLoraSelection([], { name: 'folder/new', strength: null });
    expect(loras[0].strength).toBe('1.00');
    expect(loras[0].clipStrength).toBe('1.00');
  });

  it('enables an existing LoRA in place instead of duplicating it', () => {
    const current = [
      { name: 'folder/a', strength: '0.80', clipStrength: '0.70', active: false },
      { name: 'folder/b', strength: '1.00', active: true },
    ];
    const { loras, changed } = applyLoraSelection(current, {
      name: 'folder/a.safetensors',
    });
    expect(changed).toBe(true);
    expect(loras).toHaveLength(2);
    expect(loras[0]).toEqual({
      name: 'folder/a',
      strength: '0.80',
      clipStrength: '0.70',
      active: true,
    });
    expect(loras[1]).toBe(current[1]);
  });

  it('matches a legacy entry stored without its folder', () => {
    const current = [{ name: '8f3c1a9d2b7e4f60', strength: '1.00', active: false }];
    const { loras, changed } = applyLoraSelection(current, {
      name: 'portraits/8f3c1a9d2b7e4f60',
    });
    expect(changed).toBe(true);
    expect(loras).toHaveLength(1);
    expect(loras[0].active).toBe(true);
  });

  it('treats the same file name in different folders as a different LoRA', () => {
    const current = [{ name: 'other/same', strength: '1.00', active: false }];
    const { loras } = applyLoraSelection(current, { name: 'folder/same' });
    expect(loras).toHaveLength(2);
    expect(loras[1].name).toBe('folder/same');
  });

  it('reports no change when the LoRA is already active', () => {
    const current = [{ name: 'folder/a', strength: '1.00', active: true }];
    const { loras, changed } = applyLoraSelection(current, { name: 'folder/a' });
    expect(changed).toBe(false);
    expect(loras).toBe(current);
  });
});

describe('addLoraSearchWidget', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    respondWithLibrary();
    resetAvailableLorasCache();
    document.body.replaceChildren();
  });

  it('creates a non-serialized widget with an empty, typable input', async () => {
    const { node, widget, input } = await mountSearch();

    expect(node.widgets).toContain(widget);
    expect(widget.serialize).toBe(false);
    expect(widget.options.hideInPanel).toBe(true);
    expect(widget.computeSize()[1]).toBeGreaterThan(0);
    expect(input.value).toBe('');
    expect(input.placeholder).toMatch(/Search LoRAs to add/);
    expect(node.container.classList.contains('lm-lora-search')).toBe(true);
  });

  it('shows matching LoRAs as the user types, by file name in file-name mode', async () => {
    const { input } = await mountSearch({ displayMode: 'file_name' });

    await typeQuery(input, 'portrait');

    // Both names start with the query; the shorter one ranks first, as the
    // backend's own relative-path ranking does.
    expect(resultLabels()).toEqual([
      'portraits/8f3c1a9d2b7e4f60',
      'portraits/another-portrait-blend',
    ]);
  });

  it('matches titles in model-name mode', async () => {
    const { input } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'wash');
    expect(resultLabels()).toEqual(['Watercolour Wash']);

    await typeQuery(input, 'watercolour_wash');
    expect(resultLabels()).toEqual([]);
  });

  it('follows a display mode change without rebuilding the widget', async () => {
    const { input, state } = await mountSearch({ displayMode: 'file_name' });

    await typeQuery(input, 'golden');
    expect(resultLabels()).toEqual([]);

    state.displayMode = 'model_name';
    await typeQuery(input, 'golden');
    expect(resultLabels()).toEqual(['Golden Hour Portrait']);
  });

  it('adds the highlighted match on Enter and clears the field', async () => {
    const { input, onSelect } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'wash');
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await flush();

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].name).toBe('styles/watercolour_wash');
    expect(input.value).toBe('');
    expect(resultRows()).toHaveLength(0);
  });

  it('moves the highlight with the arrow keys before Enter', async () => {
    const { input, onSelect } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'portrait');
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    expect(resultRows()[0].dataset.active).toBe('true');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));
    expect(resultRows()[1].dataset.active).toBe('true');
    expect(resultRows()[0].dataset.active).toBe('false');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    await flush();

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].label).toBe('Golden Hour Portrait');
  });

  it('selects a match on click', async () => {
    const { input, onSelect } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'wash');
    const [row] = resultRows();
    row.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    await flush();

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].name).toBe('styles/watercolour_wash');
    expect(input.value).toBe('');
  });

  it('clears and closes on Escape', async () => {
    const { input, onSelect } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'portrait');
    expect(resultRows().length).toBeGreaterThan(0);

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await flush();

    expect(input.value).toBe('');
    expect(resultRows()).toHaveLength(0);
    expect(document.querySelector('.lm-lora-search-results.is-open')).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('starts empty again after the field loses focus', async () => {
    const { input } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'portrait');
    expect(input.value).toBe('portrait');

    input.blur();
    await flush();
    input.focus();
    await flush();

    expect(input.value).toBe('');
  });

  it('removes its popover when the node is removed', async () => {
    const { widget, input } = await mountSearch({ displayMode: 'model_name' });

    await typeQuery(input, 'portrait');
    widget.onRemove();
    await flush();

    expect(document.querySelector('.lm-lora-search-results')).toBeNull();
  });
});
