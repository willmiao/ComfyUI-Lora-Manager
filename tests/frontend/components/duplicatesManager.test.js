import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const recreateVirtualScrollMock = vi.fn();
const translateMock = vi.fn((key) => key);

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
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
