import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  UTILS_MODULE,
  LORA_UTILS_MODULE,
  LORA_CANVAS_API_MODULE,
  RECIPE_CANVAS_API_MODULE,
  STYLES_MODULE,
  QUICK_PANEL_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../web/comfyui/utils.js', import.meta.url).pathname,
  LORA_UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url).pathname,
  LORA_CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  RECIPE_CANVAS_API_MODULE: new URL('../../../web/comfyui/recipe_canvas_api.js', import.meta.url).pathname,
  STYLES_MODULE: new URL('../../../web/comfyui/lm_styles_loader.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
}));

const { appMock, loraApiMocks, recipeApiMocks } = vi.hoisted(() => ({
  appMock: {
    registerExtension: vi.fn(),
    graph: { setDirtyCanvas: vi.fn() },
    canvas: { selected_nodes: {} },
  },
  loraApiMocks: {
    searchLoraLibrary: vi.fn(),
    fetchLoraDetails: vi.fn(),
    fetchLoraFolderIndex: vi.fn(),
    fetchActiveFilters: vi.fn(),
    countActiveFilters: vi.fn(),
    openLoraManager: vi.fn(),
    recommendedStrength: vi.fn(() => undefined),
  },
  recipeApiMocks: {
    searchRecipes: vi.fn(),
    fetchRecipeDetails: vi.fn(),
    openRecipeManager: vi.fn(),
  },
}));

let graphNodes = [];

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(UTILS_MODULE, () => ({
  LORA_PATTERN: /<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>/,
  getAllGraphNodes: () => graphNodes.map((node) => ({ graph: appMock.graph, node })),
  getWidgetByName: (node, name) => name === 'loras' ? node.lorasWidget : null,
}));
vi.mock(LORA_UTILS_MODULE, () => ({
  normalizeLoraNameKey: (name) => String(name || '').replace(/\\/g, '/').replace(/\.(safetensors|ckpt|pt|bin)$/i, ''),
}));
vi.mock(LORA_CANVAS_API_MODULE, () => loraApiMocks);
vi.mock(RECIPE_CANVAS_API_MODULE, () => recipeApiMocks);
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));

function makeNode() {
  return {
    id: 7,
    title: 'Character Loader',
    lorasWidget: {
      value: [],
      callback: vi.fn(),
    },
    setDirtyCanvas: vi.fn(),
  };
}

const astral = {
  name: 'characters/astral',
  label: 'Astral Portrait',
  strength: 0.7,
  status: 'ready',
  inLibrary: true,
};
const missing = {
  name: 'characters/missing',
  label: 'Missing LoRA',
  strength: 0.5,
  status: 'missing',
  inLibrary: false,
};

function makeRecipe(id = 'a', overrides = {}) {
  const loras = overrides.loras || [astral, missing];
  const counts = { ready: 0, missing: 0, deleted: 0 };
  for (const lora of loras) counts[lora.status] += 1;
  return {
    id,
    title: id === 'a' ? 'Cyberpunk portrait' : 'Soft light portrait',
    fileUrl: `/previews/${id}.png`,
    baseModel: 'Flux',
    favorite: id === 'a',
    loras,
    loraCount: loras.length,
    ready: counts.ready,
    missing: counts.missing,
    deleted: counts.deleted,
    ...overrides,
  };
}

async function flush() {
  for (let index = 0; index < 10; index += 1) {
    await Promise.resolve();
  }
}

describe('Recipe quick panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    graphNodes = [];
    localStorage.removeItem('lm:quick-panel:asset-view');
    vi.clearAllMocks();
    loraApiMocks.searchLoraLibrary.mockResolvedValue([
      { relativePath: 'characters/astral.safetensors', modelName: 'Astral Portrait' },
    ]);
    loraApiMocks.fetchLoraFolderIndex.mockResolvedValue({
      count: 1,
      folders: {},
      items: [{ relativePath: 'characters/astral.safetensors', modelName: 'Astral Portrait' }],
    });
    loraApiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      base_model: 'Flux',
      file_path: '/models/characters/astral.safetensors',
    });
    loraApiMocks.fetchActiveFilters.mockResolvedValue(null);
    loraApiMocks.countActiveFilters.mockReturnValue(0);

    recipeApiMocks.searchRecipes.mockResolvedValue([
      makeRecipe('a'),
      makeRecipe('b', { loras: [astral], favorite: false }),
    ]);
    recipeApiMocks.fetchRecipeDetails.mockImplementation(async (id) => (
      id === 'a' ? makeRecipe('a') : makeRecipe('b', { loras: [astral], favorite: false })
    ));
  });

  afterEach(async () => {
    const { closeQuickPanel } = await import(QUICK_PANEL_MODULE);
    closeQuickPanel();
  });

  it('opens in the Recipes view and renders rows, detail and actions', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];
    const quick = new LoraQuickPanel({ node: graphNodes[0], initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    expect(quick.assetView).toBe('recipe');
    expect(quick.panel.titleElement.textContent).toContain('Recipe');
    expect(quick.assetTabs.recipe.classList.contains('is-active')).toBe(true);
    expect(quick.resultsElement.querySelectorAll('.lm-quick__recipe-row')).toHaveLength(2);

    const firstRow = quick.resultsElement.querySelector('.lm-quick__recipe-row');
    expect(firstRow.textContent).toContain('Cyberpunk portrait');
    expect(firstRow.textContent).toContain('2 LoRAs · Flux');
    expect(firstRow.textContent).toContain('1 missing');
    expect(firstRow.querySelector('.lm-quick__recipe-thumb')).not.toBeNull();

    expect(quick.detailElement.textContent).toContain('Cyberpunk portrait');
    expect(quick.detailElement.textContent).toContain('Astral Portrait');
    expect(quick.detailElement.textContent).toContain('0.70');
    expect(quick.detailElement.querySelector('.lm-quick__recipe-lora.is-missing')).not.toBeNull();
    expect(quick.detailElement.textContent).toContain('1 missing will be skipped');
    const buttons = [...quick.detailElement.querySelectorAll('.lm-quick__actions button')];
    expect(buttons.map((button) => button.textContent)).toEqual([
      'Append',
      'Replace',
      'Open in manager',
    ]);
  });

  it('appends the available recipe LoRAs and skips missing entries', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node, initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    quick.applyRecipe('append', true);

    expect(node.lorasWidget.value).toHaveLength(1);
    expect(node.lorasWidget.value[0]).toMatchObject({
      name: 'characters/astral',
      strength: '0.70',
      active: true,
    });
    expect(quick.statusElement.textContent).toContain('Applied 1 LoRA');
    expect(quick.statusElement.textContent).toContain('1 skipped');
    expect(quick.panel.isOpen()).toBe(true);
  });

  it('replaces the node list with the available recipe entries', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    node.lorasWidget.value = [{ name: 'old/one', strength: '0.20', clipStrength: '0.20', active: true }];
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node, initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    quick.applyRecipe('replace', true);

    expect(node.lorasWidget.value.map((lora) => lora.name)).toEqual(['characters/astral']);
    expect(node.lorasWidget.value[0].strength).toBe('0.70');
    expect(quick.statusElement.textContent).toContain('Replaced with 1 LoRA');
    expect(quick.statusElement.textContent).toContain('1 skipped');
  });

  it('disables apply actions when there is no target node', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const quick = new LoraQuickPanel({ initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    const buttons = [...quick.detailElement.querySelectorAll('.lm-quick__actions button')];
    expect(buttons[0].disabled).toBe(true);
    expect(buttons[1].disabled).toBe(true);
    expect(quick.detailElement.textContent).toContain('No compatible LoRA node');

    quick.applyRecipe('append');
    expect(quick.statusElement.textContent).toContain('Select a LoRA node');
  });

  it('switches between LoRAs and Recipes in place and keeps the target', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node }).open();
    await quick.loadFolderIndex();
    await quick.loadSearch();
    await flush();
    expect(quick.assetView).toBe('lora');

    quick.assetTabs.recipe.click();
    await flush();

    expect(quick.assetView).toBe('recipe');
    expect(quick.targetNode).toBe(node);
    expect(quick.panel.titleElement.textContent).toContain('Recipe');
    expect(recipeApiMocks.searchRecipes).toHaveBeenCalled();
    expect(localStorage.getItem('lm:quick-panel:asset-view')).toBe('recipe');

    quick.assetTabs.lora.click();
    await flush();

    expect(quick.assetView).toBe('lora');
    expect(quick.targetNode).toBe(node);
    expect(loraApiMocks.searchLoraLibrary).toHaveBeenCalled();
    expect(quick.resultsElement.querySelector('.lm-quick__recipe-row')).toBeNull();
  });

  it('clears a recipe query on the first Escape and closes on the next', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];
    const quick = new LoraQuickPanel({ node: graphNodes[0], initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();
    quick.loadRecipeSearch = vi.fn();
    quick.searchInput.value = 'cyber';

    quick.searchInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    }));

    expect(quick.searchInput.value).toBe('');
    expect(quick.panel.isOpen()).toBe(true);
    quick.searchInput.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    }));
    expect(quick.panel.isOpen()).toBe(false);
  });

  it('opens the selected recipe in the manager', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];
    const quick = new LoraQuickPanel({ node: graphNodes[0], initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    [...quick.detailElement.querySelectorAll('.lm-quick__actions button')]
      .find((button) => button.textContent === 'Open in manager')
      .click();

    expect(recipeApiMocks.openRecipeManager).toHaveBeenCalledWith('a');
  });

  it('offers the manager from the empty state when no recipes exist', async () => {
    recipeApiMocks.searchRecipes.mockResolvedValue([]);
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];
    const quick = new LoraQuickPanel({ node: graphNodes[0], initialView: 'recipe' }).open();
    await quick.loadRecipeSearch();
    await flush();

    expect(quick.resultsElement.textContent).toContain('No recipes yet');
    const open = [...quick.resultsElement.querySelectorAll('button')]
      .find((button) => button.textContent === 'Open LoRA Manager');
    open.click();
    expect(recipeApiMocks.openRecipeManager).toHaveBeenCalledWith('');
  });

  it('opens the Recipes view through the facade and toggles it closed', async () => {
    const { openRecipeQuickPanel, toggleRecipeQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];

    const quick = openRecipeQuickPanel({ node: graphNodes[0] });
    expect(quick.assetView).toBe('recipe');
    expect(quick.targetNode).toBe(graphNodes[0]);

    await flush();
    toggleRecipeQuickPanel();
    expect(quick.panel.isOpen()).toBe(false);
  });
});
