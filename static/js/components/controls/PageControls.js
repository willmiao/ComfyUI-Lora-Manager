// PageControls.js - Manages controls for both LoRAs and Checkpoints pages
import { state, getCurrentPageState, setCurrentPageType } from '../../state/index.js';
import { getStorageItem, setStorageItem, getSessionItem, setSessionItem } from '../../utils/storageHelpers.js';
import { showToast, openCivitaiByMetadata } from '../../utils/uiHelpers.js';
import { performModelUpdateCheck } from '../../utils/updateCheckHelpers.js';
import { sidebarManager } from '../SidebarManager.js';

/**
 * PageControls class - Unified control management for model pages
 */
export class PageControls {
    constructor(pageType) {
        // Set the current page type in state
        setCurrentPageType(pageType);
        
        // Store the page type
        this.pageType = pageType;
        
        // Get the current page state
        this.pageState = getCurrentPageState();
        
        // Initialize state based on page type
        this.initializeState();
        
        // Store API methods
        this.api = null;
        
        // Use global sidebar manager
        this.sidebarManager = sidebarManager;

        this._updateCheckInProgress = false;

        // Initialize event listeners
        this.initEventListeners();
        
        // Initialize update availability filter button state
        this.initUpdateAvailableFilter();

        // Initialize favorites filter button state
        this.initFavoritesFilter();

        this.initExcludedViewControls();
        this.syncExcludedViewState();
        
        console.log(`PageControls initialized for ${pageType} page`);
        window.pageControls = this;
    }
    
    /**
     * Initialize state based on page type
     */
    initializeState() {
        // Set default values
        this.pageState.pageSize = 100;
        this.pageState.isLoading = false;
        this.pageState.hasMore = true;
        
        // Set default sort based on page type
        this.pageState.sortBy = this.pageType === 'loras' ? 'name:asc' : 'name:asc';
        
        // Load sort preference
        this.loadSortPreference();

        if (!this.pageState.viewMode) {
            this.pageState.viewMode = 'active';
        }
        if (!this.pageState.excludedViewState) {
            this.pageState.excludedViewState = {
                sortBy: 'name:asc',
                search: '',
            };
        }
        if (!this.pageState.filters?.search) {
            this.pageState.filters.search = '';
        }
    }
    
    /**
     * Register API methods for the page
     * @param {Object} api - API methods for the page
     */
    registerAPI(api) {
        this.api = api;
        console.log(`API methods registered for ${this.pageType} page`);
        
        // Initialize sidebar manager after API is registered
        this.initSidebarManager();
    }
    
    /**
     * Initialize sidebar manager
     */
    async initSidebarManager() {
        try {
            this.sidebarManager.setHostPageControls(this);
            const shouldShowSidebar = state?.global?.settings?.show_folder_sidebar !== false;
            await this.sidebarManager.setSidebarEnabled(shouldShowSidebar);
        } catch (error) {
            console.error('Failed to initialize SidebarManager:', error);
        }
    }
    
    /**
     * Initialize event listeners for controls
     */
    initEventListeners() {
        // Sort select handler
        const sortSelect = document.getElementById('sortSelect');
        if (sortSelect) {
            sortSelect.value = this.pageState.sortBy;
            sortSelect.addEventListener('change', async (e) => {
                this.pageState.sortBy = e.target.value;
                this.saveSortPreference(e.target.value);
                await this.resetAndReload();
            });
        }
        
        // Refresh button handler
        const refreshBtn = document.querySelector('[data-action="refresh"]');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshModels(false)); // Regular refresh (incremental)
        }
        
        // Initialize dropdown functionality
        this.initDropdowns();
        
        // Clear custom filter handler
        const clearFilterBtn = document.querySelector('.clear-filter');
        if (clearFilterBtn) {
            clearFilterBtn.addEventListener('click', () => this.clearCustomFilter());
        }
        
        // Page-specific event listeners
        this.initPageSpecificListeners();
    }

    initExcludedViewControls() {
        const backButton = document.getElementById('excludedViewBackBtn');
        if (backButton) {
            backButton.addEventListener('click', async () => {
                await this.exitExcludedView();
            });
        }
    }
    
    /**
     * Initialize dropdown functionality
     */
    initDropdowns() {
        // Handle dropdown toggles
        const dropdownToggles = document.querySelectorAll('.dropdown-toggle');
        dropdownToggles.forEach(toggle => {
            toggle.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent triggering parent button
                const dropdownGroup = toggle.closest('.dropdown-group');
                
                // Close all other open dropdowns first
                document.querySelectorAll('.dropdown-group.active').forEach(group => {
                    if (group !== dropdownGroup) {
                        group.classList.remove('active');
                    }
                });
                
                // Toggle current dropdown
                dropdownGroup.classList.toggle('active');
            });
        });
        
        // Handle full rebuild option
        const fullRebuildOption = document.querySelector('[data-action="full-rebuild"]');
        if (fullRebuildOption) {
            fullRebuildOption.addEventListener('click', (e) => {
                e.stopPropagation();
                this.refreshModels(true);
                // Close the dropdown
                document.querySelector('.dropdown-group.active')?.classList.remove('active');
            });
        }

        const checkUpdatesOption = document.getElementById('checkUpdatesMenuItem');
        if (checkUpdatesOption) {
            checkUpdatesOption.addEventListener('click', async (e) => {
                e.stopPropagation();
                await this.handleCheckModelUpdates(e.currentTarget);
            });
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.dropdown-group')) {
                document.querySelectorAll('.dropdown-group.active').forEach(group => {
                    group.classList.remove('active');
                });
            }
        });
    }

    async handleCheckModelUpdates(menuItem) {
        if (this._updateCheckInProgress) {
            return;
        }

        const updateFilterBtn = document.getElementById('updateFilterBtn');
        const dropdownToggle = document.getElementById('updateFilterMenuToggle');
        const dropdownGroup = menuItem?.closest('.dropdown-group');
        const iconElement = updateFilterBtn?.querySelector('i');

        const setLoadingState = (isLoading) => {
            if (updateFilterBtn) {
                updateFilterBtn.disabled = isLoading;
                updateFilterBtn.classList.toggle('loading', isLoading);
                updateFilterBtn.setAttribute('aria-busy', isLoading ? 'true' : 'false');

                if (iconElement) {
                    if (isLoading) {
                        if (!iconElement.dataset.originalClass) {
                            iconElement.dataset.originalClass = iconElement.className;
                        }
                        iconElement.className = 'fas fa-spinner fa-spin';
                    } else {
                        const originalClass = iconElement.dataset.originalClass;
                        if (originalClass) {
                            iconElement.className = originalClass;
                            delete iconElement.dataset.originalClass;
                        } else {
                            iconElement.classList.remove('fa-spinner', 'fa-spin');
                            if (!iconElement.classList.contains('fa-exclamation-circle')) {
                                iconElement.classList.add('fa-exclamation-circle');
                            }
                        }
                    }
                }
            }

            if (dropdownToggle) {
                dropdownToggle.disabled = isLoading;
                dropdownToggle.classList.toggle('loading', isLoading);
            }

            if (menuItem) {
                menuItem.classList.toggle('disabled', isLoading);
                if (isLoading) {
                    menuItem.setAttribute('aria-disabled', 'true');
                } else {
                    menuItem.removeAttribute('aria-disabled');
                }
            }
        };

        this._updateCheckInProgress = true;
        setLoadingState(true);

        const handleComplete = () => {
            this._updateCheckInProgress = false;
            setLoadingState(false);
        };

        try {
            await performModelUpdateCheck({
                onComplete: handleComplete,
            });
        } catch (error) {
            console.error('Failed to check model updates:', error);
        } finally {
            if (this._updateCheckInProgress) {
                this._updateCheckInProgress = false;
                setLoadingState(false);
            }
            dropdownGroup?.classList.remove('active');
        }
    }

    /**
     * Initialize page-specific event listeners
     */
    initPageSpecificListeners() {
        // Fetch from Civitai button - available for both loras and checkpoints
        const fetchButton = document.querySelector('[data-action="fetch"]');
        if (fetchButton) {
            fetchButton.addEventListener('click', () => this.fetchFromCivitai());
        }
        
        const downloadButton = document.querySelector('[data-action="download"]');
        if (downloadButton) {
            downloadButton.addEventListener('click', () => this.showDownloadModal());
        }
        
        // Find duplicates button - available for both loras and checkpoints
        const duplicatesButton = document.querySelector('[data-action="find-duplicates"]');
        if (duplicatesButton) {
            duplicatesButton.addEventListener('click', () => this.findDuplicates());
        }
        
        const bulkButton = document.querySelector('[data-action="bulk"]');
        if (bulkButton) {
            bulkButton.addEventListener('click', () => this.toggleBulkMode());
        }

        // Favorites filter button handler
        const favoriteFilterBtn = document.getElementById('favoriteFilterBtn');
        if (favoriteFilterBtn) {
            favoriteFilterBtn.addEventListener('click', () => this.toggleFavoritesOnly());
        }

        const updateFilterBtn = document.getElementById('updateFilterBtn');
        if (updateFilterBtn) {
            updateFilterBtn.addEventListener('click', () => this.toggleUpdateAvailableOnly());
        }
    }
    
    /**
     * Load sort preference from storage
     */
    loadSortPreference() {
        const savedSort = getStorageItem(`${this.pageType}_sort`);
        if (savedSort) {
            // Handle legacy format conversion
            const convertedSort = this.convertLegacySortFormat(savedSort);
            this.pageState.sortBy = convertedSort;
            const sortSelect = document.getElementById('sortSelect');
            if (sortSelect) {
                sortSelect.value = convertedSort;
            }
        }
    }
    
    /**
     * Convert legacy sort format to new format
     * @param {string} sortValue - The sort value to convert
     * @returns {string} - Converted sort value
     */
    convertLegacySortFormat(sortValue) {
        // Convert old format to new format with direction
        switch (sortValue) {
            case 'name':
                return 'name:asc';
            case 'date':
                return 'date:desc'; // Newest first is more intuitive default
            case 'size':
                return 'size:desc'; // Largest first is more intuitive default
            default:
                // If it's already in new format or unknown, return as is
                return sortValue.includes(':') ? sortValue : 'name:asc';
        }
    }
    
    /**
     * Save sort preference to storage
     * @param {string} sortValue - The sort value to save
     */
    saveSortPreference(sortValue) {
        if (this.pageState.viewMode === 'excluded') {
            this.pageState.excludedViewState = {
                ...(this.pageState.excludedViewState || {}),
                sortBy: sortValue,
            };
            return;
        }
        setStorageItem(`${this.pageType}_sort`, sortValue);
    }
    
    /**
     * Open model page on Civitai
     * @param {string} modelName - Name of the model
     */
    openCivitai(modelName) {
        // Get card selector based on page type
        const cardSelector = this.pageType === 'loras' 
            ? `.model-card[data-name="${modelName}"]`
            : `.checkpoint-card[data-name="${modelName}"]`;
            
        const card = document.querySelector(cardSelector);
        if (!card) return;
        
        const metaData = JSON.parse(card.dataset.meta);
        const civitaiId = metaData.modelId;
        const versionId = metaData.id;

        openCivitaiByMetadata(civitaiId, versionId, modelName);
    }
    
    /**
     * Reset and reload the models list
     */
    async resetAndReload(updateFolders = false) {
        if (!this.api) {
            console.error('API methods not registered');
            return;
        }

        try {
            await this.api.resetAndReload(updateFolders);
            
            // Refresh sidebar after reload if folders were updated
            if (updateFolders && this.sidebarManager) {
                await this.sidebarManager.refresh();
            }
        } catch (error) {
            console.error(`Error reloading ${this.pageType}:`, error);
            showToast('toast.controls.reloadFailed', { pageType: this.pageType, message: error.message }, 'error');
        }
    }
    
    /**
     * Refresh models list
     * @param {boolean} fullRebuild - Whether to perform a full rebuild
     */
    async refreshModels(fullRebuild = false) {
        if (!this.api) {
            console.error('API methods not registered');
            return;
        }

        try {
            await this.api.refreshModels(fullRebuild);
            
            // Refresh sidebar after rebuild
            if (this.sidebarManager) {
                await this.sidebarManager.refresh();
            }
        } catch (error) {
            console.error(`Error ${fullRebuild ? 'rebuilding' : 'refreshing'} ${this.pageType}:`, error);
            showToast('toast.controls.refreshFailed', { action: fullRebuild ? 'rebuild' : 'refresh', pageType: this.pageType, message: error.message }, 'error');
        }

        if (window.modelDuplicatesManager) {
            // Update duplicates badge after refresh
            window.modelDuplicatesManager.updateDuplicatesBadgeAfterRefresh();
        }
    }
    
    /**
     * Fetch metadata from Civitai (available for both LoRAs and Checkpoints)
     */
    async fetchFromCivitai() {
        if (!this.api) {
            console.error('API methods not registered');
            return;
        }
        
        try {
            await this.api.fetchFromCivitai();
        } catch (error) {
            console.error('Error fetching metadata:', error);
            showToast('toast.controls.fetchMetadataFailed', { message: error.message }, 'error');
        }
    }
    
    /**
     * Show download modal
     */
    showDownloadModal() {
        this.api.showDownloadModal();
    }
    
    /**
     * Toggle bulk mode
     */
    toggleBulkMode() {
        this.api.toggleBulkMode();
    }
    
    /**
     * Clear custom filter
     */
    async clearCustomFilter() {
        if (!this.api) {
            console.error('API methods not registered');
            return;
        }
        
        try {
            await this.api.clearCustomFilter();
        } catch (error) {
            console.error('Error clearing custom filter:', error);
            showToast('toast.controls.clearFilterFailed', { message: error.message }, 'error');
        }
    }
    
    /**
     * Initialize the favorites filter button state
     */
    initFavoritesFilter() {
        const favoriteFilterBtn = document.getElementById('favoriteFilterBtn');
        if (favoriteFilterBtn) {
            // Get current state from session storage with page-specific key
            const storageKey = `show_favorites_only_${this.pageType}`;
            const showFavoritesOnly = getSessionItem(storageKey, false);

            // Update button state
            if (showFavoritesOnly) {
                favoriteFilterBtn.classList.add('active');
            }

            // Update app state
            this.pageState.showFavoritesOnly = showFavoritesOnly;
        }

        this.updateActionButtonStates();
    }

    /**
     * Initialize update availability filter button state
     */
    initUpdateAvailableFilter() {
        const storageKey = `show_update_available_only_${this.pageType}`;
        const storedValue = getSessionItem(storageKey, false);
        const showUpdatesOnly = storedValue === true || storedValue === 'true';

        this.pageState.showUpdateAvailableOnly = showUpdatesOnly;

        const updateFilterBtn = document.getElementById('updateFilterBtn');
        if (updateFilterBtn) {
            updateFilterBtn.classList.toggle('active', showUpdatesOnly);
        }

        this.updateActionButtonStates();
    }

    /**
     * Toggle favorites-only filter and reload models
     */
    async toggleFavoritesOnly() {
        if (this.pageState.viewMode === 'excluded') {
            return;
        }
        const favoriteFilterBtn = document.getElementById('favoriteFilterBtn');
        
        // Toggle the filter state in storage
        const storageKey = `show_favorites_only_${this.pageType}`;
        const currentState = this.pageState.showFavoritesOnly;
        const newState = !currentState;
        
        // Update session storage
        setSessionItem(storageKey, newState);
        
        // Update state
        this.pageState.showFavoritesOnly = newState;
        
        // Update button appearance
        if (favoriteFilterBtn) {
            favoriteFilterBtn.classList.toggle('active', newState);
        }

        // Reload models with new filter
        await this.resetAndReload(true);
    }

    /**
     * Toggle update-available-only filter and reload models
     */
    async toggleUpdateAvailableOnly() {
        if (this.pageState.viewMode === 'excluded') {
            return;
        }
        const updateFilterBtn = document.getElementById('updateFilterBtn');
        const storageKey = `show_update_available_only_${this.pageType}`;
        const newState = !this.pageState.showUpdateAvailableOnly;

        setSessionItem(storageKey, newState);

        this.pageState.showUpdateAvailableOnly = newState;

        if (updateFilterBtn) {
            updateFilterBtn.classList.toggle('active', newState);
        }

        await this.resetAndReload(true);
    }

    cloneFilters(filters = this.pageState.filters) {
        return JSON.parse(JSON.stringify(filters || {}));
    }

    buildExcludedFilters(search = '') {
        return {
            baseModel: [],
            tags: {},
            license: {},
            modelTypes: [],
            search,
            tagLogic: 'any',
        };
    }

    applyFilterState(filters) {
        this.pageState.filters = filters;

        if (window.filterManager) {
            window.filterManager.filters = window.filterManager.initializeFilters(filters);
            window.filterManager.updateActiveFiltersCount();
            if (typeof window.filterManager.updateSelections === 'function') {
                window.filterManager.updateSelections();
            }
            window.filterManager.closeFilterPanel();
        }
    }

    updateActionButtonStates() {
        const favoriteFilterBtn = document.getElementById('favoriteFilterBtn');
        if (favoriteFilterBtn) {
            favoriteFilterBtn.classList.toggle('active', Boolean(this.pageState.showFavoritesOnly));
        }

        const updateFilterBtn = document.getElementById('updateFilterBtn');
        if (updateFilterBtn) {
            updateFilterBtn.classList.toggle('active', Boolean(this.pageState.showUpdateAvailableOnly));
        }
    }

    syncExcludedViewState() {
        const isExcludedView = this.pageState.viewMode === 'excluded';
        const sortSelect = document.getElementById('sortSelect');
        const searchInput = document.getElementById('searchInput');
        const excludedBanner = document.getElementById('excludedViewBanner');
        const filterButton = document.getElementById('filterButton');
        const breadcrumbContainer = document.getElementById('breadcrumbContainer');
        const duplicatesBanner = document.getElementById('duplicatesBanner');
        const alphabetBarContainer = document.querySelector('.alphabet-bar-container');
        const hiddenSelectors = [
            '[data-action="fetch"]',
            '[data-action="download"]',
            '[data-action="bulk"]',
            '[data-action="find-duplicates"]',
            '#favoriteFilterBtn',
            '.update-filter-group',
        ];
        const customFilterIndicator = document.getElementById('customFilterIndicator');

        document.body.classList.toggle('excluded-view-active', isExcludedView);
        excludedBanner?.classList.toggle('hidden', !isExcludedView);
        breadcrumbContainer?.classList.toggle('hidden', isExcludedView);
        alphabetBarContainer?.classList.toggle('hidden', isExcludedView);

        if (duplicatesBanner && isExcludedView) {
            duplicatesBanner.style.display = 'none';
        }

        hiddenSelectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach((element) => {
                element.classList.toggle('hidden', isExcludedView);
            });
        });

        if (customFilterIndicator && isExcludedView) {
            customFilterIndicator.classList.add('hidden');
        }

        if (filterButton) {
            filterButton.disabled = isExcludedView;
            filterButton.classList.toggle('hidden', isExcludedView);
        }

        const activeFiltersCount = document.getElementById('activeFiltersCount');
        if (activeFiltersCount && isExcludedView) {
            activeFiltersCount.style.display = 'none';
        }

        if (sortSelect) {
            sortSelect.value = this.pageState.sortBy;
        }
        if (searchInput) {
            searchInput.value = this.pageState.filters?.search || '';
        }

        this.updateActionButtonStates();

        if (this.sidebarManager) {
            const shouldShowSidebar = !isExcludedView && state?.global?.settings?.show_folder_sidebar !== false;
            this.sidebarManager.setSidebarEnabled(shouldShowSidebar).catch((error) => {
                console.error('Failed to update sidebar visibility:', error);
            });
        }
    }

    suspendInteractiveModes() {
        const snapshot = {
            bulkMode: Boolean(state.bulkMode),
            duplicatesMode: Boolean(this.pageState.duplicatesMode),
        };

        if (snapshot.bulkMode && window.bulkManager?.toggleBulkMode) {
            window.bulkManager.toggleBulkMode();
        }

        if (snapshot.duplicatesMode && window.modelDuplicatesManager?.exitDuplicateMode) {
            window.modelDuplicatesManager.exitDuplicateMode();
        }

        return snapshot;
    }

    async restoreInteractiveModes(snapshot = {}) {
        if (snapshot.bulkMode && !state.bulkMode && window.bulkManager?.toggleBulkMode) {
            window.bulkManager.toggleBulkMode();
        }

        if (!snapshot.duplicatesMode || this.pageState.duplicatesMode) {
            return;
        }

        const duplicatesManager = window.modelDuplicatesManager;
        if (!duplicatesManager) {
            return;
        }

        if (typeof duplicatesManager.enterDuplicateMode === 'function' &&
            Array.isArray(duplicatesManager.duplicateGroups) &&
            duplicatesManager.duplicateGroups.length > 0) {
            duplicatesManager.enterDuplicateMode();
            return;
        }

        if (typeof duplicatesManager.findDuplicates === 'function') {
            await duplicatesManager.findDuplicates();
        }
    }

    syncCustomFilterIndicator() {
        const indicator = document.getElementById('customFilterIndicator');
        if (!indicator) {
            return;
        }

        if (this.pageState.viewMode === 'excluded') {
            indicator.classList.add('hidden');
            return;
        }

        if (typeof this.checkCustomFilters === 'function') {
            this.checkCustomFilters();
        }
    }

    async enterExcludedView() {
        if (this.pageState.viewMode === 'excluded') {
            return;
        }

        const interactionSnapshot = this.suspendInteractiveModes();

        this.pageState.activeViewSnapshot = {
            sortBy: this.pageState.sortBy,
            activeFolder: this.pageState.activeFolder,
            activeLetterFilter: this.pageState.activeLetterFilter ?? null,
            showFavoritesOnly: this.pageState.showFavoritesOnly,
            showUpdateAvailableOnly: this.pageState.showUpdateAvailableOnly,
            bulkMode: interactionSnapshot.bulkMode,
            duplicatesMode: interactionSnapshot.duplicatesMode,
            filters: this.cloneFilters(),
        };

        const excludedState = this.pageState.excludedViewState || {
            sortBy: 'name:asc',
            search: '',
        };

        this.pageState.viewMode = 'excluded';
        this.pageState.sortBy = excludedState.sortBy || 'name:asc';
        this.pageState.currentPage = 1;
        this.pageState.activeFolder = null;
        this.pageState.activeLetterFilter = null;
        this.pageState.showFavoritesOnly = false;
        this.pageState.showUpdateAvailableOnly = false;

        this.applyFilterState(this.buildExcludedFilters(excludedState.search || ''));
        this.syncExcludedViewState();
        await this.resetAndReload(false);
    }

    async exitExcludedView() {
        if (this.pageState.viewMode !== 'excluded') {
            return;
        }

        this.pageState.excludedViewState = {
            ...(this.pageState.excludedViewState || {}),
            sortBy: this.pageState.sortBy,
            search: this.pageState.filters?.search || '',
        };

        const snapshot = this.pageState.activeViewSnapshot || {};
        this.pageState.viewMode = 'active';
        this.pageState.sortBy = snapshot.sortBy || this.convertLegacySortFormat(getStorageItem(`${this.pageType}_sort`) || 'name:asc');
        this.pageState.currentPage = 1;
        this.pageState.activeFolder = snapshot.activeFolder ?? getStorageItem(`${this.pageType}_activeFolder`);
        this.pageState.activeLetterFilter = snapshot.activeLetterFilter ?? null;
        this.pageState.showFavoritesOnly = Boolean(snapshot.showFavoritesOnly);
        this.pageState.showUpdateAvailableOnly = Boolean(snapshot.showUpdateAvailableOnly);
        this.applyFilterState(snapshot.filters || this.buildExcludedFilters(''));
        this.pageState.activeViewSnapshot = null;

        this.syncExcludedViewState();
        await this.resetAndReload(true);
        this.syncCustomFilterIndicator();
        await this.restoreInteractiveModes(snapshot);
    }
    
    /**
     * Find duplicate models
     */
    findDuplicates() {
        if (window.modelDuplicatesManager) {
            // Change to toggle functionality
            window.modelDuplicatesManager.toggleDuplicateMode();
        } else {
            console.error('Model duplicates manager not available');
        }
    }
    
    /**
     * Clean up resources
     */
    destroy() {
        // Note: We don't destroy the global sidebar manager, just clean it up
        // The global instance will be reused for other page controls
        if (this.sidebarManager && this.sidebarManager.isInitialized) {
            this.sidebarManager.cleanup();
        }
    }
}