/**
 * ModelTags.js
 * Module for handling model tag editing functionality - 共享版本
 */
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { translate } from '../../utils/i18nHelpers.js';
import { getPriorityTagSuggestions } from '../../utils/priorityTagHelpers.js';
import { state } from '../../state/index.js';

const MODEL_TYPE_SUGGESTION_KEY_MAP = {
    loras: 'lora',
    lora: 'lora',
    checkpoints: 'checkpoint',
    checkpoint: 'checkpoint',
    embeddings: 'embedding',
    embedding: 'embedding',
};
const METADATA_ITEM_SELECTOR = '.metadata-item';
const METADATA_ITEMS_CONTAINER_SELECTOR = '.metadata-items';
const METADATA_ITEM_DRAGGING_CLASS = 'metadata-item-dragging';
const METADATA_ITEM_PLACEHOLDER_CLASS = 'metadata-item-placeholder';
const METADATA_ITEMS_SORTING_CLASS = 'metadata-items-sorting';
const BODY_DRAGGING_CLASS = 'metadata-drag-active';

let activeModelTypeKey = '';
let priorityTagSuggestions = [];
let priorityTagSuggestionsLoaded = false;
let priorityTagSuggestionsPromise = null;
let activeTagDragState = null;

// Configurable options for tag editing (set by setupTagEditMode)
let tagEditOptions = {
    showSuggestions: true,
    saveHandler: null,
    onSaved: null,
    normalizeTag: true,
};

function normalizeModelTypeKey(modelType) {
    if (!modelType) {
        return '';
    }
    const lower = String(modelType).toLowerCase();
    if (MODEL_TYPE_SUGGESTION_KEY_MAP[lower]) {
        return MODEL_TYPE_SUGGESTION_KEY_MAP[lower];
    }
    if (lower.endsWith('s')) {
        return lower.slice(0, -1);
    }
    return lower;
}

function resolveModelTypeKey(modelType = null) {
    if (modelType) {
        return normalizeModelTypeKey(modelType);
    }
    if (activeModelTypeKey) {
        return activeModelTypeKey;
    }
    if (state?.currentPageType) {
        return normalizeModelTypeKey(state.currentPageType);
    }
    return '';
}

function resetSuggestionState() {
    priorityTagSuggestions = [];
    priorityTagSuggestionsLoaded = false;
    priorityTagSuggestionsPromise = null;
}

function setActiveModelTypeKey(modelType = null) {
    const resolvedKey = resolveModelTypeKey(modelType);
    if (resolvedKey === activeModelTypeKey) {
        return activeModelTypeKey;
    }
    activeModelTypeKey = resolvedKey;
    resetSuggestionState();
    return activeModelTypeKey;
}

function ensurePriorityTagSuggestions(modelType = null) {
    if (modelType !== null && modelType !== undefined) {
        setActiveModelTypeKey(modelType);
    } else if (!activeModelTypeKey) {
        setActiveModelTypeKey();
    }

    if (!activeModelTypeKey) {
        resetSuggestionState();
        priorityTagSuggestionsLoaded = true;
        return Promise.resolve([]);
    }

    if (priorityTagSuggestionsLoaded && !priorityTagSuggestionsPromise) {
        return Promise.resolve(priorityTagSuggestions);
    }

    if (!priorityTagSuggestionsPromise) {
        const requestKey = activeModelTypeKey;
        priorityTagSuggestionsPromise = getPriorityTagSuggestions(requestKey)
            .then((tags) => {
                if (activeModelTypeKey === requestKey) {
                    priorityTagSuggestions = tags;
                    priorityTagSuggestionsLoaded = true;
                }
                return tags;
            })
            .catch(() => {
                if (activeModelTypeKey === requestKey) {
                    priorityTagSuggestions = [];
                    priorityTagSuggestionsLoaded = true;
                }
                return [];
            })
            .finally(() => {
                if (activeModelTypeKey === requestKey) {
                    priorityTagSuggestionsPromise = null;
                }
            });
    }

    return priorityTagSuggestionsPromise;
}

activeModelTypeKey = resolveModelTypeKey();

if (activeModelTypeKey) {
    ensurePriorityTagSuggestions();
}

window.addEventListener('lm:priority-tags-updated', () => {
    if (!activeModelTypeKey) {
        return;
    }
    resetSuggestionState();
    ensurePriorityTagSuggestions().then(() => {
        document.querySelectorAll('.metadata-edit-container .metadata-suggestions-container').forEach((container) => {
            renderPriorityTagSuggestions(container, getCurrentEditTags());
        });
        updateSuggestionsDropdown();
    });
});

// Create a named function so we can remove it later
let saveTagsHandler = null;

/**
 * Set up tag editing mode
 * @param {string|null} modelType - Model type for suggestions (e.g. 'loras', 'checkpoints')
 * @param {Object} [options] - Optional configuration
 * @param {boolean} [options.showSuggestions=true] - Show priority tag suggestions dropdown
 * @param {Function} [options.saveHandler] - Custom save function, async (filePath, tags) => {}
 * @param {Function} [options.onSaved] - Called after successful save, (tags) => {}
 * @param {boolean} [options.normalizeTag=true] - Lowercase tag on add
 */
export function setupTagEditMode(modelType = null, options = {}) {
    // Store options for use by saveTags and addNewTag
    tagEditOptions = {
        showSuggestions: options.showSuggestions !== false,
        saveHandler: options.saveHandler || null,
        onSaved: options.onSaved || null,
        normalizeTag: options.normalizeTag !== false,
    };

    const root = options.container || document;
    const editBtn = root.querySelector('.edit-tags-btn');
    if (!editBtn) return;

    if (tagEditOptions.showSuggestions) {
        setActiveModelTypeKey(modelType);
        ensurePriorityTagSuggestions();
    }
    
    // Store original tags for restoring on cancel
    let originalTags = [];
    
    // Remove any previously attached click handler
    if (editBtn._hasClickHandler) {
        editBtn.removeEventListener('click', editBtn._clickHandler);
    }
    
    // Create new handler and store reference
    const editBtnClickHandler = function() {
        const tagsSection = this.closest('.model-tags-container');
        if (!tagsSection) return;
        const isEditMode = tagsSection.classList.toggle('edit-mode');
        const filePath = this.dataset.filePath;
        
        // Toggle edit mode UI elements
        const compactTagsDisplay = tagsSection.querySelector('.model-tags-compact');
        const tagsEditContainer = tagsSection.querySelector('.metadata-edit-container');
        
        if (isEditMode) {
            // Enter edit mode
            this.innerHTML = '<i class="fas fa-times"></i>'; // Change to cancel icon
            this.title = "Cancel editing";
            
            // Get all tags from tooltip, not just the visible ones in compact display
            originalTags = Array.from(
                tagsSection.querySelectorAll('.tooltip-tag')
            ).map(tag => tag.textContent);
            
            // Hide compact display, show edit container
            compactTagsDisplay.style.display = 'none';
            
            // If edit container doesn't exist yet, create it
            if (!tagsEditContainer) {
                const editContainer = document.createElement('div');
                editContainer.className = 'metadata-edit-container';
                
                // Move the edit button inside the container header for better visibility
                const editBtnClone = editBtn.cloneNode(true);
                editBtnClone.classList.add('metadata-header-btn');
                
                // Create edit UI with edit button in the header
                editContainer.innerHTML = createTagEditUI(originalTags, editBtnClone.outerHTML);
                tagsSection.appendChild(editContainer);
                
                // Setup the tag input field behavior
                setupTagInput(tagsSection);
                
                // Create and add preset suggestions dropdown
                if (tagEditOptions.showSuggestions) {
                    const tagForm = editContainer.querySelector('.metadata-add-form');
                    const suggestionsDropdown = createSuggestionsDropdown(originalTags);
                    tagForm.appendChild(suggestionsDropdown);
                }
                
                // Setup delete buttons for existing tags
                setupDeleteButtons();
                setupTagDragAndDrop(tagsSection);
                
                // Transfer click event from original button to the cloned one
                const newEditBtn = editContainer.querySelector('.metadata-header-btn');
                if (newEditBtn) {
                    newEditBtn.addEventListener('click', function() {
                        editBtn.click();
                    });
                }
                
                // Hide the original button when in edit mode
                editBtn.style.display = 'none';
            } else {
                // Just show the existing edit container
                tagsEditContainer.style.display = 'block';
                editBtn.style.display = 'none';
                setupTagDragAndDrop(tagsSection);
            }
        } else {
            // Exit edit mode
            this.innerHTML = '<i class="fas fa-pencil-alt"></i>'; // Change back to edit icon
            this.title = "Edit tags";
            editBtn.style.display = 'block';
            
            // Show compact display, hide edit container
            compactTagsDisplay.style.display = 'flex';
            if (tagsEditContainer) tagsEditContainer.style.display = 'none';
            
            // Check if we're exiting edit mode due to "Save" or "Cancel"
            if (!this.dataset.skipRestore) {
                // If canceling, restore original tags
                restoreOriginalTags(tagsSection, originalTags);
            } else {
                // Reset the skip restore flag
                delete this.dataset.skipRestore;
            }
        }
    };
    
    // Store the handler reference on the button itself
    editBtn._clickHandler = editBtnClickHandler;
    editBtn._hasClickHandler = true;
    editBtn.addEventListener('click', editBtnClickHandler);
    
    // Clean up any previous document click handler
    if (saveTagsHandler) {
        document.removeEventListener('click', saveTagsHandler);
    }
    
    // Create new save handler and store reference
    saveTagsHandler = function(e) {
        if (e.target.classList.contains('save-tags-btn') || 
            e.target.closest('.save-tags-btn')) {
            saveTags(e.target);
        }
    };
    
    // Add the new handler
    document.addEventListener('click', saveTagsHandler);
}

// ...existing helper functions...

/**
 * Save tags
 * @param {Element} [triggerElement] - The element that triggered the save (e.g. save button)
 */
async function saveTags(triggerElement = null) {
    let editBtn;
    let scope;
    if (triggerElement) {
        scope = triggerElement.closest('.model-tags-container');
        editBtn = scope ? scope.querySelector('.edit-tags-btn') : document.querySelector('.edit-tags-btn');
    } else {
        scope = document.querySelector('.model-tags-container');
        editBtn = scope ? scope.querySelector('.edit-tags-btn') : null;
    }
    if (!editBtn || !scope) return;
    
    const filePath = editBtn.dataset.filePath;
    const tagElements = scope.querySelectorAll('.metadata-item');
    let tags = Array.from(tagElements).map(tag => tag.dataset.tag);
    
    // Flush uncommitted input as a tag so it's not silently lost on save
    const tagInput = scope.querySelector('.metadata-input');
    if (tagInput) {
        const pendingTag = tagEditOptions.normalizeTag ? tagInput.value.trim().toLowerCase() : tagInput.value.trim();
        if (pendingTag && !tags.includes(pendingTag)) {
            tags.push(pendingTag);
        }
        tagInput.value = '';
    }

    // Get original tags to compare
    const originalTagElements = scope.querySelectorAll('.tooltip-tag');
    const originalTags = Array.from(originalTagElements).map(tag => tag.textContent);
    
    // Check if tags have actually changed
    const tagsChanged = JSON.stringify(tags) !== JSON.stringify(originalTags);
    
    if (!tagsChanged) {
        // No changes made, just exit edit mode without API call
        editBtn.dataset.skipRestore = "true";
        editBtn.click();
        return;
    }
    
    try {
        // Use custom save handler if provided, otherwise default model API
        if (tagEditOptions.saveHandler) {
            await tagEditOptions.saveHandler(filePath, tags);
        } else {
            await getModelApiClient().saveModelMetadata(filePath, { tags: tags });
        }
        
        // Set flag to skip restoring original tags when exiting edit mode
        editBtn.dataset.skipRestore = "true";
        
        // Use custom onSaved if provided (e.g. for recipe dirty state + re-render)
        if (tagEditOptions.onSaved) {
            tagEditOptions.onSaved(tags);
        } else {
            // Update the compact tags display
            const compactTagsContainer = scope;
            if (compactTagsContainer) {
                // Generate new compact tags HTML
                const compactTagsDisplay = compactTagsContainer.querySelector('.model-tags-compact');
                
                if (compactTagsDisplay) {
                    // Clear current tags
                    compactTagsDisplay.innerHTML = '';
                    
                    // Add visible tags (up to 5)
                    const visibleTags = tags.slice(0, 5);
                    visibleTags.forEach(tag => {
                        const span = document.createElement('span');
                        span.className = 'model-tag-compact';
                        span.textContent = tag;
                        compactTagsDisplay.appendChild(span);
                    });
                    
                    // Add more indicator if needed
                    const remainingCount = Math.max(0, tags.length - 5);
                    if (remainingCount > 0) {
                        const more = document.createElement('span');
                        more.className = 'model-tag-more';
                        more.dataset.count = remainingCount;
                        more.textContent = `+${remainingCount}`;
                        compactTagsDisplay.appendChild(more);
                    }
                }
                
                // Update tooltip content
                const tooltipContent = compactTagsContainer.querySelector('.tooltip-content');
                if (tooltipContent) {
                    tooltipContent.innerHTML = '';
                    
                    tags.forEach(tag => {
                        const span = document.createElement('span');
                        span.className = 'tooltip-tag';
                        span.textContent = tag;
                        tooltipContent.appendChild(span);
                    });
                }
            }
            
            // Exit edit mode
            editBtn.click();
        }
        
        showToast('modelTags.messages.updated', {}, 'success');
    } catch (error) {
        console.error('Error saving tags:', error);
        showToast('modelTags.messages.updateFailed', {}, 'error');
    }
}

/**
 * Create the tag editing UI
 * @param {Array} currentTags - Current tags
 * @param {string} editBtnHTML - HTML for the edit button to include in header
 * @returns {string} HTML markup for tag editing UI
 */
function createTagEditUI(currentTags, editBtnHTML = '') {
    return `
        <div class="metadata-edit-content">
            <div class="metadata-edit-header">
                <label>Edit Tags</label>
                ${editBtnHTML}
            </div>
            <div class="metadata-items">
                ${currentTags.map(tag => `
                    <div class="metadata-item" data-tag="${tag}">
                        <span class="metadata-item-content">${tag}</span>
                        <button class="metadata-delete-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `).join('')}
            </div>
            <div class="metadata-edit-controls">
                <button class="save-tags-btn" title="Save changes">
                    <i class="fas fa-save"></i> Save
                </button>
            </div>
            <div class="metadata-add-form">
                <input type="text" class="metadata-input" placeholder="Type to add or click suggestions below">
            </div>
        </div>
    `;
}

/**
 * Create suggestions dropdown with preset tags
 * @param {Array} existingTags - Already added tags
 * @returns {HTMLElement} - Dropdown element
 */
function createSuggestionsDropdown(existingTags = []) {
    const dropdown = document.createElement('div');
    dropdown.className = 'metadata-suggestions-dropdown';

    // Create header
    const header = document.createElement('div');
    header.className = 'metadata-suggestions-header';
    header.innerHTML = `
        <span>Suggested Tags</span>
        <small>Click to add</small>
    `;
    dropdown.appendChild(header);
    
    // Create tag container
    const container = document.createElement('div');
    container.className = 'metadata-suggestions-container';
    if (priorityTagSuggestionsLoaded && !priorityTagSuggestionsPromise) {
        renderPriorityTagSuggestions(container, existingTags);
    } else {
        container.innerHTML = `<div class="metadata-suggestions-loading">${translate('settings.priorityTags.loadingSuggestions', 'Loading suggestions…')}</div>`;
        ensurePriorityTagSuggestions().then(() => {
            if (!container.isConnected) {
                return;
            }
            renderPriorityTagSuggestions(container, getCurrentEditTags());
            updateSuggestionsDropdown();
        }).catch(() => {
            if (container.isConnected) {
                container.innerHTML = '';
            }
        });
    }

    dropdown.appendChild(container);
    return dropdown;
}

function renderPriorityTagSuggestions(container, existingTags = []) {
    container.innerHTML = '';

    priorityTagSuggestions.forEach((tag) => {
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
                addNewTag(tag);

                const input = document.querySelector('.metadata-input');
                if (input) input.value = tag;
                if (input) input.focus();

                updateSuggestionsDropdown();
            });
        }

        container.appendChild(item);
    });
}

/**
 * Set up tag input behavior
 * @param {Element} scopeContainer - The .model-tags-container element
 */
function setupTagInput(scopeContainer) {
    const tagInput = scopeContainer
        ? scopeContainer.querySelector('.metadata-input')
        : document.querySelector('.metadata-input');
    
    if (tagInput) {
        tagInput.focus();
        tagInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addNewTag(this.value, this);
                this.value = ''; // Clear input after adding
            }
        });
    }
}

/**
 * Set up delete buttons for tags
 */
function setupDeleteButtons() {
    document.querySelectorAll('.metadata-delete-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const tag = this.closest('.metadata-item');
            tag.remove();
            
            // Update status of items in the suggestion dropdown
            updateSuggestionsDropdown();
        });
    });
}

/**
 * Enable drag-and-drop sorting for tag items
 * @param {Element} [scopeContainer] - Optional scoped .model-tags-container element
 */
function setupTagDragAndDrop(scopeContainer) {
    const container = scopeContainer
        ? scopeContainer.querySelector(METADATA_ITEMS_CONTAINER_SELECTOR)
        : document.querySelector(METADATA_ITEMS_CONTAINER_SELECTOR);
    if (!container) {
        return;
    }

    container.querySelectorAll(METADATA_ITEM_SELECTOR).forEach((item) => {
        item.removeAttribute('draggable');
        if (item.classList.contains(METADATA_ITEM_PLACEHOLDER_CLASS)) {
            return;
        }
        if (item.dataset.pointerDragInit === 'true') {
            return;
        }

        item.addEventListener('pointerdown', handleTagPointerDown);
        item.dataset.pointerDragInit = 'true';
    });
}

function handleTagPointerDown(event) {
    if (event.button !== 0) {
        return;
    }

    if (event.target.closest('.metadata-delete-btn')) {
        return;
    }

    const item = event.currentTarget;
    const container = item?.closest(METADATA_ITEMS_CONTAINER_SELECTOR);
    if (!item || !container) {
        return;
    }

    event.preventDefault();
    startPointerDrag({ item, container, startEvent: event });
}

function startPointerDrag({ item, container, startEvent }) {
    if (activeTagDragState) {
        finishPointerDrag();
    }

    const itemRect = item.getBoundingClientRect();
    const placeholder = document.createElement('div');
    placeholder.className = `metadata-item ${METADATA_ITEM_PLACEHOLDER_CLASS}`;
    placeholder.style.width = `${itemRect.width}px`;
    placeholder.style.height = `${itemRect.height}px`;

    container.insertBefore(placeholder, item);

    item.classList.add(METADATA_ITEM_DRAGGING_CLASS);
    item.style.width = `${itemRect.width}px`;
    item.style.height = `${itemRect.height}px`;
    item.style.position = 'fixed';
    item.style.left = `${itemRect.left}px`;
    item.style.top = `${itemRect.top}px`;
    item.style.pointerEvents = 'none';
    item.style.zIndex = '1000';

    container.classList.add(METADATA_ITEMS_SORTING_CLASS);
    if (document.body) {
        document.body.classList.add(BODY_DRAGGING_CLASS);
    }

    const dragState = {
        container,
        item,
        placeholder,
        offsetX: startEvent.clientX - itemRect.left,
        offsetY: startEvent.clientY - itemRect.top,
        lastKnownPointer: { x: startEvent.clientX, y: startEvent.clientY },
        rafId: null,
    };

    activeTagDragState = dragState;

    document.addEventListener('pointermove', handlePointerMove);
    document.addEventListener('pointerup', handlePointerUp);
    document.addEventListener('pointercancel', handlePointerUp);
}

function handlePointerMove(event) {
    if (!activeTagDragState) {
        return;
    }

    activeTagDragState.lastKnownPointer = { x: event.clientX, y: event.clientY };

    if (activeTagDragState.rafId !== null) {
        return;
    }

    activeTagDragState.rafId = requestAnimationFrame(() => {
        if (!activeTagDragState) {
            return;
        }
        activeTagDragState.rafId = null;
        updateDraggingItemPosition();
        updatePlaceholderPosition();
    });
}

function handlePointerUp() {
    finishPointerDrag();
}

function updateDraggingItemPosition() {
    if (!activeTagDragState) {
        return;
    }

    const { item, offsetX, offsetY, lastKnownPointer } = activeTagDragState;
    const left = lastKnownPointer.x - offsetX;
    const top = lastKnownPointer.y - offsetY;
    item.style.left = `${left}px`;
    item.style.top = `${top}px`;
}

function updatePlaceholderPosition() {
    if (!activeTagDragState) {
        return;
    }

    const { container, placeholder, item, lastKnownPointer } = activeTagDragState;
    const siblings = Array.from(
        container.querySelectorAll(
            `${METADATA_ITEM_SELECTOR}:not(.${METADATA_ITEM_PLACEHOLDER_CLASS})`
        )
    ).filter((element) => element !== item);

    let insertAfter = null;

    for (const sibling of siblings) {
        const rect = sibling.getBoundingClientRect();

        if (lastKnownPointer.y < rect.top) {
            container.insertBefore(placeholder, sibling);
            return;
        }

        if (lastKnownPointer.y <= rect.bottom) {
            if (lastKnownPointer.x < rect.left + rect.width / 2) {
                container.insertBefore(placeholder, sibling);
                return;
            }
            insertAfter = sibling;
            continue;
        }

        insertAfter = sibling;
    }

    if (!insertAfter) {
        container.insertBefore(placeholder, container.firstElementChild);
        return;
    }

    container.insertBefore(placeholder, insertAfter.nextSibling);
}

function finishPointerDrag() {
    if (!activeTagDragState) {
        return;
    }

    const { container, item, placeholder, rafId } = activeTagDragState;

    document.removeEventListener('pointermove', handlePointerMove);
    document.removeEventListener('pointerup', handlePointerUp);
    document.removeEventListener('pointercancel', handlePointerUp);

    container.classList.remove(METADATA_ITEMS_SORTING_CLASS);
    if (document.body) {
        document.body.classList.remove(BODY_DRAGGING_CLASS);
    }

    if (rafId !== null) {
        cancelAnimationFrame(rafId);
        activeTagDragState.rafId = null;
        updateDraggingItemPosition();
        updatePlaceholderPosition();
    }

    if (placeholder && placeholder.parentNode === container) {
        container.insertBefore(item, placeholder);
        container.removeChild(placeholder);
    }

    item.classList.remove(METADATA_ITEM_DRAGGING_CLASS);
    item.style.position = '';
    item.style.width = '';
    item.style.height = '';
    item.style.left = '';
    item.style.top = '';
    item.style.pointerEvents = '';
    item.style.zIndex = '';

    activeTagDragState = null;

    updateSuggestionsDropdown();
}

/**
 * Add a new tag
 * @param {string} tag - Tag to add
 * @param {Element} [scopeElement] - Element within the correct .model-tags-container for scoping
 */
function addNewTag(tag, scopeElement = null) {
    tag = tagEditOptions.normalizeTag ? tag.trim().toLowerCase() : tag.trim();
    if (!tag) return;
    
    const scope = scopeElement ? scopeElement.closest('.model-tags-container') : document;
    const tagsContainer = scope.querySelector('.metadata-items');
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
    const existingTags = Array.from(currentTags).map(tag => tag.dataset.tag);
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
    
    // Add event listener to delete button
    const deleteBtn = newTag.querySelector('.metadata-delete-btn');
    deleteBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        newTag.remove();
        
        // Update status of items in the suggestion dropdown
        updateSuggestionsDropdown();
    });
    
    tagsContainer.appendChild(newTag);
    setupTagDragAndDrop(scope);
    
    // Update status of items in the suggestions dropdown
    updateSuggestionsDropdown();
}

/**
 * Update status of items in the suggestions dropdown
 */
function updateSuggestionsDropdown() {
    const dropdown = document.querySelector('.metadata-suggestions-dropdown');
    if (!dropdown) return;

    // Get all current tags
    const existingTags = getCurrentEditTags();
    
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
        } else {
            // Re-enable items that are no longer in the list
            item.classList.remove('already-added');
            
            // Remove indicator if it exists
            const indicator = item.querySelector('.added-indicator');
            if (indicator) indicator.remove();
            
            // Restore click event if not already set
            if (!item.onclick) {
                item.onclick = () => {
                    const tag = item.querySelector('.metadata-suggestion-text').textContent;
                    addNewTag(tag);
                    
                    // Also populate the input field
                    const input = document.querySelector('.metadata-input');
                    if (input) input.value = tag;
                    
                    // Focus the input
                    if (input) input.focus();
                };
            }
        }
    });
}

function getCurrentEditTags() {
    const currentTags = document.querySelectorAll(
        `${METADATA_ITEM_SELECTOR}[data-tag]`
    );
    return Array.from(currentTags)
        .map(tag => tag.dataset.tag)
        .filter(Boolean);
}

/**
 * Restore original tags when canceling edit
 * @param {HTMLElement} section - The tags section
 * @param {Array} originalTags - Original tags array
 */
function restoreOriginalTags(section, originalTags) {
    // Nothing to do here as we're just hiding the edit UI
    // and showing the original compact tags which weren't modified
}
