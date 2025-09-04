import { state, getCurrentPageState } from '../state/index.js';
import { showToast, copyToClipboard, sendLoraToWorkflow } from '../utils/uiHelpers.js';
import { updateCardsForBulkMode } from '../components/shared/ModelCard.js';
import { modalManager } from './ModalManager.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { MODEL_TYPES, MODEL_CONFIG } from '../api/apiConfig.js';

export class BulkManager {
    constructor() {
        this.bulkBtn = document.getElementById('bulkOperationsBtn');
        // Remove bulk panel references since we're using context menu now
        this.bulkContextMenu = null; // Will be set by core initialization
        
        // Model type specific action configurations
        this.actionConfig = {
            [MODEL_TYPES.LORA]: {
                sendToWorkflow: true,
                copyAll: true,
                refreshAll: true,
                moveAll: true,
                deleteAll: true
            },
            [MODEL_TYPES.EMBEDDING]: {
                sendToWorkflow: false,
                copyAll: false,
                refreshAll: true,
                moveAll: true,
                deleteAll: true
            },
            [MODEL_TYPES.CHECKPOINT]: {
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
    
    async sendAllModelsToWorkflow() {
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
        
        await sendLoraToWorkflow(loraSyntaxes.join(', '), false, 'lora');
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
}

export const bulkManager = new BulkManager();
