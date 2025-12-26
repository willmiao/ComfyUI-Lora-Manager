import { getCurrentPageState } from '../state/index.js';
import { showToast, updatePanelPositions } from '../utils/uiHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { removeStorageItem, setStorageItem, getStorageItem } from '../utils/storageHelpers.js';
import { MODEL_TYPE_DISPLAY_NAMES } from '../utils/constants.js';
import { translate } from '../utils/i18nHelpers.js';

export class FilterManager {
    constructor(options = {}) {
        this.options = {
            ...options
        };

        this.currentPage = options.page || document.body.dataset.page || 'loras';
        const pageState = getCurrentPageState();

        this.filters = this.initializeFilters(pageState ? pageState.filters : undefined);

        this.filterPanel = document.getElementById('filterPanel');
        this.filterButton = document.getElementById('filterButton');
        this.activeFiltersCount = document.getElementById('activeFiltersCount');
        this.tagsLoaded = false;

        this.initialize();

        // Store this instance in the state
        if (pageState) {
            pageState.filterManager = this;
            pageState.filters = this.cloneFilters();
        }
    }

    initialize() {
        // Create base model filter tags if they exist
        if (document.getElementById('baseModelTags')) {
            this.createBaseModelTags();
        }

        if (document.getElementById('modelTypeTags')) {
            this.createModelTypeTags();
        }

        // Add click handlers for license filter tags if supported on this page
        if (this.shouldShowLicenseFilters()) {
            this.initializeLicenseFilters();
        }

        // Add click handler for filter button
        if (this.filterButton) {
            this.filterButton.addEventListener('click', () => {
                this.toggleFilterPanel();
            });
        }

        // Close filter panel when clicking outside
        document.addEventListener('click', (e) => {
            if (this.filterPanel && !this.filterPanel.contains(e.target) &&
                e.target !== this.filterButton &&
                !this.filterButton.contains(e.target) &&
                !this.filterPanel.classList.contains('hidden')) {
                this.closeFilterPanel();
            }
        });

        // Initialize active filters from localStorage if available
        this.loadFiltersFromStorage();
    }

    async loadTopTags() {
        try {
            // Show loading state
            const tagsContainer = document.getElementById('modelTagsFilter');
            if (!tagsContainer) return;

            tagsContainer.innerHTML = '<div class="tags-loading">Loading tags...</div>';

            // Determine the API endpoint based on the page type
            const tagsEndpoint = `/api/lm/${this.currentPage}/top-tags?limit=20`;

            const response = await fetch(tagsEndpoint);
            if (!response.ok) throw new Error('Failed to fetch tags');

            const data = await response.json();
            if (data.success && data.tags) {
                this.createTagFilterElements(data.tags);

                // After creating tag elements, mark any previously selected ones
                this.updateTagSelections();
            } else {
                throw new Error('Invalid response format');
            }
        } catch (error) {
            console.error('Error loading top tags:', error);
            const tagsContainer = document.getElementById('modelTagsFilter');
            if (tagsContainer) {
                tagsContainer.innerHTML = '<div class="tags-error">Failed to load tags</div>';
            }
        }
    }

    createTagFilterElements(tags) {
        const tagsContainer = document.getElementById('modelTagsFilter');
        if (!tagsContainer) return;

        tagsContainer.innerHTML = '';

        if (!tags.length) {
            tagsContainer.innerHTML = `<div class="no-tags">No ${this.currentPage === 'recipes' ? 'recipe ' : ''}tags available</div>`;
            return;
        }

        tags.forEach(tag => {
            const tagEl = document.createElement('div');
            tagEl.className = 'filter-tag tag-filter';
            const tagName = tag.tag;
            tagEl.dataset.tag = tagName;
            tagEl.innerHTML = `${tagName} <span class="tag-count">${tag.count}</span>`;

            // Add click handler to cycle through tri-state filter and automatically apply
            tagEl.addEventListener('click', async () => {
                const currentState = (this.filters.tags && this.filters.tags[tagName]) || 'none';
                const newState = this.getNextTriStateState(currentState);
                this.setTagFilterState(tagName, newState);
                this.applyTagElementState(tagEl, newState);

                this.updateActiveFiltersCount();

                // Auto-apply filter when tag is clicked
                await this.applyFilters(false);
            });

            this.applyTagElementState(tagEl, (this.filters.tags && this.filters.tags[tagName]) || 'none');
            tagsContainer.appendChild(tagEl);
        });

        // Add "No tags" as a special filter at the end
        const noTagsEl = document.createElement('div');
        noTagsEl.className = 'filter-tag tag-filter special-tag';
        const noTagsLabel = translate('header.filter.noTags', {}, 'No tags');
        const noTagsKey = '__no_tags__';
        noTagsEl.dataset.tag = noTagsKey;
        noTagsEl.innerHTML = noTagsLabel;

        noTagsEl.addEventListener('click', async () => {
            const currentState = (this.filters.tags && this.filters.tags[noTagsKey]) || 'none';
            const newState = this.getNextTriStateState(currentState);
            this.setTagFilterState(noTagsKey, newState);
            this.applyTagElementState(noTagsEl, newState);

            this.updateActiveFiltersCount();

            await this.applyFilters(false);
        });

        this.applyTagElementState(noTagsEl, (this.filters.tags && this.filters.tags[noTagsKey]) || 'none');
        tagsContainer.appendChild(noTagsEl);
    }

    initializeLicenseFilters() {
        const licenseTags = document.querySelectorAll('.license-tag');
        licenseTags.forEach(tag => {
            tag.addEventListener('click', async () => {
                const licenseType = tag.dataset.license;

                // Ensure license object exists
                if (!this.filters.license) {
                    this.filters.license = {};
                }

                // Get current state
                let currentState = this.filters.license[licenseType] || 'none'; // none, include, exclude

                // Cycle through states: none -> include -> exclude -> none
                let newState;
                switch (currentState) {
                    case 'none':
                        newState = 'include';
                        tag.classList.remove('exclude');
                        tag.classList.add('active');
                        break;
                    case 'include':
                        newState = 'exclude';
                        tag.classList.remove('active');
                        tag.classList.add('exclude');
                        break;
                    case 'exclude':
                        newState = 'none';
                        tag.classList.remove('active', 'exclude');
                        break;
                }

                // Update filter state
                if (newState === 'none') {
                    delete this.filters.license[licenseType];
                    // Clean up empty license object
                    if (Object.keys(this.filters.license).length === 0) {
                        delete this.filters.license;
                    }
                } else {
                    this.filters.license[licenseType] = newState;
                }

                this.updateActiveFiltersCount();

                // Auto-apply filter when tag is clicked
                await this.applyFilters(false);
            });
        });

        // Update selections based on stored filters
        this.updateLicenseSelections();
    }

    updateLicenseSelections() {
        const licenseTags = document.querySelectorAll('.license-tag');
        licenseTags.forEach(tag => {
            const licenseType = tag.dataset.license;
            const state = (this.filters.license && this.filters.license[licenseType]) || 'none';

            // Reset classes
            tag.classList.remove('active', 'exclude');

            // Apply appropriate class based on state
            switch (state) {
                case 'include':
                    tag.classList.add('active');
                    break;
                case 'exclude':
                    tag.classList.add('exclude');
                    break;
                default:
                    // none state - no classes needed
                    break;
            }
        });
    }

    createBaseModelTags() {
        const baseModelTagsContainer = document.getElementById('baseModelTags');
        if (!baseModelTagsContainer) return;

        // Set the API endpoint based on current page
        const apiEndpoint = `/api/lm/${this.currentPage}/base-models`;

        // Fetch base models
        fetch(apiEndpoint)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.base_models) {
                    baseModelTagsContainer.innerHTML = '';

                    data.base_models.forEach(model => {
                        const tag = document.createElement('div');
                        tag.className = `filter-tag base-model-tag`;
                        tag.dataset.baseModel = model.name;
                        tag.innerHTML = `${model.name} <span class="tag-count">${model.count}</span>`;

                        // Add click handler to toggle selection and automatically apply
                        tag.addEventListener('click', async () => {
                            tag.classList.toggle('active');

                            if (tag.classList.contains('active')) {
                                if (!this.filters.baseModel.includes(model.name)) {
                                    this.filters.baseModel.push(model.name);
                                }
                            } else {
                                this.filters.baseModel = this.filters.baseModel.filter(m => m !== model.name);
                            }

                            this.updateActiveFiltersCount();

                            // Auto-apply filter when tag is clicked
                            await this.applyFilters(false);
                        });

                        baseModelTagsContainer.appendChild(tag);
                    });

                    // Update selections based on stored filters
                    this.updateTagSelections();
                }
            })
            .catch(error => {
                console.error(`Error fetching base models for ${this.currentPage}:`, error);
                baseModelTagsContainer.innerHTML = '<div class="tags-error">Failed to load base models</div>';
            });
    }

    async createModelTypeTags() {
        const modelTypeContainer = document.getElementById('modelTypeTags');
        if (!modelTypeContainer) return;

        modelTypeContainer.innerHTML = '<div class="tags-loading">Loading model types...</div>';

        try {
            const response = await fetch(`/api/lm/${this.currentPage}/model-types?limit=20`);
            if (!response.ok) {
                throw new Error('Failed to fetch model types');
            }

            const data = await response.json();
            if (!data.success || !Array.isArray(data.model_types)) {
                throw new Error('Invalid response format');
            }

            const normalizedTypes = data.model_types
                .map(entry => {
                    if (!entry || !entry.type) {
                        return null;
                    }
                    const typeKey = entry.type.toString().trim().toLowerCase();
                    if (!typeKey || !MODEL_TYPE_DISPLAY_NAMES[typeKey]) {
                        return null;
                    }
                    return {
                        type: typeKey,
                        count: Number(entry.count) || 0,
                    };
                })
                .filter(Boolean);

            if (!normalizedTypes.length) {
                modelTypeContainer.innerHTML = '<div class="no-tags">No model types available</div>';
                return;
            }

            modelTypeContainer.innerHTML = '';

            normalizedTypes.forEach(({ type, count }) => {
                const tag = document.createElement('div');
                tag.className = 'filter-tag model-type-tag';
                tag.dataset.modelType = type;
                tag.innerHTML = `${MODEL_TYPE_DISPLAY_NAMES[type]} <span class="tag-count">${count}</span>`;

                if (this.filters.modelTypes.includes(type)) {
                    tag.classList.add('active');
                }

                tag.addEventListener('click', async () => {
                    const isSelected = this.filters.modelTypes.includes(type);
                    if (isSelected) {
                        this.filters.modelTypes = this.filters.modelTypes.filter(value => value !== type);
                        tag.classList.remove('active');
                    } else {
                        this.filters.modelTypes.push(type);
                        tag.classList.add('active');
                    }

                    this.updateActiveFiltersCount();
                    await this.applyFilters(false);
                });

                modelTypeContainer.appendChild(tag);
            });

            this.updateModelTypeSelections();
        } catch (error) {
            console.error('Error loading model types:', error);
            modelTypeContainer.innerHTML = '<div class="tags-error">Failed to load model types</div>';
        }
    }

    toggleFilterPanel() {
        if (this.filterPanel) {
            const isHidden = this.filterPanel.classList.contains('hidden');

            if (isHidden) {
                // Update panel positions before showing
                updatePanelPositions();

                this.filterPanel.classList.remove('hidden');
                this.filterButton.classList.add('active');

                // Load tags if they haven't been loaded yet
                if (!this.tagsLoaded) {
                    this.loadTopTags();
                    this.tagsLoaded = true;
                }
            } else {
                this.closeFilterPanel();
            }
        }
    }

    closeFilterPanel() {
        if (this.filterPanel) {
            this.filterPanel.classList.add('hidden');
        }
        if (this.filterButton) {
            this.filterButton.classList.remove('active');
        }
    }

    updateTagSelections() {
        // Update base model tags
        const baseModelTags = document.querySelectorAll('.base-model-tag');
        baseModelTags.forEach(tag => {
            const baseModel = tag.dataset.baseModel;
            if (this.filters.baseModel.includes(baseModel)) {
                tag.classList.add('active');
            } else {
                tag.classList.remove('active');
            }
        });

        // Update model tags
        const modelTags = document.querySelectorAll('.tag-filter');
        modelTags.forEach(tag => {
            const tagName = tag.dataset.tag;
            const state = (this.filters.tags && this.filters.tags[tagName]) || 'none';
            this.applyTagElementState(tag, state);
        });

        // Update license tags if visible on this page
        if (this.shouldShowLicenseFilters()) {
            this.updateLicenseSelections();
        }
        this.updateModelTypeSelections();
    }

    updateModelTypeSelections() {
        const typeTags = document.querySelectorAll('.model-type-tag');
        typeTags.forEach(tag => {
            const modelType = tag.dataset.modelType;
            if (this.filters.modelTypes.includes(modelType)) {
                tag.classList.add('active');
            } else {
                tag.classList.remove('active');
            }
        });
    }

    updateActiveFiltersCount() {
        const tagFilterCount = this.filters.tags ? Object.keys(this.filters.tags).length : 0;
        const licenseFilterCount = this.filters.license ? Object.keys(this.filters.license).length : 0;
        const modelTypeFilterCount = this.filters.modelTypes.length;
        const totalActiveFilters = this.filters.baseModel.length + tagFilterCount + licenseFilterCount + modelTypeFilterCount;

        if (this.activeFiltersCount) {
            if (totalActiveFilters > 0) {
                this.activeFiltersCount.textContent = totalActiveFilters;
                this.activeFiltersCount.style.display = 'inline-flex';
            } else {
                this.activeFiltersCount.style.display = 'none';
            }
        }
    }

    async applyFilters(showToastNotification = true) {
        const pageState = getCurrentPageState();
        const storageKey = `${this.currentPage}_filters`;

        // Save filters to localStorage
        const filtersSnapshot = this.cloneFilters();
        setStorageItem(storageKey, filtersSnapshot);

        // Update state with current filters
        pageState.filters = filtersSnapshot;

        // Call the appropriate manager's load method based on page type
        if (this.currentPage === 'recipes' && window.recipeManager) {
            await window.recipeManager.loadRecipes(true);
        } else if (this.currentPage === 'loras' || this.currentPage === 'embeddings' || this.currentPage === 'checkpoints') {
            // For models page, reset the page and reload
            await getModelApiClient().loadMoreWithVirtualScroll(true, false);
        }

        // Update filter button to show active state
        if (this.hasActiveFilters()) {
            this.filterButton.classList.add('active');
            if (showToastNotification) {
                const baseModelCount = this.filters.baseModel.length;
                const tagsCount = this.filters.tags ? Object.keys(this.filters.tags).length : 0;

                let message = '';
                if (baseModelCount > 0 && tagsCount > 0) {
                    message = `Filtering by ${baseModelCount} base model${baseModelCount > 1 ? 's' : ''} and ${tagsCount} tag${tagsCount > 1 ? 's' : ''}`;
                } else if (baseModelCount > 0) {
                    message = `Filtering by ${baseModelCount} base model${baseModelCount > 1 ? 's' : ''}`;
                } else if (tagsCount > 0) {
                    message = `Filtering by ${tagsCount} tag${tagsCount > 1 ? 's' : ''}`;
                }

                showToast('toast.filters.applied', { message }, 'success');
            }
        } else {
            this.filterButton.classList.remove('active');
            if (showToastNotification) {
                showToast('toast.filters.cleared', {}, 'info');
            }
        }
    }

    async clearFilters() {
        // Clear all filters
        this.filters = this.initializeFilters({
            ...this.filters,
            baseModel: [],
            tags: {},
            license: {},
            modelTypes: []
        });

        // Update state
        const pageState = getCurrentPageState();
        pageState.filters = this.cloneFilters();

        // Update UI
        this.updateTagSelections();
        this.updateActiveFiltersCount();

        // Remove from local Storage
        const storageKey = `${this.currentPage}_filters`;
        removeStorageItem(storageKey);

        // Update UI
        if (this.hasActiveFilters()) {
            this.filterButton.classList.add('active');
        } else {
            this.filterButton.classList.remove('active');
        }

        // Reload data using the appropriate method for the current page
        if (this.currentPage === 'recipes' && window.recipeManager) {
            await window.recipeManager.loadRecipes(true);
        } else if (this.currentPage === 'loras' || this.currentPage === 'checkpoints' || this.currentPage === 'embeddings') {
            await getModelApiClient().loadMoreWithVirtualScroll(true, true);
        }

        showToast('toast.filters.cleared', {}, 'info');
    }

    loadFiltersFromStorage() {
        const storageKey = `${this.currentPage}_filters`;
        const savedFilters = getStorageItem(storageKey);

        if (savedFilters) {
            try {
                // Ensure backward compatibility with older filter format
                this.filters = this.initializeFilters(savedFilters);

                // Update state with loaded filters
                const pageState = getCurrentPageState();
                pageState.filters = this.cloneFilters();

                this.updateTagSelections();
                this.updateActiveFiltersCount();

                if (this.hasActiveFilters()) {
                    this.filterButton.classList.add('active');
                }
            } catch (error) {
                console.error(`Error loading ${this.currentPage} filters from storage:`, error);
            }
        }
    }

    hasActiveFilters() {
        const tagCount = this.filters.tags ? Object.keys(this.filters.tags).length : 0;
        const licenseCount = this.filters.license ? Object.keys(this.filters.license).length : 0;
        const modelTypeCount = this.filters.modelTypes.length;
        return (
            this.filters.baseModel.length > 0 ||
            tagCount > 0 ||
            licenseCount > 0 ||
            modelTypeCount > 0
        );
    }

    initializeFilters(existingFilters = {}) {
        const source = existingFilters || {};
        return {
            ...source,
            baseModel: Array.isArray(source.baseModel) ? [...source.baseModel] : [],
            tags: this.normalizeTagFilters(source.tags),
            license: this.shouldShowLicenseFilters() ? this.normalizeLicenseFilters(source.license) : {},
            modelTypes: this.normalizeModelTypeFilters(source.modelTypes)
        };
    }

    shouldShowLicenseFilters() {
        return this.currentPage !== 'recipes';
    }

    normalizeTagFilters(tagFilters) {
        if (!tagFilters) {
            return {};
        }

        if (Array.isArray(tagFilters)) {
            return tagFilters.reduce((acc, tag) => {
                if (typeof tag === 'string' && tag.trim().length > 0) {
                    acc[tag] = 'include';
                }
                return acc;
            }, {});
        }

        if (typeof tagFilters === 'object') {
            const normalized = {};
            Object.entries(tagFilters).forEach(([tag, state]) => {
                if (!tag) {
                    return;
                }
                const normalizedState = typeof state === 'string' ? state.toLowerCase() : '';
                if (normalizedState === 'include' || normalizedState === 'exclude') {
                    normalized[tag] = normalizedState;
                }
            });
            return normalized;
        }

        return {};
    }

    normalizeLicenseFilters(licenseFilters) {
        if (!licenseFilters || typeof licenseFilters !== 'object') {
            return {};
        }

        const normalized = {};
        Object.entries(licenseFilters).forEach(([key, state]) => {
            const normalizedState = typeof state === 'string' ? state.toLowerCase() : '';
            if (normalizedState === 'include' || normalizedState === 'exclude') {
                normalized[key] = normalizedState;
            }
        });
        return normalized;
    }

    normalizeModelTypeFilters(modelTypes) {
        if (!Array.isArray(modelTypes)) {
            return [];
        }

        const seen = new Set();
        return modelTypes.reduce((acc, type) => {
            if (typeof type !== 'string') {
                return acc;
            }

            const normalized = type.trim().toLowerCase();
            if (!normalized || seen.has(normalized)) {
                return acc;
            }

            seen.add(normalized);
            acc.push(normalized);
            return acc;
        }, []);
    }

    cloneFilters() {
        return {
            ...this.filters,
            baseModel: [...(this.filters.baseModel || [])],
            tags: { ...(this.filters.tags || {}) },
            license: { ...(this.filters.license || {}) },
            modelTypes: [...(this.filters.modelTypes || [])]
        };
    }

    getNextTriStateState(currentState) {
        switch (currentState) {
            case 'none':
                return 'include';
            case 'include':
                return 'exclude';
            default:
                return 'none';
        }
    }

    setTagFilterState(tagName, state) {
        if (!this.filters.tags) {
            this.filters.tags = {};
        }

        if (state === 'none') {
            delete this.filters.tags[tagName];
        } else {
            this.filters.tags[tagName] = state;
        }
    }

    applyTagElementState(element, state) {
        if (!element) {
            return;
        }

        element.classList.remove('active', 'exclude');
        if (state === 'include') {
            element.classList.add('active');
        } else if (state === 'exclude') {
            element.classList.add('exclude');
        }
    }
}
