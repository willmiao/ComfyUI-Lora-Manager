import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock dependencies
vi.mock('../../../static/js/state/index.js', () => ({
    getCurrentPageState: vi.fn(() => ({
        filters: {},
    })),
    state: {
        currentPageType: 'recipes',
        loadingManager: {
            showSimpleLoading: vi.fn(),
            hide: vi.fn(),
        },
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
    updatePanelPositions: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    getModelApiClient: vi.fn(() => ({
        loadMoreWithVirtualScroll: vi.fn().mockResolvedValue(),
    })),
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getStorageItem: vi.fn(),
    setStorageItem: vi.fn(),
    removeStorageItem: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: vi.fn((key, _params, fallback) => fallback || key),
}));

vi.mock('../../../static/js/managers/FilterPresetManager.js', () => ({
    FilterPresetManager: vi.fn().mockImplementation(() => ({
        renderPresets: vi.fn(),
        saveActivePreset: vi.fn(),
        restoreActivePreset: vi.fn(),
        updateAddButtonState: vi.fn(),
        hasEmptyWildcardResult: vi.fn(() => false),
    })),
    EMPTY_WILDCARD_MARKER: '__EMPTY_WILDCARD_RESULT__',
}));

import { FilterManager } from '../../../static/js/managers/FilterManager.js';
import { getStorageItem } from '../../../static/js/utils/storageHelpers.js';

const ALL_STATUSES = ['ready', 'missing', 'deleted'];

describe('FilterManager - LoRA Availability', () => {
    let manager;
    let mockFilterPanel;
    let mockActiveFiltersCount;

    function createAvailabilityTags() {
        const container = document.createElement('div');
        container.id = 'loraAvailabilityTags';
        ALL_STATUSES.forEach(status => {
            const tag = document.createElement('div');
            tag.className = 'filter-tag lora-availability-tag';
            tag.dataset.availability = status;
            container.appendChild(tag);
        });
        document.body.appendChild(container);
        return container;
    }

    beforeEach(() => {
        vi.clearAllMocks();
        getStorageItem.mockReturnValue(undefined);
        document.body.innerHTML = '';

        mockFilterPanel = document.createElement('div');
        mockFilterPanel.id = 'filterPanel';
        mockFilterPanel.classList.add('hidden');
        document.body.appendChild(mockFilterPanel);

        mockActiveFiltersCount = document.createElement('span');
        createAvailabilityTags();

        const originalGetElementById = document.getElementById;
        document.getElementById = vi.fn((id) => {
            if (id === 'filterPanel') return mockFilterPanel;
            if (id === 'filterButton') return document.createElement('button');
            if (id === 'activeFiltersCount') return mockActiveFiltersCount;
            if (id === 'baseModelTags') return document.createElement('div');
            if (id === 'modelTypeTags') return document.createElement('div');
            return originalGetElementById.call(document, id);
        });
    });

    describe('initializeFilters', () => {
        it('should default to no statuses selected on the recipes page', () => {
            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.loraAvailability).toEqual([]);
        });

        it('should restore a saved selection from storage', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['missing'],
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.loraAvailability).toEqual(['missing']);
        });

        it('should drop invalid stored values', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['missing', 'bogus', 'missing'],
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.loraAvailability).toEqual(['missing']);
        });

        it('should default to no statuses when the stored value is not an array', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: 'missing',
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.loraAvailability).toEqual([]);
        });
    });

    describe('hasActiveFilters', () => {
        it('should be inactive when no statuses are selected', () => {
            manager = new FilterManager({ page: 'recipes' });

            expect(manager.hasActiveFilters()).toBe(false);
        });

        it('should be active when at least one status is selected', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['ready'],
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.hasActiveFilters()).toBe(true);
        });
    });

    describe('updateActiveFiltersCount', () => {
        it('should count selected statuses', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['missing', 'deleted'],
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(mockActiveFiltersCount.textContent).toBe('2');
        });
    });

    describe('chip interaction', () => {
        it('should select a status when its chip is clicked', async () => {
            manager = new FilterManager({ page: 'recipes' });

            const readyTag = document.querySelector('[data-availability="ready"]');
            expect(readyTag.classList.contains('active')).toBe(false);

            readyTag.click();
            await new Promise(resolve => setTimeout(resolve, 0));

            expect(manager.filters.loraAvailability).toEqual(['ready']);
            expect(readyTag.classList.contains('active')).toBe(true);
        });

        it('should deselect a selected status when its chip is clicked again', async () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['ready'],
            });

            manager = new FilterManager({ page: 'recipes' });

            const readyTag = document.querySelector('[data-availability="ready"]');
            // Restored state should mark the chip active
            expect(readyTag.classList.contains('active')).toBe(true);

            readyTag.click();
            await new Promise(resolve => setTimeout(resolve, 0));

            expect(manager.filters.loraAvailability).toEqual([]);
            expect(readyTag.classList.contains('active')).toBe(false);
        });

        it('should mark all chips active when a stored all-statuses array is restored', () => {
            // Legacy stored value: all statuses selected. Under positive
            // selection semantics the backend treats this as show-all.
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: [...ALL_STATUSES],
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.loraAvailability).toEqual(ALL_STATUSES);
            document.querySelectorAll('.lora-availability-tag').forEach(tag => {
                expect(tag.classList.contains('active')).toBe(true);
            });
        });
    });

    describe('cloneFilters', () => {
        it('should include loraAvailability in cloned filters', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['deleted'],
            });

            manager = new FilterManager({ page: 'recipes' });

            const cloned = manager.cloneFilters();

            expect(cloned.loraAvailability).toEqual(['deleted']);
        });

        it('should clone an empty selection as an empty array', () => {
            manager = new FilterManager({ page: 'recipes' });

            const cloned = manager.cloneFilters();

            expect(cloned.loraAvailability).toEqual([]);
        });
    });

    describe('clearFilters', () => {
        it('should reset loraAvailability to no statuses selected', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                loraAvailability: ['deleted'],
            });

            manager = new FilterManager({ page: 'recipes' });
            expect(manager.filters.loraAvailability).toEqual(['deleted']);

            manager.clearFilters();

            expect(manager.filters.loraAvailability).toEqual([]);
        });
    });
});
