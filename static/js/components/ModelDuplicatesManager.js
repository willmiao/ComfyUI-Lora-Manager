// Model Duplicates Manager Component for LoRAs and Checkpoints
import { showToast, showActionToast } from '../utils/uiHelpers.js';
import { handleUndoDelete } from '../utils/undoHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { state, getCurrentPageState } from '../state/index.js';
import { formatDate } from '../utils/formatters.js';
import { getPreviewMediaExtension, isVideoPreviewUrl } from '../utils/mediaTypes.js';
import { resetAndReload} from '../api/modelApiFactory.js';
import { getShowDuplicatesNotification, setShowDuplicatesNotification } from '../utils/storageHelpers.js';
import { DuplicatesViewManager } from './shared/DuplicatesViewManager.js';

export class ModelDuplicatesManager extends DuplicatesViewManager {
    constructor(pageManager, modelType = 'loras') {
        super();
        this.pageManager = pageManager;
        this.modelType = modelType; // Use the provided modelType or default to 'loras'

        // Verification tracking
        this.verifiedGroups = new Set(); // Track which groups have been verified
        this.mismatchedFiles = new Map(); // Map file paths to actual hashes for mismatched files
        
        // Badge visibility preference
        this.showBadge = getShowDuplicatesNotification(); // Default to true (show badge)
        
        // Event handler references for cleanup
        this.badgeToggleHandler = null;
        this.helpTooltipHandlers = {
            mouseenter: null,
            mouseleave: null,
            click: null
        };
        
        // Bind methods
        this.renderModelCard = this.renderModelCard.bind(this);
        this.renderTooltip = this.renderTooltip.bind(this);
        this.checkDuplicatesCount = this.checkDuplicatesCount.bind(this);
        this.handleVerifyHashes = this.handleVerifyHashes.bind(this);
        
        // Keep track of which controls need to be re-enabled
        this.disabledControls = [];
        
        // Check for duplicates on load
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', this.checkDuplicatesCount);
        } else {
            this.checkDuplicatesCount();
        }
    }
    
    // Method to check for duplicates count using existing endpoint
    async checkDuplicatesCount() {
        try {
            const params = this._buildFilterQueryParams();
            const endpoint = `/api/lm/${this.modelType}/find-duplicates`;
            const url = params.toString() ? `${endpoint}?${params}` : endpoint;

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`Failed to get duplicates count: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success) {
                const duplicatesCount = (data.duplicates || []).length;
                this.updateDuplicatesBadge(duplicatesCount);
            } else {
                this.updateDuplicatesBadge(0);
            }
        } catch (error) {
            console.error('Error checking duplicates count:', error);
            this.updateDuplicatesBadge(0);
        }
    }
    
    // Method to update the badge
    updateDuplicatesBadge(count) {
        const badge = document.getElementById('duplicatesBadge');
        if (!badge) return;
        
        // Check if badge should be hidden based on user preference
        if (!this.showBadge && !this.inDuplicateMode) {
            badge.style.display = 'none';
            badge.textContent = '';
            return;
        }
        
        if (count > 0) {
            badge.style.display = 'inline-flex';
            badge.textContent = count;
        } else {
            badge.textContent = '';
        }
    }
    
    // Toggle method to enter/exit duplicates mode
    toggleDuplicateMode() {
        if (this.inDuplicateMode) {
            this.exitDuplicateMode();
        } else {
            this.findDuplicates();
        }
    }
    
    async findDuplicates({ suppressEmptyToast = false } = {}) {
        if (this._isDeleting) return false;

        try {
            const params = this._buildFilterQueryParams();
            const endpoint = `/api/lm/${this.modelType}/find-duplicates`;
            const url = params.toString() ? `${endpoint}?${params}` : endpoint;

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to find duplicates: ${response.statusText}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error finding duplicates');
            }

            this.duplicateGroups = data.duplicates || [];
            this._pruneVerificationState();

            // Update the badge with the current count
            this.updateDuplicatesBadge(this.duplicateGroups.length);

            if (this.duplicateGroups.length === 0) {
                if (!suppressEmptyToast) {
                    showToast('toast.duplicates.noDuplicatesFound', { type: this.modelType }, 'info');
                }
                // If already in duplicate mode, exit to clear the display
                if (this.inDuplicateMode) {
                    this.exitDuplicateMode();
                }
                return false;
            }

            this.enterDuplicateMode();
            return true;
        } catch (error) {
            console.error('Error finding duplicates:', error);
            showToast('toast.duplicates.findFailed', { message: error.message }, 'error');
            return false;
        }
    }

    /**
     * Build query parameters from current filter state for duplicate finding.
     * @returns {URLSearchParams} The query parameters to append to the API endpoint
     */
    _buildFilterQueryParams() {
        const params = new URLSearchParams();
        const pageState = getCurrentPageState();
        const filters = pageState?.filters;

        if (!filters) return params;

        // Base model filters
        if (filters.baseModel && Array.isArray(filters.baseModel)) {
            filters.baseModel.forEach(m => params.append('base_model', m));
        }

        // Tag filters (tri-state: include/exclude)
        if (filters.tags && typeof filters.tags === 'object') {
            Object.entries(filters.tags).forEach(([tag, state]) => {
                if (state === 'include') {
                    params.append('tag_include', tag);
                } else if (state === 'exclude') {
                    params.append('tag_exclude', tag);
                }
            });
        }

        // Model type filters
        if (filters.modelTypes && Array.isArray(filters.modelTypes)) {
            filters.modelTypes.forEach(t => params.append('model_type', t));
        }

        // Folder filter (from active folder state)
        if (pageState.activeFolder) {
            params.append('folder', pageState.activeFolder);
        }

        // Favorites filter
        if (pageState.showFavoritesOnly) {
            params.append('favorites_only', 'true');
        }

        return params;
    }
    
    enterDuplicateMode() {
        this.inDuplicateMode = true;
        this.selectedForDeletion.clear();
        
        // Update state
        const pageState = getCurrentPageState();
        pageState.duplicatesMode = true;
        
        // Show duplicates banner
        const banner = document.getElementById('duplicatesBanner');
        const countSpan = document.getElementById('duplicatesCount');
        
        if (banner && countSpan) {
            countSpan.textContent = `Found ${this.duplicateGroups.length} duplicate group${this.duplicateGroups.length !== 1 ? 's' : ''}`;
            banner.style.display = 'block';
            
            // Setup help tooltip behavior
            this.setupHelpTooltip();
            
            // Setup badge toggle control
            this.setupBadgeToggle();
        }
        
        // Disable virtual scrolling if active
        if (state.virtualScroller) {
            state.virtualScroller.disable();
        }
        
        // Add duplicate-mode class to the body
        document.body.classList.add('duplicate-mode');
        
        // Render duplicate groups
        this.renderDuplicateGroups();
        
        // Update selected count
        this.updateSelectedCount();
        
        this._setDuplicatesButtonActive(true);
        
        // Disable all control buttons except the duplicates button
        this.disableControlButtons();
    }
    
    async exitDuplicateMode() {
        const refreshLibrary = this._libraryNeedsRefresh;
        this._libraryNeedsRefresh = false;
        this.inDuplicateMode = false;
        this.selectedForDeletion.clear();
        
        // Update state
        const pageState = getCurrentPageState();
        pageState.duplicatesMode = false;
        
        // Clean up event handlers before hiding banner
        this.cleanupEventHandlers();
        
        // Hide duplicates banner
        const banner = document.getElementById('duplicatesBanner');
        if (banner) {
            banner.style.display = 'none';
        }
        
        // Remove duplicate-mode class from the body
        document.body.classList.remove('duplicate-mode');
        
        // Clear the model grid first
        this._stopProgressiveGroupRendering();
        const modelGrid = document.getElementById('modelGrid');
        if (modelGrid) {
            modelGrid.innerHTML = '';
        }
        
        // Re-enable virtual scrolling
        state.virtualScroller?.calculateLayout?.();
        state.virtualScroller?.enable();
        
        this._setDuplicatesButtonActive(false);
        
        // Re-enable all control buttons
        this.enableControlButtons();

        if (refreshLibrary) {
            await resetAndReload(true);
            this.updateDuplicatesBadge(this.duplicateGroups.length);
        } else {
            this.checkDuplicatesCount();
        }
    }
    
    // Disable all control buttons except the duplicates button
    disableControlButtons() {
        this.disabledControls = [];
        
        // Select all control buttons except the duplicates button
        const controlButtons = document.querySelectorAll('.control-group button:not(#findDuplicatesBtn), .dropdown-group, .toggle-folders-btn, #favoriteFilterBtn');
        
        controlButtons.forEach(button => {
            // Only disable enabled buttons (don't disable already disabled buttons)
            if (!button.disabled && !button.classList.contains('disabled')) {
                this.disabledControls.push(button);
                button.disabled = true;
                button.classList.add('disabled-during-duplicates');
            }
        });
    }
    
    // Re-enable all previously disabled control buttons
    enableControlButtons() {
        this.disabledControls.forEach(button => {
            button.disabled = false;
            button.classList.remove('disabled-during-duplicates');
        });
        this.disabledControls = [];
    }
    
    renderDuplicateGroups() {
        const modelGrid = document.getElementById('modelGrid');
        if (!modelGrid) return;

        this._startProgressiveGroupRendering(
            modelGrid,
            (group, groupIndex) => this._createDuplicateGroup(group, groupIndex)
        );
        if (this.duplicateGroups.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.className = 'duplicates-empty-state';
            emptyState.textContent = translate('duplicates.noGroups');
            modelGrid.appendChild(emptyState);
        }
    }

    _createDuplicateGroup(group, groupIndex) {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'duplicate-group';
        groupDiv.dataset.hash = group.hash;

        const header = document.createElement('div');
        header.className = 'duplicate-group-header';

        const verificationBadge = document.createElement('span');
        verificationBadge.className = 'verification-badge';
        if (this.verifiedGroups.has(group.hash)) {
            verificationBadge.classList.add('verified');
            verificationBadge.innerHTML = '<i class="fas fa-check-circle"></i> Verified';
        } else {
            verificationBadge.classList.add('metadata');
            verificationBadge.innerHTML = '<i class="fas fa-tag"></i> Metadata Hash';
        }

        const selectableModels = group.models.filter(model => !this.mismatchedFiles.has(model.file_path));
        const allSelected = selectableModels.length > 0 && selectableModels.every(
            model => this.selectedForDeletion.has(model.file_path)
        );
        header.innerHTML = `
            <span>Duplicate Group #${groupIndex + 1} (${group.models.length} models with same hash: ${group.hash})</span>
            <span>
                <button class="btn-verify-hashes" data-hash="${group.hash}" title="Recalculate SHA256 hashes to verify if these are true duplicates">
                    <i class="fas fa-fingerprint"></i> Verify Hashes
                </button>
                <button class="btn-select-all" onclick="modelDuplicatesManager.toggleSelectAllInGroup('${group.hash}')">
                    ${allSelected ? 'Deselect All' : 'Select All'}
                </button>
                <button class="btn-select-latest" onclick="modelDuplicatesManager.selectLatestInGroup('${group.hash}')">
                    Keep Latest
                </button>
            </span>
        `;

        const headerFirstSpan = header.querySelector('span:first-child');
        headerFirstSpan.appendChild(verificationBadge);
        groupDiv.appendChild(header);

        const cardsDiv = document.createElement('div');
        cardsDiv.className = 'card-group-container';
        this._renderCardGroup(
            groupDiv,
            cardsDiv,
            group.models,
            model => this.renderModelCard(model, group.hash)
        );
        groupDiv.appendChild(cardsDiv);

        const verifyButton = header.querySelector('.btn-verify-hashes');
        if (verifyButton) {
            verifyButton.addEventListener('click', event => {
                event.stopPropagation();
                this.handleVerifyHashes(group);
            });
        }

        return groupDiv;
    }

    _getGroupFilePaths(group) {
        return new Set((group?.models || []).map(model => model.file_path));
    }

    _clearMismatchStateForGroup(group) {
        this._getGroupFilePaths(group).forEach(filePath => {
            this.mismatchedFiles.delete(filePath);
        });
    }

    _pruneVerificationState() {
        const visiblePaths = new Set();
        const visibleHashes = new Set();

        this.duplicateGroups.forEach(group => {
            visibleHashes.add(group.hash);
            this._getGroupFilePaths(group).forEach(filePath => visiblePaths.add(filePath));
        });

        Array.from(this.mismatchedFiles.keys()).forEach(filePath => {
            if (!visiblePaths.has(filePath)) {
                this.mismatchedFiles.delete(filePath);
            }
        });

        Array.from(this.selectedForDeletion).forEach(filePath => {
            if (!visiblePaths.has(filePath)) {
                this.selectedForDeletion.delete(filePath);
            }
        });

        Array.from(this.verifiedGroups).forEach(hash => {
            if (!visibleHashes.has(hash)) {
                this.verifiedGroups.delete(hash);
            }
        });
    }
    
    renderModelCard(model, groupHash) {
        // Create basic card structure
        const card = document.createElement('div');
        card.className = 'model-card duplicate';
        card.dataset.hash = model.sha256;
        card.dataset.filePath = model.file_path;
        
        // Check if this model is a mismatched file
        const isMismatched = this.mismatchedFiles.has(model.file_path);
        
        // Add mismatched class if needed
        if (isMismatched) {
            card.classList.add('hash-mismatch');
        }
        
        // Create card content using structure similar to createLoraCard in LoraCard.js
        const previewContainer = document.createElement('div');
        previewContainer.className = 'card-preview';
        
        // Determine if preview is a video (the URL may be versioned, so the
        // extension lives in the decoded `path` query parameter)
        const isVideo = isVideoPreviewUrl(model.preview_url);
        let preview;
        
        if (isVideo) {
            // Create video element for video previews
            preview = document.createElement('video');
            preview.controls = false;
            preview.muted = true;
            preview.loop = true;
            preview.playsInline = true;
            preview.preload = 'metadata';
            preview.style.pointerEvents = 'none';
            
            const source = document.createElement('source');
            source.src = model.preview_url;
            source.type = getPreviewMediaExtension(model.preview_url) === '.webm' ? 'video/webm' : 'video/mp4';
            preview.appendChild(source);
        } else {
            // Create image element for standard previews
            preview = document.createElement('img');
            preview.loading = 'lazy';
            preview.alt = model.model_name;
            
            if (model.preview_url) {
                preview.src = model.preview_url;
            } else {
                // Use placeholder
                preview.src = '/loras_static/images/no-preview.png';
            }
        }
        
        // Add NSFW blur if needed
        if (model.preview_nsfw_level > 0) {
            preview.classList.add('nsfw');
        }
        
        previewContainer.appendChild(preview);
        
        // Add hash mismatch badge if needed
        if (isMismatched) {
            const mismatchBadge = document.createElement('div');
            mismatchBadge.className = 'mismatch-badge';
            mismatchBadge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Different Hash';
            previewContainer.appendChild(mismatchBadge);
        }
        
        // Mark as latest if applicable
        if (model.is_latest) {
            card.classList.add('latest');
        }
        
        // Move tooltip listeners to the preview container for consistent behavior
        // regardless of whether the preview is an image or video
        previewContainer.addEventListener('mouseover', () => this.renderTooltip(card, model));
        previewContainer.addEventListener('mouseout', () => {
            const tooltip = document.querySelector('.model-tooltip');
            if (tooltip) tooltip.remove();
        });
        
        // Add card footer with just model name
        const footer = document.createElement('div');
        footer.className = 'card-footer';
        
        const modelInfo = document.createElement('div');
        modelInfo.className = 'model-info';
        
        const modelName = document.createElement('span');
        modelName.className = 'model-name';
        modelName.textContent = model.model_name;
        modelInfo.appendChild(modelName);
        
        footer.appendChild(modelInfo);
        previewContainer.appendChild(footer);
        card.appendChild(previewContainer);
        
        // Add selection checkbox
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'selector-checkbox';
        checkbox.dataset.filePath = model.file_path;
        checkbox.dataset.groupHash = groupHash;
        
        // Check if already selected
        if (this.selectedForDeletion.has(model.file_path)) {
            checkbox.checked = true;
            card.classList.add('duplicate-selected');
        }
        
        // Disable checkbox for mismatched files
        if (isMismatched) {
            checkbox.disabled = true;
            checkbox.title = "This file has a different actual hash and can't be selected";
        }
        
        // Add change event to checkbox
        checkbox.addEventListener('change', (e) => {
            e.stopPropagation();
            this.toggleCardSelection(model.file_path, card, checkbox);
        });
        
        // Make the entire card clickable for selection
        card.addEventListener('click', (e) => {
            // Don't toggle if clicking on the checkbox directly or card actions
            if (e.target === checkbox || e.target.closest('.card-actions')) {
                return;
            }
            
            // Don't toggle if it's a mismatched file
            if (isMismatched) {
                return;
            }
            
            // Toggle checkbox state
            checkbox.checked = !checkbox.checked;
            this.toggleCardSelection(model.file_path, card, checkbox);
        });
        
        card.appendChild(checkbox);

        const keepButton = document.createElement('button');
        keepButton.type = 'button';
        keepButton.className = 'keep-item-btn';
        keepButton.textContent = translate('duplicates.keepThis');
        keepButton.title = translate('duplicates.keepThisTooltip');
        keepButton.addEventListener('click', event => {
            event.stopPropagation();
            this.keepModelInGroup(model.file_path, groupHash);
        });
        card.appendChild(keepButton);
        return card;
    }
    
    renderTooltip(card, model) {
        // Remove any existing tooltips
        const existingTooltip = document.querySelector('.model-tooltip');
        if (existingTooltip) existingTooltip.remove();
        
        // Create tooltip
        const tooltip = document.createElement('div');
        tooltip.className = 'model-tooltip';
        
        // Check if this model is a mismatched file and get the actual hash
        const isMismatched = this.mismatchedFiles.has(model.file_path);
        const actualHash = isMismatched ? this.mismatchedFiles.get(model.file_path) : null;
        
        // Add model information to tooltip
        let tooltipContent = `
            <div class="tooltip-header">${model.model_name}</div>
            <div class="tooltip-info">
                <div><strong>Version:</strong> ${model.civitai?.name || 'Unknown'}</div>
                <div><strong>Filename:</strong> ${model.file_name}</div>
                <div><strong>Path:</strong> ${model.file_path}</div>
                <div><strong>Base Model:</strong> ${model.base_model || 'Unknown'}</div>
                <div><strong>Modified:</strong> ${formatDate(model.modified)}</div>
                <div><strong>Metadata Hash:</strong> <span class="hash-value">${model.sha256}</span></div>
        `;
        
        // Add actual hash information if available
        if (isMismatched && actualHash) {
            tooltipContent += `<div class="hash-mismatch-info"><strong>Actual Hash:</strong> <span class="hash-value">${actualHash}</span></div>`;
        }
        
        tooltipContent += `</div>`;
        tooltip.innerHTML = tooltipContent;
        
        // Position tooltip relative to card
        const cardRect = card.getBoundingClientRect();
        tooltip.style.top = `${cardRect.top + window.scrollY - 10}px`;
        tooltip.style.left = `${cardRect.left + window.scrollX + cardRect.width + 10}px`;
        
        // Add tooltip to document
        document.body.appendChild(tooltip);
        
        // Check if tooltip is outside viewport and adjust if needed
        const tooltipRect = tooltip.getBoundingClientRect();
        if (tooltipRect.right > window.innerWidth) {
            tooltip.style.left = `${cardRect.left + window.scrollX - tooltipRect.width - 10}px`;
        }
    }
    
    toggleSelectAllInGroup(hash) {
        if (this._isDeleting) return;

        const group = this.duplicateGroups.find(entry => entry.hash === hash);
        if (!group) return;

        const selectableModels = group.models.filter(model => !this.mismatchedFiles.has(model.file_path));
        const allSelected = selectableModels.length > 0 && selectableModels.every(
            model => this.selectedForDeletion.has(model.file_path)
        );
        selectableModels.forEach(model => {
            if (allSelected) {
                this.selectedForDeletion.delete(model.file_path);
            } else {
                this.selectedForDeletion.add(model.file_path);
            }
        });

        const groupDiv = Array.from(document.querySelectorAll('.duplicate-group')).find(
            element => element.dataset.hash === hash
        );
        this._syncRenderedGroupSelection(groupDiv);
        const button = groupDiv?.querySelector('.btn-select-all');
        if (button) {
            button.textContent = !allSelected ? 'Deselect All' : 'Select All';
        }

        this.updateSelectedCount();
    }
    
    keepModelInGroup(filePath, hash) {
        const group = this.duplicateGroups.find(entry => entry.hash === hash);
        if (!group) return;

        const selectableIds = new Set(
            group.models
                .filter(model => !this.mismatchedFiles.has(model.file_path))
                .map(model => model.file_path)
        );
        this._keepItemInGroup(group, filePath, selectableIds);
    }

    selectLatestInGroup(hash, updateCount = true) {
        if (this._isDeleting) return;

        const group = this.duplicateGroups.find(entry => entry.hash === hash);
        if (!group || group.models.length === 0) return;

        const sortedModels = [...group.models].sort((a, b) => (b.modified || 0) - (a.modified || 0));
        const keeper = sortedModels[0];
        this.selectedForDeletion.delete(keeper.file_path);
        group.models.forEach(model => {
            if (model === keeper || this.mismatchedFiles.has(model.file_path)) return;
            this.selectedForDeletion.add(model.file_path);
        });

        const groupDiv = Array.from(document.querySelectorAll('.duplicate-group')).find(
            element => element.dataset.hash === hash
        );
        this._syncRenderedGroupSelection(groupDiv);
        const button = groupDiv?.querySelector('.btn-select-all');
        if (button) {
            button.textContent = 'Select All';
        }

        if (updateCount) {
            this.updateSelectedCount();
        }
    }

    selectLatestDuplicates() {
        if (this._isDeleting) return;

        this.duplicateGroups.forEach(group => {
            this.selectLatestInGroup(group.hash, false);
        });
        this.updateSelectedCount();
    }
    
    async deleteSelectedDuplicates() {
        if (this._isDeleting) return false;

        if (this.selectedForDeletion.size === 0) {
            showToast('toast.duplicates.noItemsSelected', { type: this.modelType }, 'info');
            return;
        }
        
        try {
            this._prepareDeleteConfirmation();
            modalManager.showModal('duplicateDeleteModal');
        } catch (error) {
            console.error('Error preparing delete:', error);
            showToast('toast.duplicates.deleteError', { message: error.message }, 'error');
        }
    }
    
    _applySuccessfulDeletions(deletedPaths) {
        this._libraryNeedsRefresh = true;
        state.virtualScroller?.removeMultipleItemsByFilePath?.(deletedPaths);
        this._removeSuccessfullyDeleted(deletedPaths);
        this._pruneVerificationState();

        const groupCount = this.duplicateGroups.length;
        const countSpan = document.getElementById('duplicatesCount');
        if (countSpan) {
            countSpan.textContent = `Found ${groupCount} duplicate group${groupCount !== 1 ? 's' : ''}`;
        }
        this.updateDuplicatesBadge(groupCount);
        this.renderDuplicateGroups();
        this.updateSelectedCount();
    }

    // Execute deletion after confirmation
    async confirmDeleteDuplicates() {
        if (this._isDeleting) return false;
        if (this.selectedForDeletion.size === 0) {
            modalManager.closeModal('duplicateDeleteModal');
            return false;
        }

        const filePaths = Array.from(this.selectedForDeletion);
        this._isDeleting = true;
        this._setDeletingState(true);
        state.loadingManager?.showSimpleLoading(
            translate('duplicates.deleting', { count: filePaths.length })
        );

        try {           
            // Close the modal
            modalManager.closeModal('duplicateDeleteModal');
            
            // Call API to bulk delete
            const response = await fetch(`/api/lm/${this.modelType}/bulk-delete`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ file_paths: filePaths })
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete selected models');
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error deleting models');
            }

            const results = Array.isArray(data.results) ? data.results : [];
            const failures = results.filter(entry => entry && entry.success === false);

            const batchIds = !data.batch_id && Array.isArray(data.batch_ids) && data.batch_ids.length
                ? data.batch_ids
                : null;

            if (data.batch_id || batchIds) {
                // One undo action restores the whole selected group
                const refreshFn = async () => {
                    await resetAndReload(true);
                    this._libraryNeedsRefresh = false;
                    if (this.inDuplicateMode) {
                        await this.findDuplicates({ suppressEmptyToast: true });
                    }
                };
                const onAction = data.batch_id
                    ? () => handleUndoDelete(data.batch_id, refreshFn)
                    : async () => {
                        for (const id of batchIds) {
                            const succeeded = await handleUndoDelete(id, null, { showToast: false, refresh: false });
                            if (!succeeded) {
                                showToast('toast.undo.failed', { error: '' }, 'error');
                                return;
                            }
                        }
                        await refreshFn();
                        showToast('toast.undo.restored', {}, 'success');
                    };
                showActionToast('toast.undo.deletedBulk', { count: data.total_deleted }, 'success', {
                    actionText: translate('toast.undo.action'),
                    onAction,
                });
            } else {
                showToast('toast.duplicates.deleteSuccess', { count: data.total_deleted, type: this.modelType }, 'success');
            }

            // Per-file failures are reported in `results` while the request as
            // a whole still succeeded; never hide them behind the success toast.
            if (failures.length > 0) {
                showToast('toast.duplicates.deletePartialFailed', {
                    failed: failures.length,
                    type: this.modelType,
                    message: failures[0].error || '',
                }, 'error');
            }

            // Files are gone from disk but the library cache was not updated:
            // the deleted cards would otherwise reappear after the refresh and
            // only a full rebuild can clear them.
            if (data.cache_updated === false && data.total_deleted > 0) {
                showToast('toast.duplicates.cacheUpdateFailed', {}, 'warning');
            }
            
            const deletedPaths = results.length > 0
                ? results.filter(entry => entry?.success && entry.file_path).map(entry => entry.file_path)
                : (data.total_deleted > 0 ? filePaths : []);
            if (deletedPaths.length > 0) {
                this._applySuccessfulDeletions(deletedPaths);
            }
            
        } catch (error) {
            console.error('Error deleting models:', error);
            showToast('toast.duplicates.deleteFailed', { type: this.modelType, message: error.message }, 'error');
        } finally {
            this._isDeleting = false;
            this._setDeletingState(false);
            state.loadingManager?.hide();
        }
    }
    
    // Public method to update the badge after refresh
    updateDuplicatesBadgeAfterRefresh() {
        // Use this method after refresh operations
        this.checkDuplicatesCount();
    }

    // Add this new method for tooltip behavior
    setupHelpTooltip() {
      const helpIcon = document.getElementById('duplicatesHelp');
      const helpTooltip = document.getElementById('duplicatesHelpTooltip');
      
      if (!helpIcon || !helpTooltip) return;
      
      // Clean up existing handlers first
      this.cleanupHelpTooltipHandlers();
      
      // Create new handler functions and store references
      this.helpTooltipHandlers.mouseenter = (e) => {
          // Get the container's positioning context
          const bannerContent = helpIcon.closest('.banner-content');
          
          // Get positions relative to the viewport
          const iconRect = helpIcon.getBoundingClientRect();
          const bannerRect = bannerContent.getBoundingClientRect();
          
          // Set initial position relative to the banner content
          helpTooltip.style.display = 'block';
          helpTooltip.style.top = `${iconRect.bottom - bannerRect.top + 10}px`;
          helpTooltip.style.left = `${iconRect.left - bannerRect.left - 10}px`;
          
          // Check if the tooltip is going off-screen to the right
          const tooltipRect = helpTooltip.getBoundingClientRect();
          const viewportWidth = window.innerWidth;
          
          if (tooltipRect.right > viewportWidth - 20) {
              // Reposition relative to container if too close to right edge
              helpTooltip.style.left = `${bannerContent.offsetWidth - tooltipRect.width - 20}px`;
          }
      };
      
      this.helpTooltipHandlers.mouseleave = () => {
          helpTooltip.style.display = 'none';
      };
      
      this.helpTooltipHandlers.click = (e) => {
          if (!helpIcon.contains(e.target)) {
              helpTooltip.style.display = 'none';
          }
      };
      
      // Add event listeners
      helpIcon.addEventListener('mouseenter', this.helpTooltipHandlers.mouseenter);
      helpIcon.addEventListener('mouseleave', this.helpTooltipHandlers.mouseleave);
      document.addEventListener('click', this.helpTooltipHandlers.click);
    }

    // Handle verify hashes button click
    async handleVerifyHashes(group) {
        try {
            const groupHash = group.hash;
            
            // Check if already verified
            if (this.verifiedGroups.has(groupHash)) {
                showToast('toast.models.verificationAlreadyDone', {}, 'info');
                return;
            }
            
            // Show loading state
            state.loadingManager.showSimpleLoading('Verifying hashes...');
            
            // Get file paths for all models in the group
            const filePaths = group.models.map(model => model.file_path);
            
            // Make API request to verify hashes
            const response = await fetch(`/api/lm/${this.modelType}/verify-duplicates`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ file_paths: filePaths })
            });
            
            if (!response.ok) {
                throw new Error(`Verification failed: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Unknown error during verification');
            }
            
            // Process verification results
            const verifiedAsDuplicates = data.verified_as_duplicates;
            const mismatchedFiles = data.mismatched_files || [];

            this._clearMismatchStateForGroup(group);
            
            // Update mismatchedFiles map
            if (data.new_hash_map) {
                Object.entries(data.new_hash_map).forEach(([path, hash]) => {
                    this.mismatchedFiles.set(path, hash);
                    this.selectedForDeletion.delete(path);
                });
            }
            
            // Mark this group as verified
            this.verifiedGroups.add(groupHash);
            
            // Re-render the duplicate groups to show verification status
            this.renderDuplicateGroups();
            this.updateSelectedCount();
            
            // Show appropriate toast message
            if (mismatchedFiles.length > 0) {
                showToast('toast.models.verificationCompleteMismatch', { count: mismatchedFiles.length }, 'warning');
            } else {
                showToast('toast.models.verificationCompleteSuccess', {}, 'success');
            }
            
        } catch (error) {
            console.error('Error verifying hashes:', error);
            showToast('toast.models.verificationFailed', { message: error.message }, 'error');
        } finally {
            // Hide loading state
            state.loadingManager.hide();
        }
    }
    
    // Add this new method for badge toggle setup
    setupBadgeToggle() {
        const toggleControl = document.getElementById('badgeToggleControl');
        const toggleInput = document.getElementById('badgeToggleInput');
        
        if (!toggleControl || !toggleInput) return;
        
        // Clean up existing handler first
        this.cleanupBadgeToggleHandler();
        
        // Set initial state based on stored preference (default to true/checked)
        toggleInput.checked = this.showBadge;
        
        // Create and store the handler function
        this.badgeToggleHandler = (e) => {
            this.showBadge = e.target.checked;
            setShowDuplicatesNotification(this.showBadge);
            
            // Update badge visibility immediately if not in duplicate mode
            if (!this.inDuplicateMode) {
                this.updateDuplicatesBadge(this.duplicateGroups.length);
            }
            
            showToast(
                this.showBadge ? 'Duplicates notification will be shown' : 'Duplicates notification will be hidden',
                'info'
            );
        };
        
        // Add change event listener
        toggleInput.addEventListener('change', this.badgeToggleHandler);
    }
    
    // Clean up all event handlers
    cleanupEventHandlers() {
        this.cleanupBadgeToggleHandler();
        this.cleanupHelpTooltipHandlers();
    }
    
    // Clean up badge toggle event handler
    cleanupBadgeToggleHandler() {
        if (this.badgeToggleHandler) {
            const toggleInput = document.getElementById('badgeToggleInput');
            if (toggleInput) {
                toggleInput.removeEventListener('change', this.badgeToggleHandler);
            }
            this.badgeToggleHandler = null;
        }
    }
    
    // Clean up help tooltip event handlers
    cleanupHelpTooltipHandlers() {
        const helpIcon = document.getElementById('duplicatesHelp');
        
        if (helpIcon && this.helpTooltipHandlers.mouseenter) {
            helpIcon.removeEventListener('mouseenter', this.helpTooltipHandlers.mouseenter);
        }
        
        if (helpIcon && this.helpTooltipHandlers.mouseleave) {
            helpIcon.removeEventListener('mouseleave', this.helpTooltipHandlers.mouseleave);
        }
        
        if (this.helpTooltipHandlers.click) {
            document.removeEventListener('click', this.helpTooltipHandlers.click);
        }
        
        // Reset handler references
        this.helpTooltipHandlers = {
            mouseenter: null,
            mouseleave: null,
            click: null
        };
        
        // Hide tooltip if it's visible
        const helpTooltip = document.getElementById('duplicatesHelpTooltip');
        if (helpTooltip) {
            helpTooltip.style.display = 'none';
        }
    }
}
