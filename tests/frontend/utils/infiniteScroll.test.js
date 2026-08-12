import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  VirtualScrollerMock,
  MasonryScrollerMock,
  RecipeCardMock,
  fetchRecipesPageMock,
  getModelApiClientMock,
} = vi.hoisted(() => {
  const makeScrollerClass = () => vi.fn(function (options) {
    this.options = options;
    this.initialize = vi.fn(async () => {});
    this.dispose = vi.fn();
    this.reset = vi.fn();
    this.handlePageUpDown = vi.fn();
  });

  return {
    VirtualScrollerMock: makeScrollerClass(),
    MasonryScrollerMock: makeScrollerClass(),
    RecipeCardMock: vi.fn(function () {
      this.element = document.createElement('div');
    }),
    fetchRecipesPageMock: vi.fn(async () => ({ items: [], totalItems: 0, hasMore: false })),
    getModelApiClientMock: vi.fn(() => ({
      fetchModelsPage: vi.fn(async () => ({ items: [], totalItems: 0, hasMore: false })),
    })),
  };
});

vi.mock('../../../static/js/utils/VirtualScroller.js', () => ({
  VirtualScroller: VirtualScrollerMock,
}));

vi.mock('../../../static/js/utils/MasonryScroller.js', () => ({
  MasonryScroller: MasonryScrollerMock,
}));

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
  RecipeCard: RecipeCardMock,
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  fetchRecipesPage: fetchRecipesPageMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
}));

vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
  createModelCard: vi.fn(() => document.createElement('div')),
  setupModelCardEventDelegation: vi.fn(),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
}));

import {
  initializeInfiniteScroll,
  recreateVirtualScroll,
} from '../../../static/js/utils/infiniteScroll.js';
import { state } from '../../../static/js/state/index.js';

function setupPageDom() {
  const pageContent = document.createElement('div');
  pageContent.className = 'page-content';
  const container = document.createElement('div');
  container.className = 'container';
  pageContent.appendChild(container);
  document.body.appendChild(pageContent);

  const grid = document.createElement('div');
  vi.spyOn(document, 'getElementById').mockImplementation((id) =>
    id === 'recipeGrid' || id === 'modelGrid' ? grid : null);

  return { grid };
}

describe('infiniteScroll scroller class branching', () => {
  let originalSettings;

  beforeEach(() => {
    originalSettings = state.global.settings;
    state.global.settings = { ...originalSettings };
    if (state.pages.recipes) {
      state.pages.recipes.duplicatesMode = false;
    }
    state.virtualScroller = null;
    state.keyboardNavHandler = null;
    setupPageDom();
  });

  afterEach(() => {
    state.global.settings = originalSettings;
    state.virtualScroller = null;
    state.keyboardNavHandler = null;
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('constructs MasonryScroller for the recipes page when recipes_layout is masonry', async () => {
    state.global.settings.recipes_layout = 'masonry';

    await initializeInfiniteScroll('recipes');

    expect(MasonryScrollerMock).toHaveBeenCalledTimes(1);
    expect(VirtualScrollerMock).not.toHaveBeenCalled();
    expect(state.virtualScroller).toBeInstanceOf(MasonryScrollerMock);
  });

  it('constructs VirtualScroller for the recipes page when recipes_layout is grid', async () => {
    state.global.settings.recipes_layout = 'grid';

    await initializeInfiniteScroll('recipes');

    expect(VirtualScrollerMock).toHaveBeenCalledTimes(1);
    expect(MasonryScrollerMock).not.toHaveBeenCalled();
    expect(state.virtualScroller).toBeInstanceOf(VirtualScrollerMock);
  });

  it('falls back to the grid branch when recipes_layout is missing', async () => {
    delete state.global.settings.recipes_layout;

    await expect(initializeInfiniteScroll('recipes')).resolves.toBeUndefined();

    expect(VirtualScrollerMock).toHaveBeenCalledTimes(1);
    expect(MasonryScrollerMock).not.toHaveBeenCalled();
  });

  it('always constructs VirtualScroller for the loras page regardless of recipes_layout', async () => {
    state.global.settings.recipes_layout = 'masonry';

    await initializeInfiniteScroll('loras');

    expect(VirtualScrollerMock).toHaveBeenCalledTimes(1);
    expect(MasonryScrollerMock).not.toHaveBeenCalled();
  });
});

describe('recreateVirtualScroll', () => {
  let originalSettings;

  beforeEach(() => {
    originalSettings = state.global.settings;
    state.global.settings = { ...originalSettings };
    if (state.pages.recipes) {
      state.pages.recipes.duplicatesMode = false;
    }
    state.virtualScroller = null;
    state.keyboardNavHandler = null;
    setupPageDom();
  });

  afterEach(() => {
    state.global.settings = originalSettings;
    state.virtualScroller = null;
    state.keyboardNavHandler = null;
    document.body.innerHTML = '';
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('cleans up keyboard navigation, disposes the old scroller, and rebuilds with the new layout', async () => {
    state.global.settings.recipes_layout = 'grid';
    await initializeInfiniteScroll('recipes');
    const oldScroller = state.virtualScroller;
    const oldKeyboardHandler = state.keyboardNavHandler;
    expect(oldKeyboardHandler).toBeTypeOf('function');

    const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener');
    state.global.settings.recipes_layout = 'masonry';

    await recreateVirtualScroll('recipes');

    // cleanupKeyboardNavigation removed the previous document keydown listener
    expect(removeEventListenerSpy).toHaveBeenCalledWith('keydown', oldKeyboardHandler);
    // Old scroller disposed and replaced by a new masonry instance
    expect(oldScroller.dispose).toHaveBeenCalledTimes(1);
    expect(MasonryScrollerMock).toHaveBeenCalledTimes(1);
    expect(state.virtualScroller).toBeInstanceOf(MasonryScrollerMock);
    expect(state.virtualScroller).not.toBe(oldScroller);
    // A fresh keyboard navigation listener was registered for the new instance
    expect(state.keyboardNavHandler).toBeTypeOf('function');
    expect(state.keyboardNavHandler).not.toBe(oldKeyboardHandler);
  });

  it('works when there is no existing virtual scroller', async () => {
    state.global.settings.recipes_layout = 'masonry';

    await expect(recreateVirtualScroll('recipes')).resolves.toBeUndefined();

    expect(MasonryScrollerMock).toHaveBeenCalledTimes(1);
    expect(state.virtualScroller).toBeInstanceOf(MasonryScrollerMock);
  });
});
