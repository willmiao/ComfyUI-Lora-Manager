import { showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';

/**
 * ModelDescription.js
 * Handles model description related functionality - General version
 */

/**
 * Set up tab switching functionality
 */
export function setupTabSwitching(options = {}) {
    const { onTabChange } = options;
    const tabButtons = document.querySelectorAll('.showcase-tabs .tab-btn');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', async () => {
            // Remove active class from all tabs
            document.querySelectorAll('.showcase-tabs .tab-btn').forEach(btn => 
                btn.classList.remove('active')
            );
            document.querySelectorAll('.tab-content .tab-pane').forEach(tab => 
                tab.classList.remove('active')
            );
            
            // Add active class to clicked tab
            button.classList.add('active');
            const tabId = `${button.dataset.tab}-tab`;
            document.getElementById(tabId).classList.add('active');
            
            // If switching to description tab, load content lazily
            if (button.dataset.tab === 'description') {
                await loadModelDescription();
            }

            if (typeof onTabChange === 'function') {
                try {
                    await onTabChange(button.dataset.tab);
                } catch (error) {
                    console.error('Error handling tab change:', error);
                }
            }
        });
    });
}

/**
 * Load model description lazily
 */
async function loadModelDescription() {
    const descriptionContent = document.querySelector('.model-description-content');
    const descriptionLoading = document.querySelector('.model-description-loading');
    const showcaseSection = document.querySelector('.showcase-section');
    
    if (!descriptionContent || !showcaseSection) return;
    
    // Check if already loaded
    if (descriptionContent.dataset.loaded === 'true') {
        return;
    }
    
    const filePath = showcaseSection.dataset.filepath;
    if (!filePath) return;
    
    try {
        // Show loading state
        descriptionLoading?.classList.remove('hidden');
        descriptionContent.classList.add('hidden');
        
        // Fetch description from API
        const { getModelApiClient } = await import('../../api/modelApiFactory.js');
        const description = await getModelApiClient().fetchModelDescription(filePath);
        
        // Update content
        const noDescriptionText = translate('modals.model.description.noDescription', {}, 'No model description available');
        descriptionContent.innerHTML = description || `<div class="no-description">${noDescriptionText}</div>`;
        descriptionContent.dataset.loaded = 'true';
        
        // Set up editing functionality
        await setupModelDescriptionEditing(filePath);
        
    } catch (error) {
        console.error('Error loading model description:', error);
        const failedText = translate('modals.model.description.failedToLoad', {}, 'Failed to load model description');
        descriptionContent.innerHTML = `<div class="no-description">${failedText}</div>`;
    } finally {
        // Hide loading state
        descriptionLoading?.classList.add('hidden');
        descriptionContent.classList.remove('hidden');
    }
}

/**
 * Set up model description editing functionality
 * @param {string} filePath - File path
 */
export async function setupModelDescriptionEditing(filePath) {
    const descContent = document.querySelector('.model-description-content');
    const descContainer = document.querySelector('.model-description-container');
    if (!descContent || !descContainer) return;

    // Add edit button if not present
    let editBtn = descContainer.querySelector('.edit-model-description-btn');
    if (!editBtn) {
        editBtn = document.createElement('button');
        editBtn.className = 'edit-model-description-btn';
        // Set title using i18n
        const editTitle = translate('modals.model.description.editTitle', {}, 'Edit model description');
        editBtn.title = editTitle;
        editBtn.innerHTML = '<i class="fas fa-pencil-alt"></i>';
        descContainer.insertBefore(editBtn, descContent);
    }

    // Show edit button on hover
    descContainer.addEventListener('mouseenter', () => {
        editBtn.classList.add('visible');
    });
    descContainer.addEventListener('mouseleave', () => {
        if (!descContainer.classList.contains('editing')) {
            editBtn.classList.remove('visible');
        }
    });

    // Handle edit button click
    editBtn.addEventListener('click', () => {
        descContainer.classList.add('editing');
        descContent.setAttribute('contenteditable', 'true');
        descContent.dataset.originalValue = descContent.innerHTML.trim();
        descContent.focus();

        // Place cursor at the end
        const range = document.createRange();
        const sel = window.getSelection();
        range.selectNodeContents(descContent);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);

        editBtn.classList.add('visible');
    });

    // Keyboard events
    descContent.addEventListener('keydown', function(e) {
        if (!this.getAttribute('contenteditable')) return;
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.blur();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this.innerHTML = this.dataset.originalValue;
            exitEditMode();
        }
    });

    // Save on blur
    descContent.addEventListener('blur', async function() {
        if (!this.getAttribute('contenteditable')) return;
        const newValue = this.innerHTML.trim();
        const originalValue = this.dataset.originalValue;
        if (newValue === originalValue) {
            exitEditMode();
            return;
        }
        if (!newValue) {
            this.innerHTML = originalValue;
            showToast('modals.model.description.validation.cannotBeEmpty', {}, 'error');
            exitEditMode();
            return;
        }
        try {
            // Save to backend
            const { getModelApiClient } = await import('../../api/modelApiFactory.js');
            await getModelApiClient().saveModelMetadata(filePath, { modelDescription: newValue });
            showToast('modals.model.description.messages.updated', {}, 'success');
        } catch (err) {
            this.innerHTML = originalValue;
            showToast('modals.model.description.messages.updateFailed', {}, 'error');
        } finally {
            exitEditMode();
        }
    });

    function exitEditMode() {
        descContent.removeAttribute('contenteditable');
        descContainer.classList.remove('editing');
        editBtn.classList.remove('visible');
    }
}
