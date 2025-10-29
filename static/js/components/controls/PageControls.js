// PageControls.js - Manages controls for both LoRAs and Checkpoints pages
import { getCurrentPageState, setCurrentPageType } from '../../state/index.js';
import { getStorageItem, setStorageItem, getSessionItem, setSessionItem } from '../../utils/storageHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
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
        
        console.log(`PageControls initialized for ${pageType} page`);
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
            await this.sidebarManager.initialize(this);
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
        
        // Handle quick refresh option
        const quickRefreshOption = document.querySelector('[data-action="quick-refresh"]');
        if (quickRefreshOption) {
            quickRefreshOption.addEventListener('click', (e) => {
                e.stopPropagation();
                this.refreshModels(false);
                // Close the dropdown
                document.querySelector('.dropdown-group.active')?.classList.remove('active');
            });
        }
        
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

        try {
            await performModelUpdateCheck();
        } catch (error) {
            console.error('Failed to check model updates:', error);
        } finally {
            this._updateCheckInProgress = false;
            setLoadingState(false);
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
        
        // Build URL
        if (civitaiId) {
            let url = `https://civitai.com/models/${civitaiId}`;
            if (versionId) {
                url += `?modelVersionId=${versionId}`;
            }
            window.open(url, '_blank');
        } else {
            // If no ID, try searching by name
            window.open(`https://civitai.com/models?query=${encodeURIComponent(modelName)}`, '_blank');
        }
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
    }

    /**
     * Toggle favorites-only filter and reload models
     */
    async toggleFavoritesOnly() {
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
