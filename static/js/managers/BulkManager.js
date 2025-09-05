import { state, getCurrentPageState } from '../state/index.js';
import { showToast, copyToClipboard, sendLoraToWorkflow } from '../utils/uiHelpers.js';
import { updateCardsForBulkMode } from '../components/shared/ModelCard.js';
import { modalManager } from './ModalManager.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { MODEL_TYPES, MODEL_CONFIG } from '../api/apiConfig.js';
import { PRESET_TAGS } from '../utils/constants.js';

export class BulkManager {
    constructor() {
        this.bulkBtn = document.getElementById('bulkOperationsBtn');
        // Remove bulk panel references since we're using context menu now
        this.bulkContextMenu = null; // Will be set by core initialization
        
        // Model type specific action configurations
        this.actionConfig = {
            [MODEL_TYPES.LORA]: {
                addTags: true,
                sendToWorkflow: true,
                copyAll: true,
                refreshAll: true,
                moveAll: true,
                deleteAll: true
            },
            [MODEL_TYPES.EMBEDDING]: {
                addTags: true,
                sendToWorkflow: false,
                copyAll: false,
                refreshAll: true,
                moveAll: true,
                deleteAll: true
            },
            [MODEL_TYPES.CHECKPOINT]: {
                addTags: true,
                sendToWorkflow: false,
                copyAll: false,
                refreshAll: true,
                moveAll: false,
                deleteAll: true
            }
        };
    }

    initialize() {
        this.setupEventListeners();
        this.setupGlobalKeyboardListeners();
    }

    setBulkContextMenu(bulkContextMenu) {
        this.bulkContextMenu = bulkContextMenu;
    }

    setupEventListeners() {
        // Only setup bulk mode toggle button listener now
        // Context menu actions are handled by BulkContextMenu
    }

    setupGlobalKeyboardListeners() {
        document.addEventListener('keydown', (e) => {
            if (modalManager.isAnyModalOpen()) {
                return;
            }

            const searchInput = document.getElementById('searchInput');
            if (searchInput && document.activeElement === searchInput) {
                return;
            }

            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
                e.preventDefault();
                if (!state.bulkMode) {
                    this.toggleBulkMode();
                    setTimeout(() => this.selectAllVisibleModels(), 50);
                } else {
                    this.selectAllVisibleModels();
                }
            } else if (e.key === 'Escape' && state.bulkMode) {
                this.toggleBulkMode();
            } else if (e.key.toLowerCase() === 'b') {
                this.toggleBulkMode();
            }
        });
    }

    toggleBulkMode() {
        state.bulkMode = !state.bulkMode;
        
        this.bulkBtn.classList.toggle('active', state.bulkMode);
        
        updateCardsForBulkMode(state.bulkMode);
        
        if (!state.bulkMode) {
            this.clearSelection();
            
            // Hide context menu when exiting bulk mode
            if (this.bulkContextMenu) {
                this.bulkContextMenu.hideMenu();
            }
        }
    }

    clearSelection() {
        document.querySelectorAll('.model-card.selected').forEach(card => {
            card.classList.remove('selected');
        });
        state.selectedModels.clear();
        
        // Update context menu header if visible
        if (this.bulkContextMenu) {
            this.bulkContextMenu.updateSelectedCountHeader();
        }
    }

    toggleCardSelection(card) {
        const filepath = card.dataset.filepath;
        
        if (card.classList.contains('selected')) {
            card.classList.remove('selected');
            state.selectedModels.delete(filepath);
        } else {
            card.classList.add('selected');
            state.selectedModels.add(filepath);
            
            // Cache the metadata for this model
            const metadataCache = this.getMetadataCache();
            metadataCache.set(filepath, {
                fileName: card.dataset.file_name,
                usageTips: card.dataset.usage_tips,
                previewUrl: this.getCardPreviewUrl(card),
                isVideo: this.isCardPreviewVideo(card),
                modelName: card.dataset.name
            });
        }
        
        // Update context menu header if visible
        if (this.bulkContextMenu) {
            this.bulkContextMenu.updateSelectedCountHeader();
        }
    }

    getMetadataCache() {
        const currentType = state.currentPageType;
        const pageState = getCurrentPageState();
        
        // Initialize metadata cache if it doesn't exist
        if (currentType === MODEL_TYPES.LORA) {
            if (!state.loraMetadataCache) {
                state.loraMetadataCache = new Map();
            }
            return state.loraMetadataCache;
        } else {
            if (!pageState.metadataCache) {
                pageState.metadataCache = new Map();
            }
            return pageState.metadataCache;
        }
    }
    
    getCardPreviewUrl(card) {
        const img = card.querySelector('img');
        const video = card.querySelector('video source');
        return img ? img.src : (video ? video.src : '/loras_static/images/no-preview.png');
    }
    
    isCardPreviewVideo(card) {
        return card.querySelector('video') !== null;
    }

    applySelectionState() {
        if (!state.bulkMode) return;
        
        document.querySelectorAll('.model-card').forEach(card => {
            const filepath = card.dataset.filepath;
            if (state.selectedModels.has(filepath)) {
                card.classList.add('selected');
                
                const metadataCache = this.getMetadataCache();
                metadataCache.set(filepath, {
                    fileName: card.dataset.file_name,
                    usageTips: card.dataset.usage_tips,
                    previewUrl: this.getCardPreviewUrl(card),
                    isVideo: this.isCardPreviewVideo(card),
                    modelName: card.dataset.name
                });
            } else {
                card.classList.remove('selected');
            }
        });
    }

    async copyAllModelsSyntax() {
        if (state.currentPageType !== MODEL_TYPES.LORA) {
            showToast('toast.loras.copyOnlyForLoras', {}, 'warning');
            return;
        }
        
        if (state.selectedModels.size === 0) {
            showToast('toast.loras.noLorasSelected', {}, 'warning');
            return;
        }
        
        const loraSyntaxes = [];
        const missingLoras = [];
        const metadataCache = this.getMetadataCache();
        
        for (const filepath of state.selectedModels) {
            const metadata = metadataCache.get(filepath);
            
            if (metadata) {
                const usageTips = JSON.parse(metadata.usageTips || '{}');
                const strength = usageTips.strength || 1;
                loraSyntaxes.push(`<lora:${metadata.fileName}:${strength}>`);
            } else {
                missingLoras.push(filepath);
            }
        }
        
        if (missingLoras.length > 0) {
            console.warn('Missing metadata for some selected loras:', missingLoras);
            showToast('toast.loras.missingDataForLoras', { count: missingLoras.length }, 'warning');
        }
        
        if (loraSyntaxes.length === 0) {
            showToast('toast.loras.noValidLorasToCopy', {}, 'error');
            return;
        }
        
        await copyToClipboard(loraSyntaxes.join(', '), `Copied ${loraSyntaxes.length} LoRA syntaxes to clipboard`);
    }
    
    async sendAllModelsToWorkflow(replaceMode = false) {
        if (state.currentPageType !== MODEL_TYPES.LORA) {
            showToast('toast.loras.sendOnlyForLoras', {}, 'warning');
            return;
        }
        
        if (state.selectedModels.size === 0) {
            showToast('toast.loras.noLorasSelected', {}, 'warning');
            return;
        }
        
        const loraSyntaxes = [];
        const missingLoras = [];
        const metadataCache = this.getMetadataCache();
        
        for (const filepath of state.selectedModels) {
            const metadata = metadataCache.get(filepath);
            
            if (metadata) {
                const usageTips = JSON.parse(metadata.usageTips || '{}');
                const strength = usageTips.strength || 1;
                loraSyntaxes.push(`<lora:${metadata.fileName}:${strength}>`);
            } else {
                missingLoras.push(filepath);
            }
        }
        
        if (missingLoras.length > 0) {
            console.warn('Missing metadata for some selected loras:', missingLoras);
            showToast('toast.loras.missingDataForLoras', { count: missingLoras.length }, 'warning');
        }
        
        if (loraSyntaxes.length === 0) {
            showToast('toast.loras.noValidLorasToSend', {}, 'error');
            return;
        }
        
        await sendLoraToWorkflow(loraSyntaxes.join(', '), replaceMode, 'lora');
    }
    
    showBulkDeleteModal() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }
        
        const countElement = document.getElementById('bulkDeleteCount');
        if (countElement) {
            countElement.textContent = state.selectedModels.size;
        }
        
        modalManager.showModal('bulkDeleteModal');
    }
    
    async confirmBulkDelete() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            modalManager.closeModal('bulkDeleteModal');
            return;
        }
        
        modalManager.closeModal('bulkDeleteModal');
        
        try {
            const apiClient = getModelApiClient();
            const filePaths = Array.from(state.selectedModels);
            
            const result = await apiClient.bulkDeleteModels(filePaths);
            
            if (result.success) {
                const currentConfig = MODEL_CONFIG[state.currentPageType];
                showToast('toast.models.deletedSuccessfully', { 
                    count: result.deleted_count, 
                    type: currentConfig.displayName.toLowerCase() 
                }, 'success');
                
                filePaths.forEach(path => {
                    state.virtualScroller.removeItemByFilePath(path);
                });
                this.clearSelection();

                if (window.modelDuplicatesManager) {
                    window.modelDuplicatesManager.updateDuplicatesBadgeAfterRefresh();
                }
            } else {
                showToast('toast.models.deleteFailed', { error: result.error || 'Failed to delete models' }, 'error');
            }
        } catch (error) {
            console.error('Error during bulk delete:', error);
            showToast('toast.models.deleteFailedGeneral', {}, 'error');
        }
    }
    
    deselectItem(filepath) {
        const card = document.querySelector(`.model-card[data-filepath="${filepath}"]`);
        if (card) {
            card.classList.remove('selected');
        }
        
        state.selectedModels.delete(filepath);
    }

    selectAllVisibleModels() {
        if (!state.virtualScroller || !state.virtualScroller.items) {
            showToast('toast.bulk.unableToSelectAll', {}, 'error');
            return;
        }
        
        const oldCount = state.selectedModels.size;
        const metadataCache = this.getMetadataCache();
        
        state.virtualScroller.items.forEach(item => {
            if (item && item.file_path) {
                state.selectedModels.add(item.file_path);
                
                if (!metadataCache.has(item.file_path)) {
                    metadataCache.set(item.file_path, {
                        fileName: item.file_name,
                        usageTips: item.usage_tips || '{}',
                        previewUrl: item.preview_url || '/loras_static/images/no-preview.png',
                        isVideo: item.is_video || false,
                        modelName: item.name || item.file_name
                    });
                }
            }
        });
        
        this.applySelectionState();
        
        const newlySelected = state.selectedModels.size - oldCount;
        const currentConfig = MODEL_CONFIG[state.currentPageType];
        showToast('toast.models.selectedAdditional', { 
            count: newlySelected, 
            type: currentConfig.displayName.toLowerCase() 
        }, 'success');
        
        if (this.isStripVisible) {
            this.updateThumbnailStrip();
        }
    }

    async refreshAllMetadata() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }
        
        try {
            const apiClient = getModelApiClient();
            const filePaths = Array.from(state.selectedModels);
            
            const result = await apiClient.refreshBulkModelMetadata(filePaths);
            
            if (result.success) {
                const metadataCache = this.getMetadataCache();
                for (const filepath of state.selectedModels) {
                    const metadata = metadataCache.get(filepath);
                    if (metadata) {
                        const card = document.querySelector(`.model-card[data-filepath="${filepath}"]`);
                        if (card) {
                            metadataCache.set(filepath, {
                                ...metadata,
                                fileName: card.dataset.file_name,
                                usageTips: card.dataset.usage_tips,
                                previewUrl: this.getCardPreviewUrl(card),
                                isVideo: this.isCardPreviewVideo(card),
                                modelName: card.dataset.name
                            });
                        }
                    }
                }
                
                if (this.isStripVisible) {
                    this.updateThumbnailStrip();
                }
            }
            
        } catch (error) {
            console.error('Error during bulk metadata refresh:', error);
            showToast('toast.models.refreshMetadataFailed', {}, 'error');
        }
    }
    
    showBulkAddTagsModal() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }
        
        const countElement = document.getElementById('bulkAddTagsCount');
        if (countElement) {
            countElement.textContent = state.selectedModels.size;
        }
        
        // Clear any existing tags in the modal
        const tagsContainer = document.getElementById('bulkTagsItems');
        if (tagsContainer) {
            tagsContainer.innerHTML = '';
        }
        
        modalManager.showModal('bulkAddTagsModal', null, null, () => {
            // Cleanup when modal is closed
            this.cleanupBulkAddTagsModal();
        });
        
        // Initialize the bulk tags editing interface
        this.initializeBulkTagsInterface();
    }
    
    initializeBulkTagsInterface() {
        // Setup tag input behavior
        const tagInput = document.querySelector('.bulk-metadata-input');
        if (tagInput) {
            tagInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.addBulkTag(e.target.value.trim());
                    e.target.value = '';
                    // Update dropdown to show added indicator
                    this.updateBulkSuggestionsDropdown();
                }
            });
        }
        
        // Create suggestions dropdown
        const tagForm = document.querySelector('#bulkAddTagsModal .metadata-add-form');
        if (tagForm) {
            const suggestionsDropdown = this.createBulkSuggestionsDropdown(PRESET_TAGS);
            tagForm.appendChild(suggestionsDropdown);
        }
        
        // Setup save button
        const appendBtn = document.querySelector('.bulk-append-tags-btn');
        const replaceBtn = document.querySelector('.bulk-replace-tags-btn');
        
        if (appendBtn) {
            appendBtn.addEventListener('click', () => {
                this.saveBulkTags('append');
            });
        }
        
        if (replaceBtn) {
            replaceBtn.addEventListener('click', () => {
                this.saveBulkTags('replace');
            });
        }
    }
    
    createBulkSuggestionsDropdown(presetTags) {
        const dropdown = document.createElement('div');
        dropdown.className = 'metadata-suggestions-dropdown';
        
        const header = document.createElement('div');
        header.className = 'metadata-suggestions-header';
        header.innerHTML = `
            <span>Suggested Tags</span>
            <small>Click to add</small>
        `;
        dropdown.appendChild(header);
        
        const container = document.createElement('div');
        container.className = 'metadata-suggestions-container';
        
        presetTags.forEach(tag => {
            // Check if tag is already added
            const existingTags = this.getBulkExistingTags();
            const isAdded = existingTags.includes(tag);
            
            const item = document.createElement('div');
            item.className = `metadata-suggestion-item ${isAdded ? 'already-added' : ''}`;
            item.title = tag;
            item.innerHTML = `
                <span class="metadata-suggestion-text">${tag}</span>
                ${isAdded ? '<span class="added-indicator"><i class="fas fa-check"></i></span>' : ''}
            `;
            
            if (!isAdded) {
                item.addEventListener('click', () => {
                    this.addBulkTag(tag);
                    const input = document.querySelector('.bulk-metadata-input');
                    if (input) {
                        input.value = tag;
                        input.focus();
                    }
                    // Update dropdown to show added indicator
                    this.updateBulkSuggestionsDropdown();
                });
            }
            
            container.appendChild(item);
        });
        
        dropdown.appendChild(container);
        return dropdown;
    }
    
    addBulkTag(tag) {
        tag = tag.trim().toLowerCase();
        if (!tag) return;
        
        const tagsContainer = document.getElementById('bulkTagsItems');
        if (!tagsContainer) return;
        
        // Validation: Check length
        if (tag.length > 30) {
            showToast('modelTags.validation.maxLength', {}, 'error');
            return;
        }
        
        // Validation: Check total number
        const currentTags = tagsContainer.querySelectorAll('.metadata-item');
        if (currentTags.length >= 30) {
            showToast('modelTags.validation.maxCount', {}, 'error');
            return;
        }
        
        // Validation: Check for duplicates
        const existingTags = Array.from(currentTags).map(tagEl => tagEl.dataset.tag);
        if (existingTags.includes(tag)) {
            showToast('modelTags.validation.duplicate', {}, 'error');
            return;
        }
        
        // Create new tag
        const newTag = document.createElement('div');
        newTag.className = 'metadata-item';
        newTag.dataset.tag = tag;
        newTag.innerHTML = `
            <span class="metadata-item-content">${tag}</span>
            <button class="metadata-delete-btn">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add delete button event listener
        const deleteBtn = newTag.querySelector('.metadata-delete-btn');
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            newTag.remove();
            // Update dropdown to show/hide added indicator
            this.updateBulkSuggestionsDropdown();
        });
        
        tagsContainer.appendChild(newTag);
    }
    
    /**
     * Get existing tags in the bulk tags container
     * @returns {Array} Array of existing tag strings
     */
    getBulkExistingTags() {
        const tagsContainer = document.getElementById('bulkTagsItems');
        if (!tagsContainer) return [];
        
        const currentTags = tagsContainer.querySelectorAll('.metadata-item');
        return Array.from(currentTags).map(tag => tag.dataset.tag);
    }
    
    /**
     * Update status of items in the bulk suggestions dropdown
     */
    updateBulkSuggestionsDropdown() {
        const dropdown = document.querySelector('.metadata-suggestions-dropdown');
        if (!dropdown) return;
        
        // Get all current tags
        const existingTags = this.getBulkExistingTags();
        
        // Update status of each item in dropdown
        dropdown.querySelectorAll('.metadata-suggestion-item').forEach(item => {
            const tagText = item.querySelector('.metadata-suggestion-text').textContent;
            const isAdded = existingTags.includes(tagText);
            
            if (isAdded) {
                item.classList.add('already-added');
                
                // Add indicator if it doesn't exist
                let indicator = item.querySelector('.added-indicator');
                if (!indicator) {
                    indicator = document.createElement('span');
                    indicator.className = 'added-indicator';
                    indicator.innerHTML = '<i class="fas fa-check"></i>';
                    item.appendChild(indicator);
                }
                
                // Remove click event
                item.onclick = null;
                item.removeEventListener('click', item._clickHandler);
            } else {
                // Re-enable items that are no longer in the list
                item.classList.remove('already-added');
                
                // Remove indicator if it exists
                const indicator = item.querySelector('.added-indicator');
                if (indicator) indicator.remove();
                
                // Restore click event if not already set
                if (!item._clickHandler) {
                    item._clickHandler = () => {
                        this.addBulkTag(tagText);
                        const input = document.querySelector('.bulk-metadata-input');
                        if (input) {
                            input.value = tagText;
                            input.focus();
                        }
                        // Update dropdown to show added indicator
                        this.updateBulkSuggestionsDropdown();
                    };
                    item.addEventListener('click', item._clickHandler);
                }
            }
        });
    }
    
    async saveBulkTags(mode = 'append') {
        const tagElements = document.querySelectorAll('#bulkTagsItems .metadata-item');
        const tags = Array.from(tagElements).map(tag => tag.dataset.tag);
        
        if (tags.length === 0) {
            showToast('toast.models.noTagsToAdd', {}, 'warning');
            return;
        }
        
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }
        
        try {
            const apiClient = getModelApiClient();
            const filePaths = Array.from(state.selectedModels);
            let successCount = 0;
            let failCount = 0;
            
            // Add or replace tags for each selected model based on mode
            for (const filePath of filePaths) {
                try {
                    if (mode === 'replace') {
                        await apiClient.saveModelMetadata(filePath, { tags: tags });
                    } else {
                        await apiClient.addTags(filePath, { tags: tags });
                    }
                    successCount++;
                } catch (error) {
                    console.error(`Failed to ${mode} tags for ${filePath}:`, error);
                    failCount++;
                }
            }
            
            modalManager.closeModal('bulkAddTagsModal');
            
            if (successCount > 0) {
                const currentConfig = MODEL_CONFIG[state.currentPageType];
                const toastKey = mode === 'replace' ? 'toast.models.tagsReplacedSuccessfully' : 'toast.models.tagsAddedSuccessfully';
                showToast(toastKey, { 
                    count: successCount, 
                    tagCount: tags.length,
                    type: currentConfig.displayName.toLowerCase() 
                }, 'success');
            }
            
            if (failCount > 0) {
                const toastKey = mode === 'replace' ? 'toast.models.tagsReplaceFailed' : 'toast.models.tagsAddFailed';
                showToast(toastKey, { count: failCount }, 'warning');
            }
            
        } catch (error) {
            console.error('Error during bulk tag operation:', error);
            const toastKey = mode === 'replace' ? 'toast.models.bulkTagsReplaceFailed' : 'toast.models.bulkTagsAddFailed';
            showToast(toastKey, {}, 'error');
        }
    }
    
    cleanupBulkAddTagsModal() {
        // Clear tags container
        const tagsContainer = document.getElementById('bulkTagsItems');
        if (tagsContainer) {
            tagsContainer.innerHTML = '';
        }
        
        // Clear input
        const input = document.querySelector('.bulk-metadata-input');
        if (input) {
            input.value = '';
        }
        
        // Remove event listeners (they will be re-added when modal opens again)
        const appendBtn = document.querySelector('.bulk-append-tags-btn');
        if (appendBtn) {
            appendBtn.replaceWith(appendBtn.cloneNode(true));
        }
        
        const replaceBtn = document.querySelector('.bulk-replace-tags-btn');
        if (replaceBtn) {
            replaceBtn.replaceWith(replaceBtn.cloneNode(true));
        }

        // Remove the suggestions dropdown
        const tagForm = document.querySelector('#bulkAddTagsModal .metadata-add-form');
        if (tagForm) {
            const dropdown = tagForm.querySelector('.metadata-suggestions-dropdown');
            if (dropdown) {
                dropdown.remove();
            }
        }
    }
}

export const bulkManager = new BulkManager();
