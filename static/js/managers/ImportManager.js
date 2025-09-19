import { modalManager } from './ModalManager.js';
import { LoadingManager } from './LoadingManager.js';
import { ImportStepManager } from './import/ImportStepManager.js';
import { ImageProcessor } from './import/ImageProcessor.js';
import { RecipeDataManager } from './import/RecipeDataManager.js';
import { DownloadManager } from './import/DownloadManager.js';
import { FolderTreeManager } from '../components/FolderTreeManager.js';
import { formatFileSize } from '../utils/formatters.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { state } from '../state/index.js';
import { MODEL_TYPES } from '../api/apiConfig.js';
import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';

export class ImportManager {
    constructor() {
        // Core state properties
        this.recipeImage = null;
        this.recipeData = null;
        this.recipeName = '';
        this.recipeTags = [];
        this.missingLoras = [];
        this.initialized = false;
        this.selectedFolder = '';
        this.downloadableLoRAs = [];
        this.recipeId = null;
        this.importMode = 'url'; // Default mode: 'url' or 'upload'
        this.useDefaultPath = false;
        this.apiClient = null;
        
        // Initialize sub-managers
        this.loadingManager = new LoadingManager();
        this.stepManager = new ImportStepManager();
        this.imageProcessor = new ImageProcessor(this);
        this.recipeDataManager = new RecipeDataManager(this);
        this.downloadManager = new DownloadManager(this);
        this.folderTreeManager = new FolderTreeManager();
        
        // Bind methods
        this.formatFileSize = formatFileSize;
        this.updateTargetPath = this.updateTargetPath.bind(this);
        this.handleToggleDefaultPath = this.toggleDefaultPath.bind(this);
    }

    showImportModal(recipeData = null, recipeId = null) {
        if (!this.initialized) {
            const modal = document.getElementById('importModal');
            if (!modal) {
                console.error('Import modal element not found');
                return;
            }
            this.initializeEventHandlers();
            this.initialized = true;
        }
        
        // Get API client for LoRAs
        this.apiClient = getModelApiClient(MODEL_TYPES.LORA);
        
        // Reset state
        this.resetSteps();
        if (recipeData) {
            this.downloadableLoRAs = recipeData.loras;
            this.recipeId = recipeId;
        }
        
        // Show modal
        modalManager.showModal('importModal', null, () => {
            this.cleanupFolderBrowser();
            this.stepManager.removeInjectedStyles();
        });

        // Verify visibility and focus on URL input
        setTimeout(() => {      
            // Ensure URL option is selected and focus on the input
            this.toggleImportMode('url');
            const urlInput = document.getElementById('imageUrlInput');
            if (urlInput) {
                urlInput.focus();
            }
        }, 50);
    }

    initializeEventHandlers() {
        // Default path toggle handler
        const useDefaultPathToggle = document.getElementById('importUseDefaultPath');
        if (useDefaultPathToggle) {
            useDefaultPathToggle.addEventListener('change', this.handleToggleDefaultPath);
        }
    }

    resetSteps() {
        // Clear UI state
        this.stepManager.removeInjectedStyles();
        this.stepManager.showStep('uploadStep');
        
        // Reset form inputs
        const fileInput = document.getElementById('recipeImageUpload');
        if (fileInput) fileInput.value = '';
        
        const urlInput = document.getElementById('imageUrlInput');
        if (urlInput) urlInput.value = '';
        
        const uploadError = document.getElementById('uploadError');
        if (uploadError) uploadError.textContent = '';
        
        const importUrlError = document.getElementById('importUrlError');
        if (importUrlError) importUrlError.textContent = '';
        
        const recipeName = document.getElementById('recipeName');
        if (recipeName) recipeName.value = '';
        
        const tagsContainer = document.getElementById('tagsContainer');
        if (tagsContainer) tagsContainer.innerHTML = `<div class="empty-tags">${translate('recipes.controls.import.noTagsAdded', {}, 'No tags added')}</div>`;
        
        // Clear folder path input
        const folderPathInput = document.getElementById('importFolderPath');
        if (folderPathInput) {
            folderPathInput.value = '';
        }
        
        // Reset state variables
        this.recipeImage = null;
        this.recipeData = null;
        this.recipeName = '';
        this.recipeTags = [];
        this.missingLoras = [];
        this.downloadableLoRAs = [];
        this.selectedFolder = '';
        
        // Reset import mode
        this.importMode = 'url';
        this.toggleImportMode('url');
        
        // Clear folder tree selection
        if (this.folderTreeManager) {
            this.folderTreeManager.clearSelection();
        }
        
        // Reset default path toggle
        this.loadDefaultPathSetting();
        
        // Reset duplicate related properties
        this.duplicateRecipes = [];
    }

    toggleImportMode(mode) {
        this.importMode = mode;
        
        // Update toggle buttons
        const uploadBtn = document.querySelector('.toggle-btn[data-mode="upload"]');
        const urlBtn = document.querySelector('.toggle-btn[data-mode="url"]');
        
        if (uploadBtn && urlBtn) {
            if (mode === 'upload') {
                uploadBtn.classList.add('active');
                urlBtn.classList.remove('active');
            } else {
                uploadBtn.classList.remove('active');
                urlBtn.classList.add('active');
            }
        }
        
        // Show/hide appropriate sections
        const uploadSection = document.getElementById('uploadSection');
        const urlSection = document.getElementById('urlSection');
        
        if (uploadSection && urlSection) {
            if (mode === 'upload') {
                uploadSection.style.display = 'block';
                urlSection.style.display = 'none';
            } else {
                uploadSection.style.display = 'none';
                urlSection.style.display = 'block';
            }
        }
        
        // Clear error messages
        const uploadError = document.getElementById('uploadError');
        const importUrlError = document.getElementById('importUrlError');
        
        if (uploadError) uploadError.textContent = '';
        if (importUrlError) importUrlError.textContent = '';
    }

    handleImageUpload(event) {
        this.imageProcessor.handleFileUpload(event);
    }

    async handleUrlInput() {
        await this.imageProcessor.handleUrlInput();
    }

    async uploadAndAnalyzeImage() {
        await this.imageProcessor.uploadAndAnalyzeImage();
    }

    showRecipeDetailsStep() {
        this.recipeDataManager.showRecipeDetailsStep();
    }

    handleRecipeNameChange(event) {
        this.recipeName = event.target.value.trim();
    }

    addTag() {
        this.recipeDataManager.addTag();
    }
    
    removeTag(tag) {
        this.recipeDataManager.removeTag(tag);
    }

    proceedFromDetails() {
        this.recipeDataManager.proceedFromDetails();
    }

    async proceedToLocation() {
        this.stepManager.showStep('locationStep');
        
        try {
            // Fetch LoRA roots
            const rootsData = await this.apiClient.fetchModelRoots();
            const loraRoot = document.getElementById('importLoraRoot');
            loraRoot.innerHTML = rootsData.roots.map(root => 
                `<option value="${root}">${root}</option>`
            ).join('');

            // Set default root if available
            const defaultRootKey = 'default_lora_root';
            const defaultRoot = state.global.settings[defaultRootKey];
            if (defaultRoot && rootsData.roots.includes(defaultRoot)) {
                loraRoot.value = defaultRoot;
            }

            // Set autocomplete="off" on folderPath input
            const folderPathInput = document.getElementById('importFolderPath');
            if (folderPathInput) {
                folderPathInput.setAttribute('autocomplete', 'off');
            }

            // Setup folder tree manager
            this.folderTreeManager.init({
                elementsPrefix: 'import',
                onPathChange: (path) => {
                    this.selectedFolder = path;
                    this.updateTargetPath();
                }
            });
            
            // Initialize folder tree
            await this.initializeFolderTree();
            
            // Setup lora root change handler
            loraRoot.addEventListener('change', async () => {
                await this.initializeFolderTree();
                this.updateTargetPath();
            });
            
            // Load default path setting for LoRAs
            this.loadDefaultPathSetting();
            
            this.updateTargetPath();
        } catch (error) {
            showToast('toast.recipes.importFailed', { message: error.message }, 'error');
        }
    }

    backToUpload() {
        this.stepManager.showStep('uploadStep');
        
        // Reset file input
        const fileInput = document.getElementById('recipeImageUpload');
        if (fileInput) fileInput.value = '';
        
        // Reset URL input
        const urlInput = document.getElementById('imageUrlInput');
        if (urlInput) urlInput.value = '';
        
        // Clear error messages
        const uploadError = document.getElementById('uploadError');
        if (uploadError) uploadError.textContent = '';
        
        const importUrlError = document.getElementById('importUrlError');
        if (importUrlError) importUrlError.textContent = '';
    }

    backToDetails() {
        this.stepManager.showStep('detailsStep');
    }

    async saveRecipe() {
        await this.downloadManager.saveRecipe();
    }

    loadDefaultPathSetting() {
        const storageKey = 'use_default_path_loras';
        this.useDefaultPath = getStorageItem(storageKey, false);
        
        const toggleInput = document.getElementById('importUseDefaultPath');
        if (toggleInput) {
            toggleInput.checked = this.useDefaultPath;
            this.updatePathSelectionUI();
        }
    }

    toggleDefaultPath(event) {
        this.useDefaultPath = event.target.checked;
        
        // Save to localStorage for LoRAs
        const storageKey = 'use_default_path_loras';
        setStorageItem(storageKey, this.useDefaultPath);
        
        this.updatePathSelectionUI();
        this.updateTargetPath();
    }

    updatePathSelectionUI() {
        const manualSelection = document.getElementById('importManualPathSelection');
        
        // Always show manual path selection, but disable/enable based on useDefaultPath
        if (manualSelection) {
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
        }
        
        // Always update the main path display
        this.updateTargetPath();
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
                showToast('toast.recipes.folderTreeFailed', {}, 'error');
            }
        } catch (error) {
            console.error('Error initializing folder tree:', error);
            showToast('toast.recipes.folderTreeError', {}, 'error');
        }
    }

    cleanupFolderBrowser() {
        if (this.folderTreeManager) {
            this.folderTreeManager.destroy();
        }
    }

    updateTargetPath() {
        const pathDisplay = document.getElementById('importTargetPathDisplay');
        const loraRoot = document.getElementById('importLoraRoot').value;
        
        let fullPath = loraRoot || translate('recipes.controls.import.selectLoraRoot', {}, 'Select a LoRA root directory');         if (loraRoot) {
            if (this.useDefaultPath) {
                // Show actual template path
                try {
                    const templates = state.global.settings.download_path_templates;
                    const template = templates.lora;
                    fullPath += `/${template}`;
                } catch (error) {
                    console.error('Failed to fetch template:', error);
                    fullPath += '/[Auto-organized by path template]';
                }
            } else {
                // Show manual path selection
                const selectedPath = this.folderTreeManager ? this.folderTreeManager.getSelectedPath() : '';
                if (selectedPath) {
                    fullPath += '/' + selectedPath;
                }
            }
        }

        if (pathDisplay) {
            pathDisplay.innerHTML = `<span class="path-text">${fullPath}</span>`;
        }
    }

    /**
     * NOTE: This function is no longer needed with the simplified duplicates flow.
     * We're keeping it as a no-op stub to avoid breaking existing code that might call it.
     */
    markDuplicateForDeletion(recipeId, buttonElement) {
        // This functionality has been removed
        console.log('markDuplicateForDeletion is deprecated');
    }

    /**
     * NOTE: This function is no longer needed with the simplified duplicates flow.
     * We're keeping it as a no-op stub to avoid breaking existing code that might call it.
     */
    importRecipeAnyway() {
        // This functionality has been simplified
        // Just proceed with normal flow
        this.proceedFromDetails();
    }

    downloadMissingLoras(recipeData, recipeId) {
        // Store the recipe data and ID
        this.recipeData = recipeData;
        this.recipeId = recipeId;
        
        // Show the modal and go to location step
        this.showImportModal(recipeData, recipeId);
        this.proceedToLocation();
        
        // Update the modal title
        const modalTitle = document.querySelector('#importModal h2');
        if (modalTitle) modalTitle.textContent = translate('recipes.controls.import.downloadMissingLoras', {}, 'Download Missing LoRAs');
        
        // Update the save button text
        const saveButton = document.querySelector('#locationStep .primary-btn');
        if (saveButton) saveButton.textContent = translate('recipes.controls.import.downloadMissingLoras', {}, 'Download Missing LoRAs');
        
        // Hide the back button
        const backButton = document.querySelector('#locationStep .secondary-btn');
        if (backButton) backButton.style.display = 'none';
    }
}
