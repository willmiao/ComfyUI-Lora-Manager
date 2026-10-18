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

// The single-recipe rematch now opens the options dialog first and only
// starts once confirmOptions() is invoked (the user clicking Rematch).
async function confirmRematchOptions() {
  const { rematchModalManager } = await import(
    '../../../static/js/managers/RematchModalManager.js'
  );
  return rematchModalManager.confirmOptions();
}

async function cancelRematchOptions() {
  const { rematchModalManager } = await import(
    '../../../static/js/managers/RematchModalManager.js'
  );
  rematchModalManager.cancelOptions();
}

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
  // mirror would render 0 matched entries in the summary modal here.
  it('posts to the per-recipe rematch endpoint and opens the summary modal', async () => {
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

    // The click only opened the options dialog — nothing started yet.
    expect(global.fetch).not.toHaveBeenCalled();

    await confirmRematchOptions();
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenNthCalledWith(1, '/api/lm/recipe/recipe-1/rematch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ relaxed: false }),
    });
    // Non-noop runs open the summary modal instead of toasting.
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchComplete',
      expect.anything(),
      expect.anything()
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.rematchSkipped',
      expect.anything(),
      expect.anything()
    );
    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    expect(summaryModal.querySelector('.summary-header').classList.contains('success')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-success .stat-card-value').textContent).toBe('2');
    expect(summaryModal.querySelector('.stat-card-failure .stat-card-value').textContent).toBe('0');
    expect(global.fetch).toHaveBeenNthCalledWith(2, '/api/lm/recipe/recipe-1');
    expect(updateSingleItemMock).toHaveBeenCalledWith('/recipes/recipe-1.webp', {
      id: 'recipe-1',
      title: 'Updated Recipe',
    });
  });

  it('opens the summary modal when the entries had no local match', async () => {
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
    await confirmRematchOptions();
    await flushAsyncTasks();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-success .stat-card-value').textContent).toBe('0');
    expect(summaryModal.querySelector('.stat-card-total .stat-card-value').textContent).toBe('2');
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
    await confirmRematchOptions();
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
    await confirmRematchOptions();
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
    await confirmRematchOptions();
    await flushAsyncTasks();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.rematchFailed',
      { message: 'network down' },
      'error'
    );
  });

  it('sends relaxed: true when the relaxed checkbox is checked', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    document.body.insertAdjacentHTML(
      'beforeend',
      '<input type="checkbox" id="rematchOptionsRelaxed">'
    );

    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, rematched: 0, skipped: 1 }),
    });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();

    // The dialog resets the checkbox to unchecked on open; the user opts in.
    document.getElementById('rematchOptionsRelaxed').checked = true;
    await confirmRematchOptions();
    await flushAsyncTasks();

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe-1/rematch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ relaxed: true }),
    });
  });

  it('starts nothing when the options dialog is cancelled', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();
    await cancelRematchOptions();
    await flushAsyncTasks();

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('lists L4 filename matches in the summary modal with undo buttons', async () => {
    const menu = await createMenu();
    const card = document.getElementById('card');
    menu.showMenu(100, 100, card);

    const l4Matches = [
      { recipe_id: 'recipe-1', type: 'lora', entry: 'old.safetensors', file_name: 'new.safetensors', lora_index: 0 },
    ];
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, rematched: 1, matched_entries: 1, l4_matches: l4Matches }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 'recipe-1', title: 'Updated Recipe' }),
      });

    document
      .querySelector('[data-action="rematch"]')
      .dispatchEvent(new Event('click', { bubbles: true }));

    await flushAsyncTasks();
    await confirmRematchOptions();
    await flushAsyncTasks();

    const summaryModal = document.getElementById('rematchSummaryModal');
    expect(summaryModal).not.toBeNull();
    // L4 matches to review force the warning header
    expect(summaryModal.querySelector('.summary-header').classList.contains('warning')).toBe(true);
    expect(summaryModal.querySelector('.stat-card-skipped .stat-card-value').textContent).toBe('1');
    const rows = summaryModal.querySelectorAll('tr[data-l4-index]');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('old.safetensors');
    expect(rows[0].textContent).toContain('new.safetensors');
    expect(rows[0].querySelector('.rematch-undo-btn[data-action="undo-match"][data-index="0"]')).not.toBeNull();
  });
});
