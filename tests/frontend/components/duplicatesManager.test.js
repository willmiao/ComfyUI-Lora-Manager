import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const recreateVirtualScrollMock = vi.fn();

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
  RecipeCard: class {},
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
