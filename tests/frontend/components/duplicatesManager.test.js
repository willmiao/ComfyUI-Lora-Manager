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
      this.element.className = 'model-card';
      const preview = document.createElement('div');
      preview.className = 'card-preview';
      this.element.appendChild(preview);
    }
  },
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({}));

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

describe('DuplicatesManager card selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCurrentPageType('recipes');
    setupDom();
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
  });

  afterEach(() => {
    state.virtualScroller = null;
  });

  it('toggles selection when the preview area is clicked', () => {
    const manager = new DuplicatesManager({});
    manager.duplicateGroups = [{
      key: 'g-1',
      recipes: [
        { id: 'r1', modified: 1 },
        { id: 'r2', modified: 2 },
      ],
    }];
    manager.renderDuplicateGroups();

    const checkbox = document.querySelector('.selector-checkbox[data-recipe-id="r1"]');
    const card = checkbox.closest('.model-card');
    card.querySelector('.card-preview').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(manager.selectedForDeletion.has('r1')).toBe(true);
    expect(checkbox.checked).toBe(true);
    expect(card.classList.contains('duplicate-selected')).toBe(true);
  });

  it('keeps the clicked recipe and selects the other recipes in its group', () => {
    const manager = new DuplicatesManager({});
    manager.duplicateGroups = [{
      key: 'g-1',
      recipes: [
        { id: 'r1', modified: 1 },
        { id: 'r2', modified: 2 },
        { id: 'r3', modified: 3 },
      ],
    }];
    manager.renderDuplicateGroups();

    const keeper = document.querySelector('.selector-checkbox[data-recipe-id="r2"]').closest('.model-card');
    const keepButton = keeper.querySelector('.keep-item-btn');
    expect(keepButton.title).toBe('duplicates.keepThisTooltip');
    keepButton.click();

    expect(manager.selectedForDeletion.has('r1')).toBe(true);
    expect(manager.selectedForDeletion.has('r2')).toBe(false);
    expect(manager.selectedForDeletion.has('r3')).toBe(true);
  });

  it('keeps the latest recipe in every group before later groups are rendered', () => {
    const originalObserver = global.IntersectionObserver;
    global.IntersectionObserver = class {
      constructor() {}
      observe() {}
      disconnect() {}
    };

    try {
      const manager = new DuplicatesManager({});
      manager.duplicateGroups = Array.from({ length: 30 }, (_, index) => ({
        key: `g-${index}`,
        recipes: [
          { id: `r-${index}-old`, modified: 1 },
          { id: `r-${index}-new`, modified: 2 },
        ],
      }));
      manager.renderDuplicateGroups();

      expect(document.querySelectorAll('.duplicate-group')).toHaveLength(25);
      manager.selectLatestDuplicates();

      expect(manager.selectedForDeletion.size).toBe(30);
      expect(manager.selectedForDeletion.has('r-29-old')).toBe(true);
      expect(manager.selectedForDeletion.has('r-29-new')).toBe(false);
    } finally {
      if (originalObserver) {
        global.IntersectionObserver = originalObserver;
      } else {
        delete global.IntersectionObserver;
      }
    }
  });
});

describe('DuplicatesManager toolbar button', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setCurrentPageType('recipes');
    setupDom();
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
  });

  afterEach(() => {
    state.virtualScroller = null;
  });

  it('shows Exit Duplicates while active and restores the original button on exit', async () => {
    document.body.insertAdjacentHTML('beforeend', `
      <button id="findDuplicatesBtn" title="Find Duplicates">
        <span>Duplicates</span><span id="duplicatesBadge" class="badge"></span>
      </button>
    `);
    const manager = new DuplicatesManager({});
    manager.duplicateGroups = [{
      key: 'g-1',
      recipes: [{ id: 'r1', modified: 1 }, { id: 'r2', modified: 2 }],
    }];

    manager.enterDuplicateMode();

    const button = document.getElementById('findDuplicatesBtn');
    expect(button.classList.contains('active')).toBe(true);
    expect(button.textContent).toContain('duplicates.exitDuplicates');
    expect(button.title).toBe('Exit Duplicates Mode');

    await manager.exitDuplicateMode();

    expect(button.classList.contains('active')).toBe(false);
    expect(button.textContent.trim()).toBe('Duplicates');
    expect(button.title).toBe('Find Duplicates');
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
    state.loadingManager = {
      showSimpleLoading: vi.fn(),
      hide: vi.fn(),
    };
    globalThis.modalManager = { showModal: vi.fn(), closeModal: vi.fn() };
    globalThis.recipeManager = { loadRecipes: vi.fn() };
  });

  afterEach(() => {
    state.pendingLayoutRecreate = false;
    state.virtualScroller = null;
    state.loadingManager = null;
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

  it('shows the undo action toast and refreshes the current view on undo', async () => {
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
    expect(manager.inDuplicateMode).toBe(true);
    expect(recreateVirtualScrollMock).not.toHaveBeenCalled();

    await lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    expect(handleUndoDeleteMock).toHaveBeenCalledWith('recipe-batch-1', expect.any(Function));
    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    await refreshFn();
    expect(globalThis.fetch).toHaveBeenLastCalledWith('/api/lm/recipes/find-duplicates');
    manager.inDuplicateMode = false;
    await refreshFn();
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
    expect(globalThis.fetch).toHaveBeenLastCalledWith('/api/lm/recipes/find-duplicates');
    expect(globalThis.recipeManager.loadRecipes).not.toHaveBeenCalled();
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

  it('updates groups locally and retains visible failed recipes for retry', async () => {
    mockBulkDelete({
      success: true,
      total_deleted: 1,
      batch_id: 'recipe-batch-1',
      deleted: ['r1'],
      failed: [{ id: 'r2', reason: 'The file is in use' }],
    });

    const manager = new DuplicatesManager({});
    manager.duplicateGroups = [{
      key: 'g-1',
      recipes: [
        { id: 'r1', file_path: '/recipes/r1.png', modified: 1 },
        { id: 'r2', file_path: '/recipes/r2.png', modified: 2 },
        { id: 'r3', file_path: '/recipes/r3.png', modified: 3 },
      ],
    }];
    const removeMultipleMock = vi.fn();
    state.virtualScroller.removeMultipleItemsByFilePath = removeMultipleMock;
    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add('r1');
    manager.selectedForDeletion.add('r2');

    await manager.confirmDeleteDuplicates();

    expect(manager.duplicateGroups[0].recipes.map(recipe => recipe.id)).toEqual(['r2', 'r3']);
    expect(Array.from(manager.selectedForDeletion)).toEqual(['r2']);
    expect(removeMultipleMock).toHaveBeenCalledWith(['/recipes/r1.png']);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.deletePartialFailed',
      { failed: 1, type: 'recipes', message: 'The file is in use' },
      'error'
    );
    expect(manager.inDuplicateMode).toBe(true);
    expect(recreateVirtualScrollMock).not.toHaveBeenCalled();
  });

  it('blocks duplicate submissions until deletion finishes and refreshes on exit', async () => {
    let finishDelete;
    globalThis.fetch = vi.fn(() => new Promise(resolve => {
      finishDelete = () => resolve({
        ok: true,
        json: async () => ({ success: true, total_deleted: 1, batch_id: 'recipe-batch-1' }),
      });
    }));

    const manager = new DuplicatesManager({});
    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add('r1');

    const firstRequest = manager.confirmDeleteDuplicates();
    await Promise.resolve();

    expect(manager._isDeleting).toBe(true);
    expect(state.loadingManager.showSimpleLoading).toHaveBeenCalledWith(
      'duplicates.deleting'
    );
    expect(translateMock).toHaveBeenCalledWith('duplicates.deleting', { count: 1 });
    expect(await manager.confirmDeleteDuplicates()).toBe(false);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    finishDelete();
    await firstRequest;

    expect(manager._isDeleting).toBe(false);
    expect(recreateVirtualScrollMock).not.toHaveBeenCalled();
    expect(state.loadingManager.hide).toHaveBeenCalled();

    await manager.exitDuplicateMode();
    expect(recreateVirtualScrollMock).toHaveBeenCalledWith('recipes');
  });
});
