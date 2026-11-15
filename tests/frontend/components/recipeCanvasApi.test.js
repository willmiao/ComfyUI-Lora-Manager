import { describe, expect, it, vi } from 'vitest';

const { API_MODULE, APP_MODULE, fetchApiMock } = vi.hoisted(() => ({
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  fetchApiMock: vi.fn(),
}));

vi.mock(API_MODULE, () => ({ api: { fetchApi: fetchApiMock } }));
vi.mock(APP_MODULE, () => ({
  app: { registerExtension: vi.fn(), graph: {}, ui: { settings: { settingsById: {} } } },
}));

const listPayload = {
  items: [
    {
      id: 'recipe-1',
      title: 'Cyberpunk portrait',
      file_url: '/loras_static/recipe-1.jpeg',
      base_model: 'Flux',
      favorite: true,
      loras: [
        { file_name: 'characters/astral.safetensors', strength: 0.7, inLibrary: true },
        { file_name: 'characters/missing.safetensors', strength: 0.5, inLibrary: false },
        { file_name: 'characters/deleted.safetensors', strength: 0.6, isDeleted: true },
        { file_name: 'characters/excluded.safetensors', strength: 0.4, inLibrary: true, exclude: true },
      ],
    },
  ],
  total: 1,
};

describe('Recipe canvas API', () => {
  it('searches recipes with the picker search options and normalizes availability', async () => {
    fetchApiMock.mockResolvedValue({ ok: true, json: async () => listPayload });

    const { searchRecipes } = await import('../../../web/comfyui/recipe_canvas_api.js');
    const recipes = await searchRecipes('cyber', 30);

    const [url] = fetchApiMock.mock.calls.at(-1);
    expect(url.startsWith('/lm/recipes?')).toBe(true);
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('page')).toBe('1');
    expect(params.get('page_size')).toBe('30');
    expect(params.get('sort_by')).toBe('date');
    expect(params.get('search')).toBe('cyber');
    expect(params.get('search_title')).toBe('true');
    expect(params.get('search_tags')).toBe('true');
    expect(params.get('search_lora_name')).toBe('true');
    expect(params.get('search_lora_model')).toBe('true');
    expect(params.get('search_prompt')).toBe('true');

    expect(recipes).toHaveLength(1);
    expect(recipes[0]).toMatchObject({
      id: 'recipe-1',
      title: 'Cyberpunk portrait',
      baseModel: 'Flux',
      favorite: true,
      loraCount: 3,
      ready: 1,
      missing: 1,
      deleted: 1,
      fileUrl: '/loras_static/recipe-1.jpeg',
    });
    expect(recipes[0].loras[0]).toMatchObject({
      name: 'characters/astral',
      strength: 0.7,
      status: 'ready',
      inLibrary: true,
    });
  });

  it('loads and normalizes a recipe detail payload', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 'recipe-2',
        title: 'Soft light',
        file_url: '/loras_static/recipe-2.jpeg',
        base_model: 'SDXL',
        loras: [{ file_name: 'styles/film.safetensors', strength: 0.35, inLibrary: true }],
      }),
    });

    const { fetchRecipeDetails } = await import('../../../web/comfyui/recipe_canvas_api.js');
    const recipe = await fetchRecipeDetails('recipe 2');

    expect(fetchApiMock).toHaveBeenLastCalledWith('/lm/recipe/recipe%202');
    expect(recipe).toMatchObject({
      id: 'recipe-2',
      title: 'Soft light',
      baseModel: 'SDXL',
      loraCount: 1,
      ready: 1,
    });
    expect(recipe.loras[0]).toMatchObject({ name: 'styles/film', strength: 0.35 });
  });

  it('rejects a detail request without an id', async () => {
    const { fetchRecipeDetails } = await import('../../../web/comfyui/recipe_canvas_api.js');
    await expect(fetchRecipeDetails('')).rejects.toThrow('Unable to determine recipe ID');
  });

  it('opens the recipe in the named manager tab', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openRecipeManager } = await import('../../../web/comfyui/recipe_canvas_api.js');
      openRecipeManager('recipe/2');

      expect(openMock).toHaveBeenCalledWith(
        `${window.location.origin}/loras/recipes#recipe=recipe%2F2`,
        'lm-lora-manager',
      );
    } finally {
      openMock.mockRestore();
    }
  });

  it('throws the backend error message when the list request fails', async () => {
    fetchApiMock.mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'Recipe scanner unavailable' }),
    });

    const { searchRecipes } = await import('../../../web/comfyui/recipe_canvas_api.js');
    await expect(searchRecipes('')).rejects.toThrow('Recipe scanner unavailable');
  });
});
