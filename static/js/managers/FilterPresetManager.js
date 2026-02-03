import { showToast } from '../utils/uiHelpers.js';
import { removeStorageItem, setStorageItem, getStorageItem } from '../utils/storageHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { state } from '../state/index.js';

// Constants for preset management
const PRESETS_STORAGE_VERSION = 'v1';
const MAX_PRESET_NAME_LENGTH = 30;
const MAX_PRESETS_COUNT = 10;

// Marker for when wildcard patterns resolve to no matches
// This ensures we return empty results instead of all models
export const EMPTY_WILDCARD_MARKER = '__EMPTY_WILDCARD_RESULT__';

// Timeout for two-step delete confirmation (ms)
const DELETE_CONFIRM_TIMEOUT = 3000;

export class FilterPresetManager {
    constructor(options = {}) {
        this.currentPage = options.page || 'loras';
        this.filterManager = options.filterManager || null;
        this.activePreset = null;

        // Race condition fix: track pending preset applications
        this.applyPresetAbortController = null;
        this.applyPresetRequestId = 0;

        // UI state for two-step delete
        this.pendingDeletePreset = null;
        this.pendingDeleteTimeout = null;

        // UI state for inline naming
        this.isInlineNamingActive = false;

        // Cache for presets to avoid repeated settings lookups
        this._presetsCache = null;
    }

    // Storage key methods (legacy - for migration only)
    getPresetsStorageKey() {
        return `${this.currentPage}_filter_presets_${PRESETS_STORAGE_VERSION}`;
    }

    getActivePresetStorageKey() {
        return `${this.currentPage}_active_preset`;
    }

    /**
     * Get settings key for filter presets based on current page
     */
    getSettingsKey() {
        return `filter_presets`;
    }

    /**
     * Get the filter presets object from settings
     * Returns an object with page keys (loras, checkpoints, embeddings) containing presets arrays
     */
    getPresetsFromSettings() {
        const settings = state?.global?.settings;
        const presets = settings?.filter_presets;
        if (presets && typeof presets === 'object') {
            return presets;
        }
        return {};
    }

    /**
     * Save filter presets to backend settings
     */
    async savePresetsToBackend(allPresets) {
        try {
            const response = await fetch('/api/lm/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ filter_presets: allPresets })
            });

            if (!response.ok) {
                throw new Error('Failed to save presets to backend');
            }

            const data = await response.json();
            if (data.success === false) {
                throw new Error(data.error || 'Failed to save presets to backend');
            }

            // Update local cache
            this._presetsCache = allPresets;

            // Update local settings state
            if (state?.global?.settings) {
                state.global.settings.filter_presets = allPresets;
            }

            return true;
        } catch (error) {
            console.error('Error saving presets to backend:', error);
            showToast('Failed to save presets to backend', {}, 'error');
            return false;
        }
    }

    /**
     * Save active preset name to localStorage
     * Note: This is UI state only, not persisted to backend
     */
    saveActivePreset() {
        const key = this.getActivePresetStorageKey();
        if (this.activePreset) {
            setStorageItem(key, this.activePreset);
        } else {
            removeStorageItem(key);
        }
    }

    /**
     * Restore active preset from localStorage
     * Note: This is UI state only, not synced from backend
     */
    restoreActivePreset() {
        const key = this.getActivePresetStorageKey();
        const savedPresetName = getStorageItem(key);

        if (savedPresetName) {
            // Verify the preset still exists
            const presets = this.loadPresets();
            const preset = presets.find(p => p.name === savedPresetName);
            if (preset) {
                this.activePreset = savedPresetName;
            } else {
                // Preset no longer exists, clear the saved value
                this.activePreset = null;
                this.saveActivePreset();
            }
        }
    }

    /**
     * Migrate presets from localStorage to backend settings
     */
    async migratePresetsFromLocalStorage() {
        const legacyKey = this.getPresetsStorageKey();
        const legacyPresets = getStorageItem(legacyKey);
        
        if (!legacyPresets || !Array.isArray(legacyPresets) || legacyPresets.length === 0) {
            return false;
        }

        // Check if we already have presets in backend for this page
        const allPresets = this.getPresetsFromSettings();
        if (allPresets[this.currentPage] && allPresets[this.currentPage].length > 0) {
            // Already migrated, clear localStorage
            removeStorageItem(legacyKey);
            return false;
        }

        // Migrate to backend
        const validPresets = legacyPresets.filter(preset => {
            if (!preset || typeof preset !== 'object') return false;
            if (!preset.name || typeof preset.name !== 'string') return false;
            if (!preset.filters || typeof preset.filters !== 'object') return false;
            return true;
        });

        if (validPresets.length > 0) {
            allPresets[this.currentPage] = validPresets;
            const success = await this.savePresetsToBackend(allPresets);
            if (success) {
                removeStorageItem(legacyKey);
                console.log(`Migrated ${validPresets.length} presets from localStorage to backend`);
            }
            return success;
        }

        return false;
    }

    loadPresets() {
        // Get presets from settings
        const allPresets = this.getPresetsFromSettings();
        let presets = allPresets[this.currentPage];

        // Fallback to localStorage if no presets in settings (migration)
        if (!presets) {
            const legacyKey = this.getPresetsStorageKey();
            presets = getStorageItem(legacyKey);
            
            // Trigger async migration
            if (presets && Array.isArray(presets) && presets.length > 0) {
                this.migratePresetsFromLocalStorage();
            }
        }

        if (!presets) {
            return [];
        }

        if (!Array.isArray(presets)) {
            console.warn('Invalid presets data format: expected array');
            return [];
        }

        const validPresets = presets.filter(preset => {
            if (!preset || typeof preset !== 'object') return false;
            if (!preset.name || typeof preset.name !== 'string') return false;
            if (!preset.filters || typeof preset.filters !== 'object') return false;
            return true;
        });



        return validPresets;
    }



    /**
     * Resolve base model patterns to actual available models
     * Supports exact matches and wildcard patterns (ending with *)
     *
     * @param {Array} patterns - Array of base model patterns
     * @param {AbortSignal} signal - Optional abort signal for cancellation
     * @returns {Promise<Array>} Resolved base model names
     */
    async resolveBaseModelPatterns(patterns, signal = null) {
        if (!patterns || patterns.length === 0) return [];

        const hasWildcards = patterns.some(p => p.endsWith('*'));

        try {
            const fetchOptions = signal ? { signal } : {};
            const response = await fetch(`/api/lm/${this.currentPage}/base-models`, fetchOptions);

            if (!response.ok) throw new Error('Failed to fetch base models');

            const data = await response.json();
            if (!data.success || !Array.isArray(data.base_models)) {
                const nonWildcards = patterns.filter(p => !p.endsWith('*'));
                if (hasWildcards && nonWildcards.length === 0) {
                    return [EMPTY_WILDCARD_MARKER];
                }
                return nonWildcards;
            }

            const availableModels = data.base_models.map(m => m.name);
            const resolvedModels = [];

            for (const pattern of patterns) {
                if (pattern.endsWith('*')) {
                    const prefix = pattern.slice(0, -1);
                    const matches = availableModels.filter(model =>
                        model.startsWith(prefix)
                    );
                    resolvedModels.push(...matches);
                } else {
                    if (availableModels.includes(pattern)) {
                        resolvedModels.push(pattern);
                    }
                }
            }

            const uniqueModels = [...new Set(resolvedModels)];

            if (hasWildcards && uniqueModels.length === 0) {
                return [EMPTY_WILDCARD_MARKER];
            }

            return uniqueModels;
        } catch (error) {
            // Rethrow abort errors so they can be handled properly
            if (error.name === 'AbortError') {
                throw error;
            }
            console.warn('Error resolving base model patterns:', error);
            const nonWildcards = patterns.filter(p => !p.endsWith('*'));
            if (hasWildcards && nonWildcards.length === 0) {
                return [EMPTY_WILDCARD_MARKER];
            }
            return nonWildcards;
        }
    }

    /**
     * Check if the base model filter represents an empty wildcard result
     */
    hasEmptyWildcardResult() {
        const filters = this.filterManager?.filters;
        return filters?.baseModel?.length === 1 &&
               filters.baseModel[0] === EMPTY_WILDCARD_MARKER;
    }

    async savePresets(presets) {
        const allPresets = this.getPresetsFromSettings();
        allPresets[this.currentPage] = presets;
        await this.savePresetsToBackend(allPresets);
    }

    validatePresetName(name) {
        if (!name || !name.trim()) {
            return { valid: false, message: translate('toast.error.presetNameEmpty', {}, 'Preset name cannot be empty') };
        }

        const trimmedName = name.trim();

        if (trimmedName.length > MAX_PRESET_NAME_LENGTH) {
            return {
                valid: false,
                message: translate('toast.error.presetNameTooLong', { max: MAX_PRESET_NAME_LENGTH }, `Preset name must be ${MAX_PRESET_NAME_LENGTH} characters or less`)
            };
        }

        const htmlSpecialChars = /[<>'&]/;
        if (htmlSpecialChars.test(trimmedName)) {
            return { valid: false, message: translate('toast.error.presetNameInvalidChars', {}, 'Preset name contains invalid characters') };
        }

        const controlChars = /[\x00-\x1F\x7F-\x9F]/;
        if (controlChars.test(trimmedName)) {
            return { valid: false, message: translate('toast.error.presetNameInvalidChars', {}, 'Preset name contains invalid characters') };
        }

        return { valid: true, name: trimmedName };
    }

    async createPreset(name, options = {}) {
        const validation = this.validatePresetName(name);
        if (!validation.valid) {
            showToast(validation.message, {}, 'error');
            return false;
        }

        const trimmedName = validation.name;
        let presets = this.loadPresets();

        const existingIndex = presets.findIndex(p => p.name.toLowerCase() === trimmedName.toLowerCase());
        const isDuplicate = existingIndex !== -1;

        if (isDuplicate) {
            if (options.overwrite) {
                presets[existingIndex] = {
                    name: trimmedName,
                    filters: this.filterManager.cloneFilters(),
                    createdAt: Date.now()
                };
                await this.savePresets(presets);
                this.renderPresets();
                showToast(
                    translate('toast.presets.overwritten', { name: trimmedName }, `Preset "${trimmedName}" overwritten`),
                    {},
                    'success'
                );
                return true;
            } else {
                const confirmMsg = translate('header.filter.presetOverwriteConfirm', { name: trimmedName }, `Preset "${trimmedName}" already exists. Overwrite?`);
                if (confirm(confirmMsg)) {
                    return this.createPreset(name, { overwrite: true });
                }
                return false;
            }
        }

        if (presets.length >= MAX_PRESETS_COUNT) {
            showToast(
                translate('toast.error.maxPresetsReached', { max: MAX_PRESETS_COUNT }, `Maximum ${MAX_PRESETS_COUNT} presets allowed. Delete one to add more.`),
                {},
                'error'
            );
            return false;
        }

        const preset = {
            name: trimmedName,
            filters: this.filterManager.cloneFilters(),
            createdAt: Date.now()
        };

        presets.push(preset);
        await this.savePresets(presets);
        
        // Auto-activate the newly created preset
        this.activePreset = trimmedName;
        this.saveActivePreset();
        
        this.renderPresets();
        showToast(
            translate('toast.presets.created', { name: trimmedName }, `Preset "${trimmedName}" created`),
            {},
            'success'
        );
        return true;
    }

    async deletePreset(name) {
        try {
            let presets = this.loadPresets();
            const filtered = presets.filter(p => p.name !== name);

            if (filtered.length === 0) {
                const allPresets = this.getPresetsFromSettings();
                delete allPresets[this.currentPage];
                await this.savePresetsToBackend(allPresets);
            } else {
                await this.savePresets(filtered);
            }

            if (this.activePreset === name) {
                this.activePreset = null;
                this.saveActivePreset();
            }

            this.renderPresets();
            showToast(
                translate('toast.presets.deleted', { name }, `Preset "${name}" deleted`),
                {},
                'success'
            );
        } catch (error) {
            console.error('Error deleting preset:', error);
            showToast(translate('toast.error.deletePresetFailed', {}, 'Failed to delete preset'), {}, 'error');
        }
    }

    /**
     * Apply a preset with race condition protection
     * Cancels any pending preset application before starting a new one
     */
    async applyPreset(name) {
        // Cancel any pending preset application
        if (this.applyPresetAbortController) {
            this.applyPresetAbortController.abort();
        }
        this.applyPresetAbortController = new AbortController();
        const signal = this.applyPresetAbortController.signal;
        const requestId = ++this.applyPresetRequestId;

        try {
            const presets = this.loadPresets();
            const preset = presets.find(p => p.name === name);

            if (!preset) {
                showToast(translate('toast.error.presetNotFound', {}, 'Preset not found'), {}, 'error');
                return;
            }

            if (!preset.filters || typeof preset.filters !== 'object') {
                showToast(translate('toast.error.invalidPreset', {}, 'Invalid preset data'), {}, 'error');
                return;
            }

            // Check if aborted before expensive operations
            if (signal.aborted) return;

            // Resolve base model patterns (supports wildcards for default presets)
            const resolvedBaseModels = await this.resolveBaseModelPatterns(
                preset.filters.baseModel,
                signal
            );

            // Check if request is still valid (another preset may have been selected)
            if (requestId !== this.applyPresetRequestId) return;
            if (signal.aborted) return;

            // Set active preset AFTER successful resolution
            this.activePreset = name;
            this.saveActivePreset();

            // Apply the preset filters with resolved base models
            this.filterManager.filters = this.filterManager.initializeFilters({
                ...preset.filters,
                baseModel: resolvedBaseModels
            });

            // Update state
            const { getCurrentPageState } = await import('../state/index.js');
            const pageState = getCurrentPageState();
            pageState.filters = this.filterManager.cloneFilters();

            // If tags haven't been loaded yet, load them first
            if (!this.filterManager.tagsLoaded) {
                await this.filterManager.loadTopTags();
                this.filterManager.tagsLoaded = true;
            }

            // Check again after async operation
            if (requestId !== this.applyPresetRequestId) return;

            // Update UI
            this.filterManager.updateTagSelections();
            this.filterManager.updateActiveFiltersCount();
            this.renderPresets();

            // Apply filters (pass true for isPresetApply so it doesn't clear activePreset)
            await this.filterManager.applyFilters(false, true);

            showToast(
                translate('toast.presets.applied', { name }, `Preset "${name}" applied`),
                {},
                'success'
            );
        } catch (error) {
            // Silently handle abort errors
            if (error.name === 'AbortError') return;

            console.error('Error applying preset:', error);
            showToast(translate('toast.error.applyPresetFailed', {}, 'Failed to apply preset'), {}, 'error');
        }
    }

    hasUserCreatedPresets() {
        // Check in settings first
        const allPresets = this.getPresetsFromSettings();
        const presets = allPresets[this.currentPage];
        if (presets && Array.isArray(presets) && presets.length > 0) {
            return true;
        }
        
        // Fallback to localStorage
        const presetsKey = this.getPresetsStorageKey();
        const localPresets = getStorageItem(presetsKey);
        return Array.isArray(localPresets) && localPresets.length > 0;
    }



    /**
     * Check if the add button should be disabled
     * Returns true if no filters are active OR a preset is already active
     */
    shouldDisableAddButton() {
        return !this.filterManager?.hasActiveFilters() || this.activePreset !== null;
    }

    /**
     * Update the add button's disabled state
     */
    updateAddButtonState() {
        const addBtn = document.querySelector('.add-preset-btn');
        if (!addBtn) return;

        const shouldDisable = this.shouldDisableAddButton();

        if (shouldDisable) {
            addBtn.classList.add('disabled');
            // Update tooltip to explain why it's disabled
            if (this.activePreset) {
                addBtn.title = translate('header.filter.savePresetDisabledActive', {}, 'Cannot save: A preset is already active. Clear filters to save new preset.');
            } else {
                addBtn.title = translate('header.filter.savePresetDisabledNoFilters', {}, 'Select filters first to save as preset');
            }
        } else {
            addBtn.classList.remove('disabled');
            addBtn.title = translate('header.filter.savePreset', {}, 'Save current filters as a new preset');
        }
    }

    /**
     * Initiate two-step delete process
     */
    initiateDelete(presetName, deleteBtn) {
        // If already pending for this preset, execute the delete
        if (this.pendingDeletePreset === presetName) {
            this.cancelPendingDelete();
            this.deletePreset(presetName);
            return;
        }

        // Cancel any previous pending delete
        this.cancelPendingDelete();

        // Set up new pending delete
        this.pendingDeletePreset = presetName;
        deleteBtn.classList.add('confirm');
        deleteBtn.innerHTML = '<i class="fas fa-check"></i>';
        deleteBtn.title = translate('header.filter.presetDeleteConfirmClick', {}, 'Click again to confirm');

        // Auto-cancel after timeout
        this.pendingDeleteTimeout = setTimeout(() => {
            this.cancelPendingDelete();
        }, DELETE_CONFIRM_TIMEOUT);
    }

    /**
     * Cancel pending delete operation
     */
    cancelPendingDelete() {
        if (this.pendingDeleteTimeout) {
            clearTimeout(this.pendingDeleteTimeout);
            this.pendingDeleteTimeout = null;
        }

        if (this.pendingDeletePreset) {
            // Reset all delete buttons to normal state
            const deleteBtns = document.querySelectorAll('.preset-delete-btn.confirm');
            deleteBtns.forEach(btn => {
                btn.classList.remove('confirm');
                btn.innerHTML = '<i class="fas fa-times"></i>';
                btn.title = translate('header.filter.presetDeleteTooltip', {}, 'Delete preset');
            });
            this.pendingDeletePreset = null;
        }
    }

    /**
     * Show inline input for preset naming
     */
    showInlineNamingInput() {
        if (this.isInlineNamingActive) return;

        // Check if there are any active filters
        if (!this.filterManager?.hasActiveFilters()) {
            showToast(translate('toast.filters.noActiveFilters', {}, 'No active filters to save'), {}, 'info');
            return;
        }

        // Check max presets limit before showing input
        const presets = this.loadPresets();
        if (presets.length >= MAX_PRESETS_COUNT) {
            showToast(
                translate('toast.error.maxPresetsReached', { max: MAX_PRESETS_COUNT }, `Maximum ${MAX_PRESETS_COUNT} presets allowed. Delete one to add more.`),
                {},
                'error'
            );
            return;
        }

        this.isInlineNamingActive = true;

        const presetsContainer = document.getElementById('filterPresets');
        if (!presetsContainer) return;

        // Find the add button and hide it
        const addBtn = presetsContainer.querySelector('.add-preset-btn');
        if (addBtn) {
            addBtn.style.display = 'none';
        }

        // Create inline input container
        const inputContainer = document.createElement('div');
        inputContainer.className = 'preset-inline-input-container';
        inputContainer.innerHTML = `
            <input type="text"
                   class="preset-inline-input"
                   placeholder="${translate('header.filter.presetNamePlaceholder', {}, 'Preset name...')}"
                   maxlength="${MAX_PRESET_NAME_LENGTH}">
            <button class="preset-inline-btn save" title="${translate('common.actions.save', {}, 'Save')}">
                <i class="fas fa-check"></i>
            </button>
            <button class="preset-inline-btn cancel" title="${translate('common.actions.cancel', {}, 'Cancel')}">
                <i class="fas fa-times"></i>
            </button>
        `;

        presetsContainer.appendChild(inputContainer);

        const input = inputContainer.querySelector('.preset-inline-input');
        const saveBtn = inputContainer.querySelector('.preset-inline-btn.save');
        const cancelBtn = inputContainer.querySelector('.preset-inline-btn.cancel');

        // Focus input
        input.focus();

        // Handle save
        const handleSave = async () => {
            const name = input.value;
            if (await this.createPreset(name)) {
                this.hideInlineNamingInput();
            }
        };

        // Handle cancel
        const handleCancel = () => {
            this.hideInlineNamingInput();
        };

        // Event listeners
        saveBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            handleSave();
        });

        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            handleCancel();
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleSave();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                handleCancel();
            }
        });

        // Prevent clicks inside from bubbling
        inputContainer.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    /**
     * Hide inline input and restore add button
     */
    hideInlineNamingInput() {
        this.isInlineNamingActive = false;

        const presetsContainer = document.getElementById('filterPresets');
        if (!presetsContainer) return;

        // Remove input container
        const inputContainer = presetsContainer.querySelector('.preset-inline-input-container');
        if (inputContainer) {
            inputContainer.remove();
        }

        // Show add button
        const addBtn = presetsContainer.querySelector('.add-preset-btn');
        if (addBtn) {
            addBtn.style.display = '';
        }
    }

    renderPresets() {
        const presetsContainer = document.getElementById('filterPresets');
        if (!presetsContainer) return;

        // Cancel any pending delete when re-rendering
        this.cancelPendingDelete();
        this.isInlineNamingActive = false;

        const presets = this.loadPresets();
        presetsContainer.innerHTML = '';

        // Render existing presets
        presets.forEach(preset => {
            const presetEl = document.createElement('div');
            presetEl.className = 'filter-preset';

            const isActive = this.activePreset === preset.name;
            if (isActive) {
                presetEl.classList.add('active');
            }

            presetEl.addEventListener('click', (e) => {
                e.stopPropagation();
            });

            const presetName = document.createElement('span');
            presetName.className = 'preset-name';
            presetName.textContent = preset.name;
            presetName.title = translate('header.filter.presetClickTooltip', { name: preset.name }, `Click to apply preset "${preset.name}"`);

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'preset-delete-btn';
            deleteBtn.innerHTML = '<i class="fas fa-times"></i>';
            deleteBtn.title = translate('header.filter.presetDeleteTooltip', {}, 'Delete preset');

            // Apply preset on name click (toggle if already active)
            presetName.addEventListener('click', async (e) => {
                e.stopPropagation();
                this.cancelPendingDelete();

                if (this.activePreset === preset.name) {
                    await this.filterManager.clearFilters();
                } else {
                    await this.applyPreset(preset.name);
                }
            });

            // Two-step delete on delete button click
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.initiateDelete(preset.name, deleteBtn);
            });

            presetEl.appendChild(presetName);
            presetEl.appendChild(deleteBtn);
            presetsContainer.appendChild(presetEl);
        });

        // Add the "Add new preset" button (always shown, unified style)
        const addBtn = document.createElement('div');
        addBtn.className = 'filter-preset add-preset-btn';
        addBtn.innerHTML = `<i class="fas fa-plus"></i> ${translate('common.actions.add', {}, 'Add')}`;
        addBtn.title = translate('header.filter.savePreset', {}, 'Save current filters as a new preset');

        addBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.cancelPendingDelete();
            this.showInlineNamingInput();
        });

        presetsContainer.appendChild(addBtn);

        // Update add button state (handles disabled state based on filters)
        this.updateAddButtonState();
    }

    /**
     * Legacy method for backward compatibility
     * @deprecated Use showInlineNamingInput instead
     */
    showSavePresetDialog() {
        this.showInlineNamingInput();
    }
}
