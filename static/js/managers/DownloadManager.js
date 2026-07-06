import { modalManager } from './ModalManager.js';
import { showToast, setupAutoNewlineOnPaste } from '../utils/uiHelpers.js';
import { state } from '../state/index.js';
import { LoadingManager } from './LoadingManager.js';
import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { FolderTreeManager } from '../components/FolderTreeManager.js';
import { translate } from '../utils/i18nHelpers.js';
import { extractCivitaiModelUrlParts } from '../utils/civitaiUtils.js';
import { formatFileSize } from '../utils/formatters.js';

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

        // Batch mode state
        this.batchModels = [];
        this.isBatchMode = false;
        this.editingBatchIndex = -1;

        // HF download state
        this.hfRepoId = null;
        this.hfSelectedFiles = [];
        this.hfRepoCollapsed = {};

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
        this.handleBackToVersionFromFiles = this.backToVersionFromFiles.bind(this);
        this.handleConfirmFileSelection = this.confirmFileSelection.bind(this);
        this.handleCloseModal = this.closeModal.bind(this);
        this.handleToggleDefaultPath = this.toggleDefaultPath.bind(this);
        this.handleBackToUrlFromBatch = this.backToUrlFromBatch.bind(this);
        this.handleNextFromBatch = this.nextFromBatch.bind(this);


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

        // File selection step buttons
        document.getElementById('backToVersionFromFilesBtn').addEventListener('click', this.handleBackToVersionFromFiles);
        document.getElementById('confirmFileSelection').addEventListener('click', this.handleConfirmFileSelection);

        // Batch preview buttons
        document.getElementById('backToUrlFromBatchBtn').addEventListener('click', this.handleBackToUrlFromBatch);
        document.getElementById('nextFromBatchBtn').addEventListener('click', this.handleNextFromBatch);

        // Default path toggle handler
        document.getElementById('useDefaultPath').addEventListener('change', this.handleToggleDefaultPath);

        // Auto-append newline after pasting a URL so users can paste multiple URLs in succession
        setupAutoNewlineOnPaste('modelUrl');
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
        this.selectedFile = null;

        this.selectedFolder = '';
        this.batchModels = [];
        this.isBatchMode = false;
        this.editingBatchIndex = -1;

        // Clear folder tree selection
        if (this.folderTreeManager) {
            this.folderTreeManager.clearSelection();
        }

        // Reset default path toggle
        this.loadDefaultPathSetting();

        // Reset HF state
        this.hfRepoId = null;
        this.hfSelectedFiles = [];
        this.hfRepoCollapsed = {};
    }

    async retrieveVersionsForModel(modelId, source = null) {
        this.versions = await this.apiClient.fetchCivitaiVersions(modelId, source);
        if (!this.versions || !this.versions.length) {
            throw new Error(translate('modals.download.errors.noVersions'));
        }
        return this.versions;
    }

    async validateAndFetchVersions() {
        const rawText = document.getElementById('modelUrl').value.trim();
        const errorElement = document.getElementById('urlError');
        const urls = rawText.split('\n').map(l => l.trim()).filter(Boolean);

        if (urls.length === 0) {
            errorElement.textContent = translate('modals.download.errors.invalidUrl');
            return;
        }

        // Detect URL types — all URLs must share the same source type
        const urlTypes = urls.map(u => DownloadManager.detectUrlType(u));
        const isHf = urlTypes.every(t => t && (t.type === 'hf-resolve' || t.type === 'hf-repo'));
        const isCivitai = urlTypes.every(t => t && t.type === 'civitai');

        if (!isHf && !isCivitai) {
            const allValid = urlTypes.every(t => t !== null);
            if (!allValid) {
                errorElement.textContent = translate('modals.download.errors.invalidUrl');
                return;
            }
            // Mixed sources not supported in one batch
            if (urls.length > 1) {
                errorElement.textContent = translate('modals.download.errors.mixedSources');
                return;
            }
        }

        if (isHf) {
            return this._validateAndFetchHf(urls, errorElement);
        }

        // --- Original CivitAI flow below ---
        if (urls.length === 1) {
            this.isBatchMode = false;
            try {
                this.loadingManager.showSimpleLoading(translate('modals.download.fetchingVersions'));

                this.modelId = this.extractModelId(urls[0]);
                if (!this.modelId) {
                    throw new Error(translate('modals.download.errors.invalidUrl'));
                }

                await this.retrieveVersionsForModel(this.modelId, this.source);

                if (this.modelVersionId) {
                    this.currentVersion = this.versions.find(v => v.id.toString() === this.modelVersionId);
                }

                this.showVersionStep();
            } catch (error) {
                errorElement.textContent = error.message;
            } finally {
                this.loadingManager.hide();
            }
            return;
        }

        // Multi-URL batch mode
        this.isBatchMode = true;
        this.batchModels = [];
        errorElement.textContent = '';

        const seen = new Set();
        const parsed = [];
        for (const url of urls) {
            const result = DownloadManager.parseModelUrl(url);
            if (!result.modelId) {
                parsed.push({ url, error: translate('modals.download.errors.invalidUrl') });
                continue;
            }
            // Dedup by modelId + modelVersionId combo so users can download
            // different versions of the same model (e.g. latest + a specific version)
            const dedupKey = result.modelVersionId
                ? `${result.modelId}:${result.modelVersionId}`
                : result.modelId;
            if (seen.has(dedupKey)) continue;
            seen.add(dedupKey);
            parsed.push({ url, ...result, error: null });
        }

        if (parsed.length === 0) {
            errorElement.textContent = translate('modals.download.errors.invalidUrl');
            return;
        }

        this.loadingManager.showSimpleLoading(translate('modals.download.fetchingVersions'));

        let fetched = 0;
        const total = parsed.filter(p => !p.error).length;

        this.batchModels = new Array(parsed.length);

        const fetchPromises = parsed.map(async (item, index) => {
            if (item.error) {
                this.batchModels[index] = { ...item, versions: [], selectedVersion: null };
                return;
            }
            try {
                const versions = await this.apiClient.fetchCivitaiVersions(item.modelId, item.source);
                fetched++;
                this.loadingManager.setStatus(`${fetched}/${total}`);

                let selectedVersion = null;
                if (versions && versions.length > 0) {
                    if (item.modelVersionId) {
                        selectedVersion = versions.find(v => v.id.toString() === item.modelVersionId) || versions[0];
                    } else {
                        selectedVersion = versions[0];
                    }
                }

                this.batchModels[index] = { ...item, versions: versions || [], selectedVersion };
            } catch (err) {
                this.batchModels[index] = { ...item, versions: [], selectedVersion: null, error: err.message };
            }
        });

        await Promise.all(fetchPromises);
        this.loadingManager.hide();

        this.showBatchPreviewStep();
    }

    // ---- Hugging Face download flow ----

    async _validateAndFetchHf(urls, errorElement) {
        if (urls.length === 1) {
            const info = DownloadManager.detectUrlType(urls[0]);
            // Direct file resolve URL → skip file selection, go to location
            if (info.type === 'hf-resolve') {
                this.isBatchMode = false;
                this.hfRepoId = info.repo;
                this.hfSelectedFiles = [info.filename];
                this.source = 'huggingface';
                this.proceedToLocation();
                return;
            }
            // Repo URL → fetch file list and convert to batch items
            try {
                this.loadingManager.showSimpleLoading(translate('modals.download.fetchingRepoFiles'));
                const files = await this.apiClient.fetchHfRepoFiles(info.repo);
                if (!files || files.length === 0) {
                    throw new Error(translate('modals.download.errors.noModelFiles'));
                }
                this.isBatchMode = true;
                this.batchModels = [];
                this.source = 'huggingface';
                for (const file of files) {
                    this.batchModels.push({
                        url: urls[0],
                        source: 'huggingface',
                        repo: info.repo,
                        filename: file.filename,
                        revision: 'main',
                        displayName: file.filename,
                        fileSizeBytes: file.size,
                        selectedVersion: true,
                        versions: [],
                        checked: false,
                        error: null,
                    });
                }
                this.showBatchPreviewStep();
            } catch (err) {
                errorElement.textContent = err.message;
            } finally {
                this.loadingManager.hide();
            }
            return;
        }

        // Multiple HF URLs → batch mode: flatten all files from all repos
        this.isBatchMode = true;
        this.batchModels = [];
        this.source = 'huggingface';
        this.loadingManager.showSimpleLoading(translate('modals.download.fetchingRepoFiles'));

        for (const url of urls) {
            const info = DownloadManager.detectUrlType(url);
            if (!info) {
                this.batchModels.push({ url, error: 'Invalid URL', versions: [], selectedVersion: null });
                continue;
            }
            if (info.type === 'hf-resolve') {
                this.batchModels.push({
                    url,
                    source: 'huggingface',
                    repo: info.repo,
                    filename: info.filename,
                    revision: info.revision || 'main',
                    displayName: info.filename,
                    selectedVersion: true,
                    versions: [],
                    checked: false,
                    error: null,
                });
            } else if (info.type === 'hf-repo') {
                try {
                    const files = await this.apiClient.fetchHfRepoFiles(info.repo);
                    if (!files || files.length === 0) {
                        this.batchModels.push({ url, error: 'No model files found', versions: [], selectedVersion: null });
                        continue;
                    }
                    // Flatten: create one batch item per file, all checked by default
                    for (const file of files) {
                        this.batchModels.push({
                            url,
                            source: 'huggingface',
                            repo: info.repo,
                            filename: file.filename,
                            revision: 'main',
                            displayName: file.filename,
                            fileSizeBytes: file.size,
                            selectedVersion: true,
                            versions: [],
                            checked: false,
                            error: null,
                        });
                    }
                } catch (err) {
                    this.batchModels.push({ url, error: err.message, versions: [], selectedVersion: null });
                }
            }
        }

        this.loadingManager.hide();
        this.showBatchPreviewStep();
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

    static parseModelUrl(url) {
        const civarchiveMatch = url.match(/https?:\/\/(?:www\.)?(?:civitaiarchive|civarchive)\.com\/models\/(\d+)/i);
        if (civarchiveMatch) {
            const versionMatch = url.match(/modelVersionId=(\d+)/i);
            return {
                modelId: civarchiveMatch[1],
                modelVersionId: versionMatch ? versionMatch[1] : null,
                source: 'civarchive',
            };
        }

        const { modelId, modelVersionId } = extractCivitaiModelUrlParts(url);
        if (modelId) {
            return { modelId, modelVersionId, source: null };
        }

        return { modelId: null, modelVersionId: null, source: null };
    }

    /**
     * Detect the source type of a download URL.
     * @param {string} url
     * @returns {{ type: string, repo?: string, filename?: string, revision?: string } | null}
     *   type: 'civitai' | 'civarchive' | 'hf-resolve' | 'hf-repo' | 'direct-http'
     */
    static detectUrlType(url) {
        const trimmed = url.trim();
        if (!trimmed) return null;

        // CivitAI — matches civitai.com, civitai.red, civitai.green, etc.
        if (/civitai\.(?:com|red|green)\/models\//i.test(trimmed) || /civitaiarchive|civarchive/i.test(trimmed)) {
            // Will be parsed by existing CivitAI logic
            return { type: 'civitai' };
        }

        // Hugging Face resolve URL → direct file
        const hfResolveMatch = trimmed.match(/huggingface\.co\/([^/\s]+\/[^/\s]+)\/resolve\/([^/\s]+)\/(.+)/i);
        if (hfResolveMatch) {
            return {
                type: 'hf-resolve',
                repo: hfResolveMatch[1],
                revision: hfResolveMatch[2],
                filename: hfResolveMatch[3],
            };
        }

        // Hugging Face repo URL (huggingface.co/user/repo or bare user/repo path)
        // Require huggingface.co prefix for full URLs; bare user/repo only without ://
        const hfRepoMatch = trimmed.match(
            trimmed.includes('://')
                ? /^https?:\/\/huggingface\.co\/([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)(?:\/?$|$)/
                : /^([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)$/
        );
        if (hfRepoMatch) {
            // Reject path-traversal patterns like "../.." or "user/.."
            const parts = hfRepoMatch[1].split('/');
            if (parts.some(p => p === '.' || p === '..')) {
                return null;
            }
            return {
                type: 'hf-repo',
                repo: hfRepoMatch[1],
            };
        }

        // Direct HTTP(S) URL (non-HF)
        if (/^https?:\/\//i.test(trimmed)) {
            return { type: 'direct-http' };
        }

        return null;
    }

    extractModelId(url) {
        const result = DownloadManager.parseModelUrl(url);
        this.modelVersionId = result.modelVersionId;
        this.source = result.source;
        return result.modelId;
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
        const newList = versionList.cloneNode(false);
        versionList.parentNode.replaceChild(newList, versionList);

        newList.innerHTML = this.versions.map(version => {
            const firstImage = version.images?.find(img => !img.url.endsWith('.mp4'));
            const thumbnailUrl = firstImage ? firstImage.url : '/loras_static/images/no-preview.png';

            // Count model-type files per version
            const modelFiles = (version.files || []).filter(f => f.type === 'Model' || f.type === 'UNet' || f.type === 'Diffusion Model');
            const primaryFile = modelFiles.find(f => f.primary) || modelFiles[0] || {};
            const fileSize = version.modelSizeKB ?
                (version.modelSizeKB / 1024).toFixed(2) :
                ((primaryFile.sizeKB || 0) / 1024).toFixed(2);

            const existsLocally = version.existsLocally;
            const hasBeenDownloaded = version.hasBeenDownloaded && !existsLocally;
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

            let localStatus = '';
            if (existsLocally) {
                localStatus = `<div class="local-badge">
                    <i class="fas fa-check"></i> ${translate('modals.download.inLibrary')}
                    <div class="local-path">${localPath || ''}</div>
                 </div>`;
            } else if (hasBeenDownloaded) {
                const downloadedTooltip = translate(
                    'modals.download.downloadedTooltip',
                    {},
                    'Previously downloaded, but it is not currently in your library.'
                );
                localStatus = `<div class="downloaded-badge" title="${downloadedTooltip.replace(/"/g, '&quot;')}">
                    <i class="fas fa-history"></i> ${translate('modals.download.downloaded', {}, 'Downloaded')}
                 </div>`;
            }

            const fileBadge = modelFiles.length > 1 && !existsLocally
                ? `<span class="file-select-badge" data-version-id="${version.id}">
                     <i class="fas fa-th-list"></i> ${modelFiles.length} ${translate('modals.download.fileSelection.files')} <i class="fas fa-chevron-right badge-arrow"></i>
                   </span>`
                : '';

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
                            ${fileBadge}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Add click handlers for version selection and file badge
        newList.addEventListener('click', (event) => {
            const badge = event.target.closest('.file-select-badge');
            if (badge) {
                event.stopPropagation();
                const versionId = badge.dataset.versionId;
                this.selectVersion(versionId);
                this.showFileSelectionStep(versionId);
                return;
            }
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

    showFileSelectionStep(versionId) {
        const version = this.versions.find(v => v.id.toString() === versionId.toString());
        if (!version) return;

        this.currentVersion = version;
        const modelFiles = (version.files || []).filter(f => f.type === 'Model' || f.type === 'UNet' || f.type === 'Diffusion Model');

        document.getElementById('versionStep').style.display = 'none';
        document.getElementById('fileSelectionStep').style.display = 'block';

        const nameEl = document.getElementById('fileSelectionVersionName');
        if (nameEl) {
            nameEl.textContent = `${version.name} · ${version.baseModel || ''}`;
        }

        const container = document.getElementById('fileSelectionList');
        container.innerHTML = modelFiles.map(file => {
            const meta = file.metadata || {};
            const sizeGB = file.sizeKB ? (file.sizeKB / (1024 * 1024)).toFixed(2) : '--';
            const isSelected = this.selectedFile?.id === file.id;

            const tags = [];
            if (meta.size) tags.push(`<span class="file-tag size">${meta.size}</span>`);
            if (meta.format) tags.push(`<span class="file-tag format">${meta.format}</span>`);
            if (meta.fp) tags.push(`<span class="file-tag fp">${meta.fp}</span>`);

            const fileName = file.name || '';

            return `
                <div class="file-option ${isSelected ? 'selected' : ''}" data-file-id="${file.id}">
                    <div class="file-option-radio">
                        <input type="radio" name="fileSelection" value="${file.id}" ${isSelected ? 'checked' : ''}>
                    </div>
                    <div class="file-option-info">
                        <div class="file-option-tags">
                            ${tags.join(' ')}
                        </div>
                        <div class="file-option-name">${fileName}</div>
                    </div>
                    <div class="file-option-size">${sizeGB} GB</div>
                </div>
            `;
        }).join('');

        container.querySelectorAll('.file-option').forEach(el => {
            el.addEventListener('click', () => {
                container.querySelectorAll('.file-option').forEach(o => o.classList.remove('selected'));
                el.classList.add('selected');
                const radio = el.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;
            });
        });
    }

    confirmFileSelection() {
        const selectedRadio = document.querySelector('#fileSelectionList input[type="radio"]:checked');
        if (!selectedRadio) return;

        const version = this.currentVersion;
        if (!version) return;

        const modelFiles = (version.files || []).filter(f => f.type === 'Model' || f.type === 'UNet' || f.type === 'Diffusion Model');
        this.selectedFile = modelFiles.find(f => f.id.toString() === selectedRadio.value);

        document.getElementById('fileSelectionStep').style.display = 'none';
        document.getElementById('locationStep').style.display = 'block';
        this.proceedToLocationContent();
    }

    backToVersionFromFiles() {
        document.getElementById('fileSelectionStep').style.display = 'none';
        document.getElementById('versionStep').style.display = 'block';
    }

    async proceedToLocation() {
        // If editing a batch item's version, save and return to batch preview
        if (this.isBatchMode && this.editingBatchIndex >= 0) {
            if (this.currentVersion) {
                this.batchModels[this.editingBatchIndex].selectedVersion = this.currentVersion;
            }
            this.editingBatchIndex = -1;
            document.getElementById('versionStep').style.display = 'none';
            this.showBatchPreviewStep();
            return;
        }

        // In single-URL mode, validate version selection (skip for HF)
        if (!this.isBatchMode && this.source !== 'huggingface') {
            if (!this.currentVersion) {
                showToast('toast.loras.pleaseSelectVersion', {}, 'error');
                return;
            }
            if (this.currentVersion.existsLocally) {
                showToast('toast.loras.versionExists', {}, 'info');
                return;
            }
        }

        document.querySelectorAll('.download-step').forEach(step => step.style.display = 'none');
        document.getElementById('locationStep').style.display = 'block';
        await this.proceedToLocationContent();
    }

    async proceedToLocationContent() {

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
        fileParams = null,
        closeModal = false,
    }) {
        const config = this.apiClient?.apiConfig?.config;

        if (!this.apiClient || !config) {
            throw new Error('Download manager is not initialized with an API client');
        }

        const displayName = versionName || `#${versionId}`;
        let ws = null;
        let updateProgress = () => { };

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

            const response = await this.apiClient.downloadModel(
                modelId,
                versionId,
                modelRoot,
                targetFolder,
                useDefaultPaths,
                downloadId,
                source,
                fileParams
            );

            if (response?.skipped) {
                this.loadingManager.setStatus(translate('modals.download.status.finalizing'));
                updateProgress(100, 0, displayName);
                showToast('toast.loras.downloadSkippedByBaseModel', { baseModel: response.base_model || 'Unknown' }, 'warning');
                if (closeModal) {
                    modalManager.closeModal('downloadModal');
                }
                return true;
            }

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

    async _downloadHfSingle({ modelRoot, targetFolder, useDefaultPaths }) {
        modalManager.closeModal('downloadModal');
        this.loadingManager.restoreProgressBar();
        const totalFiles = this.hfSelectedFiles.length;
        const updateProgress = this.loadingManager.showDownloadProgress(totalFiles);

        try {
            let completedDownloads = 0;
            for (let i = 0; i < totalFiles; i++) {
                const filename = this.hfSelectedFiles[i];
                updateProgress(0, completedDownloads, filename);
                this.loadingManager.setStatus(`Downloading ${filename}...`);

                const downloadId = Date.now().toString() + '_' + i;
                const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
                const ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);

                try {
                    await new Promise((resolve, reject) => {
                        ws.onopen = resolve;
                        ws.onerror = reject;
                    });

                    // Capture completed count at WS creation time so progress
                    // updates arriving after completedDownloads increments still
                    // show the correct "N / total" position.
                    const snapshotCompleted = completedDownloads;
                    ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        if (data.status === 'progress') {
                            const metrics = {
                                bytesDownloaded: data.bytes_downloaded,
                                totalBytes: data.total_bytes,
                                bytesPerSecond: data.bytes_per_second,
                            };
                            updateProgress(data.progress, snapshotCompleted, filename, metrics);
                        }
                    };

                    const response = await this.apiClient.downloadHfModel({
                        repo: this.hfRepoId,
                        filename,
                        revision: 'main',
                        modelRoot,
                        relativePath: targetFolder,
                        useDefaultPaths,
                        download_id: downloadId,
                    });

                    if (response?.success) {
                        completedDownloads++;
                        updateProgress(100, completedDownloads, filename);
                    }
                } finally {
                    ws.close();
                }
            }

            showToast('toast.loras.downloadCompleted', {}, 'success');
            // Reload page data — model is already in scanner cache via backend
            await resetAndReload(true);
            return true;
        } catch (error) {
            console.error('Failed to download HF model:', error);
            showToast('toast.downloads.downloadError', { message: error?.message }, 'error');
            return false;
        } finally {
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

    showBatchPreviewStep() {
        document.querySelectorAll('.download-step').forEach(step => step.style.display = 'none');
        document.getElementById('batchPreviewStep').style.display = 'flex';

        const validCount = this.batchModels.filter(m => {
            if (m.error) return false;
            if (m.source === 'huggingface') return m.checked !== false;
            return m.selectedVersion;
        }).length;
        document.getElementById('downloadModalTitle').textContent =
            translate('modals.download.titleWithType', { type: this.apiClient.apiConfig.config.displayName }) +
            ` (${validCount})`;

        const list = document.getElementById('batchPreviewList');
        const hasHfItems = this.batchModels.some(m => m.source === 'huggingface' && !m.error);

        // Error items render flat, outside any group
        const errorItemsHtml = this.batchModels.map((item, index) => {
            if (!item.error) return null;
            return `
                <div class="batch-preview-item batch-preview-error" data-index="${index}">
                    <div class="batch-preview-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="batch-preview-info">
                        <div class="batch-preview-name">${item.url}</div>
                        <div class="batch-preview-meta batch-preview-error-text">${item.error}</div>
                    </div>
                    <button class="batch-preview-remove" data-index="${index}" title="${translate('common.actions.remove', {}, 'Remove')}">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
        }).filter(Boolean).join('');

        // CivitAI items render flat, outside any group (unchanged)
        const civitaiItemsHtml = this.batchModels.map((item, index) => {
            if (item.error) return null;
            if (item.source === 'huggingface') return null;
            const ver = item.selectedVersion;
            const firstImage = ver?.images?.find(img => !img.url.endsWith('.mp4'));
            const thumbnailUrl = firstImage ? firstImage.url : '/loras_static/images/no-preview.png';
            const fileSize = ver?.modelSizeKB
                ? (ver.modelSizeKB / 1024).toFixed(1)
                : (ver?.files?.[0]?.sizeKB ? (ver.files[0].sizeKB / 1024).toFixed(1) : '?');
            const existsLocally = ver?.existsLocally;
            return `
                <div class="batch-preview-item ${existsLocally ? 'batch-preview-local' : ''}" data-index="${index}">
                    <div class="batch-preview-thumbnail">
                        <img src="${thumbnailUrl}" alt="">
                    </div>
                    <div class="batch-preview-info">
                        <div class="batch-preview-name">${ver?.name || `Model #${item.modelId}`}</div>
                        <div class="batch-preview-meta">
                            ${ver?.baseModel ? `<span>${ver.baseModel}</span>` : ''}
                            <span>${fileSize} MB</span>
                            ${existsLocally ? `<span class="batch-preview-local-badge"><i class="fas fa-check"></i> ${translate('modals.download.inLibrary')}</span>` : ''}
                        </div>
                    </div>
                    ${item.versions.length > 1 ? `
                        <button class="batch-preview-change-version secondary-btn" data-index="${index}">
                            ${translate('common.actions.change', {}, 'Change')}
                        </button>
                    ` : ''}
                </div>
            `;
        }).filter(Boolean).join('');

        // Group HF items by repo (data model stays flat — only rendering groups)
        const hfGroups = {};
        this.batchModels.forEach((item, index) => {
            if (item.error || item.source !== 'huggingface') return;
            const repo = item.repo || 'unknown';
            if (!hfGroups[repo]) hfGroups[repo] = [];
            hfGroups[repo].push({ item, index });
        });

        const renderHfItem = ({ item, index }) => {
            const hfSize = item.fileSizeBytes ? formatFileSize(item.fileSizeBytes) : '?';
            return `
                <div class="batch-preview-item" data-index="${index}">
                    <input type="checkbox" class="batch-preview-checkbox"
                           data-index="${index}" ${item.checked !== false ? 'checked' : ''} />
                    <div class="batch-preview-info">
                        <div class="batch-preview-name">${item.displayName || item.filename || `HF #${index}`} <span class="hf-badge">HF</span></div>
                        <div class="batch-preview-meta">
                            <span>${hfSize}</span>
                            <span>${item.repo || ''}</span>
                        </div>
                    </div>
                    <button class="batch-preview-remove" data-index="${index}" title="${translate('common.actions.remove', {}, 'Remove')}">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
        };

        const hfGroupsHtml = Object.keys(hfGroups).map(repo => {
            const items = hfGroups[repo];
            const isCollapsed = this.hfRepoCollapsed[repo] === true;
            const allChecked = items.every(({ item }) => item.checked !== false);
            const fileCount = items.length;
            return `
                <div class="batch-preview-group" data-repo="${repo}">
                    <div class="batch-preview-group-header">
                        <i class="fas fa-chevron-right batch-preview-group-toggle ${isCollapsed ? '' : 'expanded'}"></i>
                        <span class="batch-preview-group-name">${repo}</span>
                        <span class="batch-preview-group-count">${fileCount} ${translate('modals.download.fileSelection.files', {}, 'files')}</span>
                        <input type="checkbox" class="batch-preview-group-select-all" data-repo="${repo}" ${allChecked ? 'checked' : ''} />
                    </div>
                    <div class="batch-preview-group-body ${isCollapsed ? '' : 'expanded'}">
                        ${items.map(renderHfItem).join('')}
                    </div>
                </div>
            `;
        }).join('');

        let itemsHtml = errorItemsHtml + civitaiItemsHtml + hfGroupsHtml;

        // Prepend select-all toolbar if there are HF items with checkboxes
        if (hasHfItems) {
            const allChecked = this.batchModels
                .filter(m => m.source === 'huggingface' && !m.error)
                .every(m => m.checked !== false);
            itemsHtml = `
                <div class="batch-preview-select-all">
                    <input type="checkbox" id="batchSelectAll" ${allChecked ? 'checked' : ''} />
                    <label for="batchSelectAll">${translate('modals.download.selectAll', {}, 'Select All')}</label>
                </div>
            ` + itemsHtml;
        }

        list.innerHTML = itemsHtml;

        const updateCountAndSelectAll = () => {
            const checkedCount = this.batchModels.filter(
                m => !m.error && m.checked !== false
            ).length;
            document.getElementById('downloadModalTitle').textContent =
                translate('modals.download.titleWithType', { type: this.apiClient.apiConfig.config.displayName }) +
                ` (${checkedCount})`;
            const nextBtn = document.getElementById('nextFromBatchBtn');
            nextBtn.disabled = checkedCount === 0;
            nextBtn.classList.toggle('disabled', checkedCount === 0);
            // Global select-all
            const selectAll = document.getElementById('batchSelectAll');
            if (selectAll) {
                const hfItems = this.batchModels.filter(m => m.source === 'huggingface' && !m.error);
                selectAll.checked = hfItems.length > 0 && hfItems.every(m => m.checked !== false);
            }
            // Per-group select-all
            list.querySelectorAll('.batch-preview-group-select-all').forEach(gsa => {
                const repo = gsa.dataset.repo;
                const repoItems = this.batchModels.filter(m => m.source === 'huggingface' && !m.error && m.repo === repo);
                gsa.checked = repoItems.length > 0 && repoItems.every(m => m.checked !== false);
            });
        };

        list.onclick = (e) => {
            // Per-group select-all checkbox
            const groupSelectAll = e.target.closest('.batch-preview-group-select-all');
            if (groupSelectAll) {
                const repo = groupSelectAll.dataset.repo;
                const checked = groupSelectAll.checked;
                this.batchModels.forEach((m, idx) => {
                    if (m.source === 'huggingface' && !m.error && m.repo === repo) {
                        m.checked = checked;
                        const cb = list.querySelector(`.batch-preview-checkbox[data-index="${idx}"]`);
                        if (cb) cb.checked = checked;
                    }
                });
                updateCountAndSelectAll();
                return;
            }

            const header = e.target.closest('.batch-preview-group-header');
            if (header) {
                const group = header.closest('.batch-preview-group');
                const repo = group.dataset.repo;
                const body = group.querySelector('.batch-preview-group-body');
                const toggle = group.querySelector('.batch-preview-group-toggle');
                const isCollapsed = this.hfRepoCollapsed[repo];
                if (isCollapsed) {
                    this.hfRepoCollapsed[repo] = false;
                    body.style.transition = ''; // restore in case collapse was interrupted
                    body.classList.add('expanded');
                    toggle.classList.add('expanded');
                    // force reflow so expanded class is registered before setting height
                    void body.offsetHeight;
                    body.style.maxHeight = body.scrollHeight + 'px';
                    const onEnd = (e) => {
                        if (e.propertyName !== 'max-height') return;
                        if (this.hfRepoCollapsed[repo] !== false) return;
                        body.style.maxHeight = ''; // fall back to .expanded's 9999px
                        body.removeEventListener('transitionend', onEnd);
                    };
                    body.addEventListener('transitionend', onEnd);
                } else {
                    this.hfRepoCollapsed[repo] = true;
                    body.style.maxHeight = body.scrollHeight + 'px';
                    requestAnimationFrame(() => {
                        // animate only max-height; keep expanded so opacity stays 1
                        body.style.transition = 'max-height 0.35s ease';
                        body.style.maxHeight = '0';
                        toggle.classList.remove('expanded');
                        const onEnd = (e) => {
                            if (e.propertyName !== 'max-height') return;
                            if (this.hfRepoCollapsed[repo] !== true) return; // state changed since
                            body.classList.remove('expanded');
                            body.style.transition = '';
                            body.removeEventListener('transitionend', onEnd);
                        };
                        body.addEventListener('transitionend', onEnd);
                    });
                }
                return;
            }

            const removeBtn = e.target.closest('.batch-preview-remove');
            if (removeBtn) {
                const idx = parseInt(removeBtn.dataset.index);
                this.batchModels.splice(idx, 1);
                this.showBatchPreviewStep();
                return;
            }
            const changeBtn = e.target.closest('.batch-preview-change-version');
            if (changeBtn) {
                const idx = parseInt(changeBtn.dataset.index);
                this.openBatchVersionEditor(idx);
            }
        };

        // Individual HF checkbox handler
        const checkboxes = list.querySelectorAll('.batch-preview-checkbox');
        checkboxes.forEach(cb => {
            cb.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.index);
                if (this.batchModels[idx]) {
                    this.batchModels[idx].checked = e.target.checked;
                }
                updateCountAndSelectAll();
            });
        });

        // Global select-all handler
        const selectAll = document.getElementById('batchSelectAll');
        if (selectAll) {
            selectAll.addEventListener('change', (e) => {
                const checked = e.target.checked;
                const hfCheckboxes = list.querySelectorAll('.batch-preview-checkbox');
                hfCheckboxes.forEach(cb => {
                    cb.checked = checked;
                    const idx = parseInt(cb.dataset.index);
                    if (this.batchModels[idx]) {
                        this.batchModels[idx].checked = checked;
                    }
                });
                updateCountAndSelectAll();
            });
        }

        const nextBtn = document.getElementById('nextFromBatchBtn');
        nextBtn.disabled = validCount === 0;
        nextBtn.classList.toggle('disabled', validCount === 0);
    }

    openBatchVersionEditor(index) {
        this.editingBatchIndex = index;
        const item = this.batchModels[index];

        this.versions = item.versions;
        this.currentVersion = item.selectedVersion;

        document.getElementById('batchPreviewStep').style.display = 'none';
        this.showVersionStep();
    }

    backToUrlFromBatch() {
        document.getElementById('batchPreviewStep').style.display = 'none';
        document.getElementById('urlStep').style.display = 'block';
    }

    nextFromBatch() {
        // For HF items, respect the checked flag; for CivitAI items, use selectedVersion
        const validModels = this.batchModels.filter(m => {
            if (m.error) return false;
            if (m.source === 'huggingface') return m.checked !== false;
            return m.selectedVersion;
        });
        if (validModels.length === 0) return;
        this.proceedToLocation();
    }

    backToUrl() {
        document.getElementById('versionStep').style.display = 'none';
        if (this.isBatchMode && this.editingBatchIndex >= 0) {
            this.editingBatchIndex = -1;
            this.showBatchPreviewStep();
        } else {
            document.getElementById('urlStep').style.display = 'block';
        }
    }

    backToVersions() {
        document.getElementById('locationStep').style.display = 'none';
        if (this.isBatchMode) {
            document.getElementById('batchPreviewStep').style.display = 'block';
        } else {
            document.getElementById('versionStep').style.display = 'block';
        }
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

        let targetFolder = '';
        let useDefaultPaths = false;

        if (this.useDefaultPath) {
            useDefaultPaths = true;
        } else {
            targetFolder = this.folderTreeManager.getSelectedPath();
        }
        if (!this.isBatchMode) {
            // Single-item download
            if (this.source === 'huggingface') {
                return this._downloadHfSingle({
                    modelRoot,
                    targetFolder,
                    useDefaultPaths,
                });
            }

            const fileParams = this.selectedFile ? {
                type: this.selectedFile.type || 'Model',
                format: this.selectedFile.metadata?.format || 'SafeTensor',
                size: this.selectedFile.metadata?.size || 'full',
                fp: this.selectedFile.metadata?.fp,
            } : null;

            return this.executeDownloadWithProgress({
                modelId: this.modelId,
                versionId: this.currentVersion.id,
                versionName: this.currentVersion.name,
                modelRoot,
                targetFolder,
                useDefaultPaths,
                source: this.source,
                fileParams,
                closeModal: true,
            });
        }

        // Batch download mode
        const downloadItems = this.batchModels.filter(m => {
            if (m.error) return false;
            if (!m.selectedVersion) return false;
            // HF items have selectedVersion as a boolean marker + checked flag
            if (m.source === 'huggingface') return m.checked !== false;
            return !m.selectedVersion.existsLocally;
        });
        if (downloadItems.length === 0) {
            showToast('toast.loras.downloadCompleted', {}, 'info');
            modalManager.closeModal('downloadModal');
            return;
        }

        modalManager.closeModal('downloadModal');

        const batchDownloadId = Date.now().toString();
        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const ws = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${batchDownloadId}`);

        const loadingManager = state.loadingManager || this.loadingManager;
        const updateProgress = loadingManager.showDownloadProgress(downloadItems.length);

        let completedDownloads = 0;
        let failedDownloads = 0;

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'download_id') return;

            if (data.status === 'progress' && data.download_id?.startsWith(batchDownloadId)) {
                const current = downloadItems[completedDownloads + failedDownloads];
                const name = current?.selectedVersion?.name || current?.displayName || current?.filename || `#${completedDownloads + failedDownloads + 1}`;
                const metrics = {
                    bytesDownloaded: data.bytes_downloaded,
                    totalBytes: data.total_bytes,
                    bytesPerSecond: data.bytes_per_second,
                };
                updateProgress(data.progress, completedDownloads, name, metrics);
            }
        };

        await new Promise((resolve, reject) => {
            ws.onopen = resolve;
            ws.onerror = reject;
        });

        for (let i = 0; i < downloadItems.length; i++) {
            const item = downloadItems[i];
            const name = item.displayName || item.filename || (item.selectedVersion?.name || `Model #${item.modelId}`);
            const isHf = item.source === 'huggingface';

            updateProgress(0, completedDownloads, name);
            loadingManager.setStatus(`${i + 1}/${downloadItems.length}: ${name}`);

            try {
                let response;
                if (isHf) {
                    // Per-file WebSocket for real-time progress
                    const downloadId = Date.now().toString() + '_hf_' + i;
                    const wsHf = new WebSocket(`${wsProtocol}${window.location.host}/ws/download-progress?id=${downloadId}`);
                    try {
                        await new Promise((resolve, reject) => {
                            wsHf.onopen = resolve;
                            wsHf.onerror = reject;
                        });
                        const snapshotCompleted = completedDownloads;
                        wsHf.onmessage = (event) => {
                            const data = JSON.parse(event.data);
                            if (data.status === 'progress') {
                                const metrics = {
                                    bytesDownloaded: data.bytes_downloaded,
                                    totalBytes: data.total_bytes,
                                    bytesPerSecond: data.bytes_per_second,
                                };
                                updateProgress(data.progress, snapshotCompleted, name, metrics);
                            }
                        };

                        response = await this.apiClient.downloadHfModel({
                            repo: item.repo,
                            filename: item.filename,
                            revision: item.revision || 'main',
                            modelRoot,
                            relativePath: targetFolder,
                            useDefaultPaths,
                            download_id: downloadId,
                        });
                    } finally {
                        wsHf.close();
                    }
                } else {
                    response = await this.apiClient.downloadModel(
                        item.modelId,
                        item.selectedVersion.id,
                        modelRoot,
                        targetFolder,
                        useDefaultPaths,
                        batchDownloadId,
                        item.source
                    );
                }

                if (!response.success) {
                    failedDownloads++;
                } else {
                    completedDownloads++;
                    updateProgress(100, completedDownloads, '');
                }
            } catch (err) {
                console.error(`Failed to download ${name}:`, err);
                failedDownloads++;
            }
        }

        ws.close();
        loadingManager.hide();

        if (failedDownloads === 0) {
            showToast('toast.loras.allDownloadSuccessful', { count: completedDownloads }, 'success');
        } else {
            showToast('toast.loras.downloadPartialSuccess', {
                completed: completedDownloads,
                total: downloadItems.length,
            }, 'warning');
        }

        await resetAndReload(true);
    }

    async downloadVersionWithDefaults(modelType, modelId, versionId, { 
        versionName = '', 
        source = null,
        modelRoot = '',
        targetFolder = ''
    } = {}) {
        try {
            this.apiClient = getModelApiClient(modelType);
        } catch (error) {
            this.apiClient = getModelApiClient();
        }

        this.modelId = modelId ? modelId.toString() : null;
        this.source = source;

        const useDefaultPaths = !modelRoot;
        return this.executeDownloadWithProgress({
            modelId,
            versionId,
            versionName,
            modelRoot: modelRoot || '',
            targetFolder: targetFolder || '',
            useDefaultPaths,
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

// Expose to window for browser extension integration
if (typeof window !== 'undefined') {
    window.downloadManager = downloadManager;
}
