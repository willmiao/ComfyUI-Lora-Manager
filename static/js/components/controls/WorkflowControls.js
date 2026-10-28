// WorkflowControls.js - Specific implementation for the Workflows page
import { PageControls } from './PageControls.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { showToast } from '../../utils/uiHelpers.js';
import { downloadManager } from '../../managers/DownloadManager.js';

/**
 * WorkflowControls class - Extends PageControls for the Workflows page
 * (ComfyUI workflow JSON resources)
 */
export class WorkflowControls extends PageControls {
    constructor() {
        // Initialize with 'workflows' page type
        super('workflows');

        // Register API methods specific to the Workflows page
        this.registerWorkflowAPI();
    }

    /**
     * Register workflow-specific API methods
     */
    registerWorkflowAPI() {
        const workflowAPI = {
            // Core API functions
            loadMoreModels: async (resetPage = false, updateFolders = false) => {
                return await getModelApiClient().loadMoreWithVirtualScroll(resetPage, updateFolders);
            },

            resetAndReload: async (updateFolders = false) => {
                return await resetAndReload(updateFolders);
            },

            // Add fetch from Civitai functionality for workflows
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

            // No clearCustomFilter implementation is needed for workflows
            // as custom filters are currently only used for LoRAs
            clearCustomFilter: async () => {
                showToast('toast.filters.noCustomFilterToClear', {}, 'info');
            }
        };

        // Register the API
        this.registerAPI(workflowAPI);
    }
}
