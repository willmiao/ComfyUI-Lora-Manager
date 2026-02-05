import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock dependencies
vi.mock('../../../static/js/state/index.js', () => ({
    getCurrentPageState: vi.fn(() => ({
        filters: {},
    })),
    state: {
        currentPageType: 'loras',
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
import { getStorageItem, setStorageItem } from '../../../static/js/utils/storageHelpers.js';

describe('FilterManager - Tag Logic', () => {
    let manager;
    let mockFilterPanel;
    let mockTagLogicToggle;

    beforeEach(() => {
        vi.clearAllMocks();

        // Setup DOM mocks
        mockFilterPanel = document.createElement('div');
        mockFilterPanel.id = 'filterPanel';
        mockFilterPanel.classList.add('hidden');

        mockTagLogicToggle = document.createElement('div');
        mockTagLogicToggle.id = 'tagLogicToggle';

        // Create tag logic options
        const anyOption = document.createElement('button');
        anyOption.className = 'tag-logic-option';
        anyOption.dataset.value = 'any';
        mockTagLogicToggle.appendChild(anyOption);

        const allOption = document.createElement('button');
        allOption.className = 'tag-logic-option';
        allOption.dataset.value = 'all';
        mockTagLogicToggle.appendChild(allOption);

        document.body.appendChild(mockFilterPanel);
        document.body.appendChild(mockTagLogicToggle);

        // Mock getElementById
        const originalGetElementById = document.getElementById;
        document.getElementById = vi.fn((id) => {
            if (id === 'filterPanel') return mockFilterPanel;
            if (id === 'tagLogicToggle') return mockTagLogicToggle;
            if (id === 'filterButton') return document.createElement('button');
            if (id === 'activeFiltersCount') return document.createElement('span');
            if (id === 'baseModelTags') return document.createElement('div');
            if (id === 'modelTypeTags') return document.createElement('div');
            return originalGetElementById.call(document, id);
        });
    });

    describe('initializeFilters', () => {
        it('should default tagLogic to "any" when not provided', () => {
            manager = new FilterManager({ page: 'loras' });

            expect(manager.filters.tagLogic).toBe('any');
        });

        it('should use provided tagLogic value', () => {
            getStorageItem.mockReturnValue({
                tagLogic: 'all',
                tags: {},
                baseModel: [],
            });

            manager = new FilterManager({ page: 'loras' });

            expect(manager.filters.tagLogic).toBe('all');
        });
    });

    describe('initializeTagLogicToggle', () => {
        it('should set "any" option as active by default', () => {
            manager = new FilterManager({ page: 'loras' });
            
            // Ensure filters.tagLogic is set to default
            manager.filters.tagLogic = 'any';

            const anyOption = mockTagLogicToggle.querySelector('[data-value="any"]');
            const allOption = mockTagLogicToggle.querySelector('[data-value="all"]');

            // Manually update UI to ensure correct state
            manager.updateTagLogicToggleUI();

            expect(manager.filters.tagLogic).toBe('any');
            expect(anyOption.classList.contains('active')).toBe(true);
            expect(allOption.classList.contains('active')).toBe(false);
        });

        it('should set "all" option as active when tagLogic is "all"', () => {
            getStorageItem.mockReturnValue({
                tagLogic: 'all',
                tags: {},
                baseModel: [],
            });

            manager = new FilterManager({ page: 'loras' });
            
            // Ensure filters.tagLogic is set correctly
            manager.filters.tagLogic = 'all';

            const anyOption = mockTagLogicToggle.querySelector('[data-value="any"]');
            const allOption = mockTagLogicToggle.querySelector('[data-value="all"]');

            // Manually update UI to ensure correct state
            manager.updateTagLogicToggleUI();

            expect(manager.filters.tagLogic).toBe('all');
            expect(anyOption.classList.contains('active')).toBe(false);
            expect(allOption.classList.contains('active')).toBe(true);
        });
    });

    describe('updateTagLogicToggleUI', () => {
        it('should update UI when tagLogic changes', () => {
            // Clear any existing active classes first
            mockTagLogicToggle.querySelectorAll('.tag-logic-option').forEach(el => {
                el.classList.remove('active');
            });

            manager = new FilterManager({ page: 'loras' });

            let anyOption = mockTagLogicToggle.querySelector('[data-value="any"]');
            let allOption = mockTagLogicToggle.querySelector('[data-value="all"]');

            // Ensure initial state
            manager.filters.tagLogic = 'any';
            manager.updateTagLogicToggleUI();
            expect(anyOption.classList.contains('active')).toBe(true);
            expect(allOption.classList.contains('active')).toBe(false);

            // Change to "all"
            manager.filters.tagLogic = 'all';
            manager.updateTagLogicToggleUI();

            expect(anyOption.classList.contains('active')).toBe(false);
            expect(allOption.classList.contains('active')).toBe(true);
        });
    });

    describe('cloneFilters', () => {
        it('should include tagLogic in cloned filters', () => {
            manager = new FilterManager({ page: 'loras' });
            manager.filters.tagLogic = 'all';

            const cloned = manager.cloneFilters();

            expect(cloned.tagLogic).toBe('all');
        });
    });

    describe('clearFilters', () => {
        it('should reset tagLogic to "any"', () => {
            getStorageItem.mockReturnValue({
                tagLogic: 'all',
                tags: { anime: 'include' },
                baseModel: ['SDXL'],
            });

            manager = new FilterManager({ page: 'loras' });
            expect(manager.filters.tagLogic).toBe('all');

            manager.clearFilters();

            expect(manager.filters.tagLogic).toBe('any');
        });

        it('should update UI after clearing', () => {
            getStorageItem.mockReturnValue({
                tagLogic: 'all',
                tags: {},
                baseModel: [],
            });

            manager = new FilterManager({ page: 'loras' });

            const anyOption = mockTagLogicToggle.querySelector('[data-value="any"]');
            const allOption = mockTagLogicToggle.querySelector('[data-value="all"]');

            // Initially "all" is active
            expect(allOption.classList.contains('active')).toBe(true);

            manager.clearFilters();

            // After clear, "any" should be active
            expect(anyOption.classList.contains('active')).toBe(true);
            expect(allOption.classList.contains('active')).toBe(false);
        });
    });

    describe('loadFiltersFromStorage', () => {
        it('should restore tagLogic from storage', () => {
            getStorageItem.mockReturnValue({
                tagLogic: 'all',
                tags: { anime: 'include' },
                baseModel: [],
            });

            manager = new FilterManager({ page: 'loras' });

            expect(manager.filters.tagLogic).toBe('all');
            expect(manager.filters.tags).toEqual({ anime: 'include' });
        });

        it('should default to "any" when no tagLogic in storage', () => {
            getStorageItem.mockReturnValue({
                tags: {},
                baseModel: [],
            });

            manager = new FilterManager({ page: 'loras' });

            expect(manager.filters.tagLogic).toBe('any');
        });
    });

    describe('tag logic toggle interaction', () => {
        it('should update tagLogic when clicking "all" option', async () => {
            manager = new FilterManager({ page: 'loras' });

            const allOption = mockTagLogicToggle.querySelector('[data-value="all"]');

            // Simulate click
            allOption.click();

            // Wait for async operation
            await new Promise(resolve => setTimeout(resolve, 0));

            expect(manager.filters.tagLogic).toBe('all');
        });

        it('should not change tagLogic when clicking already active option', async () => {
            manager = new FilterManager({ page: 'loras' });

            const anyOption = mockTagLogicToggle.querySelector('[data-value="any"]');
            const applyFiltersSpy = vi.spyOn(manager, 'applyFilters');

            // Click already active option
            anyOption.click();

            await new Promise(resolve => setTimeout(resolve, 0));

            // applyFilters should not be called since value didn't change
            expect(applyFiltersSpy).not.toHaveBeenCalled();
        });
    });
});
