import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const updateSingleItemMock = vi.fn();
const handleCommonMenuActionsMock = vi.fn(() => false);

const stateStub = {
  virtualScroller: { updateSingleItem: updateSingleItemMock },
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
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { showMoveModal: vi.fn() },
}));

vi.mock('../../../static/js/components/ContextMenu/ModelContextMenuMixin.js', () => ({
  ModelContextMenuMixin: {
    handleCommonMenuActions: handleCommonMenuActionsMock,
    initNSFWSelector: vi.fn(),
  },
}));

const flushAsyncTasks = async (rounds = 5) => {
  for (let i = 0; i < rounds; i++) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
};

describe('RecipeContextMenu.rematchRecipe', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <div id="recipeContextMenu" class="context-menu" style="display: none;">
        <div class="context-menu-item" data-action="rematch"></div>
        <div class="context-menu-item download-missing-item" data-action="download-missing"></div>
      </div>
      <div id="card" class="model-card" data-id="recipe-1" data-filepath="/recipes/recipe-1.webp"></div>
    `;
    global.fetch = vi.fn();
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

  // Oracle R4-F1 pin: branches on `result.rematched > 0` — a blind `repaired`
  // mirror would fire the skipped toast here.
  it('posts to the per-recipe rematch endpoint and toasts the rematched count', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, rematched: 2, skipped: 0, matched_recipes: 1, matched_entries: 2 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'recipe-1', title: 'Updated Recipe' }),
      });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenNthCalledWith(1, '/api/lm/recipe/recipe-1/rematch', {
      method: 'POST',
    });
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      { rematched: 2, skipped: 0, total: 1, entries: 2, recipes: 1, failures: 0 },
      'success'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
    expect(global.fetch).toHaveBeenNthCalledWith(2, '/api/lm/recipe/recipe-1');
    expect(updateSingleItemMock).toHaveBeenCalledWith('/recipes/recipe-1.webp', {
      id: 'recipe-1',
      title: 'Updated Recipe',
    });
  });

  it('toasts an info message when the entries had no local match', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, rematched: 0, skipped: 0, unresolved_recipes: 1, unresolved_entries: 2 }),
    });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchUnmatched',
      { entries: 2, recipes: 1, total: 1 },
      'info'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('toasts the skipped message when nothing was rematched', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, rematched: 0, skipped: 1 }),
    });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      { total: 1 },
      'info'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      expect.anything(),
      expect.anything()
    );
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  // Oracle R4-F2 pin: failure surfaces `result.error` (e.g. the 409 body).
  it('surfaces result.error when the rematch is rejected', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ success: false, error: 'Recipe rematch already in progress' }),
    });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchFailed',
      { message: 'Recipe rematch already in progress' },
      'error'
    );
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it('toasts the failure message when the fetch throws', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    global.fetch.mockRejectedValueOnce(new Error('network down'));

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchFailed',
      { message: 'network down' },
      'error'
    );
  });
});
