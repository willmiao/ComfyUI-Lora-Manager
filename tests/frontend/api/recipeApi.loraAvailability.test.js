import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const getCurrentPageStateMock = vi.hoisted(() => vi.fn());

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
    RecipeCard: vi.fn(() => ({ element: document.createElement('div') })),
}));

vi.mock('../../../static/js/state/index.js', () => ({
    state: {
        loadingManager: {
            showSimpleLoading: vi.fn(),
            hide: vi.fn(),
        },
    },
    getCurrentPageState: getCurrentPageStateMock,
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
    captureScrollPosition: vi.fn(),
    restoreScrollPosition: vi.fn(),
    recreateVirtualScroll: vi.fn(),
}));

import { fetchRecipesPage } from '../../../static/js/api/recipeApi.js';

function makePageState(loraAvailability) {
    return {
        pageSize: 50,
        currentPage: 1,
        hasMore: true,
        isLoading: false,
        sortBy: 'date:desc',
        showFavoritesOnly: false,
        activeFolder: null,
        searchOptions: { recursive: true },
        customFilter: { active: false },
        filters: { loraAvailability },
    };
}

describe('fetchRecipesPage lora_availability param', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ items: [], total: 0, total_pages: 0 }),
        });
    });

    afterEach(() => {
        delete global.fetch;
    });

    it('appends lora_availability when a subset of statuses is selected', async () => {
        getCurrentPageStateMock.mockReturnValue(makePageState(['missing', 'deleted']));

        await fetchRecipesPage(1, 50);

        const url = global.fetch.mock.calls[0][0];
        const params = new URL(url, 'http://localhost').searchParams;
        expect(params.get('lora_availability')).toBe('missing,deleted');
    });

    it('appends lora_availability when all statuses are selected (backend treats it as show-all)', async () => {
        getCurrentPageStateMock.mockReturnValue(
            makePageState(['ready', 'missing', 'deleted'])
        );

        await fetchRecipesPage(1, 50);

        const url = global.fetch.mock.calls[0][0];
        const params = new URL(url, 'http://localhost').searchParams;
        expect(params.get('lora_availability')).toBe('ready,missing,deleted');
    });

    it('omits lora_availability when no statuses are selected', async () => {
        getCurrentPageStateMock.mockReturnValue(makePageState([]));

        await fetchRecipesPage(1, 50);

        const url = global.fetch.mock.calls[0][0];
        const params = new URL(url, 'http://localhost').searchParams;
        expect(params.get('lora_availability')).toBeNull();
    });

    it('omits lora_availability when the filter is absent', async () => {
        getCurrentPageStateMock.mockReturnValue(makePageState(undefined));

        await fetchRecipesPage(1, 50);

        const url = global.fetch.mock.calls[0][0];
        const params = new URL(url, 'http://localhost').searchParams;
        expect(params.get('lora_availability')).toBeNull();
    });
});
