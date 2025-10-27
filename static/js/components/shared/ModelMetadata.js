/**
 * ModelMetadata.js
 * Handles model metadata editing functionality - General version
 */

import { BASE_MODEL_CATEGORIES } from '../../utils/constants.js';
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';

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
    if (modalElement) {
        modalElement.dataset.filePath = newFilePath;
        modalElement.setAttribute('data-file-path', newFilePath);
    }

    const modelNameContent = document.querySelector('.model-name-content');
    if (modelNameContent && modelNameContent.dataset) {
        modelNameContent.dataset.filePath = newFilePath;
        modelNameContent.setAttribute('data-file-path', newFilePath);
    }

    const baseModelContent = document.querySelector('.base-model-content');
    if (baseModelContent && baseModelContent.dataset) {
        baseModelContent.dataset.filePath = newFilePath;
        baseModelContent.setAttribute('data-file-path', newFilePath);
    }

    const fileNameContent = document.querySelector('.file-name-content');
    if (fileNameContent && fileNameContent.dataset) {
        fileNameContent.dataset.filePath = newFilePath;
        fileNameContent.setAttribute('data-file-path', newFilePath);
    }

    const editTagsBtn = document.querySelector('.edit-tags-btn');
    if (editTagsBtn) {
        editTagsBtn.dataset.filePath = newFilePath;
        editTagsBtn.setAttribute('data-file-path', newFilePath);
    }

    const editTriggerWordsBtn = document.querySelector('.edit-trigger-words-btn');
    if (editTriggerWordsBtn) {
        editTriggerWordsBtn.dataset.filePath = newFilePath;
        editTriggerWordsBtn.setAttribute('data-file-path', newFilePath);
    }

    document.querySelectorAll('[data-action="open-file-location"]').forEach((el) => {
        el.dataset.filepath = newFilePath;
        el.setAttribute('data-filepath', newFilePath);
    });

    document.querySelectorAll('[data-file-path]').forEach((el) => {
        el.dataset.filePath = newFilePath;
        el.setAttribute('data-file-path', newFilePath);
    });

    document.querySelectorAll('[data-filepath]').forEach((el) => {
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
 * Set up base model editing functionality
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
        
        // Create dropdown selector to replace the base model content
        const currentValue = originalValue;
        const dropdown = document.createElement('select');
        dropdown.className = 'base-model-selector';
        
        // Flag to track if a change was made
        let valueChanged = false;
        
        // Add options from BASE_MODEL_CATEGORIES constants
        const baseModelCategories = BASE_MODEL_CATEGORIES;
        
        // Create option groups for better organization
        Object.entries(baseModelCategories).forEach(([category, models]) => {
            const group = document.createElement('optgroup');
            group.label = category;
            
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                option.selected = model === currentValue;
                group.appendChild(option);
            });
            
            dropdown.appendChild(group);
        });
        
        // Replace content with dropdown
        baseModelContent.style.display = 'none';
        baseModelDisplay.insertBefore(dropdown, editBtn);
        
        // Hide edit button during editing
        editBtn.style.display = 'none';
        
        // Focus the dropdown
        dropdown.focus();
        
        // Handle dropdown change
        dropdown.addEventListener('change', function() {
            const selectedModel = this.value;
            baseModelContent.textContent = selectedModel;
            
            // Mark that a change was made if the value differs from original
            if (selectedModel !== originalValue) {
                valueChanged = true;
            } else {
                valueChanged = false;
            }
        });
        
        // Function to save changes and exit edit mode
        const saveAndExit = function() {
            // Check if dropdown still exists and remove it
            if (dropdown && dropdown.parentNode === baseModelDisplay) {
                baseModelDisplay.removeChild(dropdown);
            }
            
            // Show the content and edit button
            baseModelContent.style.display = '';
            editBtn.style.display = '';
            
            // Remove editing class
            baseModelDisplay.classList.remove('editing');
            
            // Only save if the value has actually changed
            if (valueChanged || baseModelContent.textContent.trim() !== originalValue) {
                const resolvedPath = getActiveModalFilePath(baseModelContent.dataset.filePath);
                saveBaseModel(resolvedPath, originalValue);
            }
            
            // Remove this event listener
            document.removeEventListener('click', outsideClickHandler);
        };
        
        // Handle outside clicks to save and exit
        const outsideClickHandler = function(e) {
            // If click is outside the dropdown and base model display
            if (!baseModelDisplay.contains(e.target)) {
                saveAndExit();
            }
        };
        
        // Add delayed event listener for outside clicks
        setTimeout(() => {
            document.addEventListener('click', outsideClickHandler);
        }, 0);
        
        // Also handle dropdown blur event
        dropdown.addEventListener('blur', function(e) {
            // Only save if the related target is not the edit button or inside the baseModelDisplay
            if (!baseModelDisplay.contains(e.relatedTarget)) {
                saveAndExit();
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
