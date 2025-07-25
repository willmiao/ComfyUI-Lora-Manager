import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { LoadingManager } from './LoadingManager.js';
import { getModelApiClient, resetAndReload } from '../api/baseModelApi.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';

export class DownloadManager {
    constructor() {
        this.currentVersion = null;
        this.versions = [];
        this.modelInfo = null;
        this.modelVersionId = null;
        this.modelId = null;
        
        this.initialized = false;
        this.selectedFolder = '';
        this.apiClient = null;

        this.loadingManager = new LoadingManager();
        this.folderClickHandler = null;
        this.updateTargetPath = this.updateTargetPath.bind(this);
        
        // Bound methods for event handling
        this.handleValidateAndFetchVersions = this.validateAndFetchVersions.bind(this);
        this.handleProceedToLocation = this.proceedToLocation.bind(this);
        this.handleStartDownload = this.startDownload.bind(this);
        this.handleBackToUrl = this.backToUrl.bind(this);
        this.handleBackToVersions = this.backToVersions.bind(this);
        this.handleCloseModal = this.closeModal.bind(this);
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
    }

    updateModalLabels() {
        const config = this.apiClient.apiConfig.config;
        
        // Update modal title
        document.getElementById('downloadModalTitle').textContent = `Download ${config.displayName} from URL`;
        
        // Update URL label
        document.getElementById('modelUrlLabel').textContent = 'Civitai URL:';
        
        // Update root selection label
        document.getElementById('modelRootLabel').textContent = `Select ${config.displayName} Root:`;
        
        // Update path preview labels
        const pathLabels = document.querySelectorAll('.path-preview label');
        pathLabels.forEach(label => {
            if (label.textContent.includes('Location Preview')) {
                label.textContent = 'Download Location Preview:';
            }
        });
        
        // Update initial path text
        const pathText = document.querySelector('#targetPathDisplay .path-text');
        if (pathText) {
            pathText.textContent = `Select a ${config.displayName} root directory`;
        }
    }

    resetSteps() {
        document.querySelectorAll('.download-step').forEach(step => step.style.display = 'none');
        document.getElementById('urlStep').style.display = 'block';
        document.getElementById('modelUrl').value = '';
        document.getElementById('urlError').textContent = '';
        
        const newFolderInput = document.getElementById('newFolder');
        if (newFolderInput) {
            newFolderInput.value = '';
        }
        
        this.currentVersion = null;
        this.versions = [];
        this.modelInfo = null;
        this.modelId = null;
        this.modelVersionId = null;
        
        this.selectedFolder = '';
        const folderBrowser = document.getElementById('folderBrowser');
        if (folderBrowser) {
            folderBrowser.querySelectorAll('.folder-item').forEach(f => 
                f.classList.remove('selected'));
        }
    }

    async validateAndFetchVersions() {
        const url = document.getElementById('modelUrl').value.trim();
        const errorElement = document.getElementById('urlError');
        
        try {
            this.loadingManager.showSimpleLoading('Fetching model versions...');
            
            this.modelId = this.extractModelId(url);
            if (!this.modelId) {
                throw new Error('Invalid Civitai URL format');
            }

            this.versions = await this.apiClient.fetchCivitaiVersions(this.modelId);
            
            if (!this.versions.length) {
                throw new Error('No versions available for this model');
            }
            
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

    extractModelId(url) {
        const modelMatch = url.match(/civitai\.com\/models\/(\d+)/);
        const versionMatch = url.match(/modelVersionId=(\d+)/);
        
        if (modelMatch) {
            this.modelVersionId = versionMatch ? versionMatch[1] : null;
            return modelMatch[1];
        }
        return null;
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
                    <div class="early-access-badge" title="Early access required">
                        <i class="fas fa-clock"></i> Early Access
                    </div>
                `;
            }
            
            const localStatus = existsLocally ? 
                `<div class="local-badge">
                    <i class="fas fa-check"></i> In Library
                    <div class="local-path">${localPath || ''}</div>
                 </div>` : '';

            return `
                <div class="version-item ${this.currentVersion?.id === version.id ? 'selected' : ''} 
                     ${existsLocally ? 'exists-locally' : ''} 
                     ${isEarlyAccess ? 'is-early-access' : ''}"
                     data-version-id="${version.id}">
                    <div class="version-thumbnail">
                        <img src="${thumbnailUrl}" alt="Version preview">
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
            nextButton.textContent = 'Already in Library';
        } else {
            nextButton.disabled = false;
            nextButton.classList.remove('disabled');
            nextButton.textContent = 'Next';
        }
    }

    async proceedToLocation() {
        if (!this.currentVersion) {
            showToast('Please select a version', 'error');
            return;
        }
        
        const existsLocally = this.currentVersion.existsLocally;
        if (existsLocally) {
            showToast('This version already exists in your library', 'info');
            return;
        }

        document.getElementById('versionStep').style.display = 'none';
        document.getElementById('locationStep').style.display = 'block';
        
        try {
            const config = this.apiClient.apiConfig.config;
            
            // Fetch model roots
            const rootsData = await this.apiClient.fetchModelRoots();
            const modelRoot = document.getElementById('modelRoot');
            modelRoot.innerHTML = rootsData.roots.map(root => 
                `<option value="${root}">${root}</option>`
            ).join('');

            // Set default root if available
            const defaultRootKey = `default_${this.apiClient.modelType}_root`;
            const defaultRoot = getStorageItem('settings', {})[defaultRootKey];
            if (defaultRoot && rootsData.roots.includes(defaultRoot)) {
                modelRoot.value = defaultRoot;
            }

            // Fetch folders
            const foldersData = await this.apiClient.fetchModelFolders();
            const folderBrowser = document.getElementById('folderBrowser');
            
            folderBrowser.innerHTML = foldersData.folders.map(folder => 
                `<div class="folder-item" data-folder="${folder}">${folder}</div>`
            ).join('');

            this.initializeFolderBrowser();
        } catch (error) {
            showToast(error.message, 'error');
        }
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
        modalManager.closeModal('downloadModal');
    }

    async startDownload() {
        const modelRoot = document.getElementById('modelRoot').value;
        const newFolder = document.getElementById('newFolder').value.trim();
        const config = this.apiClient.apiConfig.config;
        
        if (!modelRoot) {
            showToast(`Please select a ${config.displayName} root directory`, 'error');
            return;
        }

        // Construct relative path
        let targetFolder = '';
        if (this.selectedFolder) {
            targetFolder = this.selectedFolder;
        }
        if (newFolder) {
            targetFolder = targetFolder ? 
                `${targetFolder}/${newFolder}` : newFolder;
        }

        try {
            const updateProgress = this.loadingManager.showDownloadProgress(1);
            updateProgress(0, 0, this.currentVersion.name);

            const downloadId = Date.now().toString();
            
            // Setup WebSocket for progress updates
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            const ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'download_id') {
                    console.log(`Connected to download progress with ID: ${data.download_id}`);
                    return;
                }
                
                if (data.status === 'progress' && data.download_id === downloadId) {
                    updateProgress(data.progress, 0, this.currentVersion.name);
                    
                    if (data.progress < 3) {
                        this.loadingManager.setStatus(`Preparing download...`);
                    } else if (data.progress === 3) {
                        this.loadingManager.setStatus(`Downloaded preview image`);
                    } else if (data.progress > 3 && data.progress < 100) {
                        this.loadingManager.setStatus(`Downloading ${config.singularName} file`);
                    } else {
                        this.loadingManager.setStatus(`Finalizing download...`);
                    }
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            // Start download
            await this.apiClient.downloadModel(
                this.modelId,
                this.currentVersion.id,
                modelRoot,
                targetFolder,
                downloadId
            );

            showToast('Download completed successfully', 'success');
            modalManager.closeModal('downloadModal');
            
            ws.close();
            
            // Update state and trigger reload
            const pageState = this.apiClient.getPageState();
            pageState.activeFolder = targetFolder;
            
            // Save the active folder preference
            setStorageItem(`${this.apiClient.modelType}_activeFolder`, targetFolder);
            
            // Update UI folder selection
            document.querySelectorAll('.folder-tags .tag').forEach(tag => {
                const isActive = tag.dataset.folder === targetFolder;
                tag.classList.toggle('active', isActive);
                if (isActive && !tag.parentNode.classList.contains('collapsed')) {
                    tag.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });

            await resetAndReload(true);

        } catch (error) {
            showToast(error.message, 'error');
        } finally {
            this.loadingManager.hide();
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
        const newFolder = document.getElementById('newFolder').value.trim();
        const config = this.apiClient.apiConfig.config;
        
        let fullPath = modelRoot || `Select a ${config.displayName} root directory`;
        
        if (modelRoot) {
            if (this.selectedFolder) {
                fullPath += '/' + this.selectedFolder;
            }
            if (newFolder) {
                fullPath += '/' + newFolder;
            }
        }

        pathDisplay.innerHTML = `<span class="path-text">${fullPath}</span>`;
    }
}

// Create global instance
export const downloadManager = new DownloadManager();
