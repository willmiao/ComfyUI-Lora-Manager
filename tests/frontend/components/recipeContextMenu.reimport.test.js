import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const showSimpleLoadingMock = vi.fn();
const hideLoadingMock = vi.fn();
const resetAndReloadMock = vi.fn();
const probeExtensionMock = vi.fn();
const delegateReimportMock = vi.fn();

const stateStub = {
  virtualScroller: { items: [] },
  loadingManager: {
    showSimpleLoading: showSimpleLoadingMock,
    hide: hideLoadingMock,
  },
};

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  setSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  updateRecipeMetadata: vi.fn(),
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { showMoveModal: vi.fn() },
}));

vi.mock('../../../static/js/components/ContextMenu/ModelContextMenuMixin.js', () => ({
  ModelContextMenuMixin: {
    handleCommonMenuActions: vi.fn(() => false),
    initNSFWSelector: vi.fn(),
  },
}));

// Keep the real getCivitaiImageInfo (gating logic under test); mock only the
// extension communication.
vi.mock('../../../static/js/utils/extensionReimportBridge.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    probeExtension: probeExtensionMock,
    delegateReimport: delegateReimportMock,
  };
});

describe('RecipeContextMenu.reimportRecipe extension delegation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <div id="recipeContextMenu" class="context-menu" style="display: none;">
        <div class="context-menu-item" data-action="reimport"></div>
      </div>
    `;
    stateStub.virtualScroller.items = [
      {
        id: 'recipe-1',
        file_path: '/recipes/recipe-1.webp',
        title: 'Civitai Recipe',
        source_path: 'https://civitai.com/images/12345',
      },
      {
        id: 'recipe-2',
        file_path: '/recipes/recipe-2.webp',
        title: 'Local Recipe',
        source_path: '/data/imports/local.png',
      },
    ];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, recipe_id: 'new-id', loras_count: 2 }),
    });
  });

  afterEach(() => {
    delete global.fetch;
  });

  async function createMenu() {
    const { RecipeContextMenu } = await import(
      '../../../static/js/components/ContextMenu/RecipeContextMenu.js'
    );
    return new RecipeContextMenu();
  }

  it('delegates to the extension for a CivitAI image source when licensed', async () => {
    probeExtensionMock.mockResolvedValue({ supported: true, licenseValid: true });
    delegateReimportMock.mockResolvedValue({ completed: 1, failed: 0 });

    const menu = await createMenu();
    await menu.reimportRecipe('recipe-1');

    expect(delegateReimportMock).toHaveBeenCalledWith([{
      recipeId: 'recipe-1',
      imageId: 12345,
      imageUrl: 'https://civitai.com/images/12345',
      title: 'Civitai Recipe',
    }]);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.reimportSuccess', {}, 'success');
    expect(resetAndReloadMock).toHaveBeenCalledWith(false, { preserveScroll: false });
  });

  it('shows the failure toast when the extension reports failures', async () => {
    probeExtensionMock.mockResolvedValue({ supported: true, licenseValid: true });
    delegateReimportMock.mockResolvedValue({ completed: 0, failed: 1 });

    const menu = await createMenu();
    await menu.reimportRecipe('recipe-1');

    expect(showToastMock).toHaveBeenCalledWith(
      'recipes.contextMenu.reimport.failed',
      { message: 'Extension re-import failed' },
      'error'
    );
    expect(global.fetch).not.toHaveBeenCalled();
    expect(resetAndReloadMock).toHaveBeenCalledWith(false, { preserveScroll: false });
  });

  it('uses the native path for non-CivitAI sources without probing', async () => {
    const menu = await createMenu();
    await menu.reimportRecipe('recipe-2');

    expect(probeExtensionMock).not.toHaveBeenCalled();
    expect(delegateReimportMock).not.toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-2/reimport', {
      method: 'POST',
    });
    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.reimportSuccess', {}, 'success');
  });

  it('uses the native path when the extension is absent (probe timeout)', async () => {
    probeExtensionMock.mockResolvedValue(null);

    const menu = await createMenu();
    await menu.reimportRecipe('recipe-1');

    expect(delegateReimportMock).not.toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/reimport', {
      method: 'POST',
    });
  });

  it('uses the native path when the license is invalid', async () => {
    probeExtensionMock.mockResolvedValue({ supported: true, licenseValid: false });

    const menu = await createMenu();
    await menu.reimportRecipe('recipe-1');

    expect(delegateReimportMock).not.toHaveBeenCalled();
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/reimport', {
      method: 'POST',
    });
  });

  it('falls back to the native path when delegation fails', async () => {
    probeExtensionMock.mockResolvedValue({ supported: true, licenseValid: true });
    delegateReimportMock.mockRejectedValue(new Error('Extension re-import timed out'));

    const menu = await createMenu();
    await menu.reimportRecipe('recipe-1');

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/reimport', {
      method: 'POST',
    });
    expect(showToastMock).toHaveBeenCalledWith('toast.recipes.reimportSuccess', {}, 'success');
  });
});
