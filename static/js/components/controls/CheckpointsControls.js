// CheckpointsControls.js - Specific implementation for the Checkpoints page
import { PageControls } from './PageControls.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { getSessionItem, removeSessionItem } from '../../utils/storageHelpers.js';
import { downloadManager } from '../../managers/DownloadManager.js';

/**
 * CheckpointsControls class - Extends PageControls for Checkpoint-specific functionality
 */
export class CheckpointsControls extends PageControls {
    constructor() {
        // Initialize with 'checkpoints' page type
        super('checkpoints');
        
        // Register API methods specific to the Checkpoints page
        this.registerCheckpointsAPI();

        // Check for custom filters (e.g., from recipe navigation)
        this.checkCustomFilters();
    }
    
    /**
     * Register Checkpoint-specific API methods
     */
    registerCheckpointsAPI() {
        const checkpointsAPI = {
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
            
            // Add fetch from Civitai functionality for checkpoints
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
        this.registerAPI(checkpointsAPI);
    }

    /**
     * Check for custom filters sent from other pages (e.g., recipe modal)
     */
    checkCustomFilters() {
        const filterCheckpointHash = getSessionItem('recipe_to_checkpoint_filterHash');
        const filterRecipeName = getSessionItem('filterCheckpointRecipeName');

        if (filterCheckpointHash && filterRecipeName) {
            const indicator = document.getElementById('customFilterIndicator');
            const filterText = indicator?.querySelector('.customFilterText');

            if (indicator && filterText) {
                indicator.classList.remove('hidden');

                const displayText = `Viewing checkpoint from: ${filterRecipeName}`;
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
     * Clear checkpoint custom filter and reload
     */
    async clearCustomFilter() {
        // Check for View Local Versions filter first
        const vlmModelId = getSessionItem('vlm_model_id');
        if (vlmModelId) {
            removeSessionItem('vlm_model_id');
            removeSessionItem('vlm_model_name');
            removeSessionItem('vlm_base_model');
            removeSessionItem('vlm_page_type');
            this._restoreSortAfterVlm();
            // Hide the indicator
            const indicator = document.getElementById('customFilterIndicator');
            if (indicator) {
                indicator.classList.add('hidden');
            }
            await resetAndReload();
            return;
        }

        removeSessionItem('recipe_to_checkpoint_filterHash');
        removeSessionItem('recipe_to_checkpoint_filterHashes');
        removeSessionItem('filterCheckpointRecipeName');

        const indicator = document.getElementById('customFilterIndicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }

        await resetAndReload();
    }
}
