import { showToast } from '../utils/uiHelpers.js';
import { state, getCurrentPageState } from '../state/index.js';
import { modalManager } from './ModalManager.js';
import { bulkManager } from './BulkManager.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { RecipeSidebarApiClient } from '../api/recipeApi.js';
import { FolderTreeManager } from '../components/FolderTreeManager.js';
import { sidebarManager } from '../components/SidebarManager.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { translate } from '../utils/i18nHelpers.js';

class MoveManager {
    constructor() {
        this.currentFilePath = null;
        this.bulkFilePaths = null;
        this.folderTreeManager = new FolderTreeManager();
        this.initialized = false;
        this.recipeApiClient = null;
        this.useDefaultPath = false;
        this.modelRoots = [];

        // Bind methods
        this.updateTargetPath = this.updateTargetPath.bind(this);
        this.handleToggleDefaultPath = this.handleToggleDefaultPath.bind(this);
    }

    _getApiClient(modelType = null) {
        if (state.currentPageType === 'recipes') {
            if (!this.recipeApiClient) {
                this.recipeApiClient = new RecipeSidebarApiClient();
            }
            return this.recipeApiClient;
        }
        return getModelApiClient(modelType);
    }

    initializeEventListeners() {
        if (this.initialized) return;

        const modelRootSelect = document.getElementById('moveModelRoot');

        // Initialize model root directory selector
        modelRootSelect.addEventListener('change', async () => {
            await this.initializeFolderTree();
            this.updateTargetPath();
        });

        // Default path toggle handler
        const toggleInput = document.getElementById('moveUseDefaultPath');
        if (toggleInput) {
            toggleInput.addEventListener('change', this.handleToggleDefaultPath);
        }

        this.initialized = true;
    }

    resetMoveProgress() {
        const container = document.getElementById('moveProgressContainer');
        const bar = document.getElementById('moveProgressBar');
        const percent = document.getElementById('moveProgressPercent');
        const track = container?.querySelector('[role="progressbar"]');
        if (container) container.hidden = true;
        if (bar) {
            bar.classList.remove('indeterminate');
            bar.style.width = '0%';
        }
        if (percent) percent.textContent = '0%';
        if (track) track.setAttribute('aria-valuenow', '0');
    }

    setMoveBusy(isBusy) {
        const modal = document.getElementById('moveModal');
        modal?.classList.toggle('move-in-progress', isBusy);
        ['moveCancelBtn', 'moveConfirmBtn', 'moveModelRoot', 'moveFolderPath', 'moveCreateFolderBtn', 'moveUseDefaultPath']
            .forEach(id => {
                const element = document.getElementById(id);
                if (element) element.disabled = isBusy;
            });
    }

    updateMoveProgress(completed, total, currentPath = '', isActive = true) {
        const container = document.getElementById('moveProgressContainer');
        const text = document.getElementById('moveProgressText');
        const percent = document.getElementById('moveProgressPercent');
        const bar = document.getElementById('moveProgressBar');
        const track = container?.querySelector('[role="progressbar"]');
        if (!container || !bar) return;

        container.hidden = false;
        const safeTotal = Math.max(1, total || 1);
        const value = Math.max(0, Math.min(100, Math.round((completed / safeTotal) * 100)));
        const fileName = currentPath ? currentPath.split('/').pop() : '';
        const movingLabel = translate(
            'modals.moveModel.movingProgress',
            { current: Math.min(completed + (isActive ? 1 : 0), safeTotal), total: safeTotal },
            `Moving ${Math.min(completed + (isActive ? 1 : 0), safeTotal)} / ${safeTotal}`
        );
        if (text) text.textContent = fileName ? `${movingLabel}: ${fileName}` : movingLabel;
        if (percent) percent.textContent = `${value}%`;
        bar.classList.toggle('indeterminate', safeTotal === 1 && completed === 0 && isActive);
        if (!bar.classList.contains('indeterminate')) bar.style.width = `${value}%`;
        if (track) track.setAttribute('aria-valuenow', String(value));
    }

    async showMoveModal(filePath, modelType = null) {
        // Reset state
        this.currentFilePath = null;
        this.bulkFilePaths = null;
        this.resetMoveProgress();
        this.setMoveBusy(false);

        const apiClient = this._getApiClient(modelType);
        const currentPageType = state.currentPageType;
        const modelConfig = apiClient.apiConfig.config;

        // Handle bulk mode
        if (filePath === 'bulk') {
            const selectedPaths = Array.from(state.selectedModels);
            if (selectedPaths.length === 0) {
                showToast('toast.models.noModelsSelected', {}, 'warning');
                return;
            }
            this.bulkFilePaths = selectedPaths;
            document.getElementById('moveModalTitle').textContent = `Move ${selectedPaths.length} ${modelConfig.displayName}s`;
        } else {
            // Single file mode
            this.currentFilePath = filePath;
            document.getElementById('moveModalTitle').textContent = `Move ${modelConfig.displayName}`;
        }

        // Update UI labels based on model type
        document.getElementById('moveRootLabel').textContent = `Select ${modelConfig.displayName} Root:`;
        document.getElementById('moveTargetPathDisplay').querySelector('.path-text').textContent = `Select a ${modelConfig.displayName.toLowerCase()} root directory`;

        // Clear folder path input
        const folderPathInput = document.getElementById('moveFolderPath');
        if (folderPathInput) {
            folderPathInput.value = '';
        }

        // Reset folder tree selection
        if (this.folderTreeManager) {
            this.folderTreeManager.clearSelection();
        }

        try {
            // Fetch model roots
            const modelRootSelect = document.getElementById('moveModelRoot');
            let rootsData;
            if (modelType) {
                rootsData = await apiClient.fetchModelRoots(modelType);
            } else {
                rootsData = await apiClient.fetchModelRoots();
            }

            if (!rootsData.roots || rootsData.roots.length === 0) {
                throw new Error(`No ${modelConfig.displayName.toLowerCase()} roots found`);
            }

            // Populate model root selector
            modelRootSelect.innerHTML = rootsData.roots.map(root =>
                `<option value="${root}">${root}</option>`
            ).join('');

            // Set default root if available
            const settingsKey = `default_${currentPageType.slice(0, -1)}_root`;
            const defaultRoot = state.global.settings[settingsKey];
            if (defaultRoot && rootsData.roots.includes(defaultRoot)) {
                modelRootSelect.value = defaultRoot;
            }

            // Store roots for path calculations
            this.modelRoots = rootsData.roots || [];

            // Initialize event listeners
            this.initializeEventListeners();

            // Setup folder tree manager
            this.folderTreeManager.init({
                onPathChange: (path) => {
                    this.updateTargetPath();
                },
                elementsPrefix: 'move'
            });

            // Initialize folder tree
            await this.initializeFolderTree();

            // Load default path setting
            this.loadDefaultPathSetting(apiClient.modelType);

            this.updateTargetPath();
            modalManager.showModal('moveModal', null, () => {
                // Cleanup on modal close
                if (this.folderTreeManager) {
                    this.folderTreeManager.destroy();
                }
            });

        } catch (error) {
            console.error(`Error fetching ${modelConfig.displayName.toLowerCase()} roots or folders:`, error);
            showToast('toast.models.moveFailed', { message: error.message }, 'error');
        }
    }

    loadDefaultPathSetting(modelType) {
        const storageKey = `use_default_path_${modelType}`;
        this.useDefaultPath = getStorageItem(storageKey, false);

        const toggleInput = document.getElementById('moveUseDefaultPath');
        if (toggleInput) {
            toggleInput.checked = this.useDefaultPath;
            this.updatePathSelectionUI();
        }
    }

    handleToggleDefaultPath(event) {
        this.useDefaultPath = event.target.checked;

        // Save to localStorage per model type
        const apiClient = this._getApiClient();
        const modelType = apiClient.modelType;
        const storageKey = `use_default_path_${modelType}`;
        setStorageItem(storageKey, this.useDefaultPath);

        this.updatePathSelectionUI();
        this.updateTargetPath();
    }

    updatePathSelectionUI() {
        const manualSelection = document.getElementById('moveManualPathSelection');
        if (!manualSelection) return;

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
    }

    async initializeFolderTree() {
        try {
            const apiClient = this._getApiClient();
            // Fetch unified folder tree
            const treeData = await apiClient.fetchUnifiedFolderTree();

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

    updateTargetPath() {
        const pathDisplay = document.getElementById('moveTargetPathDisplay');
        const modelRoot = document.getElementById('moveModelRoot').value;
        const apiClient = this._getApiClient();
        const config = apiClient.apiConfig.config;

        let fullPath = modelRoot || translate('modals.download.selectTypeRoot', { type: config.displayName });

        if (modelRoot) {
            if (this.useDefaultPath) {
                // Show actual template path
                try {
                    const singularType = apiClient.modelType.replace(/s$/, '');
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

    /**
     * Get relative folder path from absolute file path
     * @param {string} absolutePath 
     * @returns {string} Relative folder path using forward slashes
     */
    _getRelativeFolder(absolutePath) {
        if (!absolutePath) return '';
        const normalizedPath = absolutePath.replace(/\\/g, '/');

        for (const root of this.modelRoots || []) {
            const normalizedRoot = root.replace(/\\/g, '/');
            if (normalizedPath.startsWith(normalizedRoot)) {
                let relative = normalizedPath.substring(normalizedRoot.length);
                if (relative.startsWith('/')) relative = relative.substring(1);

                // Get the directory part
                const lastSlash = relative.lastIndexOf('/');
                if (lastSlash === -1) return ''; // In the root itself
                return relative.substring(0, lastSlash);
            }
        }
        return '';
    }

    /**
     * Check if a model should be visible based on its relative folder and current page state
     * @param {string} relativeFolder 
     * @param {Object} pageState 
     * @returns {boolean}
     */
    _isModelVisible(relativeFolder, pageState) {
        if (!pageState) return true;
        // If no folder filter is active, check search recursive option
        if (pageState.activeFolder === null) return true;

        const activeFolder = pageState.activeFolder || '';
        const recursive = pageState.searchOptions?.recursive ?? true;

        const normalizedActive = activeFolder.replace(/\\/g, '/').replace(/\/$/, '');
        const normalizedRelative = relativeFolder.replace(/\\/g, '/').replace(/\/$/, '');

        if (recursive) {
            // Visible if it's in activeFolder or any subfolder
            // Special case for root: if activeFolder is empty, everything is visible in recursive mode
            if (normalizedActive === '') return true;
            
            return normalizedRelative === normalizedActive ||
                normalizedRelative.startsWith(normalizedActive + '/');
        } else {
            // Only visible if it's exactly in activeFolder
            return normalizedRelative === normalizedActive;
        }
    }

    async moveModel() {
        const selectedRoot = document.getElementById('moveModelRoot').value;
        const apiClient = this._getApiClient();
        const config = apiClient.apiConfig.config;

        if (!selectedRoot) {
            showToast('toast.models.pleaseSelectRoot', { type: config.displayName.toLowerCase() }, 'error');
            return;
        }

        // Get selected folder path from folder tree manager
        const targetFolder = this.useDefaultPath ? '' : this.folderTreeManager.getSelectedPath();

        let targetPath = selectedRoot;
        if (targetFolder) {
            targetPath = `${targetPath}/${targetFolder}`;
        }

        this.setMoveBusy(true);
        try {
            let movedFiles = []; // Array of { original_file_path, new_file_path }

            if (this.bulkFilePaths) {
                // Move one item per request so the progress bar represents completed work.
                const total = this.bulkFilePaths.length;
                const failures = [];
                let skipped = 0;
                for (let index = 0; index < total; index += 1) {
                    const filePath = this.bulkFilePaths[index];
                    this.updateMoveProgress(index, total, filePath, true);
                    try {
                        const result = await apiClient.moveSingleModel(
                            filePath,
                            targetPath,
                            this.useDefaultPath,
                            true
                        );
                        if (result?.new_file_path) {
                            movedFiles.push({
                                original_file_path: result.original_file_path || filePath,
                                new_file_path: result.new_file_path
                            });
                        } else {
                            skipped += 1;
                        }
                    } catch (error) {
                        failures.push({ filePath, message: error.message });
                    }
                    this.updateMoveProgress(index + 1, total, filePath, false);
                }

                if (failures.length > 0) {
                    showToast('toast.api.bulkMovePartial', {
                        successCount: movedFiles.length,
                        type: config.displayName,
                        failureCount: failures.length
                    }, 'warning');
                    const failureMessage = failures.slice(0, 3)
                        .map(item => `${item.filePath.split('/').pop()}: ${item.message}`)
                        .join('\n');
                    showToast('toast.api.bulkMoveFailures', { failures: failureMessage }, 'warning', 6000);
                } else if (movedFiles.length > 0) {
                    showToast('toast.api.bulkMoveSuccess', {
                        successCount: movedFiles.length,
                        type: config.displayName
                    }, 'success');
                } else if (skipped > 0) {
                    showToast('toast.api.allAlreadyInFolder', { type: config.displayName }, 'info');
                }

                // Deselect moving items and exit bulk mode
                this.bulkFilePaths.forEach(path => bulkManager.deselectItem(path));
                if (state.bulkMode) bulkManager.toggleBulkMode();
            } else {
                // Single move mode
                this.updateMoveProgress(0, 1, this.currentFilePath, true);
                const result = await apiClient.moveSingleModel(this.currentFilePath, targetPath, this.useDefaultPath);
                if (result) {
                    movedFiles.push({
                        original_file_path: result.original_file_path || this.currentFilePath,
                        new_file_path: result.new_file_path
                    });
                }
                this.updateMoveProgress(1, 1, this.currentFilePath, false);

                // Deselect moving item
                bulkManager.deselectItem(this.currentFilePath);
            }

            // Update VirtualScroller in-place instead of full reload
            if (movedFiles.length > 0 && state.virtualScroller) {
                // Get current page state for folder filter check
                const pageState = getCurrentPageState();
                const normalizedActive = (pageState.activeFolder || '').replace(/\\/g, '/').replace(/\/$/, '');
                const isRecursive = pageState.searchOptions?.recursive ?? true;
                const isFolderFiltered = pageState.activeFolder !== null;

                // Determine which items are still visible after the move
                const pathsToRemove = [];
                const pathsToUpdate = []; // { originalPath, newData }

                for (const moved of movedFiles) {
                    if (!moved.original_file_path) continue;

                    if (isFolderFiltered) {
                        // Compute relative folder of the new path
                        const newRelativeFolder = this._getRelativeFolder(moved.new_file_path);
                        const normalizedNewFolder = newRelativeFolder.replace(/\\/g, '/').replace(/\/$/, '');

                        // Check if the new location is still within the active folder
                        let stillVisible;
                        if (isRecursive) {
                            stillVisible = normalizedActive === '' ||
                                normalizedNewFolder === normalizedActive ||
                                normalizedNewFolder.startsWith(normalizedActive + '/');
                        } else {
                            stillVisible = normalizedNewFolder === normalizedActive;
                        }

                        if (stillVisible) {
                            pathsToUpdate.push({
                                originalPath: moved.original_file_path,
                                newData: {
                                    file_path: moved.new_file_path,
                                    folder: newRelativeFolder
                                }
                            });
                        } else {
                            pathsToRemove.push(moved.original_file_path);
                        }
                    } else {
                        // No folder filter active — items remain visible, just update path
                        pathsToUpdate.push({
                            originalPath: moved.original_file_path,
                            newData: {
                                file_path: moved.new_file_path,
                                folder: this._getRelativeFolder(moved.new_file_path)
                            }
                        });
                    }
                }

                // Apply updates to the VirtualScroller
                if (pathsToRemove.length > 0) {
                    state.virtualScroller.removeMultipleItemsByFilePath(pathsToRemove);
                }
                for (const update of pathsToUpdate) {
                    state.virtualScroller.updateSingleItem(update.originalPath, update.newData);
                }
            }

            // Refresh folder tree in sidebar (no model data reload)
            await sidebarManager.refresh();

            this.setMoveBusy(false);
            modalManager.closeModal('moveModal');

        } catch (error) {
            console.error('Error moving model(s):', error);
            showToast('toast.models.moveFailed', { message: error.message }, 'error');
            this.setMoveBusy(false);
        }
    }
}

export const moveManager = new MoveManager();
