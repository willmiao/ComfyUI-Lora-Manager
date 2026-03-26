import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { MODEL_TYPES } from '../api/apiConfig.js';
import { state } from '../state/index.js';
import { modalManager } from './ModalManager.js';

/**
 * Manager for downloading missing LoRAs for selected recipes in bulk
 */
export class BulkMissingLoraDownloadManager {
    constructor() {
        this.loraApiClient = getModelApiClient(MODEL_TYPES.LORA);
        this.pendingLoras = [];
        this.pendingRecipes = [];
    }

    /**
     * Collect missing LoRAs from selected recipes with deduplication
     * @param {Array} selectedRecipes - Array of selected recipe objects
     * @returns {Object} - Object containing unique missing LoRAs and statistics
     */
    collectMissingLoras(selectedRecipes) {
        const uniqueLoras = new Map(); // key: hash or modelVersionId, value: lora object
        const missingLorasByRecipe = new Map();
        let totalMissingCount = 0;

        selectedRecipes.forEach(recipe => {
            const missingLoras = [];
            
            if (recipe.loras && Array.isArray(recipe.loras)) {
                recipe.loras.forEach(lora => {
                    // Only include LoRAs not in library and not deleted
                    if (!lora.inLibrary && !lora.isDeleted) {
                        const uniqueKey = lora.hash || lora.id || lora.modelVersionId;
                        
                        if (uniqueKey && !uniqueLoras.has(uniqueKey)) {
                            // Store the LoRA info
                            uniqueLoras.set(uniqueKey, {
                                ...lora,
                                modelId: lora.modelId || lora.model_id,
                                id: lora.id || lora.modelVersionId,
                            });
                        }
                        
                        missingLoras.push(lora);
                        totalMissingCount++;
                    }
                });
            }
            
            if (missingLoras.length > 0) {
                missingLorasByRecipe.set(recipe.id || recipe.file_path, {
                    recipe,
                    missingLoras
                });
            }
        });

        return {
            uniqueLoras: Array.from(uniqueLoras.values()),
            uniqueCount: uniqueLoras.size,
            totalMissingCount,
            missingLorasByRecipe
        };
    }

    /**
     * Show confirmation modal for downloading missing LoRAs
     * @param {Object} stats - Statistics about missing LoRAs
     * @returns {Promise<boolean>} - Whether user confirmed
     */
    async showConfirmationModal(stats) {
        const { uniqueCount, totalMissingCount, uniqueLoras } = stats;

        if (uniqueCount === 0) {
            showToast('toast.recipes.noMissingLoras', {}, 'info');
            return false;
        }

        // Store pending data for confirmation
        this.pendingLoras = uniqueLoras;

        // Update modal content
        const messageEl = document.getElementById('bulkDownloadMissingLorasMessage');
        const listEl = document.getElementById('bulkDownloadMissingLorasList');
        const confirmBtn = document.getElementById('bulkDownloadMissingLorasConfirmBtn');

        if (messageEl) {
            messageEl.textContent = translate('modals.bulkDownloadMissingLoras.message', { 
                uniqueCount, 
                totalCount: totalMissingCount 
            }, `Found ${uniqueCount} unique missing LoRAs (from ${totalMissingCount} total across selected recipes).`);
        }

        if (listEl) {
            listEl.innerHTML = uniqueLoras.slice(0, 10).map(lora => `
                <li>
                    <span class="lora-name">${lora.name || lora.file_name || 'Unknown'}</span>
                    ${lora.version ? `<span class="lora-version">${lora.version}</span>` : ''}
                </li>
            `).join('') + 
            (uniqueLoras.length > 10 ? `
                <li class="more-items">${translate('modals.bulkDownloadMissingLoras.moreItems', { count: uniqueLoras.length - 10 }, `...and ${uniqueLoras.length - 10} more`)}</li>
            ` : '');
        }

        if (confirmBtn) {
            confirmBtn.innerHTML = `
                <i class="fas fa-download"></i>
                ${translate('modals.bulkDownloadMissingLoras.downloadButton', { count: uniqueCount }, `Download ${uniqueCount} LoRA(s)`)}
            `;
        }

        // Show modal
        modalManager.showModal('bulkDownloadMissingLorasModal');
        
        // Return a promise that will be resolved when user confirms or cancels
        return new Promise((resolve) => {
            this.confirmResolve = resolve;
        });
    }

    /**
     * Called when user confirms download in modal
     */
    async confirmDownload() {
        modalManager.closeModal('bulkDownloadMissingLorasModal');
        
        if (this.confirmResolve) {
            this.confirmResolve(true);
            this.confirmResolve = null;
        }

        // Execute download
        await this.executeDownload(this.pendingLoras);
        this.pendingLoras = [];
    }

    /**
     * Download missing LoRAs for selected recipes
     * @param {Array} selectedRecipes - Array of selected recipe objects
     */
    async downloadMissingLoras(selectedRecipes) {
        if (!selectedRecipes || selectedRecipes.length === 0) {
            showToast('toast.recipes.noRecipesSelected', {}, 'warning');
            return;
        }

        // Store selected recipes
        this.pendingRecipes = selectedRecipes;

        // Collect missing LoRAs with deduplication
        const stats = this.collectMissingLoras(selectedRecipes);
        
        if (stats.uniqueCount === 0) {
            showToast('toast.recipes.noMissingLorasInSelection', {}, 'info');
            return;
        }

        // Show confirmation modal
        const confirmed = await this.showConfirmationModal(stats);
        if (!confirmed) {
            return;
        }
    }

    /**
     * Execute the download process
     * @param {Array} lorasToDownload - Array of unique LoRAs to download
     */
    async executeDownload(lorasToDownload) {
        const totalLoras = lorasToDownload.length;
        
        // Get LoRA root directory
        const loraRoot = await this.getLoraRoot();
        if (!loraRoot) {
            showToast('toast.recipes.noLoraRootConfigured', {}, 'error');
            return;
        }

        // Generate batch download ID
        const batchDownloadId = Date.now().toString();
        
        // Use default paths
        const useDefaultPaths = true;

        // Set up WebSocket for progress updates
        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${batchDownloadId}`);

        // Show download progress UI
        const loadingManager = state.loadingManager;
        const updateProgress = loadingManager.showDownloadProgress(totalLoras);

        let completedDownloads = 0;
        let failedDownloads = 0;
        let currentLoraProgress = 0;

        // Set up WebSocket message handler
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Handle download ID confirmation
            if (data.type === 'download_id') {
                console.log(`Connected to batch download progress with ID: ${data.download_id}`);
                return;
            }

            // Process progress updates
            if (data.status === 'progress' && data.download_id && data.download_id.startsWith(batchDownloadId)) {
                currentLoraProgress = data.progress;
                
                const currentLora = lorasToDownload[completedDownloads + failedDownloads];
                const loraName = currentLora ? (currentLora.name || currentLora.file_name || 'Unknown') : '';

                const metrics = {
                    bytesDownloaded: data.bytes_downloaded,
                    totalBytes: data.total_bytes,
                    bytesPerSecond: data.bytes_per_second
                };

                updateProgress(currentLoraProgress, completedDownloads, loraName, metrics);

                // Update status message
                if (currentLoraProgress < 3) {
                    loadingManager.setStatus(
                        translate('recipes.controls.import.startingDownload', 
                            { current: completedDownloads + failedDownloads + 1, total: totalLoras },
                            `Starting download for LoRA ${completedDownloads + failedDownloads + 1}/${totalLoras}`
                        )
                    );
                } else if (currentLoraProgress > 3 && currentLoraProgress < 100) {
                    loadingManager.setStatus(
                        translate('recipes.controls.import.downloadingLoras', {}, `Downloading LoRAs...`)
                    );
                }
            }
        };

        // Wait for WebSocket to connect
        await new Promise((resolve, reject) => {
            ws.onopen = resolve;
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(error);
            };
        });

        // Download each LoRA sequentially
        for (let i = 0; i < lorasToDownload.length; i++) {
            const lora = lorasToDownload[i];
            
            currentLoraProgress = 0;
            
            loadingManager.setStatus(
                translate('recipes.controls.import.startingDownload', 
                    { current: i + 1, total: totalLoras },
                    `Starting download for LoRA ${i + 1}/${totalLoras}`
                )
            );
            updateProgress(0, completedDownloads, lora.name || lora.file_name || 'Unknown');

            try {
                const modelId = lora.modelId || lora.model_id;
                const versionId = lora.id || lora.modelVersionId;

                if (!modelId && !versionId) {
                    console.warn(`Skipping LoRA without model/version ID:`, lora);
                    failedDownloads++;
                    continue;
                }

                const response = await this.loraApiClient.downloadModel(
                    modelId,
                    versionId,
                    loraRoot,
                    '', // Empty relative path, use default paths
                    useDefaultPaths,
                    batchDownloadId
                );

                if (!response.success) {
                    console.error(`Failed to download LoRA ${lora.name || lora.file_name}: ${response.error}`);
                    failedDownloads++;
                } else {
                    completedDownloads++;
                    updateProgress(100, completedDownloads, '');
                }
            } catch (error) {
                console.error(`Error downloading LoRA ${lora.name || lora.file_name}:`, error);
                failedDownloads++;
            }
        }

        // Close WebSocket
        ws.close();

        // Hide loading UI
        loadingManager.hide();

        // Show completion message
        if (failedDownloads === 0) {
            showToast('toast.loras.allDownloadSuccessful', { count: completedDownloads }, 'success');
        } else {
            showToast('toast.loras.downloadPartialSuccess', {
                completed: completedDownloads,
                total: totalLoras
            }, 'warning');
        }

        // Refresh the recipes list to update LoRA status
        if (window.recipeManager) {
            window.recipeManager.loadRecipes();
        }
    }

    /**
     * Get LoRA root directory from API
     * @returns {Promise<string|null>} - LoRA root directory or null
     */
    async getLoraRoot() {
        try {
            // Fetch available LoRA roots from API
            const rootsData = await this.loraApiClient.fetchModelRoots();
            
            if (!rootsData || !rootsData.roots || rootsData.roots.length === 0) {
                console.error('No LoRA roots available');
                return null;
            }

            // Try to get default root from settings
            const defaultRootKey = 'default_lora_root';
            const defaultRoot = state.global?.settings?.[defaultRootKey];
            
            // If default root is set and exists in available roots, use it
            if (defaultRoot && rootsData.roots.includes(defaultRoot)) {
                return defaultRoot;
            }
            
            // Otherwise, return the first available root
            return rootsData.roots[0];
            
        } catch (error) {
            console.error('Error getting LoRA root:', error);
            return null;
        }
    }
}

// Export singleton instance
export const bulkMissingLoraDownloadManager = new BulkMissingLoraDownloadManager();

// Make available globally for HTML onclick handlers
if (typeof window !== 'undefined') {
    window.bulkMissingLoraDownloadManager = bulkMissingLoraDownloadManager;
}
