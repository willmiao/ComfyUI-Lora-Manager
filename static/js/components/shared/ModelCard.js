import { showToast, openCivitai, copyToClipboard, copyLoraSyntax, sendLoraToWorkflow, openExampleImagesFolder, buildLoraSyntax, sendModelPathToWorkflow } from '../../utils/uiHelpers.js';
import { state, getCurrentPageState } from '../../state/index.js';
import { showModelModal } from './ModelModal.js';
import { toggleShowcase } from './showcase/ShowcaseView.js';
import { bulkManager } from '../../managers/BulkManager.js';
import { modalManager } from '../../managers/ModalManager.js';
import { NSFW_LEVELS, getBaseModelAbbreviation } from '../../utils/constants.js';
import { MODEL_TYPES } from '../../api/apiConfig.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { showDeleteModal } from '../../utils/modalUtils.js';
import { translate } from '../../utils/i18nHelpers.js';
import { eventManager } from '../../utils/EventManager.js';

// Helper function to get display name based on settings
function getDisplayName(model) {
    const displayNameSetting = state.global.settings.model_name_display || 'model_name';
    
    if (displayNameSetting === 'file_name') {
        return model.file_name || model.model_name || 'Unknown Model';
    }
    
    return model.model_name || model.file_name || 'Unknown Model';
}

// Add global event delegation handlers using event manager
export function setupModelCardEventDelegation(modelType) {
    // Remove any existing handler first
    eventManager.removeHandler('click', 'modelCard-delegation');
    
    // Register model card event delegation with event manager
    eventManager.addHandler('click', 'modelCard-delegation', (event) => {
        return handleModelCardEvent_internal(event, modelType);
    }, {
        priority: 60, // Medium priority for model card interactions
        targetSelector: '#modelGrid',
        skipWhenModalOpen: false // Allow model card interactions even when modals are open (for some actions)
    });
}

// Event delegation handler for all model card events
function handleModelCardEvent_internal(event, modelType) {
    // Find the closest card element
    const card = event.target.closest('.model-card');
    if (!card) return false; // Continue with other handlers
    
    // Handle specific elements within the card
    if (event.target.closest('.toggle-blur-btn')) {
        event.stopPropagation();
        toggleBlurContent(card);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.show-content-btn')) {
        event.stopPropagation();
        showBlurredContent(card);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-star')) {
        event.stopPropagation();
        toggleFavorite(card);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-globe')) {
        event.stopPropagation();
        if (card.dataset.from_civitai === 'true') {
            openCivitai(card.dataset.filepath);
        }
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-paper-plane')) {
        event.stopPropagation();
        handleSendToWorkflow(card, event.shiftKey, modelType);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-copy')) {
        event.stopPropagation();
        handleCopyAction(card, modelType);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-trash')) {
        event.stopPropagation();
        showDeleteModal(card.dataset.filepath);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-image')) {
        event.stopPropagation();
        getModelApiClient().replaceModelPreview(card.dataset.filepath);
        return true; // Stop propagation
    }
    
    if (event.target.closest('.fa-folder-open')) {
        event.stopPropagation();
        handleExampleImagesAccess(card, modelType);
        return true; // Stop propagation
    }
    
    // If no specific element was clicked, handle the card click (show modal or toggle selection)
    handleCardClick(card, modelType);
    return false; // Continue with other handlers (e.g., bulk selection)
}

// Helper functions for event handling
function toggleBlurContent(card) {
    const preview = card.querySelector('.card-preview');
    const isBlurred = preview.classList.toggle('blurred');
    const icon = card.querySelector('.toggle-blur-btn i');
    
    // Update the icon based on blur state
    if (isBlurred) {
        icon.className = 'fas fa-eye';
    } else {
        icon.className = 'fas fa-eye-slash';
    }
    
    // Toggle the overlay visibility
    const overlay = card.querySelector('.nsfw-overlay');
    if (overlay) {
        overlay.style.display = isBlurred ? 'flex' : 'none';
    }
}

function showBlurredContent(card) {
    const preview = card.querySelector('.card-preview');
    preview.classList.remove('blurred');
    
    // Update the toggle button icon
    const toggleBtn = card.querySelector('.toggle-blur-btn');
    if (toggleBtn) {
        toggleBtn.querySelector('i').className = 'fas fa-eye-slash';
    }
    
    // Hide the overlay
    const overlay = card.querySelector('.nsfw-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

async function toggleFavorite(card) {
    const starIcon = card.querySelector('.fa-star');
    const isFavorite = starIcon.classList.contains('fas');
    const newFavoriteState = !isFavorite;
    
    try {
        await getModelApiClient().saveModelMetadata(card.dataset.filepath, { 
            favorite: newFavoriteState 
        });

        if (newFavoriteState) {
            showToast('modelCard.favorites.added', {}, 'success');
        } else {
            showToast('modelCard.favorites.removed', {}, 'success');
        }
    } catch (error) {
        console.error('Failed to update favorite status:', error);
        showToast('modelCard.favorites.updateFailed', {}, 'error');
    }
}

function handleSendToWorkflow(card, replaceMode, modelType) {
    if (modelType === MODEL_TYPES.LORA) {
        const usageTips = JSON.parse(card.dataset.usage_tips || '{}');
        const loraSyntax = buildLoraSyntax(card.dataset.file_name, usageTips);
        sendLoraToWorkflow(loraSyntax, replaceMode, 'lora');
    } else if (modelType === MODEL_TYPES.CHECKPOINT) {
        const modelPath = card.dataset.filepath;
        if (!modelPath) {
            const message = translate('modelCard.sendToWorkflow.missingPath', {}, 'Unable to determine model path for this card');
            showToast(message, {}, 'error');
            return;
        }

        const subtype = (card.dataset.model_type || 'checkpoint').toLowerCase();
        const isDiffusionModel = subtype === 'diffusion_model';
        const widgetName = isDiffusionModel ? 'unet_name' : 'ckpt_name';
        const actionTypeText = translate(
            isDiffusionModel ? 'uiHelpers.nodeSelector.diffusionModel' : 'uiHelpers.nodeSelector.checkpoint',
            {},
            isDiffusionModel ? 'Diffusion Model' : 'Checkpoint'
        );
        const successMessage = translate(
            isDiffusionModel ? 'uiHelpers.workflow.diffusionModelUpdated' : 'uiHelpers.workflow.checkpointUpdated',
            {},
            isDiffusionModel ? 'Diffusion model updated in workflow' : 'Checkpoint updated in workflow'
        );
        const failureMessage = translate(
            isDiffusionModel ? 'uiHelpers.workflow.diffusionModelFailed' : 'uiHelpers.workflow.checkpointFailed',
            {},
            isDiffusionModel ? 'Failed to update diffusion model node' : 'Failed to update checkpoint node'
        );
        const missingNodesMessage = translate(
            'uiHelpers.workflow.noMatchingNodes',
            {},
            'No compatible nodes available in the current workflow'
        );
        const missingTargetMessage = translate(
            'uiHelpers.workflow.noTargetNodeSelected',
            {},
            'No target node selected'
        );

        sendModelPathToWorkflow(modelPath, {
            widgetName,
            collectionType: MODEL_TYPES.CHECKPOINT,
            actionTypeText,
            successMessage,
            failureMessage,
            missingNodesMessage,
            missingTargetMessage,
        });
    } else {
        showToast('modelCard.sendToWorkflow.checkpointNotImplemented', {}, 'info');
    }
}

function handleCopyAction(card, modelType) {
    if (modelType === MODEL_TYPES.LORA) {
        copyLoraSyntax(card);
    } else if (modelType === MODEL_TYPES.CHECKPOINT) {
        // Checkpoint copy functionality - copy checkpoint name
        const checkpointName = card.dataset.file_name;
        const message = translate('modelCard.actions.checkpointNameCopied', {}, 'Checkpoint name copied');
        copyToClipboard(checkpointName, message);
    } else if (modelType === MODEL_TYPES.EMBEDDING) {
        const embeddingName = card.dataset.file_name;
        copyToClipboard(embeddingName, 'Embedding name copied');
    }
}

function handleReplacePreview(filePath, modelType) {
    apiClient.replaceModelPreview(filePath);
}

async function handleExampleImagesAccess(card, modelType) {
    const modelHash = card.dataset.sha256;
    
    try {
        const response = await fetch(`/api/lm/has-example-images?model_hash=${modelHash}`);
        const data = await response.json();
        
        if (data.has_images) {
            openExampleImagesFolder(modelHash);
        } else {
            showExampleAccessModal(card, modelType);
        }
    } catch (error) {
        console.error('Error checking for example images:', error);
        showToast('modelCard.exampleImages.checkError', {}, 'error');
    }
}

function handleCardClick(card, modelType) {
    const pageState = getCurrentPageState();
    
    if (state.bulkMode) {
        // Toggle selection using the bulk manager
        bulkManager.toggleCardSelection(card);
    } else if (pageState && pageState.duplicatesMode) {
        // In duplicates mode, don't open modal when clicking cards
        return;
    } else {
        // Normal behavior - show modal
        showModelModalFromCard(card, modelType);
    }
}

async function showModelModalFromCard(card, modelType) {
    // Create model metadata object
    const modelMeta = {
        sha256: card.dataset.sha256,
        file_path: card.dataset.filepath,
        model_name: card.dataset.name,
        file_name: card.dataset.file_name,
        folder: card.dataset.folder,
        modified: card.dataset.modified,
        file_size: parseInt(card.dataset.file_size || '0'),
        from_civitai: card.dataset.from_civitai === 'true',
        base_model: card.dataset.base_model,
        notes: card.dataset.notes || '',
        favorite: card.dataset.favorite === 'true',
        // Parse civitai metadata from the card's dataset
        civitai: JSON.parse(card.dataset.meta || '{}'),
        tags: JSON.parse(card.dataset.tags || '[]'),
        update_available: card.dataset.update_available === 'true',
        modelDescription: card.dataset.modelDescription || '',
        // LoRA specific fields
        ...(modelType === MODEL_TYPES.LORA && {
            usage_tips: card.dataset.usage_tips,
        })
    };
    
    await showModelModal(modelMeta, modelType);
}

// Function to show the example access modal (generalized for lora and checkpoint)
function showExampleAccessModal(card, modelType) {
    const modal = document.getElementById('exampleAccessModal');
    if (!modal) return;

    // Get download button and determine if download should be enabled
    const downloadBtn = modal.querySelector('#downloadExamplesBtn');
    let hasRemoteExamples = false;

    try {
        const metaData = JSON.parse(card.dataset.meta || '{}');
        hasRemoteExamples = metaData.images &&
                            Array.isArray(metaData.images) &&
                            metaData.images.length > 0 &&
                            metaData.images[0].url;
    } catch (e) {
        console.error('Error parsing meta data:', e);
    }

    // Enable or disable download button
    if (downloadBtn) {
        if (hasRemoteExamples) {
            downloadBtn.classList.remove('disabled');
            downloadBtn.removeAttribute('title');
            downloadBtn.onclick = async () => {
                // Get the model hash
                const modelHash = card.dataset.sha256;
                if (!modelHash) {
                    showToast('modelCard.exampleImages.missingHash', {}, 'error');
                    return;
                }
                
                // Close the modal
                modalManager.closeModal('exampleAccessModal');
                
                try {
                    // Use the appropriate model API client to download examples
                    const apiClient = getModelApiClient(modelType);
                    await apiClient.downloadExampleImages([modelHash]);

                    // Open the example images folder if successful
                    openExampleImagesFolder(modelHash);
                } catch (error) {
                    console.error('Error downloading example images:', error);
                    // Error already shown by the API client
                }
            };
        } else {
            downloadBtn.classList.add('disabled');
            const noRemoteImagesTitle = translate('modelCard.exampleImages.noRemoteImagesAvailable', {}, 'No remote example images available for this model on Civitai');
            downloadBtn.setAttribute('title', noRemoteImagesTitle);
            downloadBtn.onclick = null;
        }
    }

    // Set up import button
    const importBtn = modal.querySelector('#importExamplesBtn');
    if (importBtn) {
        importBtn.onclick = async () => {
            modalManager.closeModal('exampleAccessModal');

            // Get the model data from card dataset (works for both lora and checkpoint)
            const modelMeta = {
                sha256: card.dataset.sha256,
                file_path: card.dataset.filepath,
                model_name: card.dataset.name,
                file_name: card.dataset.file_name,
                folder: card.dataset.folder,
                modified: card.dataset.modified,
                file_size: card.dataset.file_size,
                from_civitai: card.dataset.from_civitai === 'true',
                base_model: card.dataset.base_model,
                notes: card.dataset.notes,
                favorite: card.dataset.favorite === 'true',
                civitai: JSON.parse(card.dataset.meta || '{}'),
                tags: JSON.parse(card.dataset.tags || '[]'),
                modelDescription: card.dataset.modelDescription || ''
            };

            // Add usage_tips if present (for lora)
            if (card.dataset.usage_tips) {
                modelMeta.usage_tips = card.dataset.usage_tips;
            }

            // Show the model modal
            await showModelModal(modelMeta, modelType);

            // Scroll to import area after modal is visible
            setTimeout(() => {
                const importArea = document.querySelector('.example-import-area');
                if (importArea) {
                    const showcaseTab = document.getElementById('showcase-tab');
                    if (showcaseTab) {
                        // First make sure showcase tab is visible
                        const tabBtn = document.querySelector('.tab-btn[data-tab="showcase"]');
                        if (tabBtn && !tabBtn.classList.contains('active')) {
                            tabBtn.click();
                        }

                        // Then toggle showcase if collapsed
                        const carousel = showcaseTab.querySelector('.carousel');
                        if (carousel && carousel.classList.contains('collapsed')) {
                            const scrollIndicator = showcaseTab.querySelector('.scroll-indicator');
                            if (scrollIndicator) {
                                toggleShowcase(scrollIndicator);
                            }
                        }

                        // Finally scroll to the import area
                        importArea.scrollIntoView({ behavior: 'smooth' });
                    }
                }
            }, 500);
        };
    }

    // Show the modal
    modalManager.showModal('exampleAccessModal');
}

export function createModelCard(model, modelType) {
    const card = document.createElement('div');
    card.className = 'model-card';  // Reuse the same class for styling
    card.draggable = true;
    card.dataset.sha256 = model.sha256;
    card.dataset.filepath = model.file_path;
    card.dataset.name = model.model_name;
    card.dataset.file_name = model.file_name;
    card.dataset.folder = model.folder || '';
    card.dataset.modified = model.modified;
    card.dataset.file_size = model.file_size;
    card.dataset.from_civitai = model.from_civitai;
    card.dataset.notes = model.notes || '';
    card.dataset.base_model = model.base_model || 'Unknown';
    card.dataset.favorite = model.favorite ? 'true' : 'false';
    const hasUpdateAvailable = Boolean(model.update_available);
    card.dataset.update_available = hasUpdateAvailable ? 'true' : 'false';

    const civitaiData = model.civitai || {};
    const modelId = civitaiData?.modelId ?? civitaiData?.model_id;
    if (modelId !== undefined && modelId !== null && modelId !== '') {
        card.dataset.modelId = modelId;
    }

    // LoRA specific data
    if (modelType === MODEL_TYPES.LORA) {
        card.dataset.usage_tips = model.usage_tips;
    }

    // checkpoint specific data
    if (modelType === MODEL_TYPES.CHECKPOINT) {
        card.dataset.model_type = model.model_type; // checkpoint or diffusion_model
    }

    // Store metadata if available
    if (model.civitai) {
        card.dataset.meta = JSON.stringify(model.civitai || {});
    }
    
    // Store tags if available
    if (model.tags && Array.isArray(model.tags)) {
        card.dataset.tags = JSON.stringify(model.tags);
    }

    if (model.modelDescription) {
        card.dataset.modelDescription = model.modelDescription;
    }

    // Store NSFW level if available
    const nsfwLevel = model.preview_nsfw_level !== undefined ? model.preview_nsfw_level : 0;
    card.dataset.nsfwLevel = nsfwLevel;
    
    // Determine if the preview should be blurred based on NSFW level and user settings
    const shouldBlur = state.settings.blur_mature_content && nsfwLevel > NSFW_LEVELS.PG13;
    if (shouldBlur) {
        card.classList.add('nsfw-content');
    }

    // Apply selection state if in bulk mode and this card is in the selected set (LoRA only)
    if (modelType === MODEL_TYPES.LORA && state.bulkMode && state.selectedLoras.has(model.file_path)) {
        card.classList.add('selected');
    }

    // Get the appropriate preview versions map
    const previewVersionsKey = modelType;
    const previewVersions = state.pages[previewVersionsKey]?.previewVersions || new Map();
    const version = previewVersions.get(model.file_path);
    const previewUrl = model.preview_url || '/loras_static/images/no-preview.png';
    const versionedPreviewUrl = version ? `${previewUrl}${previewUrl.includes('?') ? '&' : '?'}t=${version}` : previewUrl;

    // Determine NSFW warning text based on level with i18n support
    let nsfwText = translate('modelCard.nsfw.matureContent', {}, 'Mature Content');
    if (nsfwLevel >= NSFW_LEVELS.XXX) {
        nsfwText = translate('modelCard.nsfw.xxxRated', {}, 'XXX-rated Content');
    } else if (nsfwLevel >= NSFW_LEVELS.X) {
        nsfwText = translate('modelCard.nsfw.xRated', {}, 'X-rated Content');
    } else if (nsfwLevel >= NSFW_LEVELS.R) {
        nsfwText = translate('modelCard.nsfw.rRated', {}, 'R-rated Content');
    }

    // Check if autoplayOnHover is enabled for video previews
    const autoplayOnHover = state.global?.settings?.autoplay_on_hover || false;
    const isVideo = previewUrl.endsWith('.mp4');
    const videoAttrs = [
        'controls',
        'muted',
        'loop',
        'playsinline',
        'preload="none"',
        `data-src="${versionedPreviewUrl}"`
    ];

    if (!autoplayOnHover) {
        videoAttrs.push('data-autoplay="true"');
    }

    // Get favorite status from model data
    const isFavorite = model.favorite === true;
    if (hasUpdateAvailable) {
        card.classList.add('has-update');
    }

    // Generate action icons based on model type with i18n support
    const favoriteTitle = isFavorite ? 
        translate('modelCard.actions.removeFromFavorites', {}, 'Remove from favorites') :
        translate('modelCard.actions.addToFavorites', {}, 'Add to favorites');
    const globeTitle = model.from_civitai ? 
        translate('modelCard.actions.viewOnCivitai', {}, 'View on Civitai') :
        translate('modelCard.actions.notAvailableFromCivitai', {}, 'Not available from Civitai');
    let sendTitle;
    let copyTitle;
    if (modelType === MODEL_TYPES.LORA) {
        sendTitle = translate('modelCard.actions.sendToWorkflow', {}, 'Send to ComfyUI (Click: Append, Shift+Click: Replace)');
        copyTitle = translate('modelCard.actions.copyLoRASyntax', {}, 'Copy LoRA Syntax');
    } else if (modelType === MODEL_TYPES.CHECKPOINT) {
        sendTitle = translate('modelCard.actions.sendCheckpointToWorkflow', {}, 'Send to ComfyUI');
        copyTitle = translate('modelCard.actions.copyCheckpointName', {}, 'Copy checkpoint name');
    } else if (modelType === MODEL_TYPES.EMBEDDING) {
        sendTitle = translate('modelCard.actions.sendEmbeddingToWorkflow', {}, 'Send to ComfyUI');
        copyTitle = translate('modelCard.actions.copyEmbeddingName', {}, 'Copy embedding name');
    } else {
        sendTitle = translate('modelCard.actions.sendToWorkflow', {}, 'Send to ComfyUI');
        copyTitle = translate('modelCard.actions.copyLoRASyntax', {}, 'Copy value');
    }

    const updateBadgeLabel = translate('modelCard.badges.update', {}, 'Update');
    const updateBadgeTooltip = translate('modelCard.badges.updateAvailable', {}, 'Update available');
    const actionIcons = `
        <i class="${isFavorite ? 'fas fa-star favorite-active' : 'far fa-star'}" 
           title="${favoriteTitle}">
        </i>
        <i class="fas fa-globe" 
           title="${globeTitle}"
           ${!model.from_civitai ? 'style="opacity: 0.5; cursor: not-allowed"' : ''}>
        </i>
        <i class="fas fa-paper-plane" 
           title="${sendTitle}">
        </i>
        <i class="fas fa-copy" 
           title="${copyTitle}">
        </i>`;

    // Generate UI text with i18n support
    const toggleBlurTitle = translate('modelCard.actions.toggleBlur', {}, 'Toggle blur');
    const showButtonText = translate('modelCard.actions.show', {}, 'Show');
    const footerActionSetting = state.global.settings.model_card_footer_action || 'example_images';
    const footerActionTitle = footerActionSetting === 'replace_preview'
        ? translate('modelCard.actions.replacePreview', {}, 'Replace Preview')
        : translate('modelCard.actions.openExampleImages', {}, 'Open Example Images Folder');
    const footerActionIcon = footerActionSetting === 'replace_preview'
        ? 'fas fa-image'
        : 'fas fa-folder-open';

    const baseModelLabel = model.base_model || 'Unknown';
    const baseModelAbbreviation = getBaseModelAbbreviation(baseModelLabel);

    card.innerHTML = `
        <div class="card-preview ${shouldBlur ? 'blurred' : ''}">
            ${isVideo ? 
                `<video ${videoAttrs.join(' ')} style="pointer-events: none;"></video>` :
                `<img src="${versionedPreviewUrl}" alt="${model.model_name}">`
            }
            <div class="card-header">
                ${shouldBlur ? 
                  `<button class="toggle-blur-btn" title="${toggleBlurTitle}">
                      <i class="fas fa-eye"></i>
                  </button>` : ''}
                <div class="card-header-info">
                    <span class="base-model-label ${shouldBlur ? 'with-toggle' : ''}" title="${baseModelLabel}">
                        ${baseModelAbbreviation}
                    </span>
                    ${hasUpdateAvailable ? `
                        <span class="model-update-badge" title="${updateBadgeTooltip}">
                            ${updateBadgeLabel}
                        </span>
                    ` : ''}
                </div>
                <div class="card-actions">
                    ${actionIcons}
                </div>
            </div>
            ${shouldBlur ? `
                <div class="nsfw-overlay">
                    <div class="nsfw-warning">
                        <p>${nsfwText}</p>
                        <button class="show-content-btn">${showButtonText}</button>
                    </div>
                </div>
            ` : ''}
            <div class="card-footer">
                <div class="model-info">
                    <span class="model-name">${getDisplayName(model)}</span>
                    ${model.civitai?.name ? `<span class="version-name">${model.civitai.name}</span>` : ''}
                </div>
                <div class="card-actions">
                    <i class="${footerActionIcon}" 
                       title="${footerActionTitle}">
                    </i>
                </div>
            </div>
        </div>
    `;
    
    // Add video auto-play on hover functionality if needed
    const videoElement = card.querySelector('video');
    if (videoElement) {
        configureModelCardVideo(videoElement, autoplayOnHover);
    }

    return card;
}

const VIDEO_LAZY_ROOT_MARGIN = '200px 0px';
const VIDEO_LOAD_INTERVAL_MS = 120;
const VIDEO_LOAD_MAX_CONCURRENCY = 2;
let videoLazyObserver = null;

const videoLoadQueue = [];
const queuedVideoElements = new Set();
let activeVideoLoads = 0;
let queueTimer = null;

const scheduleFrame = typeof requestAnimationFrame === 'function'
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 16);

function scheduleVideoQueueProcessing(delay = 0) {
    if (queueTimer !== null) {
        return;
    }

    queueTimer = setTimeout(() => {
        queueTimer = null;
        processVideoLoadQueue();
    }, delay);
}

function dequeueVideoElement(videoElement) {
    if (!queuedVideoElements.has(videoElement)) {
        return;
    }

    queuedVideoElements.delete(videoElement);
    const index = videoLoadQueue.indexOf(videoElement);
    if (index !== -1) {
        videoLoadQueue.splice(index, 1);
    }
}

function processVideoLoadQueue() {
    if (videoLoadQueue.length === 0) {
        return;
    }

    while (activeVideoLoads < VIDEO_LOAD_MAX_CONCURRENCY && videoLoadQueue.length > 0) {
        const videoElement = videoLoadQueue.shift();
        queuedVideoElements.delete(videoElement);

        if (!videoElement || !videoElement.isConnected || videoElement.dataset.loaded === 'true') {
            continue;
        }

        activeVideoLoads++;
        videoElement.dataset.loading = 'true';

        scheduleFrame(() => {
            try {
                loadVideoSource(videoElement);
            } finally {
                delete videoElement.dataset.loading;
                activeVideoLoads--;

                if (videoLoadQueue.length > 0) {
                    scheduleVideoQueueProcessing(VIDEO_LOAD_INTERVAL_MS);
                }
            }
        });
    }

    if (videoLoadQueue.length > 0 && queueTimer === null) {
        scheduleVideoQueueProcessing(VIDEO_LOAD_INTERVAL_MS);
    }
}

function enqueueVideoElement(videoElement) {
    if (!videoElement || videoElement.dataset.loaded === 'true' || videoElement.dataset.loading === 'true') {
        return;
    }

    if (!videoElement.isConnected) {
        return;
    }

    if (queuedVideoElements.has(videoElement)) {
        return;
    }

    queuedVideoElements.add(videoElement);
    videoLoadQueue.push(videoElement);
    scheduleVideoQueueProcessing();
}

function ensureVideoLazyObserver() {
    if (videoLazyObserver) {
        return videoLazyObserver;
    }

    videoLazyObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                enqueueVideoElement(entry.target);
            }
        });
    }, {
        root: null,
        rootMargin: VIDEO_LAZY_ROOT_MARGIN,
        threshold: 0.01
    });

    return videoLazyObserver;
}

function cleanupHoverHandlers(videoElement) {
    const handlers = videoElement._hoverHandlers;
    if (!handlers) return;

    const { cardPreview, mouseEnter, mouseLeave } = handlers;
    if (cardPreview) {
        cardPreview.removeEventListener('mouseenter', mouseEnter);
        cardPreview.removeEventListener('mouseleave', mouseLeave);
    }

    delete videoElement._hoverHandlers;
}

function requestSafePlay(videoElement) {
    const playPromise = videoElement.play();
    if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => {});
    }
}

function loadVideoSource(videoElement) {
    if (!videoElement) {
        return false;
    }

    if (videoLazyObserver) {
        try {
            videoLazyObserver.unobserve(videoElement);
        } catch (error) {
            // Ignore observer errors (e.g., element already unobserved)
        }
    }

    if (videoElement.dataset.loaded === 'true' || !videoElement.isConnected) {
        return false;
    }

    const sourceElement = videoElement.querySelector('source');
    const dataSrc = videoElement.dataset.src || sourceElement?.dataset?.src;

    if (!dataSrc) {
        return false;
    }

    // Ensure src attributes are reset before applying
    videoElement.removeAttribute('src');
    if (sourceElement) {
        sourceElement.src = dataSrc;
    } else {
        videoElement.src = dataSrc;
    }

    videoElement.load();
    videoElement.dataset.loaded = 'true';

    if (videoElement.dataset.autoplay === 'true') {
        videoElement.setAttribute('autoplay', '');
        requestSafePlay(videoElement);
    }

    return true;
}

export function configureModelCardVideo(videoElement, autoplayOnHover) {
    if (!videoElement) return;

    dequeueVideoElement(videoElement);
    cleanupHoverHandlers(videoElement);

    const sourceElement = videoElement.querySelector('source');
    const existingSrc = videoElement.dataset.src || sourceElement?.dataset?.src || videoElement.currentSrc;

    if (existingSrc && !videoElement.dataset.src) {
        videoElement.dataset.src = existingSrc;
    }

    if (sourceElement && !sourceElement.dataset.src) {
        sourceElement.dataset.src = videoElement.dataset.src || sourceElement.src;
    }

    videoElement.removeAttribute('autoplay');
    videoElement.removeAttribute('src');
    videoElement.setAttribute('preload', 'none');
    videoElement.setAttribute('muted', '');
    videoElement.setAttribute('loop', '');
    videoElement.setAttribute('playsinline', '');
    videoElement.setAttribute('controls', '');
    videoElement.dataset.loaded = 'false';
    delete videoElement.dataset.loading;

    if (sourceElement) {
        sourceElement.removeAttribute('src');
        if (videoElement.dataset.src) {
            sourceElement.dataset.src = videoElement.dataset.src;
        }
    }

    if (!autoplayOnHover) {
        videoElement.dataset.autoplay = 'true';
    } else {
        delete videoElement.dataset.autoplay;
    }

    const observer = ensureVideoLazyObserver();
    observer.observe(videoElement);

    // Pause the video until it is either hovered or autoplay kicks in
    try {
        videoElement.pause();
    } catch (err) {
        // Ignore pause errors (e.g., if not loaded yet)
    }

    if (autoplayOnHover) {
        const cardPreview = videoElement.closest('.card-preview');
        if (cardPreview) {
            const mouseEnter = () => {
                dequeueVideoElement(videoElement);
                loadVideoSource(videoElement);
                requestSafePlay(videoElement);
            };
            const mouseLeave = () => {
                videoElement.pause();
                videoElement.currentTime = 0;
            };

            cardPreview.addEventListener('mouseenter', mouseEnter);
            cardPreview.addEventListener('mouseleave', mouseLeave);

            videoElement._hoverHandlers = { cardPreview, mouseEnter, mouseLeave };
        }
    }
}

// Add a method to update card appearance based on bulk mode (LoRA only)
export function updateCardsForBulkMode(isBulkMode) {
    // Update the state
    state.bulkMode = isBulkMode;
    
    document.body.classList.toggle('bulk-mode', isBulkMode);
    
    // Get all lora cards - this can now be from the DOM or through the virtual scroller
    const loraCards = document.querySelectorAll('.model-card');
    
    loraCards.forEach(card => {
        // Get all action containers for this card
        const actions = card.querySelectorAll('.card-actions');
        
        // Handle display property based on mode
        if (isBulkMode) {
            // Hide actions when entering bulk mode
            actions.forEach(actionGroup => {
                actionGroup.style.display = 'none';
            });
        } else {
            // Ensure actions are visible when exiting bulk mode
            actions.forEach(actionGroup => {
                // We need to reset to default display style which is flex
                actionGroup.style.display = 'flex';
            });
        }
    });
    
    // If using virtual scroller, we need to rerender after toggling bulk mode
    if (state.virtualScroller && typeof state.virtualScroller.scheduleRender === 'function') {
        state.virtualScroller.scheduleRender();
    }
    
    // Apply selection state to cards if entering bulk mode
    if (isBulkMode) {
        bulkManager.applySelectionState();
    }
}
