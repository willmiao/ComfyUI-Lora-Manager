import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.hoisted(() => vi.fn());
const loadingManagerMock = vi.hoisted(() => ({
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
}));

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
    },
    getCurrentPageState: vi.fn(),
  };
});

import { RecipeSidebarApiClient } from '../../../static/js/api/recipeApi.js';

describe('RecipeSidebarApiClient bulk operations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
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
});
