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

    async showMoveModal(filePath, modelType = null) {
        // Reset state
        this.currentFilePath = null;
        this.bulkFilePaths = null;

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
        const targetFolder = this.folderTreeManager.getSelectedPath();

        let targetPath = selectedRoot;
        if (targetFolder) {
            targetPath = `${targetPath}/${targetFolder}`;
        }

        try {
            if (this.bulkFilePaths) {
                // Bulk move mode
                const results = await apiClient.moveBulkModels(this.bulkFilePaths, targetPath, this.useDefaultPath);

                // Update virtual scroller visibility/metadata
                const pageState = getCurrentPageState();
                if (state.virtualScroller) {
                    results.forEach(result => {
                        if (result.success) {
                            const newRelativeFolder = this._getRelativeFolder(result.new_file_path);
                            const isVisible = this._isModelVisible(newRelativeFolder, pageState);

                            if (!isVisible) {
                                state.virtualScroller.removeItemByFilePath(result.original_file_path);
                            } else if (result.new_file_path !== result.original_file_path) {
                                const newFileNameWithExt = result.new_file_path.substring(result.new_file_path.lastIndexOf('/') + 1);
                                const baseFileName = newFileNameWithExt.substring(0, newFileNameWithExt.lastIndexOf('.'));

                                state.virtualScroller.updateSingleItem(result.original_file_path, {
                                    file_path: result.new_file_path,
                                    file_name: baseFileName,
                                    folder: newRelativeFolder
                                });
                            }
                        }
                    });
                }
            } else {
                // Single move mode
                const result = await apiClient.moveSingleModel(this.currentFilePath, targetPath, this.useDefaultPath);

                const pageState = getCurrentPageState();
                if (result && result.new_file_path && state.virtualScroller) {
                    const newRelativeFolder = this._getRelativeFolder(result.new_file_path);
                    const isVisible = this._isModelVisible(newRelativeFolder, pageState);

                    if (!isVisible) {
                        state.virtualScroller.removeItemByFilePath(this.currentFilePath);
                    } else {
                        // Update the model card even if it stays visible
                        const newFileNameWithExt = result.new_file_path.substring(result.new_file_path.lastIndexOf('/') + 1);
                        const baseFileName = newFileNameWithExt.substring(0, newFileNameWithExt.lastIndexOf('.'));

                        state.virtualScroller.updateSingleItem(this.currentFilePath, {
                            file_path: result.new_file_path,
                            file_name: baseFileName,
                            folder: newRelativeFolder
                        });
                    }
                }
            }

            // Refresh folder tags after successful move
            sidebarManager.refresh();

            modalManager.closeModal('moveModal');

            // If we were in bulk mode, exit it after successful move
            if (this.bulkFilePaths && state.bulkMode) {
                bulkManager.toggleBulkMode();
            }

        } catch (error) {
            console.error('Error moving model(s):', error);
            showToast('toast.models.moveFailed', { message: error.message }, 'error');
        }
    }
}

export const moveManager = new MoveManager();
