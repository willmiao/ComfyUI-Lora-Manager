// Duplicates Manager Component
import { showToast, showActionToast } from '../utils/uiHelpers.js';
import { handleUndoDelete } from '../utils/undoHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { RecipeCard } from './RecipeCard.js';
import { state, getCurrentPageState } from '../state/index.js';
import { recreateVirtualScroll } from '../utils/infiniteScroll.js';

export class DuplicatesManager {
    constructor(recipeManager) {
        this.recipeManager = recipeManager;
        this.duplicateGroups = [];
        this.inDuplicateMode = false;
        this.selectedForDeletion = new Set();
        this._isFindingDuplicates = false;
        // 'duplicate' (exact fingerprint match) or 'similar' (fuzzy signature)
        this.mode = 'duplicate';
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

    async findDuplicates() {
        // Guard against re-entry: the scan can take a while on large
        // libraries, and repeated clicks would pile up identical requests
        // on the backend.
        if (this._isFindingDuplicates) {
            return false;
        }
        this._isFindingDuplicates = true;
        this.mode = 'duplicate';
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
                showToast('toast.duplicates.noDuplicatesFound', { type: 'recipes' }, 'info');
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

    async findSimilar(options = {}) {
        this.mode = 'similar';
        try {
            const params = new URLSearchParams({
                weight_tolerance: options.weightTolerance ?? 0.2,
                drop_low_weight: options.dropLowWeight ? '1' : '0',
                low_weight_threshold: options.lowWeightThreshold ?? 0.3,
                match_prompt: options.matchPrompt ? '1' : '0',
                match_config: options.matchConfig ? '1' : '0',
            });
            const response = await fetch(`/api/lm/recipes/find-similar?${params.toString()}`);
            if (!response.ok) {
                throw new Error('Failed to find similar recipes');
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Unknown error finding similar recipes');
            }

            this.similarOptions = data.options || {};
            this.duplicateGroups = data.similar_groups || [];

            if (this.duplicateGroups.length === 0) {
                showToast('toast.duplicates.noSimilarFound', { type: 'recipes' }, 'info');
                return false;
            }

            this.enterDuplicateMode();
            return true;
        } catch (error) {
            console.error('Error finding similar recipes:', error);
            showToast('toast.duplicates.findSimilarFailed', { message: error.message }, 'error');
            return false;
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
            const groupCount = this.duplicateGroups.length;
            if (this.mode === 'similar') {
                countSpan.textContent = `Found ${groupCount} similar group${groupCount !== 1 ? 's' : ''}`;
            } else {
                countSpan.textContent = groupCount === 0
                    ? translate('recipes.duplicates.noGroups')
                    : translate('recipes.duplicates.found', { count: groupCount });
            }
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
    }
    
    async exitDuplicateMode() {
        this.inDuplicateMode = false;
        this.selectedForDeletion.clear();
        
        // Update state
        const pageState = getCurrentPageState();
        pageState.duplicatesMode = false;
        
        // Hide duplicates banner
        const banner = document.getElementById('duplicatesBanner');
        if (banner) {
            banner.style.display = 'none';
        }
        
        // Remove duplicate-mode class from the body
        document.body.classList.remove('duplicate-mode');
        
        // Clear the recipe grid first
        const recipeGrid = document.getElementById('recipeGrid');
        if (recipeGrid) {
            recipeGrid.innerHTML = '';
        }
        
        // Re-enable virtual scrolling, or apply a layout switch deferred
        // while duplicates mode was active (enabling the old scroller first
        // would let its pending rAF render repopulate the grid after the
        // new scroller is created, leaving orphaned/overlapping cards).
        if (state.pendingLayoutRecreate) {
            state.pendingLayoutRecreate = false;
            await recreateVirtualScroll('recipes');
        } else if (state.virtualScroller) {
            state.virtualScroller.enable();
        }
    }
    
    renderDuplicateGroups() {
        const recipeGrid = document.getElementById('recipeGrid');
        if (!recipeGrid) return;
        
        // Clear existing content
        recipeGrid.innerHTML = '';

        // Empty-state view: keep the banner (and the matching-basis toggle)
        // reachable when no groups match the current basis
        if (this.duplicateGroups.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.className = 'duplicates-empty-state';
            emptyState.textContent = translate('recipes.duplicates.noGroups');
            recipeGrid.appendChild(emptyState);
            return;
        }
        
        // Render each duplicate group
        this.duplicateGroups.forEach((group, groupIndex) => {
            const groupKey = group.key;
            const groupDiv = document.createElement('div');
            groupDiv.className = 'duplicate-group';
            groupDiv.dataset.groupKey = groupKey;
            
            // Create group header
            const header = document.createElement('div');
            header.className = 'duplicate-group-header';
            const groupTitle = this.mode === 'similar' ? 'Similar Group' : 'Duplicate Group';
            header.innerHTML = `
                <span>${groupTitle} #${groupIndex + 1} (${group.recipes.length} recipes)</span>
                <span>
                    <button class="btn-select-all" onclick="recipeManager.duplicatesManager.toggleSelectAllInGroup('${groupKey}')">
                        Select All
                    </button>
                    <button class="btn-select-latest" onclick="recipeManager.duplicatesManager.selectLatestInGroup('${groupKey}')">
                        Keep Latest
                    </button>
                </span>
            `;
            groupDiv.appendChild(header);

            // Similar mode: an expandable diff table so grouping is inspectable.
            if (this.mode === 'similar') {
                groupDiv.appendChild(this.buildSimilarDiff(group));
            }

            // Create cards container
            const cardsDiv = document.createElement('div');
            cardsDiv.className = 'card-group-container';
            
            // Add scrollable class if there are many recipes in the group
            if (group.recipes.length > 6) {
                cardsDiv.classList.add('scrollable');
                
                // Add expand/collapse toggle button
                const toggleBtn = document.createElement('button');
                toggleBtn.className = 'group-toggle-btn';
                toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
                toggleBtn.title = "Expand/Collapse";
                toggleBtn.onclick = function() {
                    cardsDiv.classList.toggle('scrollable');
                    this.innerHTML = cardsDiv.classList.contains('scrollable') ? 
                        '<i class="fas fa-chevron-down"></i>' : 
                        '<i class="fas fa-chevron-up"></i>';
                };
                groupDiv.appendChild(toggleBtn);
            }
            
            // Sort recipes by date (newest first)
            const sortedRecipes = [...group.recipes].sort((a, b) => b.modified - a.modified);
            
            // Add all recipe cards in this group
            sortedRecipes.forEach((recipe, index) => {
                // Create recipe card
                const recipeCard = new RecipeCard(recipe, (recipe) => {
                    this.recipeManager.showRecipeDetails(recipe);
                });
                const card = recipeCard.element;
                
                // Add duplicate class
                card.classList.add('duplicate');
                
                // Mark the latest one
                if (index === 0) {
                    card.classList.add('latest');
                }
                
                // Add selection checkbox
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'selector-checkbox';
                checkbox.dataset.recipeId = recipe.id;
                checkbox.dataset.groupKey = groupKey;
                
                // Check if already selected
                if (this.selectedForDeletion.has(recipe.id)) {
                    checkbox.checked = true;
                    card.classList.add('duplicate-selected');
                }
                
                // Add change event to checkbox
                checkbox.addEventListener('change', (e) => {
                    e.stopPropagation();
                    this.toggleCardSelection(recipe.id, card, checkbox);
                });
                
                // Make the entire card clickable for selection
                card.addEventListener('click', (e) => {
                    // Don't toggle if clicking on the checkbox directly or card actions
                    if (e.target === checkbox || e.target.closest('.card-actions')) {
                        return;
                    }
                    
                    // Toggle checkbox state
                    checkbox.checked = !checkbox.checked;
                    this.toggleCardSelection(recipe.id, card, checkbox);
                });
                
                card.appendChild(checkbox);
                cardsDiv.appendChild(card);
            });
            
            groupDiv.appendChild(cardsDiv);
            recipeGrid.appendChild(groupDiv);
        });
    }

    // --- Similar-mode diff table -------------------------------------------

    buildSimilarDiff(group) {
        const recipes = [...group.recipes].sort((a, b) => b.modified - a.modified);
        const wrapper = document.createElement('div');
        wrapper.className = 'similar-diff';

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'similar-diff-toggle';
        toggle.innerHTML = '<i class="fas fa-chevron-right"></i> Show diff';

        const panel = document.createElement('div');
        panel.className = 'similar-diff-panel';
        panel.style.display = 'none';
        panel.appendChild(this.buildSimilarDiffTable(recipes));

        toggle.addEventListener('click', () => {
            const isOpen = panel.style.display !== 'none';
            panel.style.display = isOpen ? 'none' : 'block';
            toggle.innerHTML = isOpen
                ? '<i class="fas fa-chevron-right"></i> Show diff'
                : '<i class="fas fa-chevron-down"></i> Hide diff';
        });

        wrapper.appendChild(toggle);
        wrapper.appendChild(panel);
        return wrapper;
    }

    buildSimilarDiffTable(recipes) {
        const table = document.createElement('table');
        table.className = 'similar-diff-table';

        // Header row: LoRA | #1 | #2 | ...
        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        headRow.appendChild(this._diffCell('th', 'LoRA'));
        recipes.forEach((recipe, i) => {
            const th = this._diffCell('th', `#${i + 1}`);
            th.title = recipe.title || '';
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');

        // Per-recipe hash -> lora entry, plus an ordered union of loras.
        const perRecipe = recipes.map(r => {
            const map = new Map();
            (r.diff_loras || []).forEach(l => map.set(l.hash, l));
            return map;
        });
        const order = [];
        const seen = new Set();
        recipes.forEach(r => (r.diff_loras || []).forEach(l => {
            if (!seen.has(l.hash)) {
                seen.add(l.hash);
                order.push({ hash: l.hash, name: l.name });
            }
        }));

        order.forEach(({ hash, name }) => {
            const row = document.createElement('tr');
            row.className = 'lora-row';
            const values = perRecipe.map(m => m.get(hash));

            // Most common weight is the reference; differing cells get highlighted.
            const counts = {};
            values.forEach(v => {
                if (v) {
                    const k = v.weight.toFixed(3);
                    counts[k] = (counts[k] || 0) + 1;
                }
            });
            const distinct = Object.keys(counts);
            const varies = distinct.length > 1;
            const modeKey = distinct.sort((a, b) => counts[b] - counts[a])[0];

            row.appendChild(this._diffCell('td', name, 'lora-name'));
            values.forEach(v => {
                if (!v) {
                    row.appendChild(this._diffCell('td', '—', 'missing'));
                    return;
                }
                const cell = this._diffCell('td', String(v.weight));
                if (v.low_weight) cell.classList.add('low-weight');
                if (varies && v.weight.toFixed(3) !== modeKey) cell.classList.add('diff');
                row.appendChild(cell);
            });
            tbody.appendChild(row);
        });

        // Prompt row (normalized compare of prompt + negative_prompt).
        tbody.appendChild(this._diffMetaRow('Prompt', recipes, r => {
            const p = r.diff_params || {};
            return `${this._norm(p.prompt)}␞${this._norm(p.negative_prompt)}`;
        }, r => {
            const p = r.diff_params || {};
            return [p.prompt, p.negative_prompt].filter(Boolean).join(' | ');
        }));

        // Config row (lists the differing gen params).
        tbody.appendChild(this._diffConfigRow('Config', recipes,
            ['steps', 'sampler', 'cfg_scale', 'size', 'clip_skip', 'denoising_strength']));

        table.appendChild(tbody);
        return table;
    }

    _diffCell(tag, text, cls) {
        const el = document.createElement(tag);
        el.textContent = text;
        if (cls) el.className = cls;
        return el;
    }

    _norm(text) {
        return (text || '').toString().toLowerCase().split(/\s+/).filter(Boolean).join(' ');
    }

    _diffMetaRow(label, recipes, compareFn, displayFn) {
        const row = document.createElement('tr');
        row.className = 'meta-row';
        row.appendChild(this._diffCell('td', label, 'meta-label'));
        const vals = recipes.map(compareFn);
        const same = vals.every(v => v === vals[0]);
        const cell = document.createElement('td');
        cell.colSpan = recipes.length;
        if (same) {
            cell.textContent = 'matched';
            cell.className = 'match-ok';
        } else {
            cell.textContent = 'differs';
            cell.className = 'match-diff';
            cell.title = recipes
                .map((r, i) => `#${i + 1}: ${displayFn(r) || '(none)'}`)
                .join('\n');
        }
        row.appendChild(cell);
        return row;
    }

    _diffConfigRow(label, recipes, keys) {
        const row = document.createElement('tr');
        row.className = 'meta-row';
        row.appendChild(this._diffCell('td', label, 'meta-label'));

        const diffs = [];
        keys.forEach(k => {
            const vals = recipes.map(r => (r.diff_params || {})[k]);
            const present = vals.some(v => v !== undefined && v !== null && v !== '');
            if (!present) return;
            const norm = v => (v === undefined || v === null || v === '') ? '—' : String(v);
            const allSame = vals.every(v => norm(v) === norm(vals[0]));
            if (!allSame) {
                const uniq = [...new Set(vals.map(norm))];
                diffs.push(`${k}: ${uniq.join(' / ')}`);
            }
        });

        const cell = document.createElement('td');
        cell.colSpan = recipes.length;
        if (diffs.length === 0) {
            cell.textContent = 'matched';
            cell.className = 'match-ok';
        } else {
            cell.textContent = diffs.join('    ');
            cell.className = 'match-diff';
        }
        row.appendChild(cell);
        return row;
    }

    // Helper method to toggle card selection state
    toggleCardSelection(recipeId, card, checkbox) {
        if (checkbox.checked) {
            this.selectedForDeletion.add(recipeId);
            card.classList.add('duplicate-selected');
        } else {
            this.selectedForDeletion.delete(recipeId);
            card.classList.remove('duplicate-selected');
        }
        
        this.updateSelectedCount();
    }
    
    updateSelectedCount() {
        const selectedCountEl = document.getElementById('duplicatesSelectedCount');
        if (selectedCountEl) {
            selectedCountEl.textContent = this.selectedForDeletion.size;
        }
        
        // Update delete button state
        const deleteBtn = document.querySelector('.btn-delete-selected');
        if (deleteBtn) {
            deleteBtn.disabled = this.selectedForDeletion.size === 0;
            deleteBtn.classList.toggle('disabled', this.selectedForDeletion.size === 0);
        }
    }
    
    toggleSelectAllInGroup(groupKey) {
        const checkboxes = document.querySelectorAll(`.selector-checkbox[data-group-key="${groupKey}"]`);
        const allSelected = Array.from(checkboxes).every(checkbox => checkbox.checked);

        // If all are selected, deselect all; otherwise select all
        checkboxes.forEach(checkbox => {
            checkbox.checked = !allSelected;
            const recipeId = checkbox.dataset.recipeId;
            const card = checkbox.closest('.model-card');

            if (!allSelected) {
                this.selectedForDeletion.add(recipeId);
                card.classList.add('duplicate-selected');
            } else {
                this.selectedForDeletion.delete(recipeId);
                card.classList.remove('duplicate-selected');
            }
        });

        // Update the button text
        const button = document.querySelector(`.duplicate-group[data-group-key="${groupKey}"] .btn-select-all`);
        if (button) {
            button.textContent = !allSelected ? "Deselect All" : "Select All";
        }

        this.updateSelectedCount();
    }
    
    selectAllInGroup(groupKey) {
        const checkboxes = document.querySelectorAll(`.selector-checkbox[data-group-key="${groupKey}"]`);
        checkboxes.forEach(checkbox => {
            checkbox.checked = true;
            this.selectedForDeletion.add(checkbox.dataset.recipeId);
            checkbox.closest('.model-card').classList.add('duplicate-selected');
        });

        // Update the button text
        const button = document.querySelector(`.duplicate-group[data-group-key="${groupKey}"] .btn-select-all`);
        if (button) {
            button.textContent = "Deselect All";
        }

        this.updateSelectedCount();
    }
    
    selectLatestInGroup(groupKey) {
        // Find all checkboxes in this group
        const checkboxes = document.querySelectorAll(`.selector-checkbox[data-group-key="${groupKey}"]`);
        
        // Get all the recipes in this group
        const group = this.duplicateGroups.find(g => g.key === groupKey);
        if (!group) return;
        
        // Sort recipes by date (newest first)
        const sortedRecipes = [...group.recipes].sort((a, b) => b.modified - a.modified);
        
        // Skip the first (latest) one and select the rest for deletion
        for (let i = 1; i < sortedRecipes.length; i++) {
            const recipeId = sortedRecipes[i].id;
            const checkbox = document.querySelector(`.selector-checkbox[data-recipe-id="${recipeId}"]`);
            
            if (checkbox) {
                checkbox.checked = true;
                this.selectedForDeletion.add(recipeId);
                checkbox.closest('.model-card').classList.add('duplicate-selected');
            }
        }
        
        // Make sure the latest one is not selected
        const latestId = sortedRecipes[0].id;
        const latestCheckbox = document.querySelector(`.selector-checkbox[data-recipe-id="${latestId}"]`);
        
        if (latestCheckbox) {
            latestCheckbox.checked = false;
            this.selectedForDeletion.delete(latestId);
            latestCheckbox.closest('.model-card').classList.remove('duplicate-selected');
        }
        
        this.updateSelectedCount();
    }
    
    selectLatestDuplicates() {
        // For each duplicate group, select all but the latest recipe
        this.duplicateGroups.forEach(group => {
            this.selectLatestInGroup(group.key);
        });
    }
    
    async deleteSelectedDuplicates() {
        if (this.selectedForDeletion.size === 0) {
            showToast('toast.duplicates.noItemsSelected', { type: 'recipes' }, 'info');
            return;
        }
        
        try {
            // Show the delete confirmation modal instead of a simple confirm
            const duplicateDeleteCount = document.getElementById('duplicateDeleteCount');
            if (duplicateDeleteCount) {
                duplicateDeleteCount.textContent = this.selectedForDeletion.size;
            }
            
            // Use the modal manager to show the confirmation modal
            modalManager.showModal('duplicateDeleteModal');
        } catch (error) {
            console.error('Error preparing delete:', error);
            showToast('toast.duplicates.deleteError', { message: error.message }, 'error');
        }
    }
    
    // Add new method to execute deletion after confirmation
    async confirmDeleteDuplicates() {
        try {           
            // Close the modal
            modalManager.closeModal('duplicateDeleteModal');
            
            // Prepare recipe IDs for deletion
            const recipeIds = Array.from(this.selectedForDeletion);
            
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
                const refreshFn = () => window.recipeManager.loadRecipes(true);
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
                        refreshFn();
                        showToast('toast.undo.restored', {}, 'success');
                    };
                showActionToast('toast.undo.deletedBulk', { count: data.total_deleted }, 'success', {
                    actionText: translate('toast.undo.action'),
                    onAction,
                });
            } else {
                showToast('toast.duplicates.deleteSuccess', { count: data.total_deleted, type: 'recipes' }, 'success');
            }
            
            // Exit duplicate mode if deletions were successful
            if (data.total_deleted > 0) {
                this.exitDuplicateMode();
            }
            
        } catch (error) {
            console.error('Error deleting recipes:', error);
            showToast('toast.duplicates.deleteFailed', { type: 'recipes', message: error.message }, 'error');
        }
    }
}
