import { state, getCurrentPageState } from '../state/index.js';
import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { getStorageItem, getSessionItem, saveMapToStorage } from '../utils/storageHelpers.js';
import { 
    getCompleteApiConfig, 
    getCurrentModelType, 
    isValidModelType,
    DOWNLOAD_ENDPOINTS,
    WS_ENDPOINTS
} from './apiConfig.js';
import { resetAndReload } from './modelApiFactory.js';
import { sidebarManager } from '../components/SidebarManager.js';

/**
 * Abstract base class for all model API clients
 */
export class BaseModelApiClient {
    constructor(modelType = null) {
        if (this.constructor === BaseModelApiClient) {
            throw new Error("BaseModelApiClient is abstract and cannot be instantiated directly");
        }
        this.modelType = modelType || getCurrentModelType();
        this.apiConfig = getCompleteApiConfig(this.modelType);
    }

    /**
     * Set the model type for this client instance
     * @param {string} modelType - The model type to use
     */
    setModelType(modelType) {
        if (!isValidModelType(modelType)) {
            throw new Error(`Invalid model type: ${modelType}`);
        }
        this.modelType = modelType;
        this.apiConfig = getCompleteApiConfig(modelType);
    }

    /**
     * Get the current page state for this model type
     */
    getPageState() {
        const currentType = state.currentPageType;
        // Temporarily switch to get the right page state
        state.currentPageType = this.modelType;
        const pageState = getCurrentPageState();
        state.currentPageType = currentType; // Restore
        return pageState;
    }

    async fetchModelsPage(page = 1, pageSize = null) {
        const pageState = this.getPageState();
        const actualPageSize = pageSize || pageState.pageSize || this.apiConfig.config.defaultPageSize;
        
        try {
            const params = this._buildQueryParams({
                page,
                page_size: actualPageSize,
                sort_by: pageState.sortBy
            }, pageState);

            const response = await fetch(`${this.apiConfig.endpoints.list}?${params}`);
            if (!response.ok) {
                throw new Error(`Failed to fetch ${this.apiConfig.config.displayName}s: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            return {
                items: data.items,
                totalItems: data.total,
                totalPages: data.total_pages,
                currentPage: page,
                hasMore: page < data.total_pages,
                folders: data.folders
            };
            
        } catch (error) {
            console.error(`Error fetching ${this.apiConfig.config.displayName}s:`, error);
            showToast('toast.api.fetchFailed', { type: this.apiConfig.config.displayName, message: error.message }, 'error');
            throw error;
        }
    }

    async loadMoreWithVirtualScroll(resetPage = false, updateFolders = false) {
        const pageState = this.getPageState();
        
        try {
            state.loadingManager.showSimpleLoading(`Loading more ${this.apiConfig.config.displayName}s...`);

            pageState.isLoading = true;
            if (resetPage) {
                pageState.currentPage = 1; // Reset to first page
            }
            
            const result = await this.fetchModelsPage(pageState.currentPage, pageState.pageSize);
            
            state.virtualScroller.refreshWithData(
                result.items,
                result.totalItems,
                result.hasMore
            );
            
            pageState.hasMore = result.hasMore;
            pageState.currentPage = pageState.currentPage + 1;
            
            if (updateFolders) {
                sidebarManager.refresh();
            }
            
            return result;
        } catch (error) {
            console.error(`Error reloading ${this.apiConfig.config.displayName}s:`, error);
            showToast('toast.api.reloadFailed', { type: this.apiConfig.config.displayName, message: error.message }, 'error');
            throw error;
        } finally {
            pageState.isLoading = false;
            state.loadingManager.hide();
        }
    }

    async deleteModel(filePath) {
        try {
            state.loadingManager.showSimpleLoading(`Deleting ${this.apiConfig.config.singularName}...`);

            const response = await fetch(this.apiConfig.endpoints.delete, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                throw new Error(`Failed to delete ${this.apiConfig.config.singularName}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                if (state.virtualScroller) {
                    state.virtualScroller.removeItemByFilePath(filePath);
                }
                showToast('toast.api.deleteSuccess', { type: this.apiConfig.config.displayName }, 'success');
                return true;
            } else {
                throw new Error(data.error || `Failed to delete ${this.apiConfig.config.singularName}`);
            }
        } catch (error) {
            console.error(`Error deleting ${this.apiConfig.config.singularName}:`, error);
            showToast('toast.api.deleteFailed', { type: this.apiConfig.config.singularName, message: error.message }, 'error');
            return false;
        } finally {
            state.loadingManager.hide();
        }
    }

    async excludeModel(filePath) {
        try {
            state.loadingManager.showSimpleLoading(`Excluding ${this.apiConfig.config.singularName}...`);

            const response = await fetch(this.apiConfig.endpoints.exclude, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            
            if (!response.ok) {
                throw new Error(`Failed to exclude ${this.apiConfig.config.singularName}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                if (state.virtualScroller) {
                    state.virtualScroller.removeItemByFilePath(filePath);
                }
                showToast('toast.api.excludeSuccess', { type: this.apiConfig.config.displayName }, 'success');
                return true;
            } else {
                throw new Error(data.error || `Failed to exclude ${this.apiConfig.config.singularName}`);
            }
        } catch (error) {
            console.error(`Error excluding ${this.apiConfig.config.singularName}:`, error);
            showToast('toast.api.excludeFailed', { type: this.apiConfig.config.singularName, message: error.message }, 'error');
            return false;
        } finally {
            state.loadingManager.hide();
        }
    }

    async renameModelFile(filePath, newFileName) {
        try {
            state.loadingManager.showSimpleLoading(`Renaming ${this.apiConfig.config.singularName} file...`);
            
            const response = await fetch(this.apiConfig.endpoints.rename, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: filePath,
                    new_file_name: newFileName
                })
            });

            const result = await response.json();

            if (result.success) {
                state.virtualScroller.updateSingleItem(filePath, { 
                    file_name: newFileName, 
                    file_path: result.new_file_path,
                    preview_url: result.new_preview_path
                });
    
                showToast('toast.api.fileNameUpdated', {}, 'success');
            } else {
                showToast('toast.api.fileRenameFailed', { error: result.error || 'Unknown error' }, 'error');
            }

            return result;
        } catch (error) {
            console.error(`Error renaming ${this.apiConfig.config.singularName} file:`, error);
            throw error;
        } finally {
            state.loadingManager.hide();
        }
    }

    replaceModelPreview(filePath) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*,video/mp4';
        
        input.onchange = async () => {
            if (!input.files || !input.files[0]) return;
            
            const file = input.files[0];
            await this.uploadPreview(filePath, file);
        };
        
        input.click();
    }

    async uploadPreview(filePath, file, nsfwLevel = 0) {
        try {
            state.loadingManager.showSimpleLoading('Uploading preview...');
            
            const formData = new FormData();
            formData.append('preview_file', file);
            formData.append('model_path', filePath);
            formData.append('nsfw_level', nsfwLevel.toString());

            const response = await fetch(this.apiConfig.endpoints.replacePreview, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const data = await response.json();
            const pageState = this.getPageState();
            
            const timestamp = Date.now();
            if (pageState.previewVersions) {
                pageState.previewVersions.set(filePath, timestamp);
                
                const storageKey = `${this.modelType}_preview_versions`;
                saveMapToStorage(storageKey, pageState.previewVersions);
            }

            const updateData = {
                preview_url: data.preview_url,
                preview_nsfw_level: data.preview_nsfw_level
            };

            state.virtualScroller.updateSingleItem(filePath, updateData);
            showToast('toast.api.previewUpdated', {}, 'success');
        } catch (error) {
            console.error('Error uploading preview:', error);
            showToast('toast.api.previewUploadFailed', {}, 'error');
        } finally {
            state.loadingManager.hide();
        }
    }

    async saveModelMetadata(filePath, data) {
        try {
            state.loadingManager.showSimpleLoading('Saving metadata...');
            
            const response = await fetch(this.apiConfig.endpoints.save, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: filePath,
                    ...data
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save metadata');
            }

            state.virtualScroller.updateSingleItem(filePath, data);
            return response.json();
        } finally {
            state.loadingManager.hide();
        }
    }

    async addTags(filePath, data) {
        try {
            const response = await fetch(this.apiConfig.endpoints.addTags, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: filePath,
                    ...data
                })
            });

            if (!response.ok) {
                throw new Error('Failed to add tags');
            }

            const result = await response.json();

            if (result.success && result.tags) {
                state.virtualScroller.updateSingleItem(filePath, { tags: result.tags });
            }

            return result;
        } catch (error) {
            console.error('Error adding tags:', error);
            throw error;
        }
    }

    async refreshModels(fullRebuild = false) {
        try {
            state.loadingManager.showSimpleLoading(
                `${fullRebuild ? 'Full rebuild' : 'Refreshing'} ${this.apiConfig.config.displayName}s...`
            );
            
            const url = new URL(this.apiConfig.endpoints.scan, window.location.origin);
            url.searchParams.append('full_rebuild', fullRebuild);
            
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`Failed to refresh ${this.apiConfig.config.displayName}s: ${response.status} ${response.statusText}`);
            }

            resetAndReload(true);
            
            showToast('toast.api.refreshComplete', { action: fullRebuild ? 'Full rebuild' : 'Refresh' }, 'success');
        } catch (error) {
            console.error('Refresh failed:', error);
            showToast('toast.api.refreshFailed', { action: fullRebuild ? 'rebuild' : 'refresh', type: this.apiConfig.config.displayName }, 'error');
        } finally {
            state.loadingManager.hide();
            state.loadingManager.restoreProgressBar();
        }
    }

    async refreshSingleModelMetadata(filePath) {
        try {
            state.loadingManager.showSimpleLoading('Refreshing metadata...');
            
            const response = await fetch(this.apiConfig.endpoints.fetchCivitai, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });

            if (!response.ok) {
                throw new Error('Failed to refresh metadata');
            }

            const data = await response.json();
            
            if (data.success) {
                if (data.metadata && state.virtualScroller) {
                    state.virtualScroller.updateSingleItem(filePath, data.metadata);
                }

                showToast('toast.api.metadataRefreshed', {}, 'success');
                return true;
            } else {
                throw new Error(data.error || 'Failed to refresh metadata');
            }
        } catch (error) {
            console.error('Error refreshing metadata:', error);
            showToast('toast.api.metadataRefreshFailed', { message: error.message }, 'error');
            return false;
        } finally {
            state.loadingManager.hide();
            state.loadingManager.restoreProgressBar();
        }
    }

    async fetchCivitaiMetadata() {
        let ws = null;
        
        await state.loadingManager.showWithProgress(async (loading) => {
            try {
                const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(`${wsProtocol}${window.location.host}${WS_ENDPOINTS.fetchProgress}`);
                
                const operationComplete = new Promise((resolve, reject) => {
                    ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        
                        switch(data.status) {
                            case 'started':
                                loading.setStatus('Starting metadata fetch...');
                                break;
                                
                            case 'processing':
                                const percent = ((data.processed / data.total) * 100).toFixed(1);
                                loading.setProgress(percent);
                                loading.setStatus(
                                    `Processing (${data.processed}/${data.total}) ${data.current_name}`
                                );
                                break;
                                
                            case 'completed':
                                loading.setProgress(100);
                                loading.setStatus(
                                    `Completed: Updated ${data.success} of ${data.processed} ${this.apiConfig.config.displayName}s`
                                );
                                resolve();
                                break;
                                
                            case 'error':
                                reject(new Error(data.error));
                                break;
                        }
                    };
                    
                    ws.onerror = (error) => {
                        reject(new Error('WebSocket error: ' + error.message));
                    };
                });
                
                // Wait for WebSocket connection to establish
                await new Promise((resolve, reject) => {
                    ws.onopen = resolve;
                    ws.onerror = reject;
                });
                
                const response = await fetch(this.apiConfig.endpoints.fetchAllCivitai, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });
                
                if (!response.ok) {
                    throw new Error('Failed to fetch metadata');
                }
                
                // Wait for the operation to complete via WebSocket
                await operationComplete;

                resetAndReload(false);
                showToast('toast.api.metadataUpdateComplete', {}, 'success');
            } catch (error) {
                console.error('Error fetching metadata:', error);
                showToast('toast.api.metadataFetchFailed', { message: error.message }, 'error');
            } finally {
                if (ws) {
                    ws.close();
                }
            }
        }, {
            initialMessage: 'Connecting...',
            completionMessage: 'Metadata update complete'
        });
    }

    async refreshBulkModelMetadata(filePaths) {
        if (!filePaths || filePaths.length === 0) {
            throw new Error('No file paths provided');
        }

        const totalItems = filePaths.length;
        let processedCount = 0;
        let successCount = 0;
        let failedItems = [];

        const progressController = state.loadingManager.showEnhancedProgress('Starting metadata refresh...');

        try {
            for (let i = 0; i < filePaths.length; i++) {
                const filePath = filePaths[i];
                const fileName = filePath.split('/').pop();
                
                try {
                    const overallProgress = Math.floor((i / totalItems) * 100);
                    progressController.updateProgress(
                        overallProgress, 
                        fileName, 
                        `Processing ${i + 1}/${totalItems}: ${fileName}`
                    );
                    
                    const response = await fetch(this.apiConfig.endpoints.fetchCivitai, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file_path: filePath })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }

                    const data = await response.json();
                    
                    if (data.success) {
                        if (data.metadata && state.virtualScroller) {
                            state.virtualScroller.updateSingleItem(filePath, data.metadata);
                        }
                        successCount++;
                    } else {
                        throw new Error(data.error || 'Failed to refresh metadata');
                    }
                    
                } catch (error) {
                    console.error(`Error refreshing metadata for ${fileName}:`, error);
                    failedItems.push({ filePath, fileName, error: error.message });
                }
                
                processedCount++;
            }

            let completionMessage;
            if (successCount === totalItems) {
                completionMessage = translate('toast.api.bulkMetadataCompleteAll', { count: successCount, type: this.apiConfig.config.displayName }, `Successfully refreshed all ${successCount} ${this.apiConfig.config.displayName}s`);
                showToast('toast.api.bulkMetadataCompleteAll', { count: successCount, type: this.apiConfig.config.displayName }, 'success');
            } else if (successCount > 0) {
                completionMessage = translate('toast.api.bulkMetadataCompletePartial', { success: successCount, total: totalItems, type: this.apiConfig.config.displayName }, `Refreshed ${successCount} of ${totalItems} ${this.apiConfig.config.displayName}s`);
                showToast('toast.api.bulkMetadataCompletePartial', { success: successCount, total: totalItems, type: this.apiConfig.config.displayName }, 'warning');
                
                // if (failedItems.length > 0) {
                //     const failureMessage = failedItems.length <= 3 
                //         ? failedItems.map(item => `${item.fileName}: ${item.error}`).join('\n')
                //         : failedItems.slice(0, 3).map(item => `${item.fileName}: ${item.error}`).join('\n') + 
                //           `\n(and ${failedItems.length - 3} more)`;
                //     showToast('toast.api.bulkMetadataFailureDetails', { failures: failureMessage }, 'warning', 6000);
                // }
            } else {
                completionMessage = translate('toast.api.bulkMetadataCompleteNone', { type: this.apiConfig.config.displayName }, `Failed to refresh metadata for any ${this.apiConfig.config.displayName}s`);
                showToast('toast.api.bulkMetadataCompleteNone', { type: this.apiConfig.config.displayName }, 'error');
            }

            await progressController.complete(completionMessage);

            return {
                success: successCount > 0,
                total: totalItems,
                processed: processedCount,
                successful: successCount,
                failed: failedItems.length,
                errors: failedItems
            };

        } catch (error) {
            console.error('Error in bulk metadata refresh:', error);
            showToast('toast.api.bulkMetadataFailed', { message: error.message }, 'error');
            await progressController.complete('Operation failed');
            throw error;
        }
    }

    async refreshUpdatesForModels(modelIds, { force = false } = {}) {
        if (!Array.isArray(modelIds) || modelIds.length === 0) {
            throw new Error('No model IDs provided');
        }

        const response = await fetch(this.apiConfig.endpoints.refreshUpdates, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_ids: modelIds,
                force
            })
        });

        let payload = {};
        try {
            payload = await response.json();
        } catch (error) {
            console.warn('Unable to parse refresh updates response as JSON', error);
        }

        if (!response.ok || payload?.success !== true) {
            const message = payload?.error || response.statusText || 'Failed to refresh updates';
            throw new Error(message);
        }

        return payload;
    }

    async fetchCivitaiVersions(modelId, source = null) {
        try {
            let requestUrl = `${this.apiConfig.endpoints.civitaiVersions}/${modelId}`;
            if (source) {
                const params = new URLSearchParams({ source });
                requestUrl = `${requestUrl}?${params.toString()}`;
            }

            const response = await fetch(requestUrl);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                if (errorData && errorData.error && errorData.error.includes('Model type mismatch')) {
                    throw new Error(`This model is not a ${this.apiConfig.config.displayName}. Please switch to the appropriate page to download this model type.`);
                }
                throw new Error('Failed to fetch model versions');
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching Civitai versions:', error);
            throw error;
        }
    }

    async fetchModelUpdateVersions(modelId, { refresh = false, force = false } = {}) {
        try {
            const params = new URLSearchParams();
            if (refresh) params.append('refresh', 'true');
            if (force) params.append('force', 'true');
            const query = params.toString();
            const requestUrl = `${this.apiConfig.endpoints.modelUpdateVersions}/${modelId}${query ? `?${query}` : ''}`;

            const response = await fetch(requestUrl);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || 'Failed to fetch model versions');
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching model update versions:', error);
            throw error;
        }
    }

    async setModelUpdateIgnore(modelId, shouldIgnore) {
        try {
            const response = await fetch(this.apiConfig.endpoints.ignoreModelUpdate, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    modelId,
                    shouldIgnore,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || 'Failed to update model ignore status');
            }

            return await response.json();
        } catch (error) {
            console.error('Error updating model ignore status:', error);
            throw error;
        }
    }

    async setVersionUpdateIgnore(modelId, versionId, shouldIgnore) {
        try {
            const response = await fetch(this.apiConfig.endpoints.ignoreVersionUpdate, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    modelId,
                    versionId,
                    shouldIgnore,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || 'Failed to update version ignore status');
            }

            return await response.json();
        } catch (error) {
            console.error('Error updating version ignore status:', error);
            throw error;
        }
    }

    async fetchModelRoots() {
        try {
            const response = await fetch(this.apiConfig.endpoints.roots);
            if (!response.ok) {
                throw new Error(`Failed to fetch ${this.apiConfig.config.displayName} roots`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching model roots:', error);
            throw error;
        }
    }

    async fetchModelFolders() {
        try {
            const response = await fetch(this.apiConfig.endpoints.folders);
            if (!response.ok) {
                throw new Error(`Failed to fetch ${this.apiConfig.config.displayName} folders`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching model folders:', error);
            throw error;
        }
    }

    async fetchUnifiedFolderTree() {
        try {
            const response = await fetch(this.apiConfig.endpoints.unifiedFolderTree);
            if (!response.ok) {
                throw new Error(`Failed to fetch unified folder tree`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching unified folder tree:', error);
            throw error;
        }
    }

    async fetchFolderTree(modelRoot) {
        try {
            const params = new URLSearchParams({ model_root: modelRoot });
            const response = await fetch(`${this.apiConfig.endpoints.folderTree}?${params}`);
            if (!response.ok) {
                throw new Error(`Failed to fetch folder tree for root: ${modelRoot}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching folder tree:', error);
            throw error;
        }
    }

    async downloadModel(modelId, versionId, modelRoot, relativePath, useDefaultPaths = false, downloadId, source = null) {
        try {
            const response = await fetch(DOWNLOAD_ENDPOINTS.download, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_id: modelId,
                    model_version_id: versionId,
                    model_root: modelRoot,
                    relative_path: relativePath,
                    use_default_paths: useDefaultPaths,
                    download_id: downloadId,
                    ...(source ? { source } : {})
                })
            });

            if (!response.ok) {
                throw new Error(await response.text());
            }

            return await response.json();
        } catch (error) {
            console.error('Error downloading model:', error);
            throw error;
        }
    }

    _buildQueryParams(baseParams, pageState) {
        const params = new URLSearchParams(baseParams);
        
        if (pageState.activeFolder !== null) {
            params.append('folder', pageState.activeFolder);
        }

        if (pageState.showFavoritesOnly) {
            params.append('favorites_only', 'true');
        }

        if (pageState.showUpdateAvailableOnly) {
            params.append('update_available_only', 'true');
        }

        if (this.apiConfig.config.supportsLetterFilter && pageState.activeLetterFilter) {
            params.append('first_letter', pageState.activeLetterFilter);
        }

        if (pageState.filters?.search) {
            params.append('search', pageState.filters.search);
            params.append('fuzzy', 'true');
            
            if (pageState.searchOptions) {
                params.append('search_filename', pageState.searchOptions.filename.toString());
                params.append('search_modelname', pageState.searchOptions.modelname.toString());
                if (pageState.searchOptions.tags !== undefined) {
                    params.append('search_tags', pageState.searchOptions.tags.toString());
                }
                if (pageState.searchOptions.creator !== undefined) {
                    params.append('search_creator', pageState.searchOptions.creator.toString());
                }
            }
        }

        params.append('recursive', pageState.searchOptions.recursive ? 'true' : 'false');
        
        if (pageState.filters) {
            if (pageState.filters.tags && pageState.filters.tags.length > 0) {
                pageState.filters.tags.forEach(tag => {
                    params.append('tag', tag);
                });
            }
            
            if (pageState.filters.baseModel && pageState.filters.baseModel.length > 0) {
                pageState.filters.baseModel.forEach(model => {
                    params.append('base_model', model);
                });
            }
        }

        this._addModelSpecificParams(params, pageState);

        return params;
    }

    _addModelSpecificParams(params, pageState) {
        if (this.modelType === 'loras') {
            const filterLoraHash = getSessionItem('recipe_to_lora_filterLoraHash');
            const filterLoraHashes = getSessionItem('recipe_to_lora_filterLoraHashes');

            if (filterLoraHash) {
                params.append('lora_hash', filterLoraHash);
            } else if (filterLoraHashes) {
                try {
                    if (Array.isArray(filterLoraHashes) && filterLoraHashes.length > 0) {
                        params.append('lora_hashes', filterLoraHashes.join(','));
                    }
                } catch (error) {
                    console.error('Error parsing lora hashes from session storage:', error);
                }
            }
        }
    }

    async moveSingleModel(filePath, targetPath) {
        // Only allow move if supported
        if (!this.apiConfig.config.supportsMove) {
            showToast('toast.api.moveNotSupported', { type: this.apiConfig.config.displayName }, 'warning');
            return null;
        }
        if (filePath.substring(0, filePath.lastIndexOf('/')) === targetPath) {
            showToast('toast.api.alreadyInFolder', { type: this.apiConfig.config.displayName }, 'info');
            return null;
        }

        const response = await fetch(this.apiConfig.endpoints.moveModel, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_path: filePath,
                target_path: targetPath
            })
        });

        const result = await response.json();

        if (!response.ok) {
            if (result && result.error) {
                throw new Error(result.error);
            }
            throw new Error(`Failed to move ${this.apiConfig.config.displayName}`);
        }

        if (result && result.message) {
            showToast('toast.api.moveInfo', { message: result.message }, 'info');
        } else {
            showToast('toast.api.moveSuccess', { type: this.apiConfig.config.displayName }, 'success');
        }

        if (result.success) {
            return {
                original_file_path: result.original_file_path || filePath,
                new_file_path: result.new_file_path
            };
        }
        return null;
    }

    async moveBulkModels(filePaths, targetPath) {
        if (!this.apiConfig.config.supportsMove) {
            showToast('toast.api.bulkMoveNotSupported', { type: this.apiConfig.config.displayName }, 'warning');
            return [];
        }
        const movedPaths = filePaths.filter(path => {
            return path.substring(0, path.lastIndexOf('/')) !== targetPath;
        });

        if (movedPaths.length === 0) {
            showToast('toast.api.allAlreadyInFolder', { type: this.apiConfig.config.displayName }, 'info');
            return [];
        }

        const response = await fetch(this.apiConfig.endpoints.moveBulk, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_paths: movedPaths,
                target_path: targetPath
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(`Failed to move ${this.apiConfig.config.displayName}s`);
        }

        if (result.success) {
            if (result.failure_count > 0) {
                showToast('toast.api.bulkMovePartial', { 
                    successCount: result.success_count, 
                    type: this.apiConfig.config.displayName, 
                    failureCount: result.failure_count 
                }, 'warning');
                console.log('Move operation results:', result.results);
                const failedFiles = result.results
                    .filter(r => !r.success)
                    .map(r => {
                        const fileName = r.original_file_path.substring(r.original_file_path.lastIndexOf('/') + 1);
                        return `${fileName}: ${r.message}`;
                    });
                if (failedFiles.length > 0) {
                    const failureMessage = failedFiles.length <= 3 
                        ? failedFiles.join('\n')
                        : failedFiles.slice(0, 3).join('\n') + `\n(and ${failedFiles.length - 3} more)`;
                    showToast('toast.api.bulkMoveFailures', { failures: failureMessage }, 'warning', 6000);
                }
            } else {
                showToast('toast.api.bulkMoveSuccess', { 
                    successCount: result.success_count, 
                    type: this.apiConfig.config.displayName 
                }, 'success');
            }
            
            // Return the results array with original_file_path and new_file_path
            return result.results || [];
        } else {
            throw new Error(result.message || `Failed to move ${this.apiConfig.config.displayName}s`);
        }
    }

    async bulkDeleteModels(filePaths) {
        if (!filePaths || filePaths.length === 0) {
            throw new Error('No file paths provided');
        }

        try {
            state.loadingManager.showSimpleLoading(`Deleting ${this.apiConfig.config.displayName.toLowerCase()}s...`);
            
            const response = await fetch(this.apiConfig.endpoints.bulkDelete, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_paths: filePaths
                })
            });
            
            if (!response.ok) {
                throw new Error(`Failed to delete ${this.apiConfig.config.displayName.toLowerCase()}s: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                return {
                    success: true,
                    deleted_count: result.deleted_count,
                    failed_count: result.failed_count || 0,
                    errors: result.errors || []
                };
            } else {
                throw new Error(result.error || `Failed to delete ${this.apiConfig.config.displayName.toLowerCase()}s`);
            }
        } catch (error) {
            console.error(`Error during bulk delete of ${this.apiConfig.config.displayName.toLowerCase()}s:`, error);
            throw error;
        } finally {
            state.loadingManager.hide();
        }
    }

    async downloadExampleImages(modelHashes, modelTypes = null) {
        let ws = null;
        
        await state.loadingManager.showWithProgress(async (loading) => {
            try {
                // Connect to WebSocket for progress updates
                const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(`${wsProtocol}${window.location.host}${WS_ENDPOINTS.fetchProgress}`);
                
                const operationComplete = new Promise((resolve, reject) => {
                    ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        
                        if (data.type !== 'example_images_progress') return;
                        
                        switch(data.status) {
                            case 'running':
                                const percent = ((data.processed / data.total) * 100).toFixed(1);
                                loading.setProgress(percent);
                                loading.setStatus(
                                    `Processing (${data.processed}/${data.total}) ${data.current_model || ''}`
                                );
                                break;
                                
                            case 'completed':
                                loading.setProgress(100);
                                loading.setStatus(
                                    `Completed: Downloaded example images for ${data.processed} models`
                                );
                                resolve();
                                break;
                                
                            case 'error':
                                reject(new Error(data.error));
                                break;
                        }
                    };
                    
                    ws.onerror = (error) => {
                        reject(new Error('WebSocket error: ' + error.message));
                    };
                });
                
                // Wait for WebSocket connection to establish
                await new Promise((resolve, reject) => {
                    ws.onopen = resolve;
                    ws.onerror = reject;
                });
                
                // Get the output directory from state
                const outputDir = state.global?.settings?.example_images_path || '';
                if (!outputDir) {
                    throw new Error('Please set the example images path in the settings first.');
                }
                
                // Determine optimize setting
                const optimize = state.global?.settings?.optimize_example_images ?? true;
                
                // Make the API request to start the download process
                const response = await fetch(DOWNLOAD_ENDPOINTS.exampleImages, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        model_hashes: modelHashes,
                        output_dir: outputDir,
                        optimize: optimize,
                        model_types: modelTypes || [this.apiConfig.config.singularName]
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Failed to download example images');
                }
                
                // Wait for the operation to complete via WebSocket
                await operationComplete;
                
                showToast('toast.api.exampleImagesDownloadSuccess', {}, 'success');
                return true;
                
            } catch (error) {
                console.error('Error downloading example images:', error);
                showToast('toast.api.exampleImagesDownloadFailed', { message: error.message }, 'error');
                throw error;
            } finally {
                if (ws) {
                    ws.close();
                }
            }
        }, {
            initialMessage: 'Starting example images download...',
            completionMessage: 'Example images download complete'
        });
    }

    async fetchModelMetadata(filePath) {
        try {
            const params = new URLSearchParams({ file_path: filePath });
            const response = await fetch(`${this.apiConfig.endpoints.metadata}?${params}`);
            
            if (!response.ok) {
                throw new Error(`Failed to fetch ${this.apiConfig.config.singularName} metadata: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                return data.metadata;
            } else {
                throw new Error(data.error || `No metadata found for ${this.apiConfig.config.singularName}`);
            }
        } catch (error) {
            console.error(`Error fetching ${this.apiConfig.config.singularName} metadata:`, error);
            throw error;
        }
    }

    async fetchModelDescription(filePath) {
        try {
            const params = new URLSearchParams({ file_path: filePath });
            const response = await fetch(`${this.apiConfig.endpoints.modelDescription}?${params}`);
            
            if (!response.ok) {
                throw new Error(`Failed to fetch ${this.apiConfig.config.singularName} description: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                return data.description;
            } else {
                throw new Error(data.error || `No description found for ${this.apiConfig.config.singularName}`);
            }
        } catch (error) {
            console.error(`Error fetching ${this.apiConfig.config.singularName} description:`, error);
            throw error;
        }
    }

    /**
     * Auto-organize models based on current path template settings
     * @param {Array} filePaths - Optional array of file paths to organize. If not provided, organizes all models.
     * @returns {Promise} - Promise that resolves when the operation is complete
     */
    async autoOrganizeModels(filePaths = null) {
        let ws = null;
        
        await state.loadingManager.showWithProgress(async (loading) => {
            try {
                // Connect to WebSocket for progress updates
                const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                ws = new WebSocket(`${wsProtocol}${window.location.host}${WS_ENDPOINTS.fetchProgress}`);
                
                const operationComplete = new Promise((resolve, reject) => {
                    ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        
                        if (data.type !== 'auto_organize_progress') return;
                        
                        switch(data.status) {
                            case 'started':
                                loading.setProgress(0);
                                const operationType = data.operation_type === 'bulk' ? 'selected models' : 'all models';
                                loading.setStatus(translate('loras.bulkOperations.autoOrganizeProgress.starting', { type: operationType }, `Starting auto-organize for ${operationType}...`));
                                break;
                                
                            case 'processing':
                                const percent = data.total > 0 ? ((data.processed / data.total) * 90).toFixed(1) : 0;
                                loading.setProgress(percent);
                                loading.setStatus(
                                    translate('loras.bulkOperations.autoOrganizeProgress.processing', {
                                        processed: data.processed,
                                        total: data.total,
                                        success: data.success,
                                        failures: data.failures,
                                        skipped: data.skipped
                                    }, `Processing (${data.processed}/${data.total}) - ${data.success} moved, ${data.skipped} skipped, ${data.failures} failed`)
                                );
                                break;
                                
                            case 'cleaning':
                                loading.setProgress(95);
                                loading.setStatus(translate('loras.bulkOperations.autoOrganizeProgress.cleaning', {}, 'Cleaning up empty directories...'));
                                break;
                                
                            case 'completed':
                                loading.setProgress(100);
                                loading.setStatus(
                                    translate('loras.bulkOperations.autoOrganizeProgress.completed', {
                                        success: data.success,
                                        skipped: data.skipped,
                                        failures: data.failures,
                                        total: data.total
                                    }, `Completed: ${data.success} moved, ${data.skipped} skipped, ${data.failures} failed`)
                                );
                                
                                setTimeout(() => {
                                    resolve(data);
                                }, 1500);
                                break;
                                
                            case 'error':
                                loading.setStatus(translate('loras.bulkOperations.autoOrganizeProgress.error', { error: data.error }, `Error: ${data.error}`));
                                reject(new Error(data.error));
                                break;
                        }
                    };
                    
                    ws.onerror = (error) => {
                        console.error('WebSocket error during auto-organize:', error);
                        reject(new Error('Connection error'));
                    };
                });
                
                // Start the auto-organize operation
                const endpoint = this.apiConfig.endpoints.autoOrganize;
                const requestOptions = {
                    method: filePaths ? 'POST' : 'GET',
                    headers: filePaths ? { 'Content-Type': 'application/json' } : {}
                };
                
                if (filePaths) {
                    requestOptions.body = JSON.stringify({ file_paths: filePaths });
                }
                
                const response = await fetch(endpoint, requestOptions);
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Failed to start auto-organize operation');
                }
                
                // Wait for the operation to complete via WebSocket
                const result = await operationComplete;
                
                // Show appropriate success message based on results
                if (result.failures === 0) {
                    showToast('toast.loras.autoOrganizeSuccess', { 
                        count: result.success,
                        type: result.operation_type === 'bulk' ? 'selected models' : 'all models'
                    }, 'success');
                } else {
                    showToast('toast.loras.autoOrganizePartialSuccess', { 
                        success: result.success,
                        failures: result.failures,
                        total: result.total
                    }, 'warning');
                }
                
            } catch (error) {
                console.error('Error during auto-organize:', error);
                showToast('toast.loras.autoOrganizeFailed', { error: error.message }, 'error');
                throw error;
            } finally {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
            }
        }, {
            initialMessage: translate('loras.bulkOperations.autoOrganizeProgress.initializing', {}, 'Initializing auto-organize...'),
            completionMessage: translate('loras.bulkOperations.autoOrganizeProgress.complete', {}, 'Auto-organize complete')
        });
    }
}
