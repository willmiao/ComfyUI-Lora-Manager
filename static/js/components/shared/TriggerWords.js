/**
 * TriggerWords.js
 * Module that handles trigger word functionality for LoRA models
 * Moved to shared directory for consistency
 */
import { showToast, copyToClipboard } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { escapeAttribute, escapeHtml } from './utils.js';

const MAX_WORDS_PER_TRIGGER_GROUP = 500;
const MAX_TRIGGER_WORD_GROUPS = 100;
const TRIGGER_WORD_CLICK_DELAY_MS = 220;

/**
 * Fetch trained words for a model
 * @param {string} filePath - Path to the model file
 * @returns {Promise<Object>} - Object with trained words and class tokens
 */
async function fetchTrainedWords(filePath) {
    try {
        const response = await fetch(`/api/lm/trained-words?file_path=${encodeURIComponent(filePath)}`);
        const data = await response.json();

        if (data.success) {
            return {
                trainedWords: data.trained_words || [], // Returns array of [word, frequency] pairs
                classTokens: data.class_tokens  // Can be null or a string
            };
        } else {
            throw new Error(data.error || 'Failed to fetch trained words');
        }
    } catch (error) {
        console.error('Error fetching trained words:', error);
        showToast('toast.triggerWords.loadFailed', {}, 'error');
        return { trainedWords: [], classTokens: null };
    }
}

/**
 * Create suggestion dropdown with trained words as tags
 * @param {Array} trainedWords - Array of [word, frequency] pairs
 * @param {string|null} classTokens - Class tokens from training
 * @param {Array} existingWords - Already added trigger words
 * @returns {HTMLElement} - Dropdown element
 */
function createSuggestionDropdown(trainedWords, classTokens, existingWords = []) {
    const dropdown = document.createElement('div');
    dropdown.className = 'metadata-suggestions-dropdown';

    // Create header
    const header = document.createElement('div');
    header.className = 'metadata-suggestions-header';

    // No suggestions case
    if ((!trainedWords || trainedWords.length === 0) && !classTokens) {
        header.innerHTML = `<span>${translate('modals.model.triggerWords.suggestions.noSuggestions')}</span>`;
        dropdown.appendChild(header);
        dropdown.innerHTML += `<div class="no-suggestions">${translate('modals.model.triggerWords.suggestions.noTrainedWords')}</div>`;
        return dropdown;
    }

    // Sort trained words by frequency (highest first) if available
    if (trainedWords && trainedWords.length > 0) {
        trainedWords.sort((a, b) => b[1] - a[1]);
    }

    // Add class tokens section if available
    if (classTokens) {
        // Add class tokens header
        const classTokensHeader = document.createElement('div');
        classTokensHeader.className = 'metadata-suggestions-header';
        classTokensHeader.innerHTML = `
            <span>${translate('modals.model.triggerWords.suggestions.classToken')}</span>
            <small>${translate('modals.model.triggerWords.suggestions.classTokenDescription')}</small>
        `;
        dropdown.appendChild(classTokensHeader);

        // Add class tokens container
        const classTokensContainer = document.createElement('div');
        classTokensContainer.className = 'class-tokens-container';

        // Create a special item for the class token
        const tokenItem = document.createElement('div');
        tokenItem.className = `metadata-suggestion-item class-token-item ${existingWords.includes(classTokens) ? 'already-added' : ''}`;
        tokenItem.title = `${translate('modals.model.triggerWords.suggestions.classToken')}: ${classTokens}`;

        const escapedToken = escapeHtml(classTokens);
        tokenItem.innerHTML = `
            <span class="metadata-suggestion-text">${escapedToken}</span>
            <div class="metadata-suggestion-meta">
                <span class="token-badge">${translate('modals.model.triggerWords.suggestions.classToken')}</span>
                ${existingWords.includes(classTokens) ?
                `<span class="added-indicator"><i class="fas fa-check"></i></span>` : ''}
            </div>
        `;

        // Add click handler if not already added
        if (!existingWords.includes(classTokens)) {
            tokenItem.addEventListener('click', () => {
                // Automatically add this word
                addNewTriggerWord(classTokens);

                // Also populate the input field for potential editing
                const input = document.querySelector('.metadata-input');
                if (input) input.value = classTokens;

                // Focus on the input
                if (input) input.focus();

                // Update dropdown without removing it
                updateTrainedWordsDropdown();
            });
        }

        classTokensContainer.appendChild(tokenItem);
        dropdown.appendChild(classTokensContainer);

        // Add separator if we also have trained words
        if (trainedWords && trainedWords.length > 0) {
            const separator = document.createElement('div');
            separator.className = 'dropdown-separator';
            dropdown.appendChild(separator);
        }
    }

    // Add trained words header if we have any
    if (trainedWords && trainedWords.length > 0) {
        header.innerHTML = `
            <span>${translate('modals.model.triggerWords.suggestions.wordSuggestions')}</span>
            <small>${translate('modals.model.triggerWords.suggestions.wordsFound', { count: trainedWords.length })}</small>
        `;
        dropdown.appendChild(header);

        // Create tag container for trained words
        const container = document.createElement('div');
        container.className = 'metadata-suggestions-container';

        // Add each trained word as a tag
        trainedWords.forEach(([word, frequency]) => {
            const isAdded = existingWords.includes(word);

            const item = document.createElement('div');
            item.className = `metadata-suggestion-item ${isAdded ? 'already-added' : ''}`;
            item.title = word; // Show full word on hover if truncated

            const escapedWord = escapeHtml(word);
            item.innerHTML = `
                <span class="metadata-suggestion-text">${escapedWord}</span>
                <div class="metadata-suggestion-meta">
                    <span class="trained-word-freq">${frequency}</span>
                    ${isAdded ? `<span class="added-indicator"><i class="fas fa-check"></i></span>` : ''}
                </div>
            `;

            if (!isAdded) {
                item.addEventListener('click', () => {
                    // Automatically add this word
                    addNewTriggerWord(word);

                    // Also populate the input field for potential editing
                    const input = document.querySelector('.metadata-input');
                    if (input) input.value = word;

                    // Focus on the input
                    if (input) input.focus();

                    // Update dropdown without removing it
                    updateTrainedWordsDropdown();
                });
            }

            container.appendChild(item);
        });

        dropdown.appendChild(container);
    } else if (!classTokens) {
        // If we have neither class tokens nor trained words
        dropdown.innerHTML += `<div class="no-suggestions">${translate('modals.model.triggerWords.suggestions.noTrainedWords')}</div>`;
    }

    return dropdown;
}

/**
 * Render trigger words
 * @param {Array} words - Array of trigger words
 * @param {string} filePath - File path
 * @returns {string} HTML content
 */
export function renderTriggerWords(words, filePath) {
    const safeFilePath = escapeAttribute(filePath || '');
    if (!words.length) return `
        <div class="info-item full-width trigger-words">
            <div class="trigger-words-header">
                <label>${translate('modals.model.triggerWords.label')}</label>
                <button class="edit-trigger-words-btn metadata-edit-btn" data-file-path="${safeFilePath}" title="${translate('modals.model.triggerWords.edit')}">
                    <i class="fas fa-pencil-alt"></i>
                </button>
            </div>
            <div class="trigger-words-content">
                <span class="no-trigger-words">${translate('modals.model.triggerWords.noTriggerWordsNeeded')}</span>
                <div class="trigger-words-tags" style="display:none;"></div>
            </div>
            <div class="metadata-edit-controls" style="display:none;">
                <button class="metadata-save-btn" title="${translate('modals.model.triggerWords.save')}">
                    <i class="fas fa-save"></i> ${translate('common.actions.save')}
                </button>
            </div>
            <div class="metadata-add-form" style="display:none;">
                <input type="text" class="metadata-input" placeholder="${translate('modals.model.triggerWords.addPlaceholder')}">
            </div>
        </div>
    `;

    return `
        <div class="info-item full-width trigger-words">
            <div class="trigger-words-header">
                <label>${translate('modals.model.triggerWords.label')}</label>
                <button class="edit-trigger-words-btn metadata-edit-btn" data-file-path="${safeFilePath}" title="${translate('modals.model.triggerWords.edit')}">
                    <i class="fas fa-pencil-alt"></i>
                </button>
            </div>
            <div class="trigger-words-content">
                <div class="trigger-words-tags">
                    ${words.map(word => {
        const escapedWord = escapeHtml(word);
        const escapedAttr = escapeAttribute(word);
        return `
                        <div class="trigger-word-tag" data-word="${escapedAttr}" title="${translate('modals.model.triggerWords.copyWord')}">
                            <span class="trigger-word-content">${escapedWord}</span>
                            <span class="trigger-word-copy">
                                <i class="fas fa-copy"></i>
                            </span>
                            <button class="metadata-delete-btn" style="display:none;" onclick="event.stopPropagation();" title="${translate('modals.model.triggerWords.deleteWord')}">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    `}).join('')}
                </div>
            </div>
            <div class="metadata-edit-controls" style="display:none;">
                <button class="metadata-save-btn" title="${translate('modals.model.triggerWords.save')}">
                    <i class="fas fa-save"></i> ${translate('common.actions.save')}
                </button>
            </div>
            <div class="metadata-add-form" style="display:none;">
                <input type="text" class="metadata-input" placeholder="${translate('modals.model.triggerWords.addPlaceholder')}">
            </div>
        </div>
    `;
}

/**
 * Set up trigger words edit mode
 */
export function setupTriggerWordsEditMode() {
    // Store trained words data
    let trainedWordsList = [];
    let classTokensValue = null;
    let isTrainedWordsLoaded = false;
    // Store original trigger words for restoring on cancel
    let originalTriggerWords = [];

    const editBtn = document.querySelector('.edit-trigger-words-btn');
    if (!editBtn) return;

    document.querySelectorAll('.trigger-word-tag').forEach(setupDisplayTriggerWordTag);

    editBtn.addEventListener('click', async function () {
        const triggerWordsSection = this.closest('.trigger-words');
        const isEditMode = triggerWordsSection.classList.toggle('edit-mode');
        const filePath = this.dataset.filePath;

        // Toggle edit mode UI elements
        const triggerWordTags = triggerWordsSection.querySelectorAll('.trigger-word-tag');
        const editControls = triggerWordsSection.querySelector('.metadata-edit-controls');
        const addForm = triggerWordsSection.querySelector('.metadata-add-form');
        const noTriggerWords = triggerWordsSection.querySelector('.no-trigger-words');
        const tagsContainer = triggerWordsSection.querySelector('.trigger-words-tags');

        if (isEditMode) {
            this.innerHTML = '<i class="fas fa-times"></i>'; // Change to cancel icon
            this.title = translate('modals.model.triggerWords.cancel');

            // Store original trigger words for potential restoration
            originalTriggerWords = Array.from(triggerWordTags).map(tag => tag.dataset.word);

            // Show edit controls and input form
            editControls.style.display = 'flex';
            addForm.style.display = 'flex';

            // If we have no trigger words yet, hide the "No trigger word needed" text
            // and show the empty tags container
            if (noTriggerWords) {
                noTriggerWords.style.display = 'none';
                if (tagsContainer) tagsContainer.style.display = 'flex';
            }

            // Disable click-to-copy and show delete buttons
            triggerWordTags.forEach(tag => {
                teardownDisplayTriggerWordTag(tag);
                tag.addEventListener('click', startEditTriggerWord);
                tag.title = translate('modals.model.triggerWords.editWord');
                const copyIcon = tag.querySelector('.trigger-word-copy');
                const deleteBtn = tag.querySelector('.metadata-delete-btn');

                if (copyIcon) copyIcon.style.display = 'none';
                if (deleteBtn) {
                    deleteBtn.style.display = 'block';

                    // Re-attach event listener to ensure it works every time
                    // First remove any existing listeners to avoid duplication
                    deleteBtn.removeEventListener('click', deleteTriggerWord);
                    deleteBtn.addEventListener('click', deleteTriggerWord);
                }
            });

            // Load trained words and display dropdown when entering edit mode
            // Add loading indicator
            const loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'metadata-loading';
            loadingIndicator.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${translate('modals.model.triggerWords.suggestions.loading')}`;
            addForm.appendChild(loadingIndicator);

            // Get currently added trigger words
            const currentTags = triggerWordsSection.querySelectorAll('.trigger-word-tag');
            const existingWords = Array.from(currentTags).map(tag => tag.dataset.word);

            // Asynchronously load trained words if not already loaded
            if (!isTrainedWordsLoaded) {
                const result = await fetchTrainedWords(filePath);
                trainedWordsList = result.trainedWords;
                classTokensValue = result.classTokens;
                isTrainedWordsLoaded = true;
            }

            // Remove loading indicator
            loadingIndicator.remove();

            // Create and display suggestion dropdown
            const dropdown = createSuggestionDropdown(trainedWordsList, classTokensValue, existingWords);
            addForm.appendChild(dropdown);

            // Focus the input
            addForm.querySelector('input').focus();

            const pendingEditTag = triggerWordsSection._pendingTriggerWordEditTag;
            delete triggerWordsSection._pendingTriggerWordEditTag;
            if (pendingEditTag && document.contains(pendingEditTag)) {
                startEditTriggerWord.call(pendingEditTag, { target: pendingEditTag, preventDefault() { }, stopPropagation() { } });
            }

        } else {
            this.innerHTML = '<i class="fas fa-pencil-alt"></i>'; // Change back to edit icon
            this.title = translate('modals.model.triggerWords.edit');

            // Hide edit controls and input form
            editControls.style.display = 'none';
            addForm.style.display = 'none';

            // Check if we're exiting edit mode due to "Save" or "Cancel"
            if (!this.dataset.skipRestore) {
                // If canceling, restore original trigger words
                restoreOriginalTriggerWords(triggerWordsSection, originalTriggerWords);
            } else {
                commitActiveTriggerWordEdit(triggerWordsSection);
                // If saving, reset UI state on current trigger words
                resetTriggerWordsUIState(triggerWordsSection);
                // Reset the skip restore flag
                delete this.dataset.skipRestore;
            }

            // If we have no trigger words, show the "No trigger word needed" text
            // and hide the empty tags container
            const currentTags = triggerWordsSection.querySelectorAll('.trigger-word-tag');
            if (noTriggerWords && currentTags.length === 0) {
                noTriggerWords.style.display = '';
                if (tagsContainer) tagsContainer.style.display = 'none';
            }

            // Remove dropdown if present
            const dropdown = triggerWordsSection.querySelector('.metadata-suggestions-dropdown');
            if (dropdown) dropdown.remove();
        }
    });

    // Set up input for adding trigger words
    const triggerWordInput = document.querySelector('.metadata-input');

    if (triggerWordInput) {
        // Add keydown event to input
        triggerWordInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addNewTriggerWord(this.value);
                this.value = ''; // Clear input after adding
            }
        });

        // Auto-commit on blur to prevent data loss when clicking save
        triggerWordInput.addEventListener('blur', function () {
            if (this.value.trim()) {
                // Small delay to avoid conflict with save button click
                setTimeout(() => {
                    if (document.contains(this) && this.value.trim()) {
                        addNewTriggerWord(this.value.trim());
                        this.value = '';
                    }
                }, 150);
            }
        });
    }

    // Set up save button
    const saveBtn = document.querySelector('.metadata-save-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveTriggerWords);
    }

    // Set up delete buttons
    document.querySelectorAll('.metadata-delete-btn').forEach(btn => {
        // Remove any existing listeners to avoid duplication
        btn.removeEventListener('click', deleteTriggerWord);
        btn.addEventListener('click', deleteTriggerWord);
    });
}

/**
 * Delete trigger word event handler
 * @param {Event} e - Click event
 */
function deleteTriggerWord(e) {
    e.stopPropagation();
    const tag = this.closest('.trigger-word-tag');
    tag.remove();

    // Update status of items in the trained words dropdown
    updateTrainedWordsDropdown();
}

/**
 * Reset UI state for trigger words after saving
 * @param {HTMLElement} section - The trigger words section
 */
function resetTriggerWordsUIState(section) {
    commitActiveTriggerWordEdit(section);

    const triggerWordTags = section.querySelectorAll('.trigger-word-tag');

    triggerWordTags.forEach(tag => {
        const copyIcon = tag.querySelector('.trigger-word-copy');
        const deleteBtn = tag.querySelector('.metadata-delete-btn');

        // Restore click-to-copy functionality
        tag.removeEventListener('click', startEditTriggerWord);
        setupDisplayTriggerWordTag(tag);
        tag.title = translate('modals.model.triggerWords.copyWord');

        // Show copy icon, hide delete button
        if (copyIcon) copyIcon.style.display = '';
        if (deleteBtn) deleteBtn.style.display = 'none';
    });
}

/**
 * Restore original trigger words when canceling edit
 * @param {HTMLElement} section - The trigger words section
 * @param {Array} originalWords - Original trigger words
 */
function restoreOriginalTriggerWords(section, originalWords) {
    const tagsContainer = section.querySelector('.trigger-words-tags');
    const noTriggerWords = section.querySelector('.no-trigger-words');

    if (!tagsContainer) return;

    // Clear current tags
    tagsContainer.innerHTML = '';

    if (originalWords.length === 0) {
        if (noTriggerWords) noTriggerWords.style.display = '';
        tagsContainer.style.display = 'none';
        return;
    }

    // Hide "no trigger words" message
    if (noTriggerWords) noTriggerWords.style.display = 'none';
    tagsContainer.style.display = 'flex';

    // Recreate original tags
    originalWords.forEach(word => {
        tagsContainer.appendChild(createTriggerWordTag(word, false));
    });
}

/**
 * Create a trigger word tag element
 * @param {string} word - Trigger word
 * @param {boolean} isEditMode - Whether the tag should be editable
 * @returns {HTMLElement} Tag element
 */
function createTriggerWordTag(word, isEditMode = false) {
    const tag = document.createElement('div');
    tag.className = 'trigger-word-tag';
    tag.dataset.word = word;
    tag.title = translate(isEditMode ? 'modals.model.triggerWords.editWord' : 'modals.model.triggerWords.copyWord');

    const escapedWord = escapeHtml(word);
    tag.innerHTML = `
        <span class="trigger-word-content">${escapedWord}</span>
        <span class="trigger-word-copy" style="${isEditMode ? 'display:none;' : ''}">
            <i class="fas fa-copy"></i>
        </span>
        <button class="metadata-delete-btn" style="${isEditMode ? '' : 'display:none;'}" onclick="event.stopPropagation();" title="${translate('modals.model.triggerWords.deleteWord')}">
            <i class="fas fa-times"></i>
        </button>
    `;

    const deleteBtn = tag.querySelector('.metadata-delete-btn');
    deleteBtn.addEventListener('click', deleteTriggerWord);

    if (isEditMode) {
        tag.addEventListener('click', startEditTriggerWord);
    } else {
        setupDisplayTriggerWordTag(tag);
    }

    return tag;
}

/**
 * Set up display-mode click-to-copy and double-click-to-edit behavior
 * @param {HTMLElement} tag - Trigger word tag
 */
function setupDisplayTriggerWordTag(tag) {
    teardownDisplayTriggerWordTag(tag);

    tag.addEventListener('click', handleDisplayTriggerWordClick);
    tag.addEventListener('dblclick', handleDisplayTriggerWordDoubleClick);
    tag.title = translate('modals.model.triggerWords.copyWord');
}

/**
 * Remove display-mode handlers and pending copy action
 * @param {HTMLElement} tag - Trigger word tag
 */
function teardownDisplayTriggerWordTag(tag) {
    if (tag.dataset.copyTimerId) {
        clearTimeout(Number(tag.dataset.copyTimerId));
        delete tag.dataset.copyTimerId;
    }
    tag.onclick = null;
    tag.removeEventListener('click', handleDisplayTriggerWordClick);
    tag.removeEventListener('dblclick', handleDisplayTriggerWordDoubleClick);
}

/**
 * Copy trigger word after a short delay so dblclick can cancel it
 * @param {MouseEvent} e - Click event
 */
function handleDisplayTriggerWordClick(e) {
    if (e.target.closest('.metadata-delete-btn') || e.target.closest('.trigger-word-edit-input')) return;

    const tag = this.closest('.trigger-word-tag');
    if (!tag || tag.closest('.trigger-words')?.classList.contains('edit-mode')) return;

    e.stopPropagation();

    if (tag.dataset.copyTimerId) {
        clearTimeout(Number(tag.dataset.copyTimerId));
    }

    const timerId = window.setTimeout(() => {
        delete tag.dataset.copyTimerId;
        copyTriggerWord(tag.dataset.word);
    }, TRIGGER_WORD_CLICK_DELAY_MS);
    tag.dataset.copyTimerId = String(timerId);
}

/**
 * Enter edit mode and start editing the double-clicked trigger word
 * @param {MouseEvent} e - Double-click event
 */
function handleDisplayTriggerWordDoubleClick(e) {
    if (e.target.closest('.metadata-delete-btn') || e.target.closest('.trigger-word-edit-input')) return;

    const tag = this.closest('.trigger-word-tag');
    const section = tag?.closest('.trigger-words');
    const editBtn = section?.querySelector('.edit-trigger-words-btn');
    if (!tag || !section || !editBtn) return;

    e.preventDefault();
    e.stopPropagation();

    if (tag.dataset.copyTimerId) {
        clearTimeout(Number(tag.dataset.copyTimerId));
        delete tag.dataset.copyTimerId;
    }

    if (!section.classList.contains('edit-mode')) {
        section._pendingTriggerWordEditTag = tag;
        editBtn.click();
        return;
    }

    startEditTriggerWord.call(tag, e);
}

/**
 * Validate a trigger word against existing tags
 * @param {string} word - Trigger word
 * @param {HTMLElement} tagsContainer - Tags container
 * @param {HTMLElement|null} currentTag - Tag being edited, if any
 * @returns {boolean} Whether the word is valid
 */
function validateTriggerWord(word, tagsContainer, currentTag = null) {
    if (word.split(/\s+/).length > MAX_WORDS_PER_TRIGGER_GROUP) {
        showToast('toast.triggerWords.tooLong', {}, 'error');
        return false;
    }

    const currentTags = tagsContainer.querySelectorAll('.trigger-word-tag');
    const existingWords = Array.from(currentTags)
        .filter(tag => tag !== currentTag)
        .map(tag => tag.dataset.word);

    if (existingWords.includes(word)) {
        showToast('toast.triggerWords.alreadyExists', {}, 'error');
        return false;
    }

    return true;
}

/**
 * Start inline editing for a trigger word tag
 * @param {Event} e - Click event
 */
function startEditTriggerWord(e) {
    if (e.target.closest('.metadata-delete-btn') || e.target.closest('.trigger-word-edit-input')) return;

    const tag = this.closest('.trigger-word-tag');
    const section = tag?.closest('.trigger-words');
    if (!tag || !section?.classList.contains('edit-mode') || tag.classList.contains('is-editing')) return;

    e.preventDefault();
    e.stopPropagation();

    commitActiveTriggerWordEdit(section);

    const content = tag.querySelector('.trigger-word-content');
    const originalWord = tag.dataset.word;
    const originalRect = tag.getBoundingClientRect();
    if (originalRect.width > 0) {
        tag.style.setProperty('--trigger-word-edit-width', `${Math.ceil(originalRect.width)}px`);
    }
    if (originalRect.height > 0) {
        tag.style.setProperty('--trigger-word-edit-height', `${Math.ceil(originalRect.height)}px`);
    }

    const editor = document.createElement('textarea');
    editor.className = 'trigger-word-edit-input';
    editor.rows = 1;
    editor.value = originalWord;
    editor.setAttribute('aria-label', translate('modals.model.triggerWords.editWord'));
    editor.placeholder = translate('modals.model.triggerWords.editPlaceholder');

    let finished = false;
    const finish = (shouldCommit) => {
        if (finished) return;
        finished = true;

        const nextWord = editor.value.trim().replace(/\s*\n+\s*/g, ' ');
        if (shouldCommit && nextWord && nextWord !== originalWord) {
            const tagsContainer = tag.closest('.trigger-words-tags');
            if (tagsContainer && validateTriggerWord(nextWord, tagsContainer, tag)) {
                tag.dataset.word = nextWord;
                content.textContent = nextWord;
            }
        }

        editor.remove();
        content.style.display = '';
        tag.classList.remove('is-editing');
        tag.style.removeProperty('--trigger-word-edit-width');
        tag.style.removeProperty('--trigger-word-edit-height');
        updateTrainedWordsDropdown();
    };

    editor.addEventListener('click', event => event.stopPropagation());
    editor.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            event.preventDefault();
            finish(true);
        } else if (event.key === 'Escape') {
            event.preventDefault();
            finish(false);
        }
    });
    editor.addEventListener('blur', () => finish(true));

    editor.style.visibility = 'hidden';
    content.after(editor);
    tag.classList.add('is-editing');
    content.style.display = 'none';
    editor.style.visibility = '';
    editor.focus();
    editor.select();
}

/**
 * Commit an active inline trigger word edit if one exists
 * @param {HTMLElement} section - Trigger words section
 */
function commitActiveTriggerWordEdit(section) {
    const input = section.querySelector('.trigger-word-edit-input');
    if (input) {
        input.dispatchEvent(new FocusEvent('blur'));
    }
}

/**
 * Add a new trigger word
 * @param {string} word - Trigger word to add
 */
function addNewTriggerWord(word) {
    word = word.trim();
    if (!word) return;

    const triggerWordsSection = document.querySelector('.trigger-words');
    let tagsContainer = document.querySelector('.trigger-words-tags');

    // Ensure tags container exists and is visible
    if (tagsContainer) {
        tagsContainer.style.display = 'flex';
    } else {
        // Create tags container if it doesn't exist
        const contentDiv = triggerWordsSection.querySelector('.trigger-words-content');
        if (contentDiv) {
            tagsContainer = document.createElement('div');
            tagsContainer.className = 'trigger-words-tags';
            contentDiv.appendChild(tagsContainer);
        }
    }

    if (!tagsContainer) return;

    // Hide "no trigger words" message if it exists
    const noTriggerWordsMsg = triggerWordsSection.querySelector('.no-trigger-words');
    if (noTriggerWordsMsg) {
        noTriggerWordsMsg.style.display = 'none';
    }

    // Validation: Check total number
    const currentTags = tagsContainer.querySelectorAll('.trigger-word-tag');
    if (currentTags.length >= MAX_TRIGGER_WORD_GROUPS) {
        showToast('toast.triggerWords.tooMany', {}, 'error');
        return;
    }

    if (!validateTriggerWord(word, tagsContainer)) return;

    const newTag = createTriggerWordTag(word, triggerWordsSection.classList.contains('edit-mode'));
    tagsContainer.appendChild(newTag);

    // Update status of items in the trained words dropdown
    updateTrainedWordsDropdown();
}

/**
 * Update status of items in the trained words dropdown
 */
function updateTrainedWordsDropdown() {
    const dropdown = document.querySelector('.metadata-suggestions-dropdown');
    if (!dropdown) return;

    // Get all current trigger words
    const currentTags = document.querySelectorAll('.trigger-word-tag');
    const existingWords = Array.from(currentTags).map(tag => tag.dataset.word);

    // Update status of each item in dropdown
    dropdown.querySelectorAll('.metadata-suggestion-item').forEach(item => {
        const wordText = item.querySelector('.metadata-suggestion-text').textContent;
        const isAdded = existingWords.includes(wordText);

        if (isAdded) {
            item.classList.add('already-added');

            // Add indicator if it doesn't exist
            let indicator = item.querySelector('.added-indicator');
            if (!indicator) {
                const meta = item.querySelector('.metadata-suggestion-meta');
                indicator = document.createElement('span');
                indicator.className = 'added-indicator';
                indicator.innerHTML = '<i class="fas fa-check"></i>';
                meta.appendChild(indicator);
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
                    const word = item.querySelector('.metadata-suggestion-text').textContent;
                    addNewTriggerWord(word);

                    // Also populate the input field
                    const input = document.querySelector('.metadata-input');
                    if (input) input.value = word;

                    // Focus the input
                    if (input) input.focus();
                };
            }
        }
    });
}

/**
 * Save trigger words
 */
async function saveTriggerWords() {
    const editBtn = document.querySelector('.edit-trigger-words-btn');
    const filePath = editBtn.dataset.filePath;
    const triggerWordsSection = editBtn.closest('.trigger-words');

    commitActiveTriggerWordEdit(triggerWordsSection);

    // Auto-commit any pending input to prevent data loss
    const input = triggerWordsSection.querySelector('.metadata-input');
    if (input && input.value.trim()) {
        addNewTriggerWord(input.value.trim());
        input.value = '';
    }

    const triggerWordTags = triggerWordsSection.querySelectorAll('.trigger-word-tag');
    const words = Array.from(triggerWordTags).map(tag => tag.dataset.word);

    try {
        // Special format for updating nested civitai.trainedWords
        await getModelApiClient().saveModelMetadata(filePath, {
            civitai: { trainedWords: words }
        });

        // Set flag to skip restoring original words when exiting edit mode
        editBtn.dataset.skipRestore = "true";

        // Exit edit mode without restoring original trigger words
        editBtn.click();

        // If we saved an empty array and there's a no-trigger-words element, show it
        const noTriggerWords = triggerWordsSection.querySelector('.no-trigger-words');
        const tagsContainer = triggerWordsSection.querySelector('.trigger-words-tags');
        if (words.length === 0 && noTriggerWords) {
            noTriggerWords.style.display = '';
            if (tagsContainer) tagsContainer.style.display = 'none';
        }

        showToast('toast.triggerWords.updateSuccess', {}, 'success');
    } catch (error) {
        console.error('Error saving trigger words:', error);
        showToast('toast.triggerWords.updateFailed', {}, 'error');
    }
}

/**
 * Copy a trigger word to clipboard
 * @param {string} word - Word to copy
 */
window.copyTriggerWord = async function (word) {
    try {
        await copyToClipboard(word, 'Trigger word copied');
    } catch (err) {
        console.error('Copy failed:', err);
        showToast('toast.triggerWords.copyFailed', {}, 'error');
    }
};
