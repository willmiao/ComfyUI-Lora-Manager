import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.hoisted(() => vi.fn());
const loadingManagerMock = vi.hoisted(() => ({
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  restoreProgressBar: vi.fn(),
}));
const virtualScrollerMock = vi.hoisted(() => ({
  updateSingleItem: vi.fn(),
  refreshWithData: vi.fn(),
}));
const getCurrentPageStateMock = vi.hoisted(() => vi.fn());
const captureScrollPositionMock = vi.hoisted(() => vi.fn());
const restoreScrollPositionMock = vi.hoisted(() => vi.fn());

vi.mock('../../../static/js/utils/uiHelpers.js', () => {
  return {
    showToast: showToastMock,
  };
});

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
  RecipeCard: vi.fn(() => ({ element: document.createElement('div') })),
}));

vi.mock('../../../static/js/state/index.js', () => {
  return {
    state: {
      loadingManager: loadingManagerMock,
      virtualScroller: virtualScrollerMock,
    },
    getCurrentPageState: getCurrentPageStateMock,
  };
});

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  captureScrollPosition: captureScrollPositionMock,
  restoreScrollPosition: restoreScrollPositionMock,
}));

import {
  RecipeSidebarApiClient,
  fetchRecipeDetails,
  resetAndReload,
  syncChanges,
  updateRecipeMetadata
} from '../../../static/js/api/recipeApi.js';

describe('RecipeSidebarApiClient bulk operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    getCurrentPageStateMock.mockReturnValue({
      pageSize: 50,
      currentPage: 1,
      hasMore: true,
      isLoading: false,
      sortBy: 'date:desc',
      showFavoritesOnly: false,
      activeFolder: null,
      searchOptions: { recursive: true },
      customFilter: { active: false },
      filters: {},
    });
  });

  afterEach(() => {
    delete global.fetch;
  });

  it('sends recipe IDs when moving in bulk', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        results: [
          {
            recipe_id: 'abc',
            original_file_path: '/recipes/abc.webp',
            new_file_path: '/recipes/target/abc.webp',
            success: true,
          },
        ],
        success_count: 1,
        failure_count: 0,
      }),
    });

    const results = await api.moveBulkModels(['/recipes/abc.webp'], '/target/folder');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipes/move-bulk',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { body } = global.fetch.mock.calls[0][1];
    expect(JSON.parse(body)).toEqual({
      recipe_ids: ['abc'],
      target_path: '/target/folder',
    });

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.bulkMoveSuccess',
      { successCount: 1, type: 'Recipe' },
      'success'
    );
    expect(results[0].recipe_id).toBe('abc');
  });

  it('posts recipe IDs for bulk delete', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        total_deleted: 2,
        total_failed: 0,
        failed: [],
      }),
    });

    const result = await api.bulkDeleteModels(['/recipes/a.webp', '/recipes/b.webp']);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipes/bulk-delete',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const parsedBody = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(parsedBody.recipe_ids).toEqual(['a', 'b']);
    expect(result).toMatchObject({
      success: true,
      deleted_count: 2,
      failed_count: 0,
    });
    expect(loadingManagerMock.hide).toHaveBeenCalled();
  });

  it('encodes recipe IDs when fetching recipe details', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'abc' }),
    });

    await fetchRecipeDetails('recipe#1?name=foo%bar');

    expect(global.fetch).toHaveBeenCalledWith('/api/lm/recipe/recipe%231%3Fname%3Dfoo%25bar');
  });

  it('updates the virtual scroller using the original list path when provided', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    await updateRecipeMetadata(
      '/recipes/new-folder/recipe#1.webp',
      { title: 'Updated Title' },
      { listFilePath: '/recipes/old-folder/recipe#1.webp' }
    );

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipe/recipe%231/update',
      expect.objectContaining({ method: 'PUT' })
    );
    expect(virtualScrollerMock.updateSingleItem).toHaveBeenCalledWith(
      '/recipes/old-folder/recipe#1.webp',
      { title: 'Updated Title' }
    );
  });

  it('preserves scroll position for recipe reloads when requested', async () => {
    const scrollSnapshot = { scrollContainer: { scrollTop: 480 }, scrollTop: 480 };
    captureScrollPositionMock.mockReturnValue(scrollSnapshot);
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{ id: 'recipe-1' }],
        total: 1,
        total_pages: 1,
      }),
    });

    await resetAndReload(false, { preserveScroll: true });

    expect(captureScrollPositionMock).toHaveBeenCalledTimes(1);
    expect(virtualScrollerMock.refreshWithData).toHaveBeenCalledWith(
      [{ id: 'recipe-1' }],
      1,
      false
    );
    expect(restoreScrollPositionMock).toHaveBeenCalledWith(scrollSnapshot);
  });

  it('uses scroll-preserving reloads for syncChanges', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
        total_pages: 0,
      }),
    });

    await syncChanges();

    expect(captureScrollPositionMock).toHaveBeenCalledTimes(1);
    expect(restoreScrollPositionMock).toHaveBeenCalledTimes(1);
    expect(loadingManagerMock.restoreProgressBar).toHaveBeenCalledTimes(1);
  });
});
