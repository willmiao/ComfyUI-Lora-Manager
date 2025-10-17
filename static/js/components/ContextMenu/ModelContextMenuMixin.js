import { showToast, getNSFWLevelName, openExampleImagesFolder } from '../../utils/uiHelpers.js';
import { modalManager } from '../../managers/ModalManager.js';
import { state } from '../../state/index.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { bulkManager } from '../../managers/BulkManager.js';

// Mixin with shared functionality for LoraContextMenu and CheckpointContextMenu
export const ModelContextMenuMixin = {
    // NSFW Selector methods
    initNSFWSelector() {
        // Remove any existing event listeners by cloning and replacing elements
        // This is a simple way to ensure we don't have duplicate event listeners
        const closeBtn = this.nsfwSelector.querySelector('.close-nsfw-selector');
        const newCloseBtn = closeBtn.cloneNode(true);
        closeBtn.parentNode.replaceChild(newCloseBtn, closeBtn);
        newCloseBtn.addEventListener('click', () => {
            this.nsfwSelector.style.display = 'none';
            this.resetNSFWSelectorState();
        });

        // Level buttons
        const levelButtons = this.nsfwSelector.querySelectorAll('.nsfw-level-btn');
        levelButtons.forEach(btn => {
            // Remove any existing event listeners by cloning and replacing the button
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            
            newBtn.addEventListener('click', async () => {
                const level = parseInt(newBtn.dataset.level);
                const mode = this.nsfwSelector.dataset.mode || 'single';

                if (mode === 'bulk') {
                    let bulkFilePaths = [];
                    if (this.nsfwSelector.dataset.bulkFilePaths) {
                        try {
                            bulkFilePaths = JSON.parse(this.nsfwSelector.dataset.bulkFilePaths);
                        } catch (error) {
                            console.warn('Failed to parse bulk file paths for content rating', error);
                        }
                    }

                    const success = await bulkManager.setBulkContentRating(level, bulkFilePaths);
                    if (success) {
                        this.nsfwSelector.style.display = 'none';
                        this.resetNSFWSelectorState();
                    }
                    return;
                }

                const filePath = this.nsfwSelector.dataset.cardPath;

                if (!filePath) return;

                try {
                    await this.saveModelMetadata(filePath, { preview_nsfw_level: level });

                    showToast('toast.contextMenu.contentRatingSet', { level: getNSFWLevelName(level) }, 'success');
                    this.nsfwSelector.style.display = 'none';
                    this.resetNSFWSelectorState();
                } catch (error) {
                    showToast('toast.contextMenu.contentRatingFailed', { message: error.message }, 'error');
                }
            });
        });

        // Close when clicking outside - use a named function so we can remove it later
        const outsideClickListener = (e) => {
            if (this.nsfwSelector.style.display === 'block' &&
                !this.nsfwSelector.contains(e.target) &&
                !e.target.closest('.context-menu-item[data-action="set-nsfw"], .context-menu-item[data-action="set-content-rating"]')) {
                this.nsfwSelector.style.display = 'none';
                this.resetNSFWSelectorState();
            }
        };
        
        // Remove previous listener if it exists
        if (this._outsideClickListener) {
            document.removeEventListener('click', this._outsideClickListener);
        }
        
        // Store and add new listener
        this._outsideClickListener = outsideClickListener;
        document.addEventListener('click', this._outsideClickListener);
    },

    resetNSFWSelectorState() {
        if (!this.nsfwSelector) return;
        delete this.nsfwSelector.dataset.bulkFilePaths;
        delete this.nsfwSelector.dataset.mode;
        delete this.nsfwSelector.dataset.cardPath;
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
        selector.querySelectorAll('.nsfw-level-btn').forEach(btn => {
            if (parseInt(btn.dataset.level) === currentLevel) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        // Store reference to current card
        selector.dataset.mode = 'single';
        selector.dataset.cardPath = card.dataset.filepath;
        delete selector.dataset.bulkFilePaths;

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
                    '/api/lm/checkpoints/relink-civitai' : 
                    '/api/lm/loras/relink-civitai';
                
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
                    showToast('toast.contextMenu.relinkSuccess', {}, 'success');
                    // Reload the current view to show updated data
                    await this.resetAndReload();
                } else {
                    throw new Error(data.error || 'Failed to re-link model');
                }
            } catch (error) {
                console.error('Error re-linking model:', error);
                showToast('toast.contextMenu.relinkFailed', { message: error.message }, 'error');
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
            case 'download-examples':
                this.downloadExampleImages();
                return true;
            case 'civitai':
                if (this.currentCard.dataset.from_civitai === 'true') {
                    if (this.currentCard.querySelector('.fa-globe')) {
                        this.currentCard.querySelector('.fa-globe').click();
                    } else {
                        showToast('toast.contextMenu.fetchMetadataFirst', {}, 'info');
                    }
                } else {
                    showToast('toast.contextMenu.noCivitaiInfo', {}, 'info');
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
    },

    // Download example images method
    async downloadExampleImages() {
        const modelHash = this.currentCard.dataset.sha256;
        if (!modelHash) {
            showToast('toast.contextMenu.missingHash', {}, 'error');
            return;
        }

        try { 
            const apiClient = getModelApiClient();
            await apiClient.downloadExampleImages([modelHash]);
        } catch (error) {
            console.error('Error downloading example images:', error);
        }
    }
};
