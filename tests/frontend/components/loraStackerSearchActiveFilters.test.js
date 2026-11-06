import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

const { settingState } = vi.hoisted(() => ({
  settingState: { activeFilters: false },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: {
        get: (id) =>
          id === 'loramanager.lora_active_filters_autocomplete'
            ? settingState.activeFilters
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
  addLoraSearchWidget,
  filterLoraCandidates,
} from '../../../web/comfyui/lora_stacker_search.js';
import {
  getActiveFilteredLoraEntries,
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

// Synthetic catalogue: every folder, file name and title below is invented and
// corresponds to no real file.
const LIBRARY = [
  {
    file_name: 'portraits/8f3c1a9d2b7e4f60',
    model_name: 'Golden Hour Portrait',
    folder: 'portraits',
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

// What the manager page's active filters leave visible: the portraits folder.
const FILTERED_PATHS = [
  'portraits/8f3c1a9d2b7e4f60.safetensors',
  'portraits/another-portrait-blend.safetensors',
];

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const createSearchNode = () => {
  const node = {
    id: 7,
    widgets: [],
    addDOMWidget(name, type, container) {
      const widget = { name, type, container, value: '', serialize: true };
      node.widgets.push(widget);
      return widget;
    },
  };
  const widget = addLoraSearchWidget(node, {
    onSelect: vi.fn(),
    getDisplayMode: () => 'model_name',
  });
  document.body.appendChild(widget.container);
  return widget;
};

const typeQuery = async (widget, query) => {
  const input = widget.inputEl;
  input.focus();
  input.value = query;
  input.dispatchEvent(new Event('input'));
  await flush();
  await flush();
  await flush();
  return [...document.querySelectorAll('.lm-lora-search-result')].map(
    (row) => row.dataset.name
  );
};

const emptyMessage = () =>
  document.querySelector('.lm-lora-search-empty')?.textContent ?? null;

const relativePathsCalls = () =>
  fetchApiMock.mock.calls
    .map(([url]) => url)
    .filter((url) => String(url).includes('/relative-paths'));

describe('Lora Stacker search field and the active-filters setting', () => {
  beforeEach(() => {
    document.body.replaceChildren();
    settingState.activeFilters = false;
    fetchApiMock.mockReset();
    fetchApiMock.mockImplementation(async (url) => {
      const text = String(url);
      if (text === '/lm/loras/cycler-list') {
        return {
          ok: true,
          json: async () => ({ success: true, loras: LIBRARY }),
        };
      }
      if (text.includes('/relative-paths')) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            relative_paths: FILTERED_PATHS,
          }),
        };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    resetAvailableLorasCache();
  });

  it('offers the whole catalogue when the setting is off', async () => {
    await getAvailableLoras();
    const widget = createSearchNode();

    const names = await typeQuery(widget, 'watercolour');

    expect(names).toEqual(['styles/watercolour_wash']);
    expect(relativePathsCalls()).toEqual([]);
  });

  it('restricts candidates to the active filters when the setting is on', async () => {
    settingState.activeFilters = true;
    await getAvailableLoras();
    const widget = createSearchNode();

    // Filtered out by the page's browse filters, so the field must not offer it.
    expect(await typeQuery(widget, 'watercolour')).toEqual([]);
    expect(emptyMessage()).toBe('No matches');

    // Still inside the filter, so it stays reachable by its title. Ranking is
    // by earliest match, so "Another Portrait Blend" comes first.
    expect(await typeQuery(widget, 'portrait')).toEqual([
      'portraits/another-portrait-blend',
      'portraits/8f3c1a9d2b7e4f60',
    ]);
  });

  it('asks the backend for the filtered subset with the same flag the textarea uses', async () => {
    settingState.activeFilters = true;
    await getAvailableLoras();
    const widget = createSearchNode();

    await typeQuery(widget, 'portrait');

    const calls = relativePathsCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain('use_active_filters=true');
    expect(calls[0]).toContain('limit=100');
    expect(calls[0]).toContain('offset=0');
  });

  it('falls back to the whole catalogue when the filtered lookup fails', async () => {
    settingState.activeFilters = true;
    fetchApiMock.mockImplementation(async (url) => {
      const text = String(url);
      if (text === '/lm/loras/cycler-list') {
        return {
          ok: true,
          json: async () => ({ success: true, loras: LIBRARY }),
        };
      }
      if (text.includes('/relative-paths')) {
        return { ok: false, json: async () => ({ success: false }) };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    await getAvailableLoras();
    const widget = createSearchNode();

    expect(await typeQuery(widget, 'watercolour')).toEqual([
      'styles/watercolour_wash',
    ]);
  });

  it('re-resolves when the setting is flipped while the node is open', async () => {
    await getAvailableLoras();
    const widget = createSearchNode();

    expect(await typeQuery(widget, 'watercolour')).toEqual([
      'styles/watercolour_wash',
    ]);

    settingState.activeFilters = true;
    expect(await typeQuery(widget, 'watercolour')).toEqual([]);

    settingState.activeFilters = false;
    expect(await typeQuery(widget, 'watercolour')).toEqual([
      'styles/watercolour_wash',
    ]);
  });
});

describe('active-filtered catalogue', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('pages through the endpoint because limit is clamped to 100', async () => {
    const firstPage = Array.from(
      { length: 100 },
      (_, index) => `batch/item_${index}.safetensors`
    );
    fetchApiMock.mockImplementation(async (url) => {
      const text = String(url);
      if (text === '/lm/loras/cycler-list') {
        return {
          ok: true,
          json: async () => ({
            success: true,
            loras: [...LIBRARY, { file_name: 'batch/item_99' }],
          }),
        };
      }
      const offset = Number(new URL(text, 'http://localhost').searchParams.get('offset'));
      return {
        ok: true,
        json: async () => ({
          success: true,
          relative_paths: offset === 0 ? firstPage : ['portraits/8f3c1a9d2b7e4f60.safetensors'],
        }),
      };
    });

    await getAvailableLoras();
    const entries = await getActiveFilteredLoraEntries();

    expect(relativePathsCalls()).toHaveLength(2);
    expect(relativePathsCalls()[1]).toContain('offset=100');
    // 101 filtered names, of which the catalogue knows three.
    expect(entries.map((entry) => entry.name).sort()).toEqual([
      'batch/item_99',
      'portraits/8f3c1a9d2b7e4f60',
    ]);
  });

  it('resolves to null instead of an empty list when the request fails', async () => {
    fetchApiMock.mockImplementation(async (url) => {
      const text = String(url);
      if (text === '/lm/loras/cycler-list') {
        return {
          ok: true,
          json: async () => ({ success: true, loras: LIBRARY }),
        };
      }
      return { ok: false, json: async () => ({ success: false }) };
    });

    await getAvailableLoras();
    expect(await getActiveFilteredLoraEntries()).toBeNull();
  });

  it('drops the cached subset when the library changes', async () => {
    fetchApiMock.mockImplementation(async (url) => {
      const text = String(url);
      if (text === '/lm/loras/cycler-list') {
        return {
          ok: true,
          json: async () => ({ success: true, loras: LIBRARY }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          success: true,
          relative_paths: FILTERED_PATHS,
        }),
      };
    });

    await getAvailableLoras();
    await getActiveFilteredLoraEntries();
    expect(relativePathsCalls()).toHaveLength(1);

    // Cached: a second call must not hit the endpoint again.
    await getActiveFilteredLoraEntries();
    expect(relativePathsCalls()).toHaveLength(1);

    resetAvailableLorasCache();
    await getAvailableLoras();
    await getActiveFilteredLoraEntries();
    expect(relativePathsCalls()).toHaveLength(2);
  });
});

describe('filtering is unaffected by the scope', () => {
  it('keeps the AND-over-tokens matching for a given entry list', () => {
    const entries = LIBRARY.map((lora) => ({
      name: lora.file_name,
      label: lora.model_name,
      folder: lora.folder,
      strength: null,
    }));
    expect(
      filterLoraCandidates(entries, 'portrait golden', 'model_name').map(
        (entry) => entry.name
      )
    ).toEqual(['portraits/8f3c1a9d2b7e4f60']);
  });
});
