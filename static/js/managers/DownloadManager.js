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

        try {
            this.loadingManager.restoreProgressBar();
            updateProgress = this.loadingManager.showDownloadProgress(1);
            updateProgress(0, 0, displayName);

            const downloadId = Date.now().toString();
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);

            ws.onmessage = event => {
                const data = JSON.parse(event.data);

                if (data.type === 'download_id') {
                    console.log(`Connected to download progress with ID: ${data.download_id}`);
                    return;
                }

                if (data.status === 'progress' && data.download_id === downloadId) {
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
            console.error('Failed to download model version:', error);
            showToast('toast.downloads.downloadError', { message: error?.message }, 'error');
            return false;
        } finally {
            try {
                if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
                    ws.close();
                }
            } catch (closeError) {
                console.debug('Failed to close download progress socket:', closeError);
            }
            this.loadingManager.hide();
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
