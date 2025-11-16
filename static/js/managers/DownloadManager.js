import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { state } from '../state/index.js';
import { LoadingManager } from './LoadingManager.js';
import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { FolderTreeManager } from '../components/FolderTreeManager.js';
import { translate } from '../utils/i18nHelpers.js';

export class DownloadManager {
    constructor() {
        this.currentVersion = null;
        this.versions = [];
        this.modelInfo = null;
        this.modelVersionId = null;
        this.modelId = null;
        this.source = null;
        
        this.initialized = false;
        this.selectedFolder = '';
        this.apiClient = null;
        this.useDefaultPath = false;
        
        this.loadingManager = new LoadingManager();
        this.folderTreeManager = new FolderTreeManager();
        this.folderClickHandler = null;
        this.updateTargetPath = this.updateTargetPath.bind(this);
        this.queuePollInterval = null; // Interval for polling download queue
        this.currentDownloadId = null; // Track the current active download ID for cancellation
        
        // Bound methods for event handling
        this.handleValidateAndFetchVersions = this.validateAndFetchVersions.bind(this);
        this.handleProceedToLocation = this.proceedToLocation.bind(this);
        this.handleStartDownload = this.startDownload.bind(this);
        this.handleBackToUrl = this.backToUrl.bind(this);
        this.handleBackToVersions = this.backToVersions.bind(this);
        this.handleCloseModal = this.closeModal.bind(this);
        this.handleToggleDefaultPath = this.toggleDefaultPath.bind(this);
    }

    showDownloadModal() {
        console.log('Showing unified download modal...');
        
        // Get API client for current page type
        this.apiClient = getModelApiClient();
        const config = this.apiClient.apiConfig.config;
        
        if (!this.initialized) {
            const modal = document.getElementById('downloadModal');
            if (!modal) {
                console.error('Unified download modal element not found');
                return;
            }
            this.initializeEventHandlers();
            this.initialized = true;
        }
        
        // Update modal title and labels based on model type
        this.updateModalLabels();
        
        modalManager.showModal('downloadModal', null, () => {
            this.cleanupFolderBrowser();
        });
        this.resetSteps();
        
        // Auto-focus on the URL input
        setTimeout(() => {
            const urlInput = document.getElementById('modelUrl');
            if (urlInput) {
                urlInput.focus();
            }
        }, 100);
    }

    initializeEventHandlers() {
        // Button event handlers
        document.getElementById('nextFromUrl').addEventListener('click', this.handleValidateAndFetchVersions);
        document.getElementById('nextFromVersion').addEventListener('click', this.handleProceedToLocation);
        document.getElementById('startDownloadBtn').addEventListener('click', this.handleStartDownload);
        document.getElementById('backToUrlBtn').addEventListener('click', this.handleBackToUrl);
        document.getElementById('backToVersionsBtn').addEventListener('click', this.handleBackToVersions);
        document.getElementById('closeDownloadModal').addEventListener('click', this.handleCloseModal);
        
        // Default path toggle handler
        document.getElementById('useDefaultPath').addEventListener('change', this.handleToggleDefaultPath);
    }

    updateModalLabels() {
        const config = this.apiClient.apiConfig.config;
        
        // Update modal title
        document.getElementById('downloadModalTitle').textContent = translate('modals.download.titleWithType', { type: config.displayName });
        
        // Update URL label
        document.getElementById('modelUrlLabel').textContent = translate('modals.download.civitaiUrl');
        
        // Update root selection label
        document.getElementById('modelRootLabel').textContent = translate('modals.download.selectTypeRoot', { type: config.displayName });
        
        // Update path preview labels
        const pathLabels = document.querySelectorAll('.path-preview label');
        pathLabels.forEach(label => {
            if (label.textContent.includes('Location Preview')) {
                label.textContent = translate('modals.download.locationPreview') + ':';
            }
        });
        
        // Update initial path text
        const pathText = document.querySelector('#targetPathDisplay .path-text');
        if (pathText) {
            pathText.textContent = translate('modals.download.selectTypeRoot', { type: config.displayName });
        }
    }

    resetSteps() {
        document.querySelectorAll('.download-step').forEach(step => step.style.display = 'none');
        document.getElementById('urlStep').style.display = 'block';
        document.getElementById('modelUrl').value = '';
        document.getElementById('urlError').textContent = '';
        
        // Clear folder path input
        const folderPathInput = document.getElementById('folderPath');
        if (folderPathInput) {
            folderPathInput.value = '';
        }
        
        this.currentVersion = null;
        this.versions = [];
        this.modelInfo = null;
        this.modelId = null;
        this.modelVersionId = null;
        this.source = null;
        
        this.selectedFolder = '';
        
        // Clear folder tree selection
        if (this.folderTreeManager) {
            this.folderTreeManager.clearSelection();
        }
        
        // Reset default path toggle
        this.loadDefaultPathSetting();
    }

    async retrieveVersionsForModel(modelId, source = null) {
        this.versions = await this.apiClient.fetchCivitaiVersions(modelId, source);
        if (!this.versions || !this.versions.length) {
            throw new Error(translate('modals.download.errors.noVersions'));
        }
        return this.versions;
    }

    async validateAndFetchVersions() {
        const url = document.getElementById('modelUrl').value.trim();
        const errorElement = document.getElementById('urlError');
        
        try {
            this.loadingManager.showSimpleLoading(translate('modals.download.fetchingVersions'));
            
            this.modelId = this.extractModelId(url);
            if (!this.modelId) {
                throw new Error(translate('modals.download.errors.invalidUrl'));
            }

            await this.retrieveVersionsForModel(this.modelId, this.source);

            // If we have a version ID from URL, pre-select it
            if (this.modelVersionId) {
                this.currentVersion = this.versions.find(v => v.id.toString() === this.modelVersionId);
            }
            
            this.showVersionStep();
        } catch (error) {
            errorElement.textContent = error.message;
        } finally {
            this.loadingManager.hide();
        }
    }

    async fetchVersionsForCurrentModel() {
        const errorElement = document.getElementById('urlError');
        if (errorElement) {
            errorElement.textContent = '';
        }
        try {
            this.loadingManager.showSimpleLoading(translate('modals.download.fetchingVersions'));
            await this.retrieveVersionsForModel(this.modelId, this.source);
            if (this.modelVersionId) {
                this.currentVersion = this.versions.find(v => v.id.toString() === this.modelVersionId);
            }
            this.showVersionStep();
        } catch (error) {
            if (errorElement) {
                errorElement.textContent = error.message;
            }
        } finally {
            this.loadingManager.hide();
        }
    }

    extractModelId(url) {
        const versionMatch = url.match(/modelVersionId=(\d+)/i);
        this.modelVersionId = versionMatch ? versionMatch[1] : null;

        const civarchiveMatch = url.match(/https?:\/\/(?:www\.)?(?:civitaiarchive|civarchive)\.com\/models\/(\d+)/i);
        if (civarchiveMatch) {
            this.source = 'civarchive';
            return civarchiveMatch[1];
        }

        const civitaiMatch = url.match(/https?:\/\/(?:www\.)?civitai\.com\/models\/(\d+)/i);
        if (civitaiMatch) {
            this.source = null;
            return civitaiMatch[1];
        }

        this.source = null;
        return null;
    }

    async openForModelVersion(modelType, modelId, versionId = null) {
        try {
            this.apiClient = getModelApiClient(modelType);
        } catch (error) {
            this.apiClient = getModelApiClient();
        }

        this.showDownloadModal();

        this.modelId = modelId ? modelId.toString() : null;
        this.modelVersionId = versionId ? versionId.toString() : null;
        this.source = null;

        if (!this.modelId) {
            return;
        }

        await this.fetchVersionsForCurrentModel();
    }

    showVersionStep() {
        document.getElementById('urlStep').style.display = 'none';
        document.getElementById('versionStep').style.display = 'block';
        
        const versionList = document.getElementById('versionList');
        versionList.innerHTML = this.versions.map(version => {
            const firstImage = version.images?.find(img => !img.url.endsWith('.mp4'));
            const thumbnailUrl = firstImage ? firstImage.url : '/loras_static/images/no-preview.png';
            
            const fileSize = version.modelSizeKB ? 
                (version.modelSizeKB / 1024).toFixed(2) : 
                (version.files[0]?.sizeKB / 1024).toFixed(2);
            
            const existsLocally = version.existsLocally;
            const localPath = version.localPath;
            const isEarlyAccess = version.availability === 'EarlyAccess';
            
            let earlyAccessBadge = '';
            if (isEarlyAccess) {
                earlyAccessBadge = `
                    <div class="early-access-badge" title="${translate('modals.download.earlyAccessTooltip')}">
                        <i class="fas fa-clock"></i> ${translate('modals.download.earlyAccess')}
                    </div>
                `;
            }
            
            const localStatus = existsLocally ? 
                `<div class="local-badge">
                    <i class="fas fa-check"></i> ${translate('modals.download.inLibrary')}
                    <div class="local-path">${localPath || ''}</div>
                 </div>` : '';

            return `
                <div class="version-item ${this.currentVersion?.id === version.id ? 'selected' : ''} 
                     ${existsLocally ? 'exists-locally' : ''} 
                     ${isEarlyAccess ? 'is-early-access' : ''}"
                     data-version-id="${version.id}">
                    <div class="version-thumbnail">
                        <img src="${thumbnailUrl}" alt="${translate('modals.download.versionPreview')}">
                    </div>
                    <div class="version-content">
                        <div class="version-header">
                            <h3>${version.name}</h3>
                            ${localStatus}
                        </div>
                        <div class="version-info">
                            ${version.baseModel ? `<div class="base-model">${version.baseModel}</div>` : ''}
                            ${earlyAccessBadge}
                        </div>
                        <div class="version-meta">
                            <span><i class="fas fa-calendar"></i> ${new Date(version.createdAt).toLocaleDateString()}</span>
                            <span><i class="fas fa-file-archive"></i> ${fileSize} MB</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        
        // Add click handlers for version selection
        versionList.addEventListener('click', (event) => {
            const versionItem = event.target.closest('.version-item');
            if (versionItem) {
                this.selectVersion(versionItem.dataset.versionId);
            }
        });
        
        // Auto-select the version if there's only one
        if (this.versions.length === 1 && !this.currentVersion) {
            this.selectVersion(this.versions[0].id.toString());
        }
        
        this.updateNextButtonState();
    }

    selectVersion(versionId) {
        this.currentVersion = this.versions.find(v => v.id.toString() === versionId.toString());
        if (!this.currentVersion) return;

        document.querySelectorAll('.version-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.versionId === versionId);
        });
        
        this.updateNextButtonState();
    }
    
    updateNextButtonState() {
        const nextButton = document.getElementById('nextFromVersion');
        if (!nextButton) return;
        
        const existsLocally = this.currentVersion?.existsLocally;
        
        if (existsLocally) {
            nextButton.disabled = true;
            nextButton.classList.add('disabled');
            nextButton.textContent = translate('modals.download.alreadyInLibrary');
        } else {
            nextButton.disabled = false;
            nextButton.classList.remove('disabled');
            nextButton.textContent = translate('common.actions.next');
        }
    }

    async proceedToLocation() {
        if (!this.currentVersion) {
            showToast('toast.loras.pleaseSelectVersion', {}, 'error');
            return;
        }
        
        const existsLocally = this.currentVersion.existsLocally;
        if (existsLocally) {
            showToast('toast.loras.versionExists', {}, 'info');
            return;
        }

        document.getElementById('versionStep').style.display = 'none';
        document.getElementById('locationStep').style.display = 'block';
        
        try {
            // Fetch model roots
            const rootsData = await this.apiClient.fetchModelRoots();
            const modelRoot = document.getElementById('modelRoot');
            modelRoot.innerHTML = rootsData.roots.map(root => 
                `<option value="${root}">${root}</option>`
            ).join('');

            // Set default root if available
            const singularType = this.apiClient.modelType.replace(/s$/, '');
            const defaultRootKey = `default_${singularType}_root`;
            const defaultRoot = state.global.settings[defaultRootKey];
            console.log(`Default root for ${this.apiClient.modelType}:`, defaultRoot);
            console.log('Available roots:', rootsData.roots);
            if (defaultRoot && rootsData.roots.includes(defaultRoot)) {
                console.log(`Setting default root: ${defaultRoot}`);
                modelRoot.value = defaultRoot;
            }

            // Set autocomplete="off" on folderPath input
            const folderPathInput = document.getElementById('folderPath');
            if (folderPathInput) {
                folderPathInput.setAttribute('autocomplete', 'off');
            }

            // Initialize folder tree
            await this.initializeFolderTree();
            
            // Setup folder tree manager
            this.folderTreeManager.init({
                onPathChange: (path) => {
                    this.selectedFolder = path;
                    this.updateTargetPath();
                }
            });
            
            // Setup model root change handler
            modelRoot.addEventListener('change', async () => {
                await this.initializeFolderTree();
                this.updateTargetPath();
            });
            
            // Load default path setting for current model type
            this.loadDefaultPathSetting();
            
            this.updateTargetPath();
        } catch (error) {
            showToast('toast.downloads.loadError', { message: error.message }, 'error');
        }
    }

    loadDefaultPathSetting() {
        const modelType = this.apiClient.modelType;
        const storageKey = `use_default_path_${modelType}`;
        this.useDefaultPath = getStorageItem(storageKey, false);
        
        const toggleInput = document.getElementById('useDefaultPath');
        if (toggleInput) {
            toggleInput.checked = this.useDefaultPath;
            this.updatePathSelectionUI();
        }
    }

    toggleDefaultPath(event) {
        this.useDefaultPath = event.target.checked;
        
        // Save to localStorage per model type
        const modelType = this.apiClient.modelType;
        const storageKey = `use_default_path_${modelType}`;
        setStorageItem(storageKey, this.useDefaultPath);
        
        this.updatePathSelectionUI();
        this.updateTargetPath();
    }

    async executeDownloadWithProgress({
        modelId,
        versionId,
        versionName = '',
        modelRoot = '',
        targetFolder = '',
        useDefaultPaths = false,
        source = null,
        closeModal = false,
    }) {
        const config = this.apiClient?.apiConfig?.config;

        if (!this.apiClient || !config) {
            throw new Error('Download manager is not initialized with an API client');
        }

        const displayName = versionName || `#${versionId}`;
        let ws = null;
        let updateProgress = () => {};
        let downloadId = Date.now().toString(); // Use let so it can be updated
        
        // Store current download ID for cancellation
        this.currentDownloadId = downloadId;

        try {
            this.loadingManager.restoreProgressBar();
            // Set up remove callback
            this.loadingManager.onRemoveCallback = async (removeDownloadId) => {
                await this.removeQueuedDownload(removeDownloadId);
            };
            // Set up cancel callback that uses the current active download ID
            // This will be updated in updateQueueDisplay when the active download changes
            const cancelHandler = () => {
                // Always use the current active download ID from loadingManager
                // This gets updated when updateQueueDisplay runs
                const activeId = this.loadingManager.activeDownloadId || this.currentDownloadId || downloadId;
                console.log('Cancel button clicked, canceling download:', activeId);
                this.cancelDownload(activeId);
            };
            updateProgress = this.loadingManager.showDownloadProgress(1, cancelHandler);
            this.currentUpdateProgress = updateProgress; // Store reference for queue updates
            updateProgress(0, 0, displayName);
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);

            // Start polling for queue updates
            this.startQueuePolling();

            ws.onmessage = event => {
                const data = JSON.parse(event.data);
                console.log('WebSocket message received:', data); // Debug log

                if (data.type === 'download_id') {
                    // Update downloadId to match backend's ID
                    const backendDownloadId = data.download_id;
                    console.log(`Connected to download progress with ID: ${backendDownloadId}`);
                    // Use backend's download_id for matching messages
                    if (backendDownloadId && backendDownloadId !== downloadId) {
                        console.log(`Updating downloadId from ${downloadId} to ${backendDownloadId}`);
                        downloadId = backendDownloadId;
                        this.currentDownloadId = backendDownloadId; // Update tracked download ID
                    }
                    return;
                }

                // Match by download_id - only update if this matches the active download
                // The queue polling will handle updating the main display with the correct active download
                if (data.status === 'progress' && data.download_id) {
                    // Update downloadId if we receive a message with a different ID (backend might have generated one)
                    if (data.download_id !== downloadId) {
                        downloadId = data.download_id;
                        this.currentDownloadId = data.download_id; // Update tracked download ID
                    }
                    
                    // Only update if this is the active download (queue polling handles the main display)
                    // WebSocket messages are used for real-time updates, but queue polling ensures correct active download
                    const activeDownloadId = this.loadingManager.activeDownloadId;
                    if (!activeDownloadId || data.download_id === activeDownloadId) {
                        const metrics = {
                            bytesDownloaded: data.bytes_downloaded,
                            totalBytes: data.total_bytes,
                            bytesPerSecond: data.bytes_per_second,
                        };

                        updateProgress(data.progress, 0, displayName, metrics);

                        if (data.progress < 3) {
                            this.loadingManager.setStatus(translate('modals.download.status.preparing'));
                        } else if (data.progress === 3) {
                            this.loadingManager.setStatus(translate('modals.download.status.downloadedPreview'));
                        } else if (data.progress > 3 && data.progress < 100) {
                            this.loadingManager.setStatus(
                                translate('modals.download.status.downloadingFile', { type: config.singularName })
                            );
                        } else {
                            this.loadingManager.setStatus(translate('modals.download.status.finalizing'));
                        }
                    }
                } else if (data.status === 'cancelled' || data.status === 'canceled') {
                    // Handle cancellation - check if there are other downloads before hiding
                    this.isCancelling = false;
                    if (this.cancellationTimeout) {
                        clearTimeout(this.cancellationTimeout);
                        this.cancellationTimeout = null;
                    }
                    
                    // Immediately refresh queue display to show next download (if any)
                    // The backend semaphore will automatically start the next download
                    this.updateQueueDisplay().then(() => {
                        // Check queue after refresh
                        return this.checkQueueStatus().then(queueData => {
                            const hasOtherDownloads = queueData && queueData.downloads && queueData.downloads.some(d => 
                                d.status === 'downloading' || d.status === 'waiting' || d.status === 'queued'
                            );
                            
                            if (!hasOtherDownloads) {
                                this.loadingManager.hide();
                            }
                        });
                    }).catch(error => {
                        // Handle errors in queue update/check
                        console.error('Error updating queue after cancellation:', error);
                        // Still try to check queue status as fallback
                        this.checkQueueStatus().then(queueData => {
                            const hasOtherDownloads = queueData && queueData.downloads && queueData.downloads.some(d => 
                                d.status === 'downloading' || d.status === 'waiting' || d.status === 'queued'
                            );
                            
                            if (!hasOtherDownloads) {
                                this.loadingManager.hide();
                            }
                        }).catch(err => {
                            console.error('Error checking queue status:', err);
                            // If all else fails, hide the popup after a delay
                            setTimeout(() => {
                                this.loadingManager.hide();
                            }, 1000);
                        });
                    });
                    
                    showToast('toast.downloads.downloadCancelled', {}, 'info');
                } else if (data.status === 'completed' || data.status === 'success') {
                    // Handle completion - don't hide here, let queue polling handle it
                    updateProgress(100, 0, displayName);
                    this.loadingManager.setStatus(translate('modals.download.status.finalizing'));
                }
            };

            ws.onerror = error => {
                console.error('WebSocket error:', error);
            };

            await this.apiClient.downloadModel(
                modelId,
                versionId,
                modelRoot,
                targetFolder,
                useDefaultPaths,
                downloadId,
                source
            );

            showToast('toast.loras.downloadCompleted', {}, 'success');

            if (closeModal) {
                modalManager.closeModal('downloadModal');
            }

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
                ws = null;
            }

            const pageState = this.apiClient.getPageState();

            if (!useDefaultPaths && targetFolder) {
                pageState.activeFolder = targetFolder;
                setStorageItem(`${this.apiClient.modelType}_activeFolder`, targetFolder);

                document.querySelectorAll('.folder-tags .tag').forEach(tag => {
                    const isActive = tag.dataset.folder === targetFolder;
                    tag.classList.toggle('active', isActive);
                    if (isActive && !tag.parentNode.classList.contains('collapsed')) {
                        tag.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            }

            await resetAndReload(true);

            return true;
        } catch (error) {
            // Don't show error toast if download was cancelled (cancellation is handled by WebSocket message handler)
            let errorMessage = error?.message || error?.error || String(error || '');
            
            // Try to parse JSON error response if it looks like JSON
            let parsedError = null;
            try {
                if (errorMessage.trim().startsWith('{')) {
                    parsedError = JSON.parse(errorMessage);
                    if (parsedError.error) {
                        errorMessage = parsedError.error;
                    }
                }
            } catch (e) {
                // Not JSON, use original error message
            }
            
            const isCancellation = this.isCancelling || 
                                  errorMessage.toLowerCase().includes('cancelled') ||
                                  errorMessage.toLowerCase().includes('cancel') ||
                                  (parsedError && parsedError.error && parsedError.error.toLowerCase().includes('cancelled'));
            
            if (isCancellation) {
                console.debug('Download was cancelled:', errorMessage);
                // Cancellation is already handled by WebSocket message handler, no need to show error
                return false;
            }
            
            console.error('Failed to download model version:', error);
            showToast('toast.downloads.downloadError', { message: errorMessage }, 'error');
            return false;
        } finally {
            try {
                if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
                    ws.close();
                }
            } catch (closeError) {
                console.debug('Failed to close download progress socket:', closeError);
            }
            
            // Check if there are still active or queued downloads before hiding
            // Only hide if this download was cancelled AND there are no other downloads
            if (!this.isCancelling) {
                // Download completed normally - check queue status
                const queueData = await this.checkQueueStatus();
                const hasActiveOrQueued = queueData && queueData.downloads && queueData.downloads.some(d => 
                    d.status === 'downloading' || d.status === 'waiting' || d.status === 'queued'
                );
                
                if (!hasActiveOrQueued) {
                    // No active or queued downloads - safe to hide
                    this.stopQueuePolling();
                    this.currentUpdateProgress = null;
                    this.loadingManager.hide();
                } else {
                    // There are other downloads - keep polling and showing
                    // Don't clear currentUpdateProgress yet, as queue polling will handle updates
                }
            }
            // If isCancelling, the cancellation handler above will check the queue
        }
    }

    startQueuePolling() {
        // Clear any existing interval
        this.stopQueuePolling();
        
        // Poll immediately, but with a small delay to allow download to register
        // This ensures the popup stays visible when starting the first download
        setTimeout(() => {
            this.updateQueueDisplay();
        }, 100);
        
        // Then poll every 2 seconds
        this.queuePollInterval = setInterval(() => {
            this.updateQueueDisplay();
        }, 2000);
    }

    stopQueuePolling() {
        if (this.queuePollInterval) {
            clearInterval(this.queuePollInterval);
            this.queuePollInterval = null;
        }
    }

    async checkQueueStatus() {
        try {
            const response = await fetch('/api/lm/active-downloads');
            if (!response.ok) {
                return null;
            }
            return await response.json();
        } catch (error) {
            console.debug('Failed to check queue status:', error);
            return null;
        }
    }

    async updateQueueDisplay() {
        try {
            const response = await fetch('/api/lm/active-downloads');
            if (!response.ok) {
                return;
            }
            
            const data = await response.json();
            if (data && data.downloads && Array.isArray(data.downloads)) {
                // Update the queue display
                this.loadingManager.updateQueueDisplay(data.downloads);
                
                // Update cancel callback to use the current active download ID
                // IMPORTANT: Only cancel downloads with status 'downloading', not 'queued' or 'waiting'
                const activeDownload = data.downloads.find(d => d.status === 'downloading');
                if (activeDownload && activeDownload.download_id) {
                    const activeDownloadId = activeDownload.download_id;
                    this.currentDownloadId = activeDownloadId;
                    
                    // Update cancel callback to always fetch current active download and cancel it
                    // This ensures we cancel the correct download even if the queue changes
                    this.loadingManager.onCancelCallback = async () => {
                        console.log('Cancel button clicked');
                        // Fetch current active downloads to ensure we cancel the right one
                        try {
                            const currentData = await this.checkQueueStatus();
                            if (currentData && currentData.downloads && Array.isArray(currentData.downloads)) {
                                const currentActive = currentData.downloads.find(d => d.status === 'downloading');
                                if (currentActive && currentActive.download_id) {
                                    console.log('Canceling active download:', currentActive.download_id);
                                    await this.cancelDownload(currentActive.download_id);
                                } else {
                                    console.warn('No active download found when cancel button clicked');
                                    // Fallback to stored ID
                                    if (activeDownloadId) {
                                        console.log('Using stored active download ID:', activeDownloadId);
                                        await this.cancelDownload(activeDownloadId);
                                    }
                                }
                            } else {
                                // Fallback to stored ID if fetch fails
                                console.log('Failed to fetch current downloads, using stored ID:', activeDownloadId);
                                await this.cancelDownload(activeDownloadId);
                            }
                        } catch (error) {
                            console.error('Error fetching current downloads for cancellation:', error);
                            // Fallback to stored ID
                            await this.cancelDownload(activeDownloadId);
                        }
                    };
                    console.log('Updated cancel callback to use active download ID:', activeDownloadId);
                } else {
                    // No active download - clear the cancel callback or set it to null
                    console.log('No active download found, clearing cancel callback');
                    this.loadingManager.onCancelCallback = null;
                }
                
                // Check if there are active downloads OR queued downloads
                // Keep popup visible as long as there are any downloads (active, waiting, or queued)
                const hasActiveDownloads = data.downloads.some(d => 
                    d.status === 'downloading' || d.status === 'waiting' || d.status === 'queued'
                );
                
                if (!hasActiveDownloads) {
                    // No active downloads - check if we should keep popup visible
                    if (!this.currentUpdateProgress) {
                        // No downloads and no download was just initiated - safe to hide
                        this.stopQueuePolling();
                        this.currentUpdateProgress = null;
                        this.loadingManager.hide();
                    } else {
                        // Download was just initiated but not yet registered - keep popup visible
                        // But respect minimized state - don't force restore if minimized
                        if (this.loadingManager.overlay && !this.loadingManager.isMinimized) {
                            this.loadingManager.overlay.style.display = 'flex';
                        }
                    }
                } else {
                    // There are active/queued downloads - ensure popup is visible
                    // But respect minimized state - don't force restore if user minimized it
                    if (this.loadingManager.overlay && !this.loadingManager.isMinimized) {
                        this.loadingManager.overlay.style.display = 'flex';
                    }
                    // If minimized, the minimized widget will be updated by updateQueueDisplay
                }
            } else {
                // No downloads data yet, but if we have a current update function, keep popup visible
                if (this.currentUpdateProgress) {
                    // Keep popup visible while waiting for download to register
                    // But respect minimized state - don't force restore if minimized
                    if (this.loadingManager.overlay && !this.loadingManager.isMinimized) {
                        this.loadingManager.overlay.style.display = 'flex';
                    }
                }
            }
        } catch (error) {
            console.debug('Failed to fetch active downloads:', error);
            // On error, if we have a current update function, keep popup visible
            // But respect minimized state - don't force restore if minimized
            if (this.currentUpdateProgress) {
                if (this.loadingManager.overlay && !this.loadingManager.isMinimized) {
                    this.loadingManager.overlay.style.display = 'flex';
                }
            }
        }
    }

    async cancelDownload(downloadId) {
        if (!downloadId) {
            console.warn('Cannot cancel download: no download ID provided');
            return;
        }
        
        console.log('cancelDownload called with downloadId:', downloadId, 'currentDownloadId:', this.currentDownloadId, 'activeDownloadId:', this.loadingManager.activeDownloadId);
        this.isCancelling = true;
        
        // Clear any existing timeout
        if (this.cancellationTimeout) {
            clearTimeout(this.cancellationTimeout);
        }
        
        // Set a timeout to ensure UI updates even if WebSocket message doesn't arrive
        this.cancellationTimeout = setTimeout(() => {
            this.isCancelling = false;
            this.cancellationTimeout = null;
            
            // Check if there are other downloads in queue
            this.checkQueueStatus().then(queueData => {
                const hasOtherDownloads = queueData && queueData.downloads && queueData.downloads.some(d => 
                    d.status === 'downloading' || d.status === 'waiting' || d.status === 'queued'
                );
                
                if (!hasOtherDownloads) {
                    this.loadingManager.hide();
                } else {
                    // Refresh queue display to show next download
                    this.updateQueueDisplay().catch(error => {
                        console.error('Error updating queue display after cancellation timeout:', error);
                        // Fallback: try to hide if update fails
                        this.loadingManager.hide();
                    });
                }
            }).catch(error => {
                console.error('Error checking queue status after cancellation timeout:', error);
                // If queue check fails, hide the popup
                this.loadingManager.hide();
            });
            
            showToast('toast.downloads.downloadCancelled', {}, 'info');
        }, 2000);
        
        try {
            // Update UI immediately
            this.loadingManager.setStatus(translate('modals.download.status.cancelling', {}, 'Cancelling download...'));
            
            // Call backend to cancel
            const response = await fetch(`/api/lm/cancel-download-get?download_id=${encodeURIComponent(downloadId)}`);
            const data = await response.json();
            
            if (!data.success) {
                console.error('Failed to cancel download:', data.error);
                showToast('toast.downloads.cancelFailed', { error: data.error }, 'error');
                this.isCancelling = false;
                if (this.cancellationTimeout) {
                    clearTimeout(this.cancellationTimeout);
                    this.cancellationTimeout = null;
                }
            }
            // If successful, WebSocket message will handle cleanup, or timeout will handle it
        } catch (error) {
            console.error('Error cancelling download:', error);
            this.isCancelling = false;
            if (this.cancellationTimeout) {
                clearTimeout(this.cancellationTimeout);
                this.cancellationTimeout = null;
            }
            showToast('toast.downloads.cancelFailed', { error: error.message }, 'error');
        }
    }
    
    async removeQueuedDownload(downloadId) {
        if (!downloadId) {
            console.warn('Cannot remove queued download: no download ID provided');
            return;
        }
        
        try {
            const response = await fetch(`/api/lm/remove-queued-download?download_id=${encodeURIComponent(downloadId)}`);
            const data = await response.json();
            
            if (data.success) {
                // Refresh queue display to update counts and order
                await this.updateQueueDisplay();
                showToast('toast.downloads.removedFromQueue', {}, 'info');
            } else {
                console.error('Failed to remove queued download:', data.error);
                showToast('toast.downloads.removeFailed', { error: data.error }, 'error');
            }
        } catch (error) {
            console.error('Error removing queued download:', error);
            showToast('toast.downloads.removeFailed', { error: error.message }, 'error');
        }
    }

    updatePathSelectionUI() {
        const manualSelection = document.getElementById('manualPathSelection');
        
        // Always show manual path selection, but disable/enable based on useDefaultPath
        manualSelection.style.display = 'block';
        if (this.useDefaultPath) {
            manualSelection.classList.add('disabled');
            // Disable all inputs and buttons inside manualSelection
            manualSelection.querySelectorAll('input, select, button').forEach(el => {
                el.disabled = true;
                el.tabIndex = -1;
            });
        } else {
            manualSelection.classList.remove('disabled');
            manualSelection.querySelectorAll('input, select, button').forEach(el => {
                el.disabled = false;
                el.tabIndex = 0;
            });
        }
        
        // Always update the main path display
        this.updateTargetPath();
    }
    
    backToUrl() {
        document.getElementById('versionStep').style.display = 'none';
        document.getElementById('urlStep').style.display = 'block';
    }

    backToVersions() {
        document.getElementById('locationStep').style.display = 'none';
        document.getElementById('versionStep').style.display = 'block';
    }

    closeModal() {
        // Clean up folder tree manager
        if (this.folderTreeManager) {
            this.folderTreeManager.destroy();
        }
        modalManager.closeModal('downloadModal');
    }

    async startDownload() {
        const modelRoot = document.getElementById('modelRoot').value;
        const config = this.apiClient.apiConfig.config;
        
        if (!modelRoot) {
            showToast('toast.models.pleaseSelectRoot', { type: config.displayName }, 'error');
            return;
        }

        // Determine target folder and use_default_paths parameter
        let targetFolder = '';
        let useDefaultPaths = false;
        
        if (this.useDefaultPath) {
            useDefaultPaths = true;
            targetFolder = ''; // Not needed when using default paths
        } else {
            targetFolder = this.folderTreeManager.getSelectedPath();
        }
        return this.executeDownloadWithProgress({
            modelId: this.modelId,
            versionId: this.currentVersion.id,
            versionName: this.currentVersion.name,
            modelRoot,
            targetFolder,
            useDefaultPaths,
            source: this.source,
            closeModal: true,
        });
    }

    async downloadVersionWithDefaults(modelType, modelId, versionId, { versionName = '', source = null } = {}) {
        try {
            this.apiClient = getModelApiClient(modelType);
        } catch (error) {
            this.apiClient = getModelApiClient();
        }

        this.modelId = modelId ? modelId.toString() : null;
        this.source = source;

        return this.executeDownloadWithProgress({
            modelId,
            versionId,
            versionName,
            modelRoot: '',
            targetFolder: '',
            useDefaultPaths: true,
            source,
            closeModal: false,
        });
    }

    async initializeFolderTree() {
        try {
            // Fetch unified folder tree
            const treeData = await this.apiClient.fetchUnifiedFolderTree();
            
            if (treeData.success) {
                // Load tree data into folder tree manager
                await this.folderTreeManager.loadTree(treeData.tree);
            } else {
                console.error('Failed to fetch folder tree:', treeData.error);
                showToast('toast.import.folderTreeFailed', {}, 'error');
            }
        } catch (error) {
            console.error('Error initializing folder tree:', error);
            showToast('toast.import.folderTreeError', {}, 'error');
        }
    }

    initializeFolderBrowser() {
        const folderBrowser = document.getElementById('folderBrowser');
        if (!folderBrowser) return;

        this.cleanupFolderBrowser();

        this.folderClickHandler = (event) => {
            const folderItem = event.target.closest('.folder-item');
            if (!folderItem) return;

            if (folderItem.classList.contains('selected')) {
                folderItem.classList.remove('selected');
                this.selectedFolder = '';
            } else {
                folderBrowser.querySelectorAll('.folder-item').forEach(f => 
                    f.classList.remove('selected'));
                folderItem.classList.add('selected');
                this.selectedFolder = folderItem.dataset.folder;
            }
            
            this.updateTargetPath();
        };

        folderBrowser.addEventListener('click', this.folderClickHandler);
        
        const modelRoot = document.getElementById('modelRoot');
        const newFolder = document.getElementById('newFolder');
        
        modelRoot.addEventListener('change', this.updateTargetPath);
        newFolder.addEventListener('input', this.updateTargetPath);
        
        this.updateTargetPath();
    }

    cleanupFolderBrowser() {
        if (this.folderClickHandler) {
            const folderBrowser = document.getElementById('folderBrowser');
            if (folderBrowser) {
                folderBrowser.removeEventListener('click', this.folderClickHandler);
                this.folderClickHandler = null;
            }
        }
        
        const modelRoot = document.getElementById('modelRoot');
        const newFolder = document.getElementById('newFolder');
        
        if (modelRoot) modelRoot.removeEventListener('change', this.updateTargetPath);
        if (newFolder) newFolder.removeEventListener('input', this.updateTargetPath);
    }
    
    updateTargetPath() {
        const pathDisplay = document.getElementById('targetPathDisplay');
        const modelRoot = document.getElementById('modelRoot').value;
        const config = this.apiClient.apiConfig.config;
        
        let fullPath = modelRoot || translate('modals.download.selectTypeRoot', { type: config.displayName });
        
        if (modelRoot) {
            if (this.useDefaultPath) {
                // Show actual template path
                try {
                    const singularType = this.apiClient.modelType.replace(/s$/, '');
                    const templates = state.global.settings.download_path_templates;
                    const template = templates[singularType];
                    fullPath += `/${template}`;
                } catch (error) {
                    console.error('Failed to fetch template:', error);
                    fullPath += '/' + translate('modals.download.autoOrganizedPath');
                }
            } else {
                // Show manual path selection
                const selectedPath = this.folderTreeManager ? this.folderTreeManager.getSelectedPath() : '';
                if (selectedPath) {
                    fullPath += '/' + selectedPath;
                }
            }
        }

        pathDisplay.innerHTML = `<span class="path-text">${fullPath}</span>`;
    }
}

// Create global instance
export const downloadManager = new DownloadManager();
