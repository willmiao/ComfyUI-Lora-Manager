import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const showActionToastMock = vi.fn();
const handleUndoDeleteMock = vi.fn();
const recreateVirtualScrollMock = vi.fn();
const translateMock = vi.fn((key) => key);

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  showActionToast: showActionToastMock,
}));

vi.mock('../../../static/js/utils/undoHelpers.js', () => ({
  handleUndoDelete: handleUndoDeleteMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
  RecipeCard: class {
    constructor() {
      this.element = document.createElement('div');
    }
  },
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  armDeleteButton: (modalElement) => {
    if (!modalElement) return null;
    const buttons = modalElement.querySelectorAll('.delete-btn');
    buttons.forEach((button) => { button.disabled = true; });
    return setTimeout(() => {
      buttons.forEach((button) => { button.disabled = false; });
    }, 1500);
  },
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  recreateVirtualScroll: recreateVirtualScrollMock,
}));

const { DuplicatesManager } = await import('../../../static/js/components/DuplicatesManager.js');
const { state, getCurrentPageState, setCurrentPageType } = await import('../../../static/js/state/index.js');

function setupDom() {
  document.body.innerHTML = `
    <div id="duplicatesBanner" style="display: block;"></div>
    <div id="recipeGrid"><div class="model-card">stale</div></div>
  `;
  document.body.classList.add('duplicate-mode');
}

describe('DuplicatesManager exitDuplicateMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCurrentPageType('recipes');
    setupDom();
    state.pendingLayoutRecreate = false;
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
  });

  afterEach(() => {
    state.pendingLayoutRecreate = false;
    state.virtualScroller = null;
  });

  it('skips enable() on the old scroller when a layout recreate was deferred', async () => {
    state.pendingLayoutRecreate = true;

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    await manager.exitDuplicateMode();

    expect(state.virtualScroller.enable).not.toHaveBeenCalled();
    expect(recreateVirtualScrollMock).toHaveBeenCalledWith('recipes');
    expect(state.pendingLayoutRecreate).toBe(false);
  });

  it('re-enables the existing scroller when no layout recreate is pending', async () => {
    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    await manager.exitDuplicateMode();

    expect(state.virtualScroller.enable).toHaveBeenCalledTimes(1);
    expect(recreateVirtualScrollMock).not.toHaveBeenCalled();
  });

  it('tolerates a missing scroller on the plain re-enable path', async () => {
    state.virtualScroller = null;

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    await expect(manager.exitDuplicateMode()).resolves.toBeUndefined();

    expect(recreateVirtualScrollMock).not.toHaveBeenCalled();
  });

  it('clears duplicates-mode state and the grid regardless of path', async () => {
    state.pendingLayoutRecreate = true;

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    await manager.exitDuplicateMode();

    expect(manager.inDuplicateMode).toBe(false);
    expect(getCurrentPageState().duplicatesMode).toBe(false);
    expect(document.body.classList.contains('duplicate-mode')).toBe(false);
    expect(document.getElementById('recipeGrid').innerHTML).toBe('');
    expect(document.getElementById('duplicatesBanner').style.display).toBe('none');
  });
});

describe('DuplicatesManager prompt matching toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    setCurrentPageType('recipes');
    setupDom();
    state.pendingLayoutRecreate = false;
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
  });

  afterEach(() => {
    state.pendingLayoutRecreate = false;
    state.virtualScroller = null;
  });

  it('sends include_prompt=1 when the preference is enabled', async () => {
    localStorage.setItem('recipes_duplicates_include_prompt', '1');
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        duplicate_groups: [
          { type: 'fingerprint', key: 'g-1', fingerprint: 'abc:0.8', count: 2, recipes: [{ id: 'r1', modified: 1 }, { id: 'r2', modified: 2 }] },
        ],
      }),
    });

    const manager = new DuplicatesManager({});
    await manager.findDuplicates();

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/lm/recipes/find-duplicates?include_prompt=1');
  });

  it('calls the endpoint without the param when disabled', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, duplicate_groups: [] }),
    });

    const manager = new DuplicatesManager({});
    await manager.findDuplicates();

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/lm/recipes/find-duplicates');
  });

  it('stays in duplicate mode with an empty view when a re-run finds no groups', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, duplicate_groups: [] }),
    });

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    await manager.findDuplicates();

    // The view stays open (with the empty state) so the matching-basis
    // toggle remains reachable — the deadlock fix
    expect(manager.inDuplicateMode).toBe(true);
    expect(manager.duplicateGroups).toEqual([]);
    expect(document.getElementById('duplicatesBanner').style.display).toBe('block');
    expect(document.querySelector('.duplicates-empty-state')).not.toBeNull();
  });

  it('enters the empty duplicates view when the toggle is on but no groups match', async () => {
    localStorage.setItem('recipes_duplicates_include_prompt', '1');
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, duplicate_groups: [] }),
    });

    const manager = new DuplicatesManager({});
    await manager.findDuplicates();

    expect(manager.inDuplicateMode).toBe(true);
    expect(document.getElementById('duplicatesBanner').style.display).toBe('block');
  });

  it('toasts and stays on the library grid when the toggle is off and no groups match', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, duplicate_groups: [] }),
    });

    const manager = new DuplicatesManager({});
    await manager.findDuplicates();

    expect(manager.inDuplicateMode).toBe(false);
    expect(showToastMock).toHaveBeenCalledWith('toast.duplicates.noDuplicatesFound', { type: 'recipes' }, 'info');
  });

  it('renders the matching basis and checkbox from the stored preference', () => {
    document.body.innerHTML = `
      <span id="duplicatesBasis"></span>
      <span id="duplicatesHelpText"></span>
      <input type="checkbox" id="promptMatchInput">
    `;
    localStorage.setItem('recipes_duplicates_include_prompt', '1');

    const manager = new DuplicatesManager({});
    manager.updateBasisDisplay();

    expect(translateMock).toHaveBeenCalledWith('recipes.duplicates.basis.loraComboAndPrompt');
    expect(translateMock).toHaveBeenCalledWith('recipes.duplicates.basis.hintPromptIncluded');
    expect(document.getElementById('promptMatchInput').checked).toBe(true);
  });

  it('shows the lora-combo basis when the preference is disabled', () => {
    document.body.innerHTML = `<span id="duplicatesBasis"></span>`;

    const manager = new DuplicatesManager({});
    manager.updateBasisDisplay();

    expect(translateMock).toHaveBeenCalledWith('recipes.duplicates.basis.loraCombo');
    expect(document.getElementById('duplicatesBasis').textContent).toBe('recipes.duplicates.basis.loraCombo');
  });
});

describe('DuplicatesManager confirmDeleteDuplicates undo flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCurrentPageType('recipes');
    setupDom();
    state.pendingLayoutRecreate = false;
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
    handleUndoDeleteMock.mockResolvedValue(true);
    globalThis.modalManager = { showModal: vi.fn(), closeModal: vi.fn() };
    globalThis.recipeManager = { loadRecipes: vi.fn() };
  });

  afterEach(() => {
    state.pendingLayoutRecreate = false;
    state.virtualScroller = null;
    delete globalThis.modalManager;
    delete globalThis.recipeManager;
    delete globalThis.fetch;
  });

  function mockBulkDelete(payload) {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
  }

  function lastActionToastOptions() {
    const call = showActionToastMock.mock.calls[showActionToastMock.mock.calls.length - 1];
    return call[3];
  }

  it('shows the undo action toast with the batch id and reloads recipes on undo', async () => {
    mockBulkDelete({ success: true, total_deleted: 2, batch_id: 'recipe-batch-1' });

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add('r1');
    manager.selectedForDeletion.add('r2');

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock).toHaveBeenCalledWith(
      'toast.undo.deletedBulk',
      { count: 2 },
      'success',
      expect.objectContaining({
        actionText: 'toast.undo.action',
        onAction: expect.any(Function),
      })
    );
    // The legacy duplicates success toast is replaced, not duplicated
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.duplicates.deleteSuccess',
      expect.anything(),
      expect.anything()
    );
    // exitDuplicateMode still runs for successful deletions
    expect(manager.inDuplicateMode).toBe(false);

    lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    expect(handleUndoDeleteMock).toHaveBeenCalledWith('recipe-batch-1', expect.any(Function));

    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    refreshFn();
    expect(globalThis.recipeManager.loadRecipes).toHaveBeenCalledWith(true);
  });

  it('undoes the batch_ids fallback sequentially with one final refresh and restored toast', async () => {
    mockBulkDelete({ success: true, total_deleted: 2, batch_ids: ['rb-1', 'rb-2'] });

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add('r1');
    manager.selectedForDeletion.add('r2');

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    await lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(2);
    expect(handleUndoDeleteMock.mock.calls[0]).toEqual(['rb-1', null, { showToast: false, refresh: false }]);
    expect(handleUndoDeleteMock.mock.calls[1]).toEqual(['rb-2', null, { showToast: false, refresh: false }]);
    expect(globalThis.recipeManager.loadRecipes).toHaveBeenCalledTimes(1);
    expect(globalThis.recipeManager.loadRecipes).toHaveBeenCalledWith(true);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.restored', {}, 'success');
  });

  it('keeps the legacy success toast when the response carries no batch field', async () => {
    mockBulkDelete({ success: true, total_deleted: 1 });

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add('r1');

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.deleteSuccess',
      { count: 1, type: 'recipes' },
      'success'
    );
  });
});

describe('DuplicatesManager deleteSelectedDuplicates delay-activate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setCurrentPageType('recipes');
    setupDom();
    document.body.insertAdjacentHTML('beforeend', `
      <div id="duplicateDeleteModal" class="modal delete-modal">
        <div class="delete-model-info"><p><span id="duplicateDeleteCount">0</span></p></div>
        <button class="cancel-btn">Cancel</button>
        <button class="delete-btn">Delete</button>
      </div>
    `);
    globalThis.modalManager = { showModal: vi.fn(), closeModal: vi.fn() };
  });

  afterEach(() => {
    vi.useRealTimers();
    delete globalThis.modalManager;
  });

  it('opens with the delete button disabled and enables it after 1500ms', async () => {
    const manager = new DuplicatesManager({});
    manager.selectedForDeletion.add('r1');

    await manager.deleteSelectedDuplicates();

    expect(globalThis.modalManager.showModal).toHaveBeenCalledWith('duplicateDeleteModal');
    const deleteBtn = document.querySelector('#duplicateDeleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    deleteBtn.click();
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1500);
    expect(deleteBtn.disabled).toBe(false);
  });
});
