import { showToast, getNSFWLevelName, openExampleImagesFolder } from '../../utils/uiHelpers.js';
import { NSFW_LEVELS } from '../../utils/constants.js';
import { getStorageItem } from '../../utils/storageHelpers.js';
import { modalManager } from '../../managers/ModalManager.js';
import { state } from '../../state/index.js';

// Mixin with shared functionality for LoraContextMenu and CheckpointContextMenu
export const ModelContextMenuMixin = {
    // NSFW Selector methods
    initNSFWSelector() {
        // Close button
        const closeBtn = this.nsfwSelector.querySelector('.close-nsfw-selector');
        closeBtn.addEventListener('click', () => {
            this.nsfwSelector.style.display = 'none';
        });

        // Level buttons
        const levelButtons = this.nsfwSelector.querySelectorAll('.nsfw-level-btn');
        levelButtons.forEach(btn => {
            btn.addEventListener('click', async () => {
                const level = parseInt(btn.dataset.level);
                const filePath = this.nsfwSelector.dataset.cardPath;
                
                if (!filePath) return;
                
                try {
                    await this.saveModelMetadata(filePath, { preview_nsfw_level: level });
                    
                    showToast(`Content rating set to ${getNSFWLevelName(level)}`, 'success');
                    this.nsfwSelector.style.display = 'none';
                } catch (error) {
                    showToast(`Failed to set content rating: ${error.message}`, 'error');
                }
            });
        });
        
        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (this.nsfwSelector.style.display === 'block' && 
                !this.nsfwSelector.contains(e.target) && 
                !e.target.closest('.context-menu-item[data-action="set-nsfw"]')) {
                this.nsfwSelector.style.display = 'none';
            }
        });
    },

    updateCardBlurEffect(card, level) {
        // Get user settings for blur threshold
        const blurThreshold = parseInt(getStorageItem('nsfwBlurLevel') || '4');
        
        // Get card preview container
        const previewContainer = card.querySelector('.card-preview');
        if (!previewContainer) return;
        
        // Get preview media element
        const previewMedia = previewContainer.querySelector('img') || previewContainer.querySelector('video');
        if (!previewMedia) return;
        
        // Check if blur should be applied
        if (level >= blurThreshold) {
            // Add blur class to the preview container
            previewContainer.classList.add('blurred');
            
            // Get or create the NSFW overlay
            let nsfwOverlay = previewContainer.querySelector('.nsfw-overlay');
            if (!nsfwOverlay) {
                // Create new overlay
                nsfwOverlay = document.createElement('div');
                nsfwOverlay.className = 'nsfw-overlay';
                
                // Create and configure the warning content
                const warningContent = document.createElement('div');
                warningContent.className = 'nsfw-warning';
                
                // Determine NSFW warning text based on level
                let nsfwText = "Mature Content";
                if (level >= NSFW_LEVELS.XXX) {
                    nsfwText = "XXX-rated Content";
                } else if (level >= NSFW_LEVELS.X) {
                    nsfwText = "X-rated Content";
                } else if (level >= NSFW_LEVELS.R) {
                    nsfwText = "R-rated Content";
                }
                
                // Add warning text and show button
                warningContent.innerHTML = `
                    <p>${nsfwText}</p>
                    <button class="show-content-btn">Show</button>
                `;
                
                // Add click event to the show button
                const showBtn = warningContent.querySelector('.show-content-btn');
                showBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    previewContainer.classList.remove('blurred');
                    nsfwOverlay.style.display = 'none';
                    
                    // Update toggle button icon if it exists
                    const toggleBtn = card.querySelector('.toggle-blur-btn');
                    if (toggleBtn) {
                        toggleBtn.querySelector('i').className = 'fas fa-eye-slash';
                    }
                });
                
                nsfwOverlay.appendChild(warningContent);
                previewContainer.appendChild(nsfwOverlay);
            } else {
                // Update existing overlay
                const warningText = nsfwOverlay.querySelector('p');
                if (warningText) {
                    let nsfwText = "Mature Content";
                    if (level >= NSFW_LEVELS.XXX) {
                        nsfwText = "XXX-rated Content";
                    } else if (level >= NSFW_LEVELS.X) {
                        nsfwText = "X-rated Content";
                    } else if (level >= NSFW_LEVELS.R) {
                        nsfwText = "R-rated Content";
                    }
                    warningText.textContent = nsfwText;
                }
                nsfwOverlay.style.display = 'flex';
            }
            
            // Get or create the toggle button in the header
            const cardHeader = previewContainer.querySelector('.card-header');
            if (cardHeader) {
                let toggleBtn = cardHeader.querySelector('.toggle-blur-btn');
                
                if (!toggleBtn) {
                    toggleBtn = document.createElement('button');
                    toggleBtn.className = 'toggle-blur-btn';
                    toggleBtn.title = 'Toggle blur';
                    toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
                    
                    // Add click event to toggle button
                    toggleBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const isBlurred = previewContainer.classList.toggle('blurred');
                        const icon = toggleBtn.querySelector('i');
                        
                        // Update icon and overlay visibility
                        if (isBlurred) {
                            icon.className = 'fas fa-eye';
                            nsfwOverlay.style.display = 'flex';
                        } else {
                            icon.className = 'fas fa-eye-slash';
                            nsfwOverlay.style.display = 'none';
                        }
                    });
                    
                    // Add to the beginning of header
                    cardHeader.insertBefore(toggleBtn, cardHeader.firstChild);
                    
                    // Update base model label class
                    const baseModelLabel = cardHeader.querySelector('.base-model-label');
                    if (baseModelLabel && !baseModelLabel.classList.contains('with-toggle')) {
                        baseModelLabel.classList.add('with-toggle');
                    }
                } else {
                    // Update existing toggle button
                    toggleBtn.querySelector('i').className = 'fas fa-eye';
                }
            }
        } else {
            // Remove blur
            previewContainer.classList.remove('blurred');
            
            // Hide overlay if it exists
            const overlay = previewContainer.querySelector('.nsfw-overlay');
            if (overlay) overlay.style.display = 'none';
            
            // Remove toggle button when content is set to PG or PG13
            const cardHeader = previewContainer.querySelector('.card-header');
            if (cardHeader) {
                const toggleBtn = cardHeader.querySelector('.toggle-blur-btn');
                if (toggleBtn) {
                    // Remove the toggle button completely
                    toggleBtn.remove();
                    
                    // Update base model label class if it exists
                    const baseModelLabel = cardHeader.querySelector('.base-model-label');
                    if (baseModelLabel && baseModelLabel.classList.contains('with-toggle')) {
                        baseModelLabel.classList.remove('with-toggle');
                    }
                }
            }
        }
    },

    showNSFWLevelSelector(x, y, card) {
        const selector = document.getElementById('nsfwLevelSelector');
        const currentLevelEl = document.getElementById('currentNSFWLevel');
        
        // Get current NSFW level
        let currentLevel = 0;
        try {
            const metaData = JSON.parse(card.dataset.meta || '{}');
            currentLevel = metaData.preview_nsfw_level || 0;
            
            // Update if we have no recorded level but have a dataset attribute
            if (!currentLevel && card.dataset.nsfwLevel) {
                currentLevel = parseInt(card.dataset.nsfwLevel) || 0;
            }
        } catch (err) {
            console.error('Error parsing metadata:', err);
        }
        
        currentLevelEl.textContent = getNSFWLevelName(currentLevel);
        
        // Position the selector
        if (x && y) {
            const viewportWidth = document.documentElement.clientWidth;
            const viewportHeight = document.documentElement.clientHeight;
            const selectorRect = selector.getBoundingClientRect();
            
            // Center the selector if no coordinates provided
            let finalX = (viewportWidth - selectorRect.width) / 2;
            let finalY = (viewportHeight - selectorRect.height) / 2;
            
            selector.style.left = `${finalX}px`;
            selector.style.top = `${finalY}px`;
        }
        
        // Highlight current level button
        document.querySelectorAll('.nsfw-level-btn').forEach(btn => {
            if (parseInt(btn.dataset.level) === currentLevel) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        
        // Store reference to current card
        selector.dataset.cardPath = card.dataset.filepath;
        
        // Show selector
        selector.style.display = 'block';
    },

    // Civitai re-linking methods
    showRelinkCivitaiModal() {
        const filePath = this.currentCard.dataset.filepath;
        if (!filePath) return;
        
        // Set up confirm button handler
        const confirmBtn = document.getElementById('confirmRelinkBtn');
        const urlInput = document.getElementById('civitaiModelUrl');
        const errorDiv = document.getElementById('civitaiModelUrlError');
        
        // Remove previous event listener if exists
        if (this._boundRelinkHandler) {
            confirmBtn.removeEventListener('click', this._boundRelinkHandler);
        }
        
        // Create new bound handler
        this._boundRelinkHandler = async () => {
            const url = urlInput.value.trim();
            const { modelId, modelVersionId } = this.extractModelVersionId(url);
            
            if (!modelId) {
                errorDiv.textContent = 'Invalid URL format. Must include model ID.';
                return;
            }
            
            errorDiv.textContent = '';
            modalManager.closeModal('relinkCivitaiModal');
            
            try {
                state.loadingManager.showSimpleLoading('Re-linking to Civitai...');
                
                const endpoint = this.modelType === 'checkpoint' ? 
                    '/api/checkpoints/relink-civitai' : 
                    '/api/relink-civitai';
                
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        file_path: filePath,
                        model_id: modelId,
                        model_version_id: modelVersionId
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`Failed to re-link model: ${response.statusText}`);
                }
                
                const data = await response.json();
                
                if (data.success) {
                    showToast('Model successfully re-linked to Civitai', 'success');
                    // Reload the current view to show updated data
                    await this.resetAndReload();
                } else {
                    throw new Error(data.error || 'Failed to re-link model');
                }
            } catch (error) {
                console.error('Error re-linking model:', error);
                showToast(`Error: ${error.message}`, 'error');
            } finally {
                state.loadingManager.hide();
            }
        };
        
        // Set new event listener
        confirmBtn.addEventListener('click', this._boundRelinkHandler);
        
        // Clear previous input
        urlInput.value = '';
        errorDiv.textContent = '';
        
        // Show modal
        modalManager.showModal('relinkCivitaiModal');
        
        // Auto-focus the URL input field after modal is shown
        setTimeout(() => urlInput.focus(), 50);
    },

    extractModelVersionId(url) {
        try {
            // Handle all three URL formats:
            // 1. https://civitai.com/models/649516
            // 2. https://civitai.com/models/649516?modelVersionId=726676
            // 3. https://civitai.com/models/649516/cynthia-pokemon-diamond-and-pearl-pdxl-lora?modelVersionId=726676
            
            const parsedUrl = new URL(url);
            
            // Extract model ID from path
            const pathMatch = parsedUrl.pathname.match(/\/models\/(\d+)/);
            const modelId = pathMatch ? pathMatch[1] : null;
            
            // Extract model version ID from query parameters
            const modelVersionId = parsedUrl.searchParams.get('modelVersionId');
            
            return { modelId, modelVersionId };
        } catch (e) {
            return { modelId: null, modelVersionId: null };
        }
    },
    
    // Common action handlers
    handleCommonMenuActions(action) {
        switch(action) {
            case 'preview':
                openExampleImagesFolder(this.currentCard.dataset.sha256);
                return true;
            case 'civitai':
                if (this.currentCard.dataset.from_civitai === 'true') {
                    if (this.currentCard.querySelector('.fa-globe')) {
                        this.currentCard.querySelector('.fa-globe').click();
                    } else {
                        showToast('Please fetch metadata from CivitAI first', 'info');
                    }
                } else {
                    showToast('No CivitAI information available', 'info');
                }
                return true;
            case 'relink-civitai':
                this.showRelinkCivitaiModal();
                return true;
            case 'set-nsfw':
                this.showNSFWLevelSelector(null, null, this.currentCard);
                return true;
            default:
                return false;
        }
    }
};
