import { describe, expect, it, vi } from 'vitest';

const { API_MODULE, fetchApiMock } = vi.hoisted(() => ({
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  fetchApiMock: vi.fn(),
}));
vi.mock(API_MODULE, () => ({ api: { fetchApi: fetchApiMock } }));

describe('LoRA canvas folder API', () => {
  it('normalizes the cached folder tree for Quick Panel rows', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        root: {
          count: 1,
          items: [],
          folders: {
            characters: {
              count: 1,
              folders: {},
              items: [{ relative_path: 'characters/astral.safetensors', model_name: 'Astral' }],
            },
          },
        },
      }),
    });

    const { fetchLoraFolderIndex } = await import('../../../web/comfyui/lora_canvas_api.js');
    const root = await fetchLoraFolderIndex();

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/loras/folder-index');
    expect(root.folders.characters.items[0]).toEqual({
      relativePath: 'characters/astral.safetensors',
      modelName: 'Astral',
    });
  });

  it('carries the license icon style from the details response', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        metadata: { model_name: 'Astral' },
        use_new_license_icons: false,
      }),
    });

    const { fetchLoraDetails } = await import('../../../web/comfyui/lora_canvas_api.js');
    const details = await fetchLoraDetails('astral');

    expect(details).toEqual({ model_name: 'Astral', use_new_license_icons: false });
  });

  it('reuses the named manager tab for full details', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openLoraManager } = await import('../../../web/comfyui/lora_canvas_api.js');
      openLoraManager('/models/astral.safetensors');

      expect(openMock).toHaveBeenCalledWith(
        `${window.location.origin}/loras#model=%2Fmodels%2Fastral.safetensors`,
        'lm-lora-manager',
      );
    } finally {
      openMock.mockRestore();
    }
  });

  it('opens the full manager in a new tab from the top button', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openLoraManagerHome } = await import('../../../web/comfyui/lora_canvas_api.js');
      openLoraManagerHome();

      expect(openMock).toHaveBeenCalledWith(`${window.location.origin}/loras`, '_blank');
    } finally {
      openMock.mockRestore();
    }
  });

  it('opens a new window from the top button when requested', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openLoraManagerHome } = await import('../../../web/comfyui/lora_canvas_api.js');
      openLoraManagerHome(true);

      expect(openMock).toHaveBeenCalledWith(
        `${window.location.origin}/loras`,
        '_blank',
        'width=1200,height=800,resizable=yes,scrollbars=yes,status=yes',
      );
    } finally {
      openMock.mockRestore();
    }
  });

  it('can still force a separate manager window', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openLoraManager } = await import('../../../web/comfyui/lora_canvas_api.js');
      openLoraManager('', true);

      expect(openMock).toHaveBeenCalledWith(
        `${window.location.origin}/loras`,
        '_blank',
        'width=1200,height=800,resizable=yes,scrollbars=yes,status=yes',
      );
    } finally {
      openMock.mockRestore();
    }
  });
});

describe('LoRA canvas active filters', () => {
  it('adds the active-filters flag to searches on demand', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, items: [] }),
    });
    const { searchLoraLibrary } = await import('../../../web/comfyui/lora_canvas_api.js');

    await searchLoraLibrary('astral', 30);
    expect(fetchApiMock.mock.calls.at(-1)[0]).not.toContain('use_active_filters');

    await searchLoraLibrary('astral', 30, { useActiveFilters: true });
    const url = fetchApiMock.mock.calls.at(-1)[0];
    expect(url).toContain('use_active_filters=true');
    expect(url).toContain('search=astral');
    expect(url).toContain('limit=30');
  });

  it('requests a filtered folder index when asked', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, root: { count: 0, folders: {}, items: [] } }),
    });
    const { fetchLoraFolderIndex } = await import('../../../web/comfyui/lora_canvas_api.js');

    await fetchLoraFolderIndex();
    expect(fetchApiMock.mock.calls.at(-1)[0]).toBe('/lm/loras/folder-index');

    await fetchLoraFolderIndex({ useActiveFilters: true });
    expect(fetchApiMock.mock.calls.at(-1)[0]).toBe(
      '/lm/loras/folder-index?use_active_filters=true',
    );
  });

  it('reads the stored active-filter snapshot', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, filters: { activeFolder: 'characters' } }),
    });
    const { fetchActiveFilters } = await import('../../../web/comfyui/lora_canvas_api.js');

    const snapshot = await fetchActiveFilters();

    expect(fetchApiMock.mock.calls.at(-1)[0]).toBe('/lm/loras/active-filters');
    expect(snapshot).toEqual({ activeFolder: 'characters' });
  });

  it('counts filters the same way the manager page badge does', async () => {
    const { countActiveFilters } = await import('../../../web/comfyui/lora_canvas_api.js');

    expect(countActiveFilters(null)).toBe(0);
    expect(countActiveFilters({ activeFolder: null, recursiveSearch: true, filters: null })).toBe(0);
    expect(countActiveFilters({ activeFolder: null, recursiveSearch: false, filters: null })).toBe(1);
    expect(
      countActiveFilters({
        activeFolder: 'characters',
        recursiveSearch: true,
        filters: {
          baseModel: ['Flux', '__EMPTY_WILDCARD_RESULT__'],
          tags: { anime: 'include', style: 'exclude' },
          autoTags: { character: 'include' },
          modelTypes: ['LoCon'],
          license: { noCredit: 'include' },
        },
      }),
    ).toBe(7);
  });
});
