// MiscControls.js - Specific implementation for the Misc (VAE/Upscaler) page
import { PageControls } from './PageControls.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { getSessionItem, removeSessionItem } from '../../utils/storageHelpers.js';
import { downloadManager } from '../../managers/DownloadManager.js';

/**
 * MiscControls class - Extends PageControls for Misc-specific functionality
 */
export class MiscControls extends PageControls {
    constructor() {
        // Initialize with 'misc' page type
        super('misc');

        // Register API methods specific to the Misc page
        this.registerMiscAPI();

        // Check for custom filters (e.g., from recipe navigation)
        this.checkCustomFilters();
    }

    /**
     * Register Misc-specific API methods
     */
    registerMiscAPI() {
        const miscAPI = {
            // Core API functions
            loadMoreModels: async (resetPage = false, updateFolders = false) => {
                return await getModelApiClient().loadMoreWithVirtualScroll(resetPage, updateFolders);
            },

            resetAndReload: async (updateFolders = false) => {
                return await resetAndReload(updateFolders);
            },

            refreshModels: async (fullRebuild = false) => {
                return await getModelApiClient().refreshModels(fullRebuild);
            },

            // Add fetch from Civitai functionality for misc models
            fetchFromCivitai: async () => {
                return await getModelApiClient().fetchCivitaiMetadata();
            },

            // Add show download modal functionality
            showDownloadModal: () => {
                downloadManager.showDownloadModal();
            },

            toggleBulkMode: () => {
                if (window.bulkManager) {
                    window.bulkManager.toggleBulkMode();
                } else {
                    console.error('Bulk manager not available');
                }
            },

            clearCustomFilter: async () => {
                await this.clearCustomFilter();
            }
        };

        // Register the API
        this.registerAPI(miscAPI);
    }

    /**
     * Check for custom filters sent from other pages (e.g., recipe modal)
     */
    checkCustomFilters() {
        const filterMiscHash = getSessionItem('recipe_to_misc_filterHash');
        const filterRecipeName = getSessionItem('filterMiscRecipeName');

        if (filterMiscHash && filterRecipeName) {
            const indicator = document.getElementById('customFilterIndicator');
            const filterText = indicator?.querySelector('.customFilterText');

            if (indicator && filterText) {
                indicator.classList.remove('hidden');

                const displayText = `Viewing misc model from: ${filterRecipeName}`;
                filterText.textContent = this._truncateText(displayText, 30);
                filterText.setAttribute('title', displayText);

                const filterElement = indicator.querySelector('.filter-active');
                if (filterElement) {
                    filterElement.classList.add('animate');
                    setTimeout(() => filterElement.classList.remove('animate'), 600);
                }
            }
        }
    }

    /**
     * Clear misc custom filter and reload
     */
    async clearCustomFilter() {
        removeSessionItem('recipe_to_misc_filterHash');
        removeSessionItem('recipe_to_misc_filterHashes');
        removeSessionItem('filterMiscRecipeName');

        const indicator = document.getElementById('customFilterIndicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }

        await resetAndReload();
    }

    /**
     * Helper to truncate text with ellipsis
     * @param {string} text
     * @param {number} maxLength
     * @returns {string}
     */
    _truncateText(text, maxLength) {
        return text.length > maxLength ? `${text.substring(0, maxLength - 3)}...` : text;
    }
}
