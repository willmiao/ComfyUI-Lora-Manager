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

describe('FilterManager - Has Workflow', () => {
    let manager;
    let mockFilterPanel;
    let mockActiveFiltersCount;

    function createHasWorkflowTag() {
        const container = document.createElement('div');
        container.id = 'hasWorkflowTags';
        const tag = document.createElement('div');
        tag.className = 'filter-tag has-workflow-tag';
        container.appendChild(tag);
        document.body.appendChild(container);
        return tag;
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
        createHasWorkflowTag();

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
        it('should default to false on the recipes page', () => {
            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.hasWorkflow).toBe(false);
        });

        it('should restore a saved true value from storage', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.hasWorkflow).toBe(true);
        });

        it('should coerce a truthy stored value to boolean', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: 1,
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.filters.hasWorkflow).toBe(true);
        });
    });

    describe('hasActiveFilters', () => {
        it('should be inactive when hasWorkflow is off', () => {
            manager = new FilterManager({ page: 'recipes' });

            expect(manager.hasActiveFilters()).toBe(false);
        });

        it('should be active when hasWorkflow is on', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(manager.hasActiveFilters()).toBe(true);
        });
    });

    describe('updateActiveFiltersCount', () => {
        it('should count hasWorkflow as one active filter', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });

            expect(mockActiveFiltersCount.textContent).toBe('1');
        });
    });

    describe('chip interaction', () => {
        it('should activate the filter when the chip is clicked', async () => {
            manager = new FilterManager({ page: 'recipes' });

            const tag = document.querySelector('.has-workflow-tag');
            expect(tag.classList.contains('active')).toBe(false);

            tag.click();
            await new Promise(resolve => setTimeout(resolve, 0));

            expect(manager.filters.hasWorkflow).toBe(true);
            expect(tag.classList.contains('active')).toBe(true);
        });

        it('should deactivate the filter when the chip is clicked again', async () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });

            const tag = document.querySelector('.has-workflow-tag');
            // Restored state should mark the chip active
            expect(tag.classList.contains('active')).toBe(true);

            tag.click();
            await new Promise(resolve => setTimeout(resolve, 0));

            expect(manager.filters.hasWorkflow).toBe(false);
            expect(tag.classList.contains('active')).toBe(false);
        });
    });

    describe('cloneFilters', () => {
        it('should include hasWorkflow in cloned filters', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });

            const cloned = manager.cloneFilters();

            expect(cloned.hasWorkflow).toBe(true);
        });

        it('should clone an unset hasWorkflow as false', () => {
            manager = new FilterManager({ page: 'recipes' });

            const cloned = manager.cloneFilters();

            expect(cloned.hasWorkflow).toBe(false);
        });
    });

    describe('clearFilters', () => {
        it('should reset hasWorkflow to false', () => {
            getStorageItem.mockReturnValue({
                baseModel: [],
                tags: {},
                hasWorkflow: true,
            });

            manager = new FilterManager({ page: 'recipes' });
            expect(manager.filters.hasWorkflow).toBe(true);

            manager.clearFilters();

            expect(manager.filters.hasWorkflow).toBe(false);
        });
    });
});
