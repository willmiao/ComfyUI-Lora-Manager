import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.hoisted(() => vi.fn());
const loadingManagerMock = vi.hoisted(() => ({
  showSimpleLoading: vi.fn(),
  show: vi.fn(),
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
  recreateVirtualScroll: vi.fn(),
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
      batch_id: null,
      batch_ids: null,
    });
    expect(loadingManagerMock.hide).toHaveBeenCalled();
  });

  it('passes through the merged batch_id from a staged bulk delete', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        total_deleted: 2,
        total_failed: 0,
        failed: [],
        batch_id: 'merged-recipe-batch',
      }),
    });

    const result = await api.bulkDeleteModels(['/recipes/a.webp', '/recipes/b.webp']);

    expect(result.batch_id).toBe('merged-recipe-batch');
    expect(result.batch_ids).toBeNull();
  });

  it('passes through the batch_ids fallback array when the merge failed', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        total_deleted: 2,
        total_failed: 0,
        failed: [],
        batch_ids: ['recipe-batch-1', 'recipe-batch-2'],
      }),
    });

    const result = await api.bulkDeleteModels(['/recipes/a.webp', '/recipes/b.webp']);

    expect(result.batch_id).toBeNull();
    expect(result.batch_ids).toEqual(['recipe-batch-1', 'recipe-batch-2']);
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

  it('reloads recipes without preserving scroll', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{ id: 'recipe-1' }],
        total: 1,
        total_pages: 1,
      }),
    });

    await resetAndReload(false);

    expect(captureScrollPositionMock).not.toHaveBeenCalled();
    expect(virtualScrollerMock.refreshWithData).toHaveBeenCalledWith(
      [{ id: 'recipe-1' }],
      1,
      false
    );
    expect(restoreScrollPositionMock).not.toHaveBeenCalled();
  });

  it('uses scroll-free reloads for syncChanges', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
        total_pages: 0,
      }),
    });

    await syncChanges();

    expect(captureScrollPositionMock).not.toHaveBeenCalled();
    expect(restoreScrollPositionMock).not.toHaveBeenCalled();
    expect(loadingManagerMock.restoreProgressBar).toHaveBeenCalledTimes(1);
  });

  it('posts exactly recipe_ids when rematching in bulk', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        total: 2,
        rematched: 2,
        skipped: 0,
        errors: 0,
        recipes: [],
      }),
    });

    const result = await api.rematchBulkModels(['/recipes/a.webp', '/recipes/b.webp']);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipes/rematch-bulk',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );

    // Exact-body assertion: no extra fields beyond recipe_ids
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
      recipe_ids: ['a', 'b'],
    });
    expect(result).toMatchObject({ success: true, rematched: 2 });
  });

  it('derives recipe IDs via extractRecipeId and skips empty paths', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, total: 1, rematched: 0, skipped: 1, errors: 0 }),
    });

    await api.rematchBulkModels(['', '/recipes/sub folder/recipe-1.webp']);

    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
      recipe_ids: ['recipe-1'],
    });
  });

  it('rejects bulk rematch without file paths', async () => {
    const api = new RecipeSidebarApiClient();

    await expect(api.rematchBulkModels([])).rejects.toThrow('No file paths provided');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('throws the backend error when bulk rematch fails', async () => {
    const api = new RecipeSidebarApiClient();
    global.fetch.mockResolvedValue({
      ok: false,
      json: async () => ({ success: false, error: 'Rematch already running' }),
    });

    await expect(api.rematchBulkModels(['/recipes/a.webp'])).rejects.toThrow('Rematch already running');
  });
});
