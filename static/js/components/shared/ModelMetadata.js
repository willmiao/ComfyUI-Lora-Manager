/**
 * ModelMetadata.js
 * Handles model metadata editing functionality - General version
 */

import { BASE_MODEL_CATEGORIES, getMergedBaseModels } from '../../utils/constants.js';
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { translate } from '../../utils/i18nHelpers.js';

// ── Filename-based base model inference ──────────────────────────────────────
// Rules are ordered by specificity — first match wins for dedup.
// Each rule checks the filename (lowercased) for a regex pattern and suggests
// the associated base model values.

const BASE_MODEL_FILENAME_RULES = [
    { pattern: /flux\.?\s*2\s*klein/i, models: ['Flux.2 Klein 9B', 'Flux.2 Klein 9B-base', 'Flux.2 Klein 4B', 'Flux.2 Klein 4B-base'] },
    { pattern: /flux\.?\s*2/i, models: ['Flux.2 D', 'Flux.2 Klein 9B', 'Flux.2 Klein 4B'] },
    { pattern: /flux\.?\s*1\s*(dev|d)\b/i, models: ['Flux.1 D'] },
    { pattern: /flux\.?\s*1\s*(schnell|s)\b/i, models: ['Flux.1 S'] },
    { pattern: /flux/i, models: ['Flux.1 D', 'Flux.1 S', 'Flux.2 D'] },
    { pattern: /sdxl/i, models: ['SDXL 1.0', 'SDXL Lightning', 'SDXL Hyper'] },
    { pattern: /sd\s*1[._-\s]?5/i, models: ['SD 1.5'] },
    { pattern: /sd\s*1[._-\s]?4/i, models: ['SD 1.4'] },
    { pattern: /sd\s*1/i, models: ['SD 1.5', 'SD 1.4', 'SD 1.5 LCM', 'SD 1.5 Hyper'] },
    { pattern: /sd\s*3[._-\s]?5/i, models: ['SD 3.5', 'SD 3.5 Medium', 'SD 3.5 Large', 'SD 3.5 Large Turbo'] },
    { pattern: /sd\s*3/i, models: ['SD 3', 'SD 3.5'] },
    { pattern: /wan\s*\.?\s*video/i, models: ['Wan Video', 'Wan Video 1.3B t2v', 'Wan Video 14B t2v', 'Wan Video 14B i2v 480p', 'Wan Video 14B i2v 720p'] },
    { pattern: /hunyuan\s*\.?\s*video/i, models: ['Hunyuan Video'] },
    { pattern: /ltxv/i, models: ['LTXV', 'LTXV2', 'LTXV 2.3'] },
    { pattern: /cogvideo/i, models: ['CogVideoX'] },
    { pattern: /pony/i, models: ['Pony', 'Pony V7'] },
    { pattern: /illustrious/i, models: ['Illustrious'] },
    { pattern: /noobai/i, models: ['NoobAI'] },
    { pattern: /pixart/i, models: ['PixArt a', 'PixArt E'] },
    { pattern: /aura\s*\.?\s*flow/i, models: ['AuraFlow'] },
    { pattern: /kolors/i, models: ['Kolors'] },
    { pattern: /hunyuan\s*1/i, models: ['Hunyuan 1'] },
    { pattern: /lumina/i, models: ['Lumina'] },
    { pattern: /hidream/i, models: ['HiDream'] },
    { pattern: /qwen/i, models: ['Qwen'] },
    { pattern: /chroma/i, models: ['Chroma'] },
    { pattern: /anima/i, models: ['Anima'] },
    { pattern: /sd\s*2[._-\s]?[01]/i, models: ['SD 2.0', 'SD 2.1'] },
    { pattern: /mochi/i, models: ['Mochi'] },
    { pattern: /svd/i, models: ['SVD'] },
    { pattern: /zimage/i, models: ['ZImageTurbo', 'ZImageBase'] },
    { pattern: /nucleus/i, models: ['Nucleus'] },
    { pattern: /krea/i, models: ['Flux.1 Krea', 'Krea 2'] },
    { pattern: /ernie/i, models: ['Ernie', 'Ernie Turbo'] },
];

/**
 * Infer likely base model(s) from a filename + model name string.
 * Returns a deduplicated array in match-priority order.
 * @param {string} filename
 * @returns {string[]}
 */
function inferBaseModelsFromFilename(filename) {
    if (!filename || typeof filename !== 'string') return [];
    const seen = new Set();
    const results = [];
    for (const rule of BASE_MODEL_FILENAME_RULES) {
        if (rule.pattern.test(filename)) {
            for (const model of rule.models) {
                if (!seen.has(model)) {
                    seen.add(model);
                    results.push(model);
                }
            }
        }
    }
    return results;
}

/**
 * Resolve the active file path for the currently open model modal.
 * Falls back to the provided value when DOM state has not been initialised yet.
 * @param {string} fallback - Optional fallback path
 * @returns {string}
 */
function getActiveModalFilePath(fallback = '') {
    const modalElement = document.getElementById('modelModal');
    if (modalElement && modalElement.dataset && modalElement.dataset.filePath) {
        return modalElement.dataset.filePath;
    }

    const fileNameContent = document.querySelector('.file-name-content');
    if (fileNameContent && fileNameContent.dataset && fileNameContent.dataset.filePath) {
        return fileNameContent.dataset.filePath;
    }

    return fallback;
}

/**
 * Update all modal controls that cache the current model file path.
 * Keeps metadata interactions in sync after renames or moves.
 * @param {string} newFilePath - Updated model file path
 */
function updateModalFilePathReferences(newFilePath) {
    if (!newFilePath) {
        return;
    }

    const modalElement = document.getElementById('modelModal');
    if (!modalElement) {
        return;
    }

    modalElement.dataset.filePath = newFilePath;
    modalElement.setAttribute('data-file-path', newFilePath);

    const scopedQuery = (selector) => modalElement.querySelector(selector);
    const scopedQueryAll = (selector) => modalElement.querySelectorAll(selector);

    const modelNameContent = scopedQuery('.model-name-content');
    if (modelNameContent && modelNameContent.dataset) {
        modelNameContent.dataset.filePath = newFilePath;
        modelNameContent.setAttribute('data-file-path', newFilePath);
    }

    const baseModelContent = scopedQuery('.base-model-content');
    if (baseModelContent && baseModelContent.dataset) {
        baseModelContent.dataset.filePath = newFilePath;
        baseModelContent.setAttribute('data-file-path', newFilePath);
    }

    const fileNameContent = scopedQuery('.file-name-content');
    if (fileNameContent && fileNameContent.dataset) {
        fileNameContent.dataset.filePath = newFilePath;
        fileNameContent.setAttribute('data-file-path', newFilePath);
    }

    const versionNameContent = scopedQuery('.version-name-content');
    if (versionNameContent && versionNameContent.dataset) {
        versionNameContent.dataset.filePath = newFilePath;
        versionNameContent.setAttribute('data-file-path', newFilePath);
    }

    const editTagsBtn = scopedQuery('.edit-tags-btn');
    if (editTagsBtn) {
        editTagsBtn.dataset.filePath = newFilePath;
        editTagsBtn.setAttribute('data-file-path', newFilePath);
    }

    const editTriggerWordsBtn = scopedQuery('.edit-trigger-words-btn');
    if (editTriggerWordsBtn) {
        editTriggerWordsBtn.dataset.filePath = newFilePath;
        editTriggerWordsBtn.setAttribute('data-file-path', newFilePath);
    }

    scopedQueryAll('[data-action="open-file-location"]').forEach((el) => {
        el.dataset.filepath = newFilePath;
        el.setAttribute('data-filepath', newFilePath);
    });

    scopedQueryAll('[data-file-path]').forEach((el) => {
        el.dataset.filePath = newFilePath;
        el.setAttribute('data-file-path', newFilePath);
    });

    scopedQueryAll('[data-filepath]').forEach((el) => {
        el.dataset.filepath = newFilePath;
        el.setAttribute('data-filepath', newFilePath);
    });
}

/**
 * Set up model name editing functionality
 * @param {string} filePath - File path
 */
export function setupModelNameEditing(filePath) {
    const modelNameContent = document.querySelector('.model-name-content');
    const editBtn = document.querySelector('.edit-model-name-btn');
    
    if (!modelNameContent || !editBtn) return;
    
    // Store the file path in a data attribute for later use
    modelNameContent.dataset.filePath = filePath;
    
    // Show edit button on hover
    const modelNameHeader = document.querySelector('.model-name-header');
    modelNameHeader.addEventListener('mouseenter', () => {
        editBtn.classList.add('visible');
    });
    
    modelNameHeader.addEventListener('mouseleave', () => {
        if (!modelNameHeader.classList.contains('editing')) {
            editBtn.classList.remove('visible');
        }
    });
    
    // Handle edit button click
    editBtn.addEventListener('click', () => {
        modelNameHeader.classList.add('editing');
        modelNameContent.setAttribute('contenteditable', 'true');
        // Store original value for comparison later
        modelNameContent.dataset.originalValue = modelNameContent.textContent.trim();
        modelNameContent.focus();
        
        // Place cursor at the end
        const range = document.createRange();
        const sel = window.getSelection();
        if (modelNameContent.childNodes.length > 0) {
            range.setStart(modelNameContent.childNodes[0], modelNameContent.textContent.length);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
        }
        
        editBtn.classList.add('visible');
    });
    
    // Handle keyboard events in edit mode
    modelNameContent.addEventListener('keydown', function(e) {
        if (!this.getAttribute('contenteditable')) return;
        
        if (e.key === 'Enter') {
            e.preventDefault();
            this.blur(); // Trigger save on Enter
        } else if (e.key === 'Escape') {
            e.preventDefault();
            // Restore original value
            this.textContent = this.dataset.originalValue;
            exitEditMode();
        }
    });
    
    // Limit model name length
    modelNameContent.addEventListener('input', function() {
        if (!this.getAttribute('contenteditable')) return;
        
        // Limit model name length
        if (this.textContent.length > 100) {
            this.textContent = this.textContent.substring(0, 100);
            // Place cursor at the end
            const range = document.createRange();
            const sel = window.getSelection();
            range.setStart(this.childNodes[0], 100);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
            
            showToast('toast.models.nameTooLong', {}, 'warning');
        }
    });
    
    // Handle focus out - save changes
    modelNameContent.addEventListener('blur', async function() {
        if (!this.getAttribute('contenteditable')) return;
        
        const newModelName = this.textContent.trim();
        const originalValue = this.dataset.originalValue;
        
        // Basic validation
        if (!newModelName) {
            // Restore original value if empty
            this.textContent = originalValue;
            showToast('toast.models.nameCannotBeEmpty', {}, 'error');
            exitEditMode();
            return;
        }
        
        if (newModelName === originalValue) {
            // No changes, just exit edit mode
            exitEditMode();
            return;
        }
        
        try {
            // Resolve current file path from modal state
            const filePath = getActiveModalFilePath(this.dataset.filePath);

            await getModelApiClient().saveModelMetadata(filePath, { model_name: newModelName });
            
            showToast('toast.models.nameUpdatedSuccessfully', {}, 'success');
        } catch (error) {
            console.error('Error updating model name:', error);
            this.textContent = originalValue; // Restore original model name
            showToast('toast.models.nameUpdateFailed', {}, 'error');
        } finally {
            exitEditMode();
        }
    });
    
    function exitEditMode() {
        modelNameContent.removeAttribute('contenteditable');
        modelNameHeader.classList.remove('editing');
        editBtn.classList.remove('visible');
    }
}

/**
 * Set up base model editing functionality with searchable dropdown
 * Shows filename-inferred suggestions at the top, supports keyboard navigation,
 * and allows typing custom values.
 * @param {string} filePath - File path
 */
export function setupBaseModelEditing(filePath) {
    const baseModelContent = document.querySelector('.base-model-content');
    const editBtn = document.querySelector('.edit-base-model-btn');
    
    if (!baseModelContent || !editBtn) return;
    
    // Store the file path in a data attribute for later use
    baseModelContent.dataset.filePath = filePath;
    
    // Show edit button on hover
    const baseModelDisplay = document.querySelector('.base-model-display');
    baseModelDisplay.addEventListener('mouseenter', () => {
        editBtn.classList.add('visible');
    });
    
    baseModelDisplay.addEventListener('mouseleave', () => {
        if (!baseModelDisplay.classList.contains('editing')) {
            editBtn.classList.remove('visible');
        }
    });
    
    // Handle edit button click
    editBtn.addEventListener('click', () => {
        baseModelDisplay.classList.add('editing');
        
        // Store the original value to check for changes later
        const originalValue = baseModelContent.textContent.trim();
        
        // ── Build the full option list ────────────────────────────────────────
        const allModels = []; // { value, label, category }
        const categorizedModels = new Set();
        
        Object.entries(BASE_MODEL_CATEGORIES).forEach(([category, models]) => {
            models.forEach(model => {
                allModels.push({ value: model, label: model, category });
                categorizedModels.add(model);
            });
        });
        
        const mergedModels = getMergedBaseModels();
        const uncategorizedModels = mergedModels.filter(model => !categorizedModels.has(model));
        if (uncategorizedModels.length > 0) {
            uncategorizedModels.forEach(model => {
                allModels.push({ value: model, label: model, category: 'Other (API)' });
            });
        }
        
        // ── Filename-based inference ──────────────────────────────────────────
        const fileName = (document.querySelector('.file-name-content')?.textContent || '') + ' ' +
                         (document.querySelector('.model-name-content')?.textContent || '');
        const inferredModels = inferBaseModelsFromFilename(fileName);
        const inferredSet = new Set(inferredModels);
        
        // ── Build search widget DOM ───────────────────────────────────────────
        const wrapper = document.createElement('div');
        wrapper.className = 'base-model-search-wrapper';
        
        // Search input row
        const inputWrapper = document.createElement('div');
        inputWrapper.className = 'base-model-search-input-wrapper';
        const searchIcon = document.createElement('i');
        searchIcon.className = 'fas fa-search search-icon';
        searchIcon.setAttribute('aria-hidden', 'true');
        inputWrapper.appendChild(searchIcon);
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'base-model-search-input';
        searchInput.placeholder = translate('modals.model.metadata.baseModelSearchPlaceholder', {}, 'Search base model…');
        searchInput.autocomplete = 'off';
        searchInput.spellcheck = false;
        inputWrapper.appendChild(searchInput);
        wrapper.appendChild(inputWrapper);
        
        // Dropdown list
        const dropdown = document.createElement('div');
        dropdown.className = 'base-model-dropdown';
        wrapper.appendChild(dropdown);
        
        // ── Render ────────────────────────────────────────────────────────────
        function renderDropdown(filterText) {
            const lowerFilter = (filterText || '').toLowerCase().trim();
            dropdown.innerHTML = '';
            let hasVisibleItems = false;
            const fragment = document.createDocumentFragment();
            
            // 1. Suggested section (filename-inferred, filtered by search)
            let suggestedToShow = inferredModels;
            if (lowerFilter) {
                suggestedToShow = inferredModels.filter(m =>
                    m.toLowerCase().includes(lowerFilter)
                );
            }
            
            if (suggestedToShow.length > 0) {
                const section = document.createElement('div');
                section.className = 'base-model-dropdown-section';
                
                const header = document.createElement('div');
                header.className = 'base-model-dropdown-header suggested-header';
                header.innerHTML = '<i class="fas fa-star" aria-hidden="true"></i> ' +
                    translate('modals.model.metadata.baseModelSuggested', {}, 'Suggested');
                section.appendChild(header);
                
                suggestedToShow.forEach(model => {
                    const item = document.createElement('div');
                    item.className = 'base-model-dropdown-item';
                    if (model === originalValue) item.classList.add('selected');
                    item.dataset.value = model;
                    item.textContent = model;
                    section.appendChild(item);
                    hasVisibleItems = true;
                });
                
                fragment.appendChild(section);
            }
            
            // 2. Categorized options (deduplicated against suggestions)
            const categoryMap = {};
            allModels.forEach(m => {
                if (inferredSet.has(m.value)) return; // already shown in Suggested
                if (lowerFilter && !m.label.toLowerCase().includes(lowerFilter)) return;
                if (!categoryMap[m.category]) categoryMap[m.category] = [];
                categoryMap[m.category].push(m);
            });
            
            Object.entries(categoryMap).forEach(([category, items]) => {
                if (items.length === 0) return;
                const section = document.createElement('div');
                section.className = 'base-model-dropdown-section';
                
                const header = document.createElement('div');
                header.className = 'base-model-dropdown-header';
                header.textContent = category;
                section.appendChild(header);
                
                items.forEach(m => {
                    const item = document.createElement('div');
                    item.className = 'base-model-dropdown-item';
                    if (m.value === originalValue) item.classList.add('selected');
                    item.dataset.value = m.value;
                    item.textContent = m.label;
                    section.appendChild(item);
                    hasVisibleItems = true;
                });
                
                fragment.appendChild(section);
            });
            
            // 3. Empty state
            if (!hasVisibleItems) {
                const empty = document.createElement('div');
                empty.className = 'base-model-dropdown-empty';
                empty.textContent = translate('modals.model.metadata.baseModelNoMatch', {}, 'No matching base models');
                fragment.appendChild(empty);
            }
            
            dropdown.appendChild(fragment);
            
            // Scroll the selected item into view
            const selected = dropdown.querySelector('.base-model-dropdown-item.selected');
            if (selected) {
                selected.scrollIntoView({ block: 'nearest' });
            }
        }
        
        // Initial render — show everything
        renderDropdown('');
        
        // ── Events ────────────────────────────────────────────────────────────
        let filterTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(filterTimeout);
            filterTimeout = setTimeout(() => renderDropdown(searchInput.value), 50);
        });
        
        // Click to select
        dropdown.addEventListener('click', (e) => {
            const item = e.target.closest('.base-model-dropdown-item');
            if (!item) return;
            baseModelContent.textContent = item.dataset.value;
            cleanup();
            const finalValue = baseModelContent.textContent.trim();
            if (finalValue !== originalValue) {
                saveBaseModel(
                    getActiveModalFilePath(baseModelContent.dataset.filePath),
                    originalValue
                );
            }
        });
        
        // Replace content with search widget
        baseModelContent.style.display = 'none';
        editBtn.style.display = 'none';
        baseModelDisplay.insertBefore(wrapper, editBtn);
        searchInput.focus();
        
        // ── Cleanup ───────────────────────────────────────────────────────────
        function cleanup() {
            if (wrapper.parentNode === baseModelDisplay) {
                baseModelDisplay.removeChild(wrapper);
            }
            baseModelContent.style.display = '';
            editBtn.style.display = '';
            baseModelDisplay.classList.remove('editing');
            document.removeEventListener('click', outsideClickHandler);
        }
        
        // Outside click → save typed/custom value if any
        const outsideClickHandler = function(e) {
            if (wrapper.contains(e.target)) return;
            
            // If user typed a custom value (not just empty), apply it
            const typedValue = searchInput.value.trim();
            if (typedValue) {
                baseModelContent.textContent = typedValue;
            }
            cleanup();
            const finalValue = baseModelContent.textContent.trim();
            if (finalValue !== originalValue) {
                saveBaseModel(
                    getActiveModalFilePath(baseModelContent.dataset.filePath),
                    originalValue
                );
            }
        };
        
        // Defer listener to avoid the opening click itself
        setTimeout(() => {
            document.addEventListener('click', outsideClickHandler);
        }, 0);
        
        // Keyboard navigation
        searchInput.addEventListener('keydown', function onKeydown(e) {
            const items = Array.from(dropdown.querySelectorAll('.base-model-dropdown-item'));
            const activeIdx = items.findIndex(el => el.classList.contains('active'));
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                items.forEach(el => el.classList.remove('active'));
                const next = Math.min(activeIdx + 1, items.length - 1);
                if (items[next]) {
                    items[next].classList.add('active');
                    items[next].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                items.forEach(el => el.classList.remove('active'));
                const prev = Math.max(activeIdx - 1, 0);
                if (items[prev]) {
                    items[prev].classList.add('active');
                    items[prev].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const activeItem = items.find(el => el.classList.contains('active'));
                if (activeItem) {
                    activeItem.click();
                } else if (searchInput.value.trim()) {
                    // Custom value typed
                    baseModelContent.textContent = searchInput.value.trim();
                    cleanup();
                    const finalValue = baseModelContent.textContent.trim();
                    if (finalValue !== originalValue) {
                        saveBaseModel(
                            getActiveModalFilePath(baseModelContent.dataset.filePath),
                            originalValue
                        );
                    }
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                baseModelContent.textContent = originalValue;
                cleanup();
            }
        });
    });
}

/**
 * Save base model
 * @param {string} filePath - File path
 * @param {string} originalValue - Original value (for comparison)
 */
async function saveBaseModel(filePath, originalValue) {
    const baseModelElement = document.querySelector('.base-model-content');
    const newBaseModel = baseModelElement.textContent.trim();
    
    // Only save if the value has actually changed
    if (newBaseModel === originalValue) {
        return; // No change, no need to save
    }

    const resolvedPath = getActiveModalFilePath(filePath);
    if (!resolvedPath) {
        return;
    }
    
    try {
        await getModelApiClient().saveModelMetadata(resolvedPath, { base_model: newBaseModel });
        
        showToast('toast.models.baseModelUpdated', {}, 'success');
    } catch (error) {
        showToast('toast.models.baseModelUpdateFailed', {}, 'error');
    }
}

/**
 * Set up file name editing functionality
 * @param {string} filePath - File path
 */
export function setupFileNameEditing(filePath) {
    const fileNameContent = document.querySelector('.file-name-content');
    const editBtn = document.querySelector('.edit-file-name-btn');
    
    if (!fileNameContent || !editBtn) return;
    
    // Store the original file path
    fileNameContent.dataset.filePath = filePath;
    
    // Show edit button on hover
    const fileNameWrapper = document.querySelector('.file-name-wrapper');
    fileNameWrapper.addEventListener('mouseenter', () => {
        editBtn.classList.add('visible');
    });
    
    fileNameWrapper.addEventListener('mouseleave', () => {
        if (!fileNameWrapper.classList.contains('editing')) {
            editBtn.classList.remove('visible');
        }
    });
    
    // Handle edit button click
    editBtn.addEventListener('click', () => {
        fileNameWrapper.classList.add('editing');
        fileNameContent.setAttribute('contenteditable', 'true');
        fileNameContent.focus();
        
        // Store original value for comparison later
        fileNameContent.dataset.originalValue = fileNameContent.textContent.trim();
        
        // Place cursor at the end
        const range = document.createRange();
        const sel = window.getSelection();
        range.selectNodeContents(fileNameContent);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
        
        editBtn.classList.add('visible');
    });
    
    // Handle keyboard events in edit mode
    fileNameContent.addEventListener('keydown', function(e) {
        if (!this.getAttribute('contenteditable')) return;
        
        if (e.key === 'Enter') {
            e.preventDefault();
            this.blur(); // Trigger save on Enter
        } else if (e.key === 'Escape') {
            e.preventDefault();
            // Restore original value
            this.textContent = this.dataset.originalValue;
            exitEditMode();
        }
    });
    
    // Handle input validation
    fileNameContent.addEventListener('input', function() {
        if (!this.getAttribute('contenteditable')) return;
        
        // Replace invalid characters for filenames
        const invalidChars = /[\\/:*?"<>|]/g;
        if (invalidChars.test(this.textContent)) {
            const cursorPos = window.getSelection().getRangeAt(0).startOffset;
            this.textContent = this.textContent.replace(invalidChars, '');
            
            // Restore cursor position
            const range = document.createRange();
            const sel = window.getSelection();
            const newPos = Math.min(cursorPos, this.textContent.length);
            
            if (this.firstChild) {
                range.setStart(this.firstChild, newPos);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            }
            
            showToast('toast.models.invalidCharactersRemoved', {}, 'warning');
        }
    });
    
    // Handle focus out - save changes
    fileNameContent.addEventListener('blur', async function() {
        if (!this.getAttribute('contenteditable')) return;
        
        const newFileName = this.textContent.trim();
        const originalValue = this.dataset.originalValue;
        
        // Basic validation
        if (!newFileName) {
            // Restore original value if empty
            this.textContent = originalValue;
            showToast('toast.models.filenameCannotBeEmpty', {}, 'error');
            exitEditMode();
            return;
        }
        
        if (newFileName === originalValue) {
            // No changes, just exit edit mode
            exitEditMode();
            return;
        }
        
        try {
            const currentFilePath = getActiveModalFilePath(this.dataset.filePath);
            const result = await getModelApiClient().renameModelFile(currentFilePath, newFileName);

            if (result && result.success && result.new_file_path) {
                const newFilePath = result.new_file_path;
                this.dataset.filePath = newFilePath;
                this.setAttribute('data-file-path', newFilePath);

                const modalElement = document.getElementById('modelModal');
                if (modalElement) {
                    modalElement.dataset.filePath = newFilePath;
                    modalElement.setAttribute('data-file-path', newFilePath);
                }

                updateModalFilePathReferences(newFilePath);
            }
        } catch (error) {
            console.error('Error renaming file:', error);
            this.textContent = originalValue; // Restore original file name
            showToast('toast.models.renameFailed', { message: error.message }, 'error');
        } finally {
            exitEditMode();
        }
    });
    
    function exitEditMode() {
        fileNameContent.removeAttribute('contenteditable');
        fileNameWrapper.classList.remove('editing');
        editBtn.classList.remove('visible');
    }
}

/**
 * Set up version name editing functionality
 * @param {string} filePath - File path
 */
export function setupVersionNameEditing(filePath) {
    const versionNameContent = document.querySelector('.version-name-content');
    const editBtn = document.querySelector('.edit-version-name-btn');

    if (!versionNameContent || !editBtn) return;

    // Store the file path in a data attribute for later use
    versionNameContent.dataset.filePath = filePath;

    // Show edit button on hover
    const versionNameWrapper = document.querySelector('.version-name-wrapper');
    versionNameWrapper.addEventListener('mouseenter', () => {
        editBtn.classList.add('visible');
    });

    versionNameWrapper.addEventListener('mouseleave', () => {
        if (!versionNameWrapper.classList.contains('editing')) {
            editBtn.classList.remove('visible');
        }
    });

    // Handle edit button click
    editBtn.addEventListener('click', () => {
        versionNameWrapper.classList.add('editing');
        versionNameContent.setAttribute('contenteditable', 'true');
        // Store original value for comparison later
        versionNameContent.dataset.originalValue = versionNameContent.textContent.trim();
        versionNameContent.focus();

        // Place cursor at the end
        const range = document.createRange();
        const sel = window.getSelection();
        if (versionNameContent.childNodes.length > 0) {
            range.setStart(versionNameContent.childNodes[0], versionNameContent.textContent.length);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);
        }

        editBtn.classList.add('visible');
    });

    // Handle keyboard events in edit mode
    versionNameContent.addEventListener('keydown', function(e) {
        if (!this.getAttribute('contenteditable')) return;

        if (e.key === 'Enter') {
            e.preventDefault();
            this.blur(); // Trigger save on Enter
        } else if (e.key === 'Escape') {
            e.preventDefault();
            // Restore original value
            this.textContent = this.dataset.originalValue;
            exitEditMode();
        }
    });

    // Limit version name length
    versionNameContent.addEventListener('input', function() {
        if (!this.getAttribute('contenteditable')) return;

        if (this.textContent.length > 100) {
            this.textContent = this.textContent.substring(0, 100);
            // Place cursor at the end
            const range = document.createRange();
            const sel = window.getSelection();
            range.setStart(this.childNodes[0], 100);
            range.collapse(true);
            sel.removeAllRanges();
            sel.addRange(range);

            showToast('toast.models.nameTooLong', {}, 'warning');
        }
    });

    // Handle focus out - save changes
    versionNameContent.addEventListener('blur', async function() {
        if (!this.getAttribute('contenteditable')) return;

        const newVersionName = this.textContent.trim();
        const originalValue = this.dataset.originalValue;

        // Basic validation
        if (!newVersionName) {
            // Restore original value if empty
            this.textContent = originalValue;
            showToast('toast.models.nameCannotBeEmpty', {}, 'error');
            exitEditMode();
            return;
        }

        if (newVersionName === originalValue) {
            // No changes, just exit edit mode
            exitEditMode();
            return;
        }

        try {
            // Resolve current file path from modal state
            const filePath = getActiveModalFilePath(this.dataset.filePath);

            await getModelApiClient().saveModelMetadata(filePath, { civitai: { name: newVersionName } });

            showToast('toast.models.nameUpdatedSuccessfully', {}, 'success');
        } catch (error) {
            console.error('Error updating version name:', error);
            this.textContent = originalValue; // Restore original version name
            showToast('toast.models.nameUpdateFailed', {}, 'error');
        } finally {
            exitEditMode();
        }
    });

    function exitEditMode() {
        versionNameContent.removeAttribute('contenteditable');
        versionNameWrapper.classList.remove('editing');
        editBtn.classList.remove('visible');
    }
}
