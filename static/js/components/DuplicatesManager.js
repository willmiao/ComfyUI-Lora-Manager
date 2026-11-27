// Duplicates Manager Component
import { showToast, showActionToast } from '../utils/uiHelpers.js';
import { handleUndoDelete } from '../utils/undoHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { RecipeCard } from './RecipeCard.js';
import { state, getCurrentPageState } from '../state/index.js';
import { recreateVirtualScroll } from '../utils/infiniteScroll.js';
import { DuplicatesViewManager } from './shared/DuplicatesViewManager.js';

export class DuplicatesManager extends DuplicatesViewManager {
    constructor(recipeManager) {
        super();
        this.recipeManager = recipeManager;
        this._isFindingDuplicates = false;
        this._initPromptMatchToggle();
        this._initHelpTooltip();
    }

    _getPromptMatchPreference() {
        return localStorage.getItem('recipes_duplicates_include_prompt') === '1';
    }

    _setPromptMatchPreference(enabled) {
        localStorage.setItem('recipes_duplicates_include_prompt', enabled ? '1' : '0');
    }

    updateBasisDisplay() {
        const basisEl = document.getElementById('duplicatesBasis');
        const helpTextEl = document.getElementById('duplicatesHelpText');
        const checkbox = document.getElementById('promptMatchInput');
        const includePrompt = this._getPromptMatchPreference();
        if (checkbox) {
            checkbox.checked = includePrompt;
        }
        if (basisEl) {
            basisEl.textContent = translate(
                includePrompt
                    ? 'recipes.duplicates.basis.loraComboAndPrompt'
                    : 'recipes.duplicates.basis.loraCombo'
            );
        }
        if (helpTextEl) {
            helpTextEl.textContent = translate(
                includePrompt
                    ? 'recipes.duplicates.basis.hintPromptIncluded'
                    : 'recipes.duplicates.basis.hintLoraCombo'
            );
        }
    }

    _initPromptMatchToggle() {
        const checkbox = document.getElementById('promptMatchInput');
        if (!checkbox) return;
        checkbox.addEventListener('change', async (e) => {
            this._setPromptMatchPreference(e.target.checked);
            this.updateBasisDisplay();
            checkbox.disabled = true;
            try {
                await this.findDuplicates();
            } finally {
                checkbox.disabled = false;
            }
        });
    }

    _initHelpTooltip() {
        const helpIcon = document.getElementById('duplicatesHelp');
        const helpTooltip = document.getElementById('duplicatesHelpTooltip');
        if (!helpIcon || !helpTooltip) return;

        helpIcon.addEventListener('mouseenter', () => {
            const bannerContent = helpIcon.closest('.banner-content');
            if (!bannerContent) return;
            const iconRect = helpIcon.getBoundingClientRect();
            const bannerRect = bannerContent.getBoundingClientRect();
            helpTooltip.style.display = 'block';
            helpTooltip.style.top = `${iconRect.bottom - bannerRect.top + 10}px`;
            helpTooltip.style.left = `${iconRect.left - bannerRect.left - 10}px`;
            const tooltipRect = helpTooltip.getBoundingClientRect();
            if (tooltipRect.right > window.innerWidth - 20) {
                helpTooltip.style.left = `${bannerContent.offsetWidth - tooltipRect.width - 20}px`;
            }
        });
        helpIcon.addEventListener('mouseleave', () => {
            helpTooltip.style.display = 'none';
        });
    }

    async findDuplicates({ suppressEmptyToast = false } = {}) {
        if (this._isDeleting) return false;

        // Guard against re-entry: the scan can take a while on large
        // libraries, and repeated clicks would pile up identical requests
        // on the backend.
        if (this._isFindingDuplicates) {
            return false;
        }
        this._isFindingDuplicates = true;
        const triggerButton = document.querySelector('[data-action="find-duplicates"]');
        if (triggerButton) {
            triggerButton.disabled = true;
            triggerButton.classList.add('loading');
        }
        state.loadingManager?.showSimpleLoading(translate('recipes.duplicates.finding'));
        try {
            const includePrompt = this._getPromptMatchPreference();
            const endpoint = includePrompt
                ? '/api/lm/recipes/find-duplicates?include_prompt=1'
                : '/api/lm/recipes/find-duplicates';
            const response = await fetch(endpoint);
            if (!response.ok) {
                throw new Error('Failed to find duplicates');
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error finding duplicates');
            }

            this.duplicateGroups = data.duplicate_groups || [];

            if (this.duplicateGroups.length === 0) {
                if (!suppressEmptyToast) {
                    showToast('toast.duplicates.noDuplicatesFound', { type: 'recipes' }, 'info');
                }
                // Keep (or enter) the duplicates view when the user is tuning
                // the matching basis, so the prompt-matching toggle stays
                // reachable; otherwise just toast and stay on the library grid.
                if (!this.inDuplicateMode && !includePrompt) {
                    return false;
                }
                this.enterDuplicateMode();
                return true;
            }

            this.enterDuplicateMode();
            return true;
        } catch (error) {
            console.error('Error finding duplicates:', error);
            showToast('toast.duplicates.findFailed', { message: error.message }, 'error');
            return false;
        } finally {
            this._isFindingDuplicates = false;
            if (triggerButton) {
                triggerButton.disabled = false;
                triggerButton.classList.remove('loading');
            }
            state.loadingManager?.hide();
        }
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
            countSpan.textContent = this.duplicateGroups.length === 0
                ? translate('recipes.duplicates.noGroups')
                : translate('recipes.duplicates.found', { count: this.duplicateGroups.length });
            banner.style.display = 'block';
        }

        // Restore the prompt-matching preference and show the matching basis
        this.updateBasisDisplay();
        
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
    }
    
    async exitDuplicateMode({ refreshLibrary = false } = {}) {
        const shouldRefreshLibrary = refreshLibrary || this._libraryNeedsRefresh;
        this._libraryNeedsRefresh = false;
        this.inDuplicateMode = false;
        this.selectedForDeletion.clear();
        
        // Update state
        const pageState = getCurrentPageState();
        pageState.duplicatesMode = false;
        this._setDuplicatesButtonActive(false);
        
        // Hide duplicates banner
        const banner = document.getElementById('duplicatesBanner');
        if (banner) {
            banner.style.display = 'none';
        }
        
        // Remove duplicate-mode class from the body
        document.body.classList.remove('duplicate-mode');
        
        // Clear the recipe grid first
        this._stopProgressiveGroupRendering();
        const recipeGrid = document.getElementById('recipeGrid');
        if (recipeGrid) {
            recipeGrid.innerHTML = '';
        }
        
        // Re-enable virtual scrolling, or apply a layout switch deferred
        // while duplicates mode was active (enabling the old scroller first
        // would let its pending rAF render repopulate the grid after the
        // new scroller is created, leaving orphaned/overlapping cards).
        if (state.pendingLayoutRecreate || shouldRefreshLibrary) {
            state.pendingLayoutRecreate = false;
            await recreateVirtualScroll('recipes');
        } else if (state.virtualScroller) {
            state.virtualScroller.calculateLayout?.();
            state.virtualScroller.enable();
        }
    }
    
    renderDuplicateGroups() {
        const recipeGrid = document.getElementById('recipeGrid');
        if (!recipeGrid) return;

        this._stopProgressiveGroupRendering();
        recipeGrid.innerHTML = '';

        if (this.duplicateGroups.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.className = 'duplicates-empty-state';
            emptyState.textContent = translate('recipes.duplicates.noGroups');
            recipeGrid.appendChild(emptyState);
            return;
        }

        this._startProgressiveGroupRendering(
            recipeGrid,
            (group, groupIndex) => this._createDuplicateGroup(group, groupIndex)
        );
    }

    _createDuplicateGroup(group, groupIndex) {
        const groupKey = group.key;
        const groupDiv = document.createElement('div');
        groupDiv.className = 'duplicate-group';
        groupDiv.dataset.groupKey = groupKey;

        const allSelected = group.recipes.length > 0 && group.recipes.every(
            recipe => this.selectedForDeletion.has(recipe.id)
        );
        const header = document.createElement('div');
        header.className = 'duplicate-group-header';
        header.innerHTML = `
            <span>Duplicate Group #${groupIndex + 1} (${group.recipes.length} recipes)</span>
            <span>
                <button class="btn-select-all" onclick="recipeManager.duplicatesManager.toggleSelectAllInGroup('${groupKey}')">
                    ${allSelected ? 'Deselect All' : 'Select All'}
                </button>
                <button class="btn-select-latest" onclick="recipeManager.duplicatesManager.selectLatestInGroup('${groupKey}')">
                    Keep Latest
                </button>
            </span>
        `;
        groupDiv.appendChild(header);

        const cardsDiv = document.createElement('div');
        cardsDiv.className = 'card-group-container';
        const sortedRecipes = [...group.recipes].sort((a, b) => b.modified - a.modified);
        this._renderCardGroup(groupDiv, cardsDiv, sortedRecipes, (recipe, index) => {
            const recipeCard = new RecipeCard(recipe, currentRecipe => {
                this.recipeManager.showRecipeDetails(currentRecipe);
            });
            const card = recipeCard.element;
            card.classList.add('duplicate');
            if (index === 0) {
                card.classList.add('latest');
            }

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'selector-checkbox';
            checkbox.dataset.recipeId = recipe.id;
            checkbox.dataset.groupKey = groupKey;

            if (this.selectedForDeletion.has(recipe.id)) {
                checkbox.checked = true;
                card.classList.add('duplicate-selected');
            }

            checkbox.addEventListener('change', event => {
                event.stopPropagation();
                this.toggleCardSelection(recipe.id, card, checkbox);
            });

            card.addEventListener('click', event => {
                if (event.target === checkbox || event.target.closest('.card-actions')) {
                    return;
                }

                checkbox.checked = !checkbox.checked;
                this.toggleCardSelection(recipe.id, card, checkbox);
            });

            card.appendChild(checkbox);

            const keepButton = document.createElement('button');
            keepButton.type = 'button';
            keepButton.className = 'keep-item-btn';
            keepButton.textContent = translate('duplicates.keepThis');
            keepButton.title = translate('duplicates.keepThisTooltip');
            keepButton.addEventListener('click', event => {
                event.stopPropagation();
                this._keepItemInGroup(group, recipe.id);
            });
            card.appendChild(keepButton);
            return card;
        });
        groupDiv.appendChild(cardsDiv);
        return groupDiv;
    }
    
    toggleSelectAllInGroup(groupKey) {
        if (this._isDeleting) return;

        const group = this.duplicateGroups.find(entry => entry.key === groupKey);
        if (!group) return;

        const allSelected = group.recipes.length > 0 && group.recipes.every(
            recipe => this.selectedForDeletion.has(recipe.id)
        );
        group.recipes.forEach(recipe => {
            if (allSelected) {
                this.selectedForDeletion.delete(recipe.id);
            } else {
                this.selectedForDeletion.add(recipe.id);
            }
        });

        const groupDiv = this._getRenderedGroup(groupKey);
        this._syncRenderedGroupSelection(groupDiv);
        const button = groupDiv?.querySelector('.btn-select-all');
        if (button) {
            button.textContent = !allSelected ? 'Deselect All' : 'Select All';
        }

        this.updateSelectedCount();
    }

    _getRenderedGroup(groupKey) {
        return Array.from(document.querySelectorAll('.duplicate-group')).find(
            element => element.dataset.groupKey === groupKey
        );
    }
    
    selectAllInGroup(groupKey) {
        if (this._isDeleting) return;

        const group = this.duplicateGroups.find(entry => entry.key === groupKey);
        if (!group) return;

        group.recipes.forEach(recipe => this.selectedForDeletion.add(recipe.id));
        const groupDiv = this._getRenderedGroup(groupKey);
        this._syncRenderedGroupSelection(groupDiv);
        const button = groupDiv?.querySelector('.btn-select-all');
        if (button) {
            button.textContent = 'Deselect All';
        }

        this.updateSelectedCount();
    }
    
    selectLatestInGroup(groupKey, updateCount = true) {
        if (this._isDeleting) return;

        const group = this.duplicateGroups.find(entry => entry.key === groupKey);
        if (!group || group.recipes.length === 0) return;

        const sortedRecipes = [...group.recipes].sort((a, b) => b.modified - a.modified);
        this.selectedForDeletion.delete(sortedRecipes[0].id);
        sortedRecipes.slice(1).forEach(recipe => this.selectedForDeletion.add(recipe.id));

        const groupDiv = this._getRenderedGroup(groupKey);
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
            this.selectLatestInGroup(group.key, false);
        });
        this.updateSelectedCount();
    }
    
    async deleteSelectedDuplicates() {
        if (this._isDeleting) return false;

        if (this.selectedForDeletion.size === 0) {
            showToast('toast.duplicates.noItemsSelected', { type: 'recipes' }, 'info');
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
    
    _applySuccessfulDeletions(deletedIds) {
        const deletedIdSet = new Set(deletedIds);
        const deletedPaths = [];
        this.duplicateGroups.forEach(group => {
            group.recipes.forEach(recipe => {
                if (deletedIdSet.has(recipe.id) && recipe.file_path) {
                    deletedPaths.push(recipe.file_path);
                }
            });
        });

        this._libraryNeedsRefresh = true;
        if (deletedPaths.length > 0) {
            state.virtualScroller?.removeMultipleItemsByFilePath?.(deletedPaths);
        }
        this._removeSuccessfullyDeleted(deletedIds);

        const countSpan = document.getElementById('duplicatesCount');
        if (countSpan) {
            countSpan.textContent = this.duplicateGroups.length === 0
                ? translate('recipes.duplicates.noGroups')
                : translate('recipes.duplicates.found', { count: this.duplicateGroups.length });
        }
        this.renderDuplicateGroups();
        this.updateSelectedCount();
    }

    // Add new method to execute deletion after confirmation
    async confirmDeleteDuplicates() {
        if (this._isDeleting) return false;
        if (this.selectedForDeletion.size === 0) {
            modalManager.closeModal('duplicateDeleteModal');
            return false;
        }

        const recipeIds = Array.from(this.selectedForDeletion);
        this._isDeleting = true;
        this._setDeletingState(true);
        state.loadingManager?.showSimpleLoading(
            translate('duplicates.deleting', { count: recipeIds.length })
        );

        try {           
            // Close the modal
            modalManager.closeModal('duplicateDeleteModal');
            
            // Call API to bulk delete
            const response = await fetch('/api/lm/recipes/bulk-delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ recipe_ids: recipeIds })
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete selected recipes');
            }
            
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error deleting recipes');
            }

            const batchIds = !data.batch_id && Array.isArray(data.batch_ids) && data.batch_ids.length
                ? data.batch_ids
                : null;

            if (data.batch_id || batchIds) {
                // One undo action restores the whole selected group
                const refreshFn = async () => {
                    if (this.inDuplicateMode) {
                        this._libraryNeedsRefresh = true;
                        await this.findDuplicates({ suppressEmptyToast: true });
                    } else {
                        await window.recipeManager.loadRecipes(true);
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
                showToast('toast.duplicates.deleteSuccess', { count: data.total_deleted, type: 'recipes' }, 'success');
            }
            
            const failures = Array.isArray(data.failed) ? data.failed : [];
            if (failures.length > 0) {
                showToast('toast.duplicates.deletePartialFailed', {
                    failed: failures.length,
                    type: 'recipes',
                    message: failures[0].reason || failures[0].error || '',
                }, 'error');
            }

            if (data.total_deleted > 0) {
                const deletedIds = Array.isArray(data.deleted)
                    ? data.deleted
                    : recipeIds.slice(0, data.total_deleted);
                this._applySuccessfulDeletions(deletedIds);
            }
            
        } catch (error) {
            console.error('Error deleting recipes:', error);
            showToast('toast.duplicates.deleteFailed', { type: 'recipes', message: error.message }, 'error');
        } finally {
            this._isDeleting = false;
            this._setDeletingState(false);
            state.loadingManager?.hide();
        }
    }
}
