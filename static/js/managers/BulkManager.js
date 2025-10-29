import { state, getCurrentPageState } from '../state/index.js';
import { showToast, copyToClipboard, sendLoraToWorkflow, buildLoraSyntax, getNSFWLevelName } from '../utils/uiHelpers.js';
import { updateCardsForBulkMode } from '../components/shared/ModelCard.js';
import { modalManager } from './ModalManager.js';
import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { MODEL_TYPES, MODEL_CONFIG } from '../api/apiConfig.js';
import { BASE_MODEL_CATEGORIES } from '../utils/constants.js';
import { getPriorityTagSuggestions } from '../utils/priorityTagHelpers.js';
import { eventManager } from '../utils/EventManager.js';
import { translate } from '../utils/i18nHelpers.js';

export class BulkManager {
    constructor() {
        this.bulkBtn = document.getElementById('bulkOperationsBtn');
        // Remove bulk panel references since we're using context menu now
        this.bulkContextMenu = null; // Will be set by core initialization
        
        // Marquee selection properties
        this.isMarqueeActive = false;
        this.isDragging = false;
        this.marqueeStart = { x: 0, y: 0 };
        this.marqueeElement = null;
        this.initialSelectedModels = new Set();
        
        // Drag detection properties
        this.dragThreshold = 5; // Pixels to move before considering it a drag
        this.mouseDownTime = 0;
        this.mouseDownPosition = { x: 0, y: 0 };
        
        // Model type specific action configurations
        this.actionConfig = {
            [MODEL_TYPES.LORA]: {
                addTags: true,
                sendToWorkflow: true,
                copyAll: true,
                refreshAll: true,
                checkUpdates: true,
                moveAll: true,
                autoOrganize: true,
                deleteAll: true,
                setContentRating: true
            },
            [MODEL_TYPES.EMBEDDING]: {
                addTags: true,
                sendToWorkflow: false,
                copyAll: false,
                refreshAll: true,
                checkUpdates: true,
                moveAll: true,
                autoOrganize: true,
                deleteAll: true,
                setContentRating: false
            },
            [MODEL_TYPES.CHECKPOINT]: {
                addTags: true,
                sendToWorkflow: false,
                copyAll: false,
                refreshAll: true,
                checkUpdates: true,
                moveAll: false,
                autoOrganize: true,
                deleteAll: true,
                setContentRating: true
            }
        };

        window.addEventListener('lm:priority-tags-updated', () => {
            const container = document.querySelector('#bulkAddTagsModal .metadata-suggestions-container');
            if (!container) {
                return;
            }
            const currentType = state.currentPageType;
            if (!currentType || currentType === 'recipes') {
                return;
            }
            getPriorityTagSuggestions(currentType).then((tags) => {
                if (!container.isConnected) {
                    return;
                }
                this.renderBulkSuggestionItems(container, tags);
                this.updateBulkSuggestionsDropdown();
            }).catch(() => {
                // Ignore refresh failures; UI will retry on next open
            });
        });
    }

    initialize() {
        // Do not initialize on recipes page
        if (state.currentPageType === 'recipes') return;
        
        // Register with event manager for coordinated event handling
        this.registerEventHandlers();
        
        // Initialize bulk mode state in event manager
        eventManager.setState('bulkMode', state.bulkMode || false);
    }

    setBulkContextMenu(bulkContextMenu) {
        this.bulkContextMenu = bulkContextMenu;
    }

    /**
     * Register all event handlers with the centralized event manager
     */
    registerEventHandlers() {
        // Register keyboard shortcuts with high priority
        eventManager.addHandler('keydown', 'bulkManager-keyboard', (e) => {
            return this.handleGlobalKeyboard(e);
        }, {
            priority: 100,
            skipWhenModalOpen: true
        });

        // Register marquee selection events
        eventManager.addHandler('mousedown', 'bulkManager-marquee-start', (e) => {
            return this.handleMarqueeStart(e);
        }, {
            priority: 80,
            skipWhenModalOpen: true,
            targetSelector: '.page-content',
            excludeSelector: '.model-card, button, input, folder-sidebar, .breadcrumb-item, #path-part, .context-menu',
            button: 0 // Left mouse button only
        });

        eventManager.addHandler('mousemove', 'bulkManager-marquee-move', (e) => {
            if (this.isMarqueeActive) {
                this.updateMarqueeSelection(e);
            } else if (this.mouseDownTime && !this.isDragging) {
                // Check if we've moved enough to consider it a drag
                const dx = e.clientX - this.mouseDownPosition.x;
                const dy = e.clientY - this.mouseDownPosition.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance >= this.dragThreshold) {
                    this.isDragging = true;
                    this.startMarqueeSelection(e, true);
                }
            }
        }, {
            priority: 90,
            skipWhenModalOpen: true
        });

        eventManager.addHandler('mouseup', 'bulkManager-marquee-end', (e) => {
            if (this.isMarqueeActive) {
                this.endMarqueeSelection(e);
                return true; // Stop propagation
            }
            
            // Reset drag detection if we had a mousedown but didn't drag
            if (this.mouseDownTime) {
                this.mouseDownTime = 0;
                return false; // Allow other handlers to process the click
            }
        }, {
            priority: 90
        });

        eventManager.addHandler('contextmenu', 'bulkManager-marquee-prevent', (e) => {
            if (this.isMarqueeActive) {
                e.preventDefault();
                return true; // Stop propagation
            }
        }, {
            priority: 100
        });

        // Modified: Clear selection and exit bulk mode on left-click page-content blank area
        // Lower priority to avoid interfering with context menu interactions
        eventManager.addHandler('mousedown', 'bulkManager-clear-on-blank', (e) => {
            // Only handle left mouse button
            if (e.button !== 0) return false;
            // Only if in bulk mode and there are selected models
            if (state.bulkMode && state.selectedModels && state.selectedModels.size > 0) {
                // Check if click is on blank area (not on a model card or excluded elements)
                this.clearSelection();
                this.toggleBulkMode();
                // Prevent further handling
                return true;
            }
            return false;
        }, {
            priority: 70, // Lower priority to let context menu events process first
            onlyInBulkMode: true,
            skipWhenModalOpen: true,
            targetSelector: '.page-content',
            excludeSelector: '.model-card, button, input, folder-sidebar, .breadcrumb-item, #path-part, .context-menu, .context-menu *',
            button: 0 // Left mouse button only
        });
    }

    /**
     * Clean up event handlers
     */
    cleanup() {
        eventManager.removeAllHandlersForSource('bulkManager-keyboard');
        eventManager.removeAllHandlersForSource('bulkManager-marquee-start');
        eventManager.removeAllHandlersForSource('bulkManager-marquee-move');
        eventManager.removeAllHandlersForSource('bulkManager-marquee-end');
        eventManager.removeAllHandlersForSource('bulkManager-marquee-prevent');
        eventManager.removeAllHandlersForSource('bulkManager-clear-on-blank');
    }

    /**
     * Handle global keyboard events through the event manager
     */
    handleGlobalKeyboard(e) {
        // Skip if modal is open (handled by event manager conditions)
        // Skip if search input is focused
        const searchInput = document.getElementById('searchInput');
        if (searchInput && document.activeElement === searchInput) {
            return false; // Don't handle, allow default behavior
        }

        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
            e.preventDefault();
            if (!state.bulkMode) {
                this.toggleBulkMode();
                setTimeout(() => this.selectAllVisibleModels(), 50);
            } else {
                this.selectAllVisibleModels();
            }
            return true; // Stop propagation
        } else if (e.key === 'Escape' && state.bulkMode) {
            this.toggleBulkMode();
            return true; // Stop propagation
        } else if (e.key.toLowerCase() === 'b') {
            this.toggleBulkMode();
            return true; // Stop propagation
        }
        
        return false; // Continue with other handlers
    }

    toggleBulkMode() {
        state.bulkMode = !state.bulkMode;
        
        // Update event manager state
        eventManager.setState('bulkMode', state.bulkMode);
        
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
            this.updateMetadataCacheFromCard(filepath, card);
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

    parseModelId(value) {
        if (value === undefined || value === null || value === '') {
            return null;
        }

        const parsed = Number.parseInt(value, 10);
        return Number.isNaN(parsed) ? null : parsed;
    }

    updateMetadataCacheFromCard(filepath, card) {
        if (!card) {
            return;
        }

        const metadataCache = this.getMetadataCache();
        const existing = metadataCache.get(filepath) || {};
        const modelId = this.parseModelId(card.dataset.modelId);

        const updated = {
            ...existing,
            fileName: card.dataset.file_name ?? existing.fileName,
            usageTips: card.dataset.usage_tips ?? existing.usageTips,
            modelName: card.dataset.name ?? existing.modelName,
        };

        if (modelId !== null) {
            updated.modelId = modelId;
        }

        metadataCache.set(filepath, updated);
    }

    escapeAttributeValue(value) {
        if (value === undefined || value === null) {
            return '';
        }

        return String(value)
            .replace(/\\/g, '\\\\')
            .replace(/"/g, '\\"');
    }

    getModelIdForFilePath(filePath) {
        const metadataCache = this.getMetadataCache();
        const cached = metadataCache.get(filePath);
        if (cached && typeof cached.modelId === 'number') {
            return cached.modelId;
        }

        const escapedPath = this.escapeAttributeValue(filePath);
        const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
        if (!card) {
            return null;
        }

        this.updateMetadataCacheFromCard(filePath, card);
        const updated = metadataCache.get(filePath);
        return updated && typeof updated.modelId === 'number' ? updated.modelId : null;
    }

    collectSelectedModelIds() {
        const metadataCache = this.getMetadataCache();
        const ids = [];
        let missingCount = 0;

        for (const filepath of state.selectedModels) {
            const cached = metadataCache.get(filepath);
            let modelId = cached && typeof cached.modelId === 'number' ? cached.modelId : null;
            if (modelId === null) {
                modelId = this.getModelIdForFilePath(filepath);
            }

            if (typeof modelId === 'number') {
                ids.push(modelId);
            } else {
                missingCount++;
            }
        }

        const uniqueIds = Array.from(new Set(ids));
        return { ids: uniqueIds, missingCount };
    }

    applySelectionState() {
        if (!state.bulkMode) return;
        
        document.querySelectorAll('.model-card').forEach(card => {
            const filepath = card.dataset.filepath;
            if (state.selectedModels.has(filepath)) {
                card.classList.add('selected');

                this.updateMetadataCacheFromCard(filepath, card);
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
                loraSyntaxes.push(buildLoraSyntax(metadata.fileName, usageTips));
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
                loraSyntaxes.push(buildLoraSyntax(metadata.fileName, usageTips));
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
                    const modelId = this.parseModelId(item?.civitai?.modelId);
                    metadataCache.set(item.file_path, {
                        fileName: item.file_name,
                        usageTips: item.usage_tips || '{}',
                        modelName: item.name || item.file_name,
                        ...(modelId !== null ? { modelId } : {})
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
                            this.updateMetadataCacheFromCard(filepath, card);
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

    async checkUpdatesForSelectedModels() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }

        const currentType = state.currentPageType;
        const currentConfig = MODEL_CONFIG[currentType] || MODEL_CONFIG[MODEL_TYPES.LORA];
        const typeLabel = (currentConfig?.displayName || 'Model').toLowerCase();

        const { ids: modelIds, missingCount } = this.collectSelectedModelIds();

        if (modelIds.length === 0) {
            showToast('toast.models.bulkUpdatesMissing', { type: typeLabel }, 'warning');
            return;
        }

        if (missingCount > 0) {
            showToast('toast.models.bulkUpdatesPartialMissing', { missing: missingCount, type: typeLabel }, 'info');
        }

        const apiClient = getModelApiClient();
        if (!apiClient || typeof apiClient.refreshUpdatesForModels !== 'function') {
            console.warn('Model API client does not support refreshUpdatesForModels');
            showToast('toast.models.bulkUpdatesFailed', { type: typeLabel, message: 'Operation not supported' }, 'error');
            return;
        }

        const loadingMessage = translate(
            'toast.models.bulkUpdatesChecking',
            { count: state.selectedModels.size, type: typeLabel },
            `Checking selected ${typeLabel}(s) for updates...`
        );
        state.loadingManager?.showSimpleLoading?.(loadingMessage);

        try {
            const response = await apiClient.refreshUpdatesForModels(modelIds);
            const records = Array.isArray(response?.records) ? response.records : [];
            const updatesCount = records.length;

            if (updatesCount > 0) {
                showToast('toast.models.bulkUpdatesSuccess', { count: updatesCount, type: typeLabel }, 'success');
            } else {
                showToast('toast.models.bulkUpdatesNone', { type: typeLabel }, 'info');
            }

            await resetAndReload(false);
        } catch (error) {
            console.error('Error checking updates for selected models:', error);
            showToast(
                'toast.models.bulkUpdatesFailed',
                { type: typeLabel, message: error?.message ?? 'Unknown error' },
                'error'
            );
        } finally {
            if (state.loadingManager?.hide) {
                state.loadingManager.hide();
            }
            if (typeof state.loadingManager?.restoreProgressBar === 'function') {
                state.loadingManager.restoreProgressBar();
            }
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
            const suggestionsDropdown = this.createBulkSuggestionsDropdown();
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
    
    createBulkSuggestionsDropdown() {
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
        container.innerHTML = `<div class="metadata-suggestions-loading">${translate('settings.priorityTags.loadingSuggestions', 'Loading suggestions…')}</div>`;

        const currentType = state.currentPageType;
        if (!currentType || currentType === 'recipes') {
            container.innerHTML = '';
        } else {
            getPriorityTagSuggestions(currentType).then((tags) => {
                if (!container.isConnected) {
                    return;
                }
                this.renderBulkSuggestionItems(container, tags);
                this.updateBulkSuggestionsDropdown();
            }).catch(() => {
                if (container.isConnected) {
                    container.innerHTML = '';
                }
            });
        }

        dropdown.appendChild(container);
        return dropdown;
    }

    renderBulkSuggestionItems(container, tags) {
        container.innerHTML = '';

        tags.forEach(tag => {
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
                    this.updateBulkSuggestionsDropdown();
                });
            }

            container.appendChild(item);
        });
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

    /**
     * Show bulk base model modal
     */
    showBulkBaseModelModal() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }

        const countElement = document.getElementById('bulkBaseModelCount');
        if (countElement) {
            countElement.textContent = state.selectedModels.size;
        }

        modalManager.showModal('bulkBaseModelModal', null, null, () => {
            this.cleanupBulkBaseModelModal();
        });

        // Initialize the bulk base model interface
        this.initializeBulkBaseModelInterface();
    }

    showBulkContentRatingSelector() {
        if (state.selectedModels.size === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }

        const selector = document.getElementById('nsfwLevelSelector');
        const currentLevelEl = document.getElementById('currentNSFWLevel');

        if (!selector || !currentLevelEl) {
            console.warn('NSFW level selector not found');
            return;
        }

        const filePaths = Array.from(state.selectedModels);
        selector.dataset.mode = 'bulk';
        selector.dataset.bulkFilePaths = JSON.stringify(filePaths);
        delete selector.dataset.cardPath;

        const selectedCards = Array.from(document.querySelectorAll('.model-card.selected'));
        const levels = new Set();

        selectedCards.forEach((card) => {
            let level = 0;
            try {
                const metaData = JSON.parse(card.dataset.meta || '{}');
                if (typeof metaData.preview_nsfw_level === 'number') {
                    level = metaData.preview_nsfw_level;
                }
            } catch (error) {
                console.warn('Failed to parse metadata for card', error);
            }

            if (!level && card.dataset.nsfwLevel) {
                const parsed = parseInt(card.dataset.nsfwLevel, 10);
                if (!Number.isNaN(parsed)) {
                    level = parsed;
                }
            }

            levels.add(level);
        });

        let highlightLevel = null;
        if (levels.size === 1) {
            highlightLevel = levels.values().next().value;
            currentLevelEl.textContent = getNSFWLevelName(highlightLevel);
        } else {
            currentLevelEl.textContent = translate('modals.contentRating.multiple', {}, 'Multiple values');
        }

        selector.querySelectorAll('.nsfw-level-btn').forEach((btn) => {
            const btnLevel = parseInt(btn.dataset.level, 10);
            if (highlightLevel !== null && btnLevel === highlightLevel) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        const viewportWidth = document.documentElement.clientWidth;
        const viewportHeight = document.documentElement.clientHeight;
        const selectorRect = selector.getBoundingClientRect();
        const finalX = Math.max((viewportWidth - selectorRect.width) / 2, 0);
        const finalY = Math.max((viewportHeight - selectorRect.height) / 2, 0);

        selector.style.left = `${finalX}px`;
        selector.style.top = `${finalY}px`;
        selector.style.display = 'block';
    }

    async setBulkContentRating(level, filePaths = null) {
        const targets = Array.isArray(filePaths) ? filePaths : Array.from(state.selectedModels);

        if (!targets || targets.length === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return false;
        }

        const totalCount = targets.length;
        const levelName = getNSFWLevelName(level);

        state.loadingManager.showSimpleLoading(translate('toast.models.bulkContentRatingUpdating', { count: totalCount }));

        let successCount = 0;
        let failureCount = 0;

        try {
            const apiClient = getModelApiClient();
            for (const filePath of targets) {
                try {
                    await apiClient.saveModelMetadata(filePath, { preview_nsfw_level: level });
                    successCount++;
                } catch (error) {
                    failureCount++;
                    console.error(`Failed to set content rating for ${filePath}:`, error);
                }
            }
        } finally {
            state.loadingManager.hideSimpleLoading();
        }

        if (successCount === totalCount) {
            showToast('toast.models.bulkContentRatingSet', { count: successCount, level: levelName }, 'success');
        } else if (successCount > 0) {
            showToast('toast.models.bulkContentRatingPartial', {
                success: successCount,
                failed: failureCount,
                level: levelName
            }, 'warning');
        } else {
            showToast('toast.models.bulkContentRatingFailed', {}, 'error');
        }

        return successCount > 0;
    }

    /**
     * Initialize bulk base model interface
     */
    initializeBulkBaseModelInterface() {
        const select = document.getElementById('bulkBaseModelSelect');
        if (!select) return;
        
        // Clear existing options
        select.innerHTML = '';
        
        // Add placeholder option
        const placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = 'Select a base model...';
        placeholderOption.disabled = true;
        placeholderOption.selected = true;
        select.appendChild(placeholderOption);
        
        // Create option groups for better organization
        Object.entries(BASE_MODEL_CATEGORIES).forEach(([category, models]) => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = category;
            
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                optgroup.appendChild(option);
            });
            
            select.appendChild(optgroup);
        });
    }
    
    /**
     * Save bulk base model changes
     */
    async saveBulkBaseModel() {
        const select = document.getElementById('bulkBaseModelSelect');
        if (!select || !select.value) {
            showToast('toast.models.baseModelNotSelected', {}, 'warning');
            return;
        }
        
        const newBaseModel = select.value;
        const selectedCount = state.selectedModels.size;
        
        if (selectedCount === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return;
        }
        
        modalManager.closeModal('bulkBaseModelModal');
        
        try {
            let successCount = 0;
            let errorCount = 0;
            const errors = [];
            
            state.loadingManager.showSimpleLoading(translate('toast.models.bulkBaseModelUpdating'));
            
            for (const filepath of state.selectedModels) {
                try {
                    await getModelApiClient().saveModelMetadata(filepath, { base_model: newBaseModel });
                    successCount++;
                } catch (error) {
                    errorCount++;
                    errors.push({ filepath, error: error.message });
                    console.error(`Failed to update base model for ${filepath}:`, error);
                }
            }
            
            // Show results
            if (errorCount === 0) {
                showToast('toast.models.bulkBaseModelUpdateSuccess', { count: successCount }, 'success');
            } else if (successCount > 0) {
                showToast('toast.models.bulkBaseModelUpdatePartial', { 
                    success: successCount, 
                    failed: errorCount 
                }, 'warning');
            } else {
                showToast('toast.models.bulkBaseModelUpdateFailed', {}, 'error');
            }
            
        } catch (error) {
            console.error('Error during bulk base model operation:', error);
            showToast('toast.models.bulkBaseModelUpdateFailed', {}, 'error');
        } finally {
            state.loadingManager.hideSimpleLoading();
        }
    }
    
    /**
     * Cleanup bulk base model modal
     */
    cleanupBulkBaseModelModal() {
        const select = document.getElementById('bulkBaseModelSelect');
        if (select) {
            select.innerHTML = '';
        }
    }

    /**
     * Auto-organize selected models based on current path template settings
     */
    async autoOrganizeSelectedModels() {
        if (state.selectedModels.size === 0) {
            showToast('toast.loras.noModelsSelected', {}, 'error');
            return;
        }

        try {
            // Get selected file paths
            const filePaths = Array.from(state.selectedModels);
            
            // Get the API client for the current model type
            const apiClient = getModelApiClient();
            
            // Call the auto-organize method with selected file paths
            await apiClient.autoOrganizeModels(filePaths);
            
            resetAndReload(true);
        } catch (error) {
            console.error('Error during bulk auto-organize:', error);
            showToast('toast.loras.autoOrganizeFailed', { error: error.message }, 'error');
        }
    }

    /**
     * Handle marquee start through event manager
     */
    handleMarqueeStart(e) {
        // Store mousedown info for potential drag detection
        this.mouseDownTime = Date.now();
        this.mouseDownPosition = { x: e.clientX, y: e.clientY };
        this.isDragging = false;
        
        // Don't start marquee yet - wait to see if user is dragging
        return false;
    }

    /**
     * Start marquee selection
     * @param {MouseEvent} e - Mouse event
     * @param {boolean} isDragging - Whether this is triggered from a drag operation
     */
    startMarqueeSelection(e, isDragging = false) {
        // Store initial mouse position
        this.marqueeStart.x = this.mouseDownPosition.x;
        this.marqueeStart.y = this.mouseDownPosition.y;
        
        // Store initial selection state
        this.initialSelectedModels = new Set(state.selectedModels);
        
        // Enter bulk mode if not already active and we're actually dragging
        if (isDragging && !state.bulkMode) {
            this.toggleBulkMode();
        }
        
        // Create marquee element
        this.createMarqueeElement();
        
        this.isMarqueeActive = true;
        
        // Update event manager state
        eventManager.setState('marqueeActive', true);
        
        // Add visual feedback class to body
        document.body.classList.add('marquee-selecting');
    }

    /**
     * Create the visual marquee selection rectangle
     */
    createMarqueeElement() {
        this.marqueeElement = document.createElement('div');
        this.marqueeElement.className = 'marquee-selection';
        this.marqueeElement.style.cssText = `
            position: fixed;
            border: 2px dashed var(--lora-accent, #007bff);
            background: rgba(0, 123, 255, 0.1);
            pointer-events: none;
            z-index: 9999;
            left: ${this.marqueeStart.x}px;
            top: ${this.marqueeStart.y}px;
            width: 0;
            height: 0;
        `;
        document.body.appendChild(this.marqueeElement);
    }

    /**
     * Update marquee selection rectangle and selected items
     */
    updateMarqueeSelection(e) {
        if (!this.marqueeElement) return;
        
        const currentX = e.clientX;
        const currentY = e.clientY;
        
        // Calculate rectangle bounds
        const left = Math.min(this.marqueeStart.x, currentX);
        const top = Math.min(this.marqueeStart.y, currentY);
        const width = Math.abs(currentX - this.marqueeStart.x);
        const height = Math.abs(currentY - this.marqueeStart.y);
        
        // Update marquee element position and size
        this.marqueeElement.style.left = left + 'px';
        this.marqueeElement.style.top = top + 'px';
        this.marqueeElement.style.width = width + 'px';
        this.marqueeElement.style.height = height + 'px';
        
        // Check which cards intersect with marquee
        this.updateCardSelection(left, top, left + width, top + height);
    }

    /**
     * Update card selection based on marquee bounds
     */
    updateCardSelection(left, top, right, bottom) {
        const cards = document.querySelectorAll('.model-card');
        const newSelection = new Set(this.initialSelectedModels);
        
        cards.forEach(card => {
            const rect = card.getBoundingClientRect();
            
            // Check if card intersects with marquee rectangle
            const intersects = !(rect.right < left || 
                               rect.left > right || 
                               rect.bottom < top || 
                               rect.top > bottom);
            
            const filepath = card.dataset.filepath;
            
            if (intersects) {
                // Add to selection if intersecting
                newSelection.add(filepath);
                card.classList.add('selected');

                // Cache metadata if not already cached
                const metadataCache = this.getMetadataCache();
                if (!metadataCache.has(filepath)) {
                    this.updateMetadataCacheFromCard(filepath, card);
                }
            } else if (!this.initialSelectedModels.has(filepath)) {
                // Remove from selection if not intersecting and wasn't initially selected
                newSelection.delete(filepath);
                card.classList.remove('selected');
            }
        });
        
        // Update global selection state
        state.selectedModels = newSelection;
        
        // Update context menu header if visible
        if (this.bulkContextMenu) {
            this.bulkContextMenu.updateSelectedCountHeader();
        }
    }

    /**
     * End marquee selection
     */
    endMarqueeSelection(e) {
        // First, mark as inactive to prevent double processing
        this.isMarqueeActive = false;
        this.isDragging = false;
        this.mouseDownTime = 0;
        
        // Update event manager state
        eventManager.setState('marqueeActive', false);
        
        // Remove marquee element
        if (this.marqueeElement) {
            this.marqueeElement.remove();
            this.marqueeElement = null;
        }
        
        // Remove visual feedback class
        document.body.classList.remove('marquee-selecting');
        
        // Get selection count
        const selectionCount = state.selectedModels.size;
        
        // If no models were selected, exit bulk mode
        if (selectionCount === 0) {
            if (state.bulkMode) {
                this.toggleBulkMode();
            }
        }
        
        // Clear initial selection state
        this.initialSelectedModels.clear();
    }
}

export const bulkManager = new BulkManager();
