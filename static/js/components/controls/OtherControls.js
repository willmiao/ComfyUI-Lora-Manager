// OtherControls.js - Specific implementation for the Other Models page
import { PageControls } from './PageControls.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { showToast } from '../../utils/uiHelpers.js';
import { downloadManager } from '../../managers/DownloadManager.js';

/**
 * OtherControls class - Extends PageControls for the Other Models page
 * (VAE, upscalers, text encoders, CLIP vision, ControlNet, ...)
 */
export class OtherControls extends PageControls {
    constructor() {
        // Initialize with 'other' page type
        super('other');

        // Register API methods specific to the Other Models page
        this.registerOtherAPI();
    }

    /**
     * Register Other-models-specific API methods
     */
    registerOtherAPI() {
        const otherAPI = {
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

            // Add fetch from Civitai functionality for other models
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

            // No clearCustomFilter implementation is needed for other models
            // as custom filters are currently only used for LoRAs
            clearCustomFilter: async () => {
                showToast('toast.filters.noCustomFilterToClear', {}, 'info');
            }
        };

        // Register the API
        this.registerAPI(otherAPI);
    }
}
