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
  captureScrollPosition: vi.fn(),
  restoreScrollPosition: vi.fn(),
  recreateVirtualScroll: vi.fn(),
}));

import { sendRecipeWorkflow } from '../../../static/js/api/recipeApi.js';

describe('sendRecipeWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    getCurrentPageStateMock.mockReturnValue({});
  });

  afterEach(() => {
    delete global.fetch;
  });

  it('posts to the send-workflow endpoint and returns the parsed result', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    const result = await sendRecipeWorkflow('recipe-1');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipe/recipe-1/send-workflow',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }
    );
    expect(result).toEqual({ success: true });
  });

  it('returns the backend error when the response is not ok', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      statusText: 'Internal Server Error',
      json: async () => ({ success: false, error: 'Standalone Mode Active' }),
    });

    const result = await sendRecipeWorkflow('recipe-1');

    expect(result).toEqual({ success: false, error: 'Standalone Mode Active' });
  });

  it('falls back to statusText when the error payload has no error field', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      statusText: 'Bad Gateway',
      json: async () => ({}),
    });

    const result = await sendRecipeWorkflow('recipe-1');

    expect(result).toEqual({ success: false, error: 'Bad Gateway' });
  });

  it('throws when the recipe ID cannot be determined', async () => {
    await expect(sendRecipeWorkflow('')).rejects.toThrow('Unable to determine recipe ID');
    await expect(sendRecipeWorkflow(null)).rejects.toThrow('Unable to determine recipe ID');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('encodes the recipe ID in the request URL', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    await sendRecipeWorkflow('recipe#1?name=foo%bar');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/recipe/recipe%231%3Fname%3Dfoo%25bar/send-workflow',
      expect.objectContaining({ method: 'POST' })
    );
  });
});
