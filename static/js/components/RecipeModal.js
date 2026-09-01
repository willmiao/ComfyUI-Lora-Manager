// Recipe Modal Component
import { showToast, copyToClipboard, sendLoraToWorkflow, sendModelPathToWorkflow, stripLoraTags, sendPromptToWorkflow, sendGenParamsToWorkflow } from '../utils/uiHelpers.js';
import { isModelWeightFile } from '../utils/modelFileTypes.js';
import { buildCivitaiUrl } from '../utils/civitaiUtils.js';
import { translate } from '../utils/i18nHelpers.js';
import { state } from '../state/index.js';
import { setSessionItem, removeSessionItem, getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { fetchRecipeDetails, updateRecipeMetadata, sendRecipeWorkflow, extractRecipeId } from '../api/recipeApi.js';
import { downloadManager } from '../managers/DownloadManager.js';
import { MODEL_TYPES } from '../api/apiConfig.js';
import { openMediaViewer } from './shared/MediaViewer.js';
import { showRecipeDeleteConfirmation } from './RecipeCard.js';
import { renderCompactTags, setupTagTooltip, escapeAttribute } from './shared/utils.js';
import { setupTagEditMode } from './shared/ModelTags.js';
import { Combobox } from './Combobox.js';

const ALLOWED_GEN_PARAM_KEYS = new Set([
    'prompt',
    'negative_prompt',
    'steps',
    'sampler',
    'cfg_scale',
    'seed',
    'size',
    'clip_skip',
    'denoising_strength',
]);

const GEN_PARAM_NORMALIZATION = {
    cfg: 'cfg_scale',
    cfgScale: 'cfg_scale',
    clipSkip: 'clip_skip',
    negativePrompt: 'negative_prompt',
    Sampler: 'sampler',
    sampler_name: 'sampler',
    scheduler: 'sampler',
    Steps: 'steps',
    Seed: 'seed',
    Size: 'size',
    Prompt: 'prompt',
    'Negative prompt': 'negative_prompt',
    'Cfg scale': 'cfg_scale',
    'Clip skip': 'clip_skip',
    'Denoising strength': 'denoising_strength',
};

const PARAM_DISPLAY_NAMES = {
    steps: 'Steps',
    sampler: 'Sampler',
    cfg_scale: 'CFG',
    seed: 'Seed',
    size: 'Size',
    clip_skip: 'Clip Skip',
    denoising_strength: 'Denoising Strength',
};

function escapeHtml(value) {
    if (value == null) {
        return '';
    }
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Call backend to open the recipe's file location and select the file.
 * Mirrors the model modal's openFileLocation, including the Docker
 * clipboard fallback.
 * @param {string} filePath
 */
async function openRecipeFileLocation(filePath) {
    try {
        const resp = await fetch('/api/lm/open-file-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 'file_path': filePath })
        });
        if (!resp.ok) throw new Error('Failed to open file location');

        const data = await resp.json();

        if (data.mode === 'clipboard' && data.path) {
            try {
                await navigator.clipboard.writeText(data.path);
                showToast('recipes.modal.openFileLocation.copied', { path: data.path }, 'success');
            } catch (clipboardErr) {
                console.warn('Clipboard API not available:', clipboardErr);
                showToast('recipes.modal.openFileLocation.clipboardFallback', { path: data.path }, 'info');
            }
        } else {
            showToast('recipes.modal.openFileLocation.success', {}, 'success');
        }
    } catch (err) {
        showToast('recipes.modal.openFileLocation.failed', {}, 'error');
    }
}

// Fallback English strings for the collapsed "Why no LoRAs?" panel.
// Translations live in locales/*.json under recipes.resources.
const NO_LORAS_REASON_FALLBACKS = {
    api_meta_no_lora_resources: 'The source API returned no LoRA resource data for this image. LoRAs shown on the CivitAI page may come from internal data that the public API does not expose.',
    api_meta_missing: 'The source API returned no generation metadata for this image.',
    no_embedded_metadata: 'The image has no embedded generation metadata, so LoRA information could not be recovered.',
    workflow_metadata_limited: "The image's embedded metadata is a ComfyUI workflow; extracting LoRA information from workflows is limited.",
    video_no_metadata: 'Video files do not carry embedded generation metadata.',
    metadata_unsupported: 'The image contains metadata in a format that could not be parsed.',
    unknown: 'The reason could not be determined from the stored recipe data.',
};

const NO_LORAS_CHANNEL_FALLBACKS = {
    batch_import_url: 'Batch import (image URL)',
    batch_import_local: 'Batch import (local file)',
    url: 'Image URL import',
    local: 'Local file import',
    upload: 'Image upload',
    widget: 'Saved from workflow',
    reimport_url: 'Re-import (image URL)',
    reimport_local: 'Re-import (local file)',
};

class RecipeModal {
    constructor() {
        this.promptEditorState = {};
        this.recipeHydrationRequestId = 0;
        this.navigationKeyHandler = null;
        this.navigationInProgress = false;
        this.resetLocalEditState();
        this.init();
    }

    createLocalEditState() {
        return {
            title: { commitVersion: 0, isDirty: false },
            tags: { commitVersion: 0, isDirty: false },
            prompt: { commitVersion: 0, isDirty: false },
            negative_prompt: { commitVersion: 0, isDirty: false },
            source_path: { commitVersion: 0, isDirty: false },
        };
    }

    resetLocalEditState() {
        this.localEditState = this.createLocalEditState();
        this.sourceUrlEditState = this.localEditState.source_path;
    }

    getLocalEditState(field) {
        if (!this.localEditState[field]) {
            this.localEditState[field] = { commitVersion: 0, isDirty: false };
        }
        return this.localEditState[field];
    }

    markFieldDirty(field) {
        this.getLocalEditState(field).isDirty = true;
    }

    clearFieldDirty(field) {
        this.getLocalEditState(field).isDirty = false;
    }

    commitField(field) {
        const fieldState = this.getLocalEditState(field);
        fieldState.isDirty = false;
        fieldState.commitVersion += 1;
    }

    captureLocalEditVersions() {
        return Object.fromEntries(
            Object.entries(this.localEditState).map(([field, state]) => [
                field,
                state.commitVersion,
            ])
        );
    }

    shouldPreserveField(field, requestVersions) {
        const fieldState = this.getLocalEditState(field);
        const requestVersion = requestVersions?.[field] ?? fieldState.commitVersion;
        return fieldState.isDirty || fieldState.commitVersion !== requestVersion;
    }

    hasFieldCommittedSinceRequest(field, requestVersions) {
        const fieldState = this.getLocalEditState(field);
        const requestVersion = requestVersions?.[field] ?? fieldState.commitVersion;
        return fieldState.commitVersion !== requestVersion;
    }

    init() {
        this.setupCopyButtons();
        this.setupStripLoraToggle();
        this.setupPromptEditors();
        this.setupNavigationControls();
        this.setupDeleteControl();

        // Set up document click handler to close edit fields
        document.addEventListener('click', (event) => {
            const recipeModal = document.getElementById('recipeModal');
            if (recipeModal && recipeModal.style.display !== 'none') {
                const mediaEl = event.target.closest('.recipe-preview-media');
                if (mediaEl && mediaEl.tagName) {
                    event.stopPropagation();
                    const isVideo = mediaEl.tagName === 'VIDEO';
                    const url = mediaEl.src || mediaEl.currentSrc;
                    if (url) {
                        openMediaViewer(url, {
                            type: isVideo ? 'video' : 'image',
                            title: document.getElementById('recipeModalTitle')?.textContent || ''
                        });
                    }
                    return;
                }
            }

            // Handle title edit
            const titleEditor = document.getElementById('recipeTitleEditor');
            if (titleEditor && titleEditor.classList.contains('active') &&
                !titleEditor.contains(event.target) &&
                !event.target.closest('.edit-icon')) {
                this.saveTitleEdit();
            }

            // Handle reconnect input
            const reconnectContainers = document.querySelectorAll('.lora-reconnect-container');
            reconnectContainers.forEach(container => {
                if (container.classList.contains('active') &&
                    !container.contains(event.target) &&
                    !event.target.closest('.lora-reconnect') &&
                    // The Combobox dropdown lives on document.body — clicks on
                    // its options are part of the reconnect interaction.
                    !event.target.closest('.lm-combobox-panel')) {
                    this.hideReconnectInput(container);
                }
            });
        });
    }

    setupNavigationControls() {
        const prevBtn = document.getElementById('recipeNavPrevBtn');
        const nextBtn = document.getElementById('recipeNavNextBtn');

        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.handleDirectionalNavigation('prev'));
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.handleDirectionalNavigation('next'));
        }
        this.updateNavigationControls();
    }

    setupDeleteControl() {
        const deleteBtn = document.getElementById('deleteRecipeBtn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.handleDeleteRecipe());
        }
    }

    handleDeleteRecipe() {
        if (!this.currentRecipe) return;
        showRecipeDeleteConfirmation(this.currentRecipe);
    }

    shouldIgnoreNavigationKey(event) {
        const target = event.target;
        if (!target) return false;
        const tagName = target.tagName ? target.tagName.toLowerCase() : '';
        return target.isContentEditable || ['input', 'textarea', 'select', 'button'].includes(tagName);
    }

    updateNavigationControls() {
        const modalElement = document.getElementById('recipeModal');
        if (!modalElement) return;

        const prevBtn = modalElement.querySelector('#recipeNavPrevBtn');
        const nextBtn = modalElement.querySelector('#recipeNavNextBtn');
        if (!prevBtn || !nextBtn) return;

        const scroller = state.virtualScroller;
        if (!scroller || typeof scroller.getNavigationState !== 'function') {
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            return;
        }

        const { hasPrev, hasNext } = scroller.getNavigationState(this.listFilePath || this.filePath || '');
        prevBtn.disabled = this.navigationInProgress || !hasPrev;
        nextBtn.disabled = this.navigationInProgress || !hasNext;
    }

    cleanupNavigationShortcuts() {
        if (this.navigationKeyHandler) {
            document.removeEventListener('keydown', this.navigationKeyHandler);
            this.navigationKeyHandler = null;
        }
        this.navigationInProgress = false;
        this._destroyAllReconnectComboboxes();
    }

    setupNavigationShortcuts() {
        const modalElement = document.getElementById('recipeModal');
        if (!modalElement) return;

        this.cleanupNavigationShortcuts();

        this.navigationKeyHandler = (event) => {
            if (this.shouldIgnoreNavigationKey(event)) return;

            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.handleDirectionalNavigation('prev');
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.handleDirectionalNavigation('next');
            } else if (event.key === 'Delete') {
                event.preventDefault();
                this.handleDeleteRecipe();
            }
        };

        document.addEventListener('keydown', this.navigationKeyHandler);
    }

    async handleDirectionalNavigation(direction) {
        if (this.navigationInProgress) return;

        const scroller = state.virtualScroller;
        const filePath = this.listFilePath || this.filePath || '';

        if (!filePath || !scroller || typeof scroller.getAdjacentItemByFilePath !== 'function') {
            return;
        }

        this.navigationInProgress = true;
        this.updateNavigationControls();

        try {
            const adjacent = await scroller.getAdjacentItemByFilePath(filePath, direction);
            if (!adjacent || !adjacent.item) {
                const toastKey = direction === 'prev' ? 'toast.recipes.noPreviousRecipe' : 'toast.recipes.noNextRecipe';
                const toastFallback = direction === 'prev' ? 'No previous recipe available' : 'No next recipe available';
                showToast(toastKey, {}, 'info', toastFallback);
                return;
            }

            this.showRecipeDetails(adjacent.item);
        } finally {
            this.navigationInProgress = false;
            this.updateNavigationControls();
        }
    }

    showRecipeDetails(recipe) {
        const hydratedRecipe = recipe || {};
        this.resetLocalEditState();
        // Store the full recipe for editing
        this.currentRecipe = hydratedRecipe;
        this.resetPromptEditors();

        // Set modal title with edit icon
        const modalTitle = document.getElementById('recipeModalTitle');
        if (modalTitle) {
            modalTitle.innerHTML = `
                <div class="editable-content">
                    <span class="content-text">${hydratedRecipe.title || 'Recipe Details'}</span>
                    <button class="edit-icon" title="Edit recipe name"><i class="fas fa-pencil-alt"></i></button>
                </div>
                <div id="recipeTitleEditor" class="content-editor">
                    <input type="text" class="title-input" value="${hydratedRecipe.title || ''}">
                </div>
            `;

            // Add event listener for title editing
            const editIcon = modalTitle.querySelector('.edit-icon');
            editIcon.addEventListener('click', () => this.showTitleEditor());

            // Add key event listener for Enter key
            const titleInput = modalTitle.querySelector('.title-input');
            titleInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.saveTitleEdit();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    this.cancelTitleEdit();
                }
            });
        }

        // Store the recipe ID for copy syntax API call
        this.recipeId = hydratedRecipe.id;
        this.filePath = hydratedRecipe.file_path;
        this.listFilePath = hydratedRecipe.file_path;

        // Render tags using shared utility
        const tagsContainer = document.getElementById('recipeTagsContainer');
        if (tagsContainer) {
            this.updateTagsDisplay(tagsContainer, hydratedRecipe.tags || []);
        }

        // Set recipe image
        const mediaContainer = document.getElementById('recipePreviewContainer');
        if (mediaContainer) {
            this.syncPreviewMedia(hydratedRecipe);
            mediaContainer.querySelector('.source-url-container')?.remove();
            mediaContainer.querySelector('.source-url-editor')?.remove();

            // Add source URL container if the recipe has a source_path
            const sourceUrlContainer = document.createElement('div');
            sourceUrlContainer.className = 'source-url-container';
            const hasSourceUrl = hydratedRecipe.source_path && hydratedRecipe.source_path.trim().length > 0;
            const sourceUrl = hasSourceUrl ? hydratedRecipe.source_path : '';
            const isValidUrl = hasSourceUrl && (sourceUrl.startsWith('http://') || sourceUrl.startsWith('https://'));

            sourceUrlContainer.innerHTML = `
                <div class="source-url-content">
                    <span class="source-url-icon"><i class="fas fa-link"></i></span>
                    <span class="source-url-text" title="${isValidUrl ? 'Click to open source URL' : 'No valid URL'}">${hasSourceUrl ? sourceUrl : 'No source URL'
                }</span>
                </div>
                <button class="source-url-edit-btn" title="Edit source URL">
                    <i class="fas fa-pencil-alt"></i>
                </button>
            `;

            // Add source URL editor
            const sourceUrlEditor = document.createElement('div');
            sourceUrlEditor.className = 'source-url-editor';
            sourceUrlEditor.innerHTML = `
                <input type="text" class="source-url-input" placeholder="Enter source URL (e.g., https://civitai.com/...)" value="${sourceUrl}">
                <div class="source-url-actions">
                    <button class="source-url-cancel-btn">Cancel</button>
                    <button class="source-url-save-btn">Save</button>
                </div>
            `;

            // Append both containers to the media container
            mediaContainer.appendChild(sourceUrlContainer);
            mediaContainer.appendChild(sourceUrlEditor);

            // Delay binding slightly so modal layout is stable, but skip if this render was torn down.
            const sourceUrlContainerRef = sourceUrlContainer;
            const sourceUrlEditorRef = sourceUrlEditor;
            setTimeout(() => {
                if (!document.body.contains(sourceUrlContainerRef) || !document.body.contains(sourceUrlEditorRef)) {
                    return;
                }
                this.setupSourceUrlHandlers();
            }, 50);
        }

        this.syncGenerationParams(hydratedRecipe.gen_params);
        this.syncResourcesSection(hydratedRecipe);
        this.syncHeaderActions();
        this.syncMetaFooter();

        // Show the modal
        modalManager.showModal('recipeModal', null, null, () => this.cleanupNavigationShortcuts());
        this.updateNavigationControls();
        this.setupNavigationShortcuts();

        if (this.recipeId) {
            // Fire-and-forget: record this open for the "Recently Opened"
            // sort. Tracking must never disturb the modal, so failures are
            // swallowed.
            fetch(`/api/lm/recipe/${encodeURIComponent(this.recipeId)}/opened`, {
                method: 'POST',
                keepalive: true,
            }).catch(() => {});

            const hydrationRequestId = ++this.recipeHydrationRequestId;
            const requestEditVersions = this.captureLocalEditVersions();
            this.hydrateRecipeDetails(
                this.recipeId,
                hydrationRequestId,
                requestEditVersions
            );
        }
    }

    /**
     * Render the meta footer: clickable file location (opens the recipe JSON
     * in the OS file manager) plus the truncated recipe ID with copy button.
     * De-emphasized by design, mirroring the model modal's hash footnote.
     */
    syncMetaFooter() {
        const footer = document.getElementById('recipeMetaFooter');
        if (!footer) {
            return;
        }

        const recipeId = this.currentRecipe?.id || '';
        const filePath = this.currentRecipe?.file_path || '';
        const openTarget = this.currentRecipe?.recipe_json_path || filePath;
        const folderPath = filePath.replace(/[^/\\]+$/, '');

        if (!recipeId && !folderPath) {
            footer.hidden = true;
            footer.innerHTML = '';
            return;
        }

        const truncatedId = recipeId.length > 14
            ? `${recipeId.slice(0, 8)}…${recipeId.slice(-4)}`
            : recipeId;
        const openLocationLabel = translate('recipes.modal.actions.openFileLocation', {}, 'Open File Location');
        const copyIdLabel = translate('recipes.modal.actions.copyId', {}, 'Copy recipe ID');

        const locationMarkup = folderPath ? `
            <span class="recipe-meta-location" role="button" tabindex="0"
                title="${escapeAttribute(folderPath)}"
                aria-label="${escapeAttribute(openLocationLabel)}"
                data-filepath="${escapeAttribute(openTarget)}">
                <i class="fas fa-folder-open" aria-hidden="true"></i>
                <span class="recipe-meta-location-path">${escapeHtml(folderPath)}</span>
            </span>` : '';

        const idMarkup = recipeId ? `
            <span class="recipe-meta-id">
                <span class="recipe-meta-id-label">${translate('recipes.modal.metadata.id', {}, 'ID')}</span>
                <span class="recipe-meta-id-value" title="${escapeAttribute(recipeId)}">${escapeHtml(truncatedId)}</span>
                <button class="recipe-meta-copy-btn" title="${escapeAttribute(copyIdLabel)}" aria-label="${escapeAttribute(copyIdLabel)}">
                    <i class="fas fa-copy" aria-hidden="true"></i>
                </button>
            </span>` : '';

        footer.innerHTML = locationMarkup + idMarkup;
        footer.hidden = false;

        const locationEl = footer.querySelector('.recipe-meta-location');
        if (locationEl) {
            const openLocation = () => {
                if (locationEl.dataset.filepath) {
                    openRecipeFileLocation(locationEl.dataset.filepath);
                }
            };
            locationEl.addEventListener('click', openLocation);
            locationEl.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    openLocation();
                }
            });
        }

        const copyBtn = footer.querySelector('.recipe-meta-copy-btn');
        if (copyBtn && recipeId) {
            copyBtn.addEventListener('click', () => {
                copyToClipboard(recipeId);
            });
        }
    }

    async hydrateRecipeDetails(recipeId, requestId, requestEditVersions = {}) {
        try {
            const fullRecipe = await fetchRecipeDetails(recipeId);
            if (requestId !== this.recipeHydrationRequestId || !fullRecipe) {
                return;
            }

            const nextRecipe = { ...this.currentRecipe };

            if (!this.hasFieldCommittedSinceRequest('title', requestEditVersions) && fullRecipe.title !== undefined) {
                nextRecipe.title = fullRecipe.title;
            }

            if (!this.hasFieldCommittedSinceRequest('tags', requestEditVersions) && fullRecipe.tags !== undefined) {
                nextRecipe.tags = Array.isArray(fullRecipe.tags) ? [...fullRecipe.tags] : fullRecipe.tags;
            }

            if (!this.hasFieldCommittedSinceRequest('source_path', requestEditVersions)) {
                nextRecipe.source_path = fullRecipe.source_path || '';
            }

            const previousFilePath = nextRecipe.file_path;
            if (fullRecipe.file_path !== undefined) {
                nextRecipe.file_path = fullRecipe.file_path;
            }
            if (fullRecipe.recipe_json_path !== undefined) {
                nextRecipe.recipe_json_path = fullRecipe.recipe_json_path;
            }
            if (fullRecipe.file_url !== undefined) {
                nextRecipe.file_url = fullRecipe.file_url;
            }
            if (fullRecipe.preview_url !== undefined) {
                nextRecipe.preview_url = fullRecipe.preview_url;
            }
            if (
                fullRecipe.file_path !== undefined &&
                fullRecipe.file_path !== previousFilePath &&
                fullRecipe.file_url === undefined &&
                fullRecipe.preview_url === undefined
            ) {
                delete nextRecipe.file_url;
                delete nextRecipe.preview_url;
            }

            if (fullRecipe.gen_params !== undefined) {
                const previousGenParams = nextRecipe.gen_params || {};
                const incomingGenParams = { ...(fullRecipe.gen_params || {}) };
                for (const [key, value] of Object.entries(previousGenParams)) {
                    if (this.hasFieldCommittedSinceRequest(key, requestEditVersions)) {
                        incomingGenParams[key] = value;
                    }
                }
                nextRecipe.gen_params = incomingGenParams;
            } else {
                const previousGenParams = nextRecipe.gen_params || {};
                const preservedGenParams = {};
                for (const [key, value] of Object.entries(previousGenParams)) {
                    if (this.hasFieldCommittedSinceRequest(key, requestEditVersions)) {
                        preservedGenParams[key] = value;
                    }
                }
                nextRecipe.gen_params = preservedGenParams;
            }

            if (fullRecipe.has_workflow !== undefined) {
                nextRecipe.has_workflow = fullRecipe.has_workflow;
            }

            if (fullRecipe.checkpoint !== undefined) {
                nextRecipe.checkpoint = fullRecipe.checkpoint;
            } else {
                delete nextRecipe.checkpoint;
            }
            if (fullRecipe.loras !== undefined) {
                nextRecipe.loras = Array.isArray(fullRecipe.loras) ? [...fullRecipe.loras] : fullRecipe.loras;
            } else {
                delete nextRecipe.loras;
            }

            this.currentRecipe = nextRecipe;
            this.filePath = this.currentRecipe.file_path || this.filePath;

            this.syncHydratedRecipeFields(requestEditVersions);
        } catch (error) {
            // Keep the cached recipe visible if hydration fails.
            console.warn('Failed to hydrate recipe details:', error);
        }
    }

    syncHydratedRecipeFields(requestEditVersions = {}) {
        this.syncPreviewMedia(this.currentRecipe);

        if (!this.shouldPreserveField('title', requestEditVersions)) {
            this.syncTitleDisplay(this.currentRecipe?.title || '');
        }

        if (!this.shouldPreserveField('tags', requestEditVersions)) {
            this.syncTagsDisplay(this.currentRecipe?.tags || []);
        }

        if (!this.shouldPreserveField('prompt', requestEditVersions)) {
            this.syncPromptField(
                'prompt',
                this.currentRecipe?.gen_params?.prompt || '',
                'No prompt information available'
            );
        }

        if (!this.shouldPreserveField('negative_prompt', requestEditVersions)) {
            this.syncPromptField(
                'negative_prompt',
                this.currentRecipe?.gen_params?.negative_prompt || '',
                'No negative prompt information available'
            );
        }

        this.syncGenerationParams(this.currentRecipe?.gen_params, { promptFieldsOnly: true });
        this.syncResourcesSection(this.currentRecipe);

        if (!this.shouldPreserveField('source_path', requestEditVersions)) {
            this.updateSourceUrlDisplay(this.currentRecipe.source_path || '', { forceInputSync: true });
        } else {
            this.updateSourceUrlDisplay(this.currentRecipe.source_path || '');
        }
        this.syncHeaderActions();
        this.syncMetaFooter();
    }

    getPreviewMediaUrl(recipe = {}) {
        return recipe.file_url ||
            recipe.preview_url ||
            (recipe.file_path ? `/loras_static/root1/preview/${recipe.file_path.split('/').pop()}` :
                '/loras_static/images/no-preview.png');
    }

    syncPreviewMedia(recipe = {}) {
        const mediaContainer = document.getElementById('recipePreviewContainer');
        if (!mediaContainer) {
            return;
        }

        const previewUrl = this.getPreviewMediaUrl(recipe);
        const isVideo = previewUrl.toLowerCase().endsWith('.mp4');
        const expectedElementId = isVideo ? 'recipeModalVideo' : 'recipeModalImage';
        let previewElement = mediaContainer.querySelector(`#${expectedElementId}`);
        const existingPreviewElement = mediaContainer.querySelector('.recipe-preview-media');

        if (!previewElement || (existingPreviewElement && existingPreviewElement !== previewElement)) {
            if (existingPreviewElement?.tagName === 'VIDEO') {
                const existingVideo = existingPreviewElement;
                existingVideo.pause();
                existingVideo.currentTime = 0;
            }

            existingPreviewElement?.remove();
            previewElement = document.createElement(isVideo ? 'video' : 'img');
            previewElement.id = expectedElementId;
            previewElement.className = 'recipe-preview-media';
            mediaContainer.prepend(previewElement);
        }

        previewElement.src = previewUrl;
        previewElement.alt = recipe.title || 'Recipe Preview';

        if (isVideo) {
            previewElement.controls = true;
            previewElement.autoplay = false;
            previewElement.loop = true;
            previewElement.muted = true;
        }
    }

    getMetadataUpdateOptions() {
        return this.listFilePath ? { listFilePath: this.listFilePath } : {};
    }

    syncTitleDisplay(title) {
        const titleContainer = document.getElementById('recipeModalTitle');
        if (!titleContainer) {
            return;
        }

        const contentText = titleContainer.querySelector('.content-text');
        if (contentText) {
            contentText.textContent = title || 'Recipe Details';
        }

        const titleInput = titleContainer.querySelector('.title-input');
        if (titleInput) {
            titleInput.value = title || '';
        }
    }

    syncHeaderActions() {
        const actionsContainer = document.getElementById('recipeHeaderActions');
        if (!actionsContainer) {
            return;
        }

        actionsContainer.querySelectorAll('.recipe-source-url-btn').forEach(btn => btn.remove());

        // Keep the delete button as the last (rightmost) header action;
        // insertBefore with null falls back to appendChild if it is missing.
        const deleteBtn = document.getElementById('deleteRecipeBtn');

        if (this.currentRecipe?.has_workflow === true) {
            const workflowBtn = document.createElement('button');
            workflowBtn.className = 'recipe-source-url-btn';
            workflowBtn.id = 'sendWorkflowBtn';
            workflowBtn.title = 'Send Workflow to ComfyUI';
            workflowBtn.innerHTML = '<i class="fas fa-project-diagram"></i> Send Workflow to ComfyUI';
            workflowBtn.addEventListener('click', () => {
                this.sendWorkflowToComfyUI();
            });
            actionsContainer.insertBefore(workflowBtn, deleteBtn);
        }

        const sourcePath = this.currentRecipe?.source_path || '';
        const isValidUrl = sourcePath.startsWith('http://') || sourcePath.startsWith('https://');
        if (isValidUrl) {
            const btn = document.createElement('button');
            btn.className = 'recipe-source-url-btn';
            btn.title = sourcePath;
            btn.innerHTML = '<i class="fas fa-globe"></i> Open Source URL';
            btn.addEventListener('click', () => {
                window.open(sourcePath, '_blank');
            });
            actionsContainer.insertBefore(btn, deleteBtn);
        }
    }

    async sendWorkflowToComfyUI() {
        if (!this.recipeId) {
            return;
        }

        try {
            const result = await sendRecipeWorkflow(this.recipeId);
            if (result?.success) {
                showToast('toast.recipes.workflowSent', {}, 'success', 'Workflow sent to ComfyUI');
                return;
            }

            const error = result?.error || '';
            if (error === 'Standalone Mode Active') {
                showToast('toast.general.cannotInteractStandalone', {}, 'warning', 'Cannot interact with ComfyUI in standalone mode');
            } else if (error === 'no_workflow') {
                showToast('toast.recipes.workflowNoWorkflow', {}, 'warning', 'No embedded workflow found in this recipe');
            } else {
                showToast('toast.recipes.workflowSendFailed', { error }, 'error', `Failed to send workflow to ComfyUI: ${error}`);
            }
        } catch (error) {
            console.error('Failed to send workflow to ComfyUI:', error);
            showToast('toast.recipes.workflowSendFailed', { error: error.message }, 'error', `Failed to send workflow to ComfyUI: ${error.message}`);
        }
    }

    syncTagsDisplay(tags) {
        const container = document.getElementById('recipeTagsContainer');
        if (!container) return;
        this.updateTagsDisplay(container, tags || []);
    }

    // Re-render tags display using shared utility, wire edit mode with ModelTags
    updateTagsDisplay(container, tags) {
        const filePath = this.filePath || '';

        container.innerHTML = renderCompactTags(tags, filePath);

        // Setup tooltip for all tags
        setupTagTooltip(container);

        // Wire edit button using shared tag editing (no suggestions for recipes)
        setupTagEditMode(null, {
            container: container,
            showSuggestions: false,
            normalizeTag: false,
            saveHandler: async (filePath, tags) => {
                await updateRecipeMetadata(filePath, { tags }, this.getMetadataUpdateOptions());
            },
            onSaved: (tags) => {
                this.currentRecipe.tags = tags;
                this.commitField('tags');
                const c = document.getElementById('recipeTagsContainer');
                if (c) this.updateTagsDisplay(c, tags);
            },
        });
    }

    syncPromptField(field, value, placeholder) {
        const contentId = field === 'prompt' ? 'recipePrompt' : 'recipeNegativePrompt';
        const editorId = field === 'prompt' ? 'recipePromptEditor' : 'recipeNegativePromptEditor';
        const inputId = field === 'prompt' ? 'recipePromptInput' : 'recipeNegativePromptInput';

        this.renderPromptContent(document.getElementById(contentId), value, placeholder);

        const input = document.getElementById(inputId);
        if (input) {
            input.value = value || '';
        }
    }

    syncGenerationParams(genParams, options = {}) {
        const promptElement = document.getElementById('recipePrompt');
        const negativePromptElement = document.getElementById('recipeNegativePrompt');
        const otherParamsElement = document.getElementById('recipeOtherParams');
        const promptInput = document.getElementById('recipePromptInput');
        const negativePromptInput = document.getElementById('recipeNegativePromptInput');
        const promptFieldsOnly = options.promptFieldsOnly === true;
        const sanitizedGenParams = this.sanitizeGenParams(genParams);

        if (sanitizedGenParams) {
            if (!promptFieldsOnly) {
                this.renderPromptContent(promptElement, sanitizedGenParams.prompt, 'No prompt information available');
                this.renderPromptContent(negativePromptElement, sanitizedGenParams.negative_prompt, 'No negative prompt information available');

                if (promptInput) {
                    promptInput.value = sanitizedGenParams.prompt || '';
                }

                if (negativePromptInput) {
                    negativePromptInput.value = sanitizedGenParams.negative_prompt || '';
                }
            }

            if (otherParamsElement) {
                otherParamsElement.innerHTML = '';
                const excludedParams = ['prompt', 'negative_prompt'];

                for (const [key, value] of Object.entries(sanitizedGenParams)) {
                    if (!excludedParams.includes(key) && value !== undefined && value !== null) {
                        const displayName = PARAM_DISPLAY_NAMES[key] || key;
                        const paramTag = document.createElement('div');
                        paramTag.className = 'param-tag';
                        paramTag.innerHTML = `
                            <span class="param-name">${displayName}:</span>
                            <span class="param-value">${value}</span>
                        `;
                        otherParamsElement.appendChild(paramTag);
                    }
                }

                if (otherParamsElement.children.length === 0) {
                    otherParamsElement.innerHTML = '<div class="no-params">No additional parameters available</div>';
                }
            }
            return;
        }

        if (!promptFieldsOnly) {
            this.renderPromptContent(promptElement, '', 'No prompt information available');
            this.renderPromptContent(negativePromptElement, '', 'No negative prompt information available');
            if (promptInput) promptInput.value = '';
            if (negativePromptInput) negativePromptInput.value = '';
        }

        if (otherParamsElement) {
            otherParamsElement.innerHTML = '<div class="no-params">No parameters available</div>';
        }
    }

    sanitizeGenParams(genParams) {
        if (!genParams || typeof genParams !== 'object') {
            return null;
        }

        const sanitized = {};

        for (const [key, value] of Object.entries(genParams)) {
            if (value === undefined || value === null || value === '') {
                continue;
            }

            if (!ALLOWED_GEN_PARAM_KEYS.has(key)) {
                continue;
            }

            sanitized[key] = value;
        }

        for (const [key, value] of Object.entries(genParams)) {
            if (value === undefined || value === null || value === '') {
                continue;
            }

            const normalizedKey = GEN_PARAM_NORMALIZATION[key] || key;
            if (!ALLOWED_GEN_PARAM_KEYS.has(normalizedKey)) {
                continue;
            }

            if (sanitized[normalizedKey] === undefined || sanitized[normalizedKey] === null || sanitized[normalizedKey] === '') {
                sanitized[normalizedKey] = value;
            }
        }

        return sanitized;
    }

    syncResourcesSection(recipe = {}) {
        const checkpointContainer = document.getElementById('recipeCheckpoint');
        const resourceDivider = document.getElementById('recipeResourceDivider');
        const lorasListElement = document.getElementById('recipeLorasList');
        const lorasCountElement = document.getElementById('recipeLorasCount');
        const loras = Array.isArray(recipe.loras) ? recipe.loras : [];

        if (checkpointContainer) {
            // The innerHTML below discards the checkpoint reconnect container;
            // tear down its Combobox panel (appended to document.body) first.
            const checkpointPanel = checkpointContainer.querySelector(
                '.lora-reconnect-container[data-lora-index="checkpoint"]'
            );
            if (checkpointPanel) {
                this._destroyReconnectCombobox(checkpointPanel);
            }
            checkpointContainer.innerHTML = '';
            if (recipe.checkpoint && typeof recipe.checkpoint === 'object') {
                checkpointContainer.innerHTML = this.renderCheckpoint(recipe.checkpoint);
                this.setupCheckpointActions(checkpointContainer, recipe.checkpoint);
                this.setupCheckpointNavigation(checkpointContainer, recipe.checkpoint);
            }
        }

        let allLorasAvailable = true;
        let missingLorasCount = 0;
        let deletedLorasCount = 0;

        loras.forEach(lora => {
            if (lora.isDeleted) {
                deletedLorasCount++;
            } else if (!lora.inLibrary) {
                allLorasAvailable = false;
                missingLorasCount++;
            }
        });

        if (lorasCountElement) {
            const totalCount = loras.length;
            let statusHTML = '';
            if (totalCount > 0) {
                if (allLorasAvailable && deletedLorasCount === 0) {
                    statusHTML = `<div class="recipe-status ready"><i class="fas fa-check-circle" aria-hidden="true"></i> ${translate('recipes.status.ready', {}, 'Ready to use')}</div>`;
                } else if (missingLorasCount > 0) {
                    // Rendered as a real button so the affordance is visible without
                    // hover and the control is keyboard/screen-reader accessible.
                    // Leading download icon: the red tint + "missing" text already
                    // encode the state, so the icon's job is to hint the action.
                    statusHTML = `<button type="button" class="recipe-status missing clickable"
                        title="${translate('recipes.status.downloadMissingTooltip', {}, 'Click to download missing LoRAs')}"
                        aria-label="${translate('recipes.status.downloadMissing', { count: missingLorasCount }, `Download ${missingLorasCount} missing LoRAs`)}">
                        <i class="fas fa-download" aria-hidden="true"></i> ${translate('recipes.status.missingCount', { count: missingLorasCount }, `${missingLorasCount} missing`)}
                    </button>`;
                } else if (deletedLorasCount > 0 && missingLorasCount === 0) {
                    statusHTML = `<div class="recipe-status partial"><i class="fas fa-info-circle" aria-hidden="true"></i> ${translate('recipes.status.deletedCount', { count: deletedLorasCount }, `${deletedLorasCount} deleted`)}</div>`;
                }
            }

            lorasCountElement.innerHTML = `<i class="fas fa-layer-group"></i> ${totalCount} ${totalCount === 1 ? 'LoRA' : 'LoRAs'} ${statusHTML}`;

            const missingStatus = lorasCountElement.querySelector('.recipe-status.missing');
            if (missingStatus && missingLorasCount > 0) {
                missingStatus.addEventListener('click', () => this.showDownloadMissingLorasModal());
            }

            setTimeout(() => {
                const viewRecipeLorasBtn = document.getElementById('viewRecipeLorasBtn');
                if (viewRecipeLorasBtn) {
                    viewRecipeLorasBtn.addEventListener('click', () => this.navigateToLorasPage());
                }
            }, 100);
        }

        if (lorasListElement && loras.length > 0) {
            // The list innerHTML below discards every reconnect container;
            // tear down their Combobox panels (appended to document.body) first.
            this._destroyAllReconnectComboboxes();
            lorasListElement.innerHTML = loras.map(lora => {
                const existsLocally = lora.inLibrary;
                const isDeleted = lora.isDeleted;
                const loraIndex = loras.indexOf(lora);

                // Mirror the checkpoint "broken" rule: deleted, an
                // unresolvable hash, or a name-only remnant with no CivitAI
                // identifiers at all cannot be fixed by downloading —
                // reconnecting a local LoRA is the only remediation.
                const needsReconnect = !existsLocally
                    && (isDeleted || lora.hashInvalid || !this.canDownloadLora(lora));

                // Status badges are pure indicators (consistent with the
                // versions-tab pattern): they never carry click behavior,
                // only a tooltip. Remediation lives in the action row below.
                let statusBadge;
                if (existsLocally) {
                    statusBadge = `
                        <div class="local-badge" title="${escapeHtml(translate('recipes.resources.inLibraryTooltip', {}, 'This model exists in your local library'))}">
                            <i class="fas fa-check" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.inLibrary', {}, 'In Library'))}
                        </div>`;
                } else if (isDeleted) {
                    statusBadge = `
                        <div class="deleted-badge" title="${escapeHtml(translate('recipes.resources.deletedTooltip', {}, 'This LoRA was deleted from the source and is no longer available for download'))}">
                            <i class="fas fa-trash-alt" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.deleted', {}, 'Deleted'))}
                        </div>`;
                } else if (lora.hashInvalid) {
                    statusBadge = `
                        <div class="invalid-hash-badge" title="${escapeHtml(translate('recipes.resources.hashInvalidTooltip', {}, 'This LoRA hash cannot be resolved on CivitAI - the model may have been updated'))}">
                            <i class="fas fa-question-circle" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.hashInvalid', {}, 'Unresolvable Hash'))}
                        </div>`;
                } else {
                    statusBadge = `
                        <div class="missing-badge" title="${escapeHtml(translate('recipes.resources.notInLibraryTooltip', {}, 'This model is not in your library'))}">
                            <i class="fas fa-exclamation-triangle" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.notInLibrary', {}, 'Not in Library'))}
                        </div>`;
                }

                const actionsRow = this.renderLoraItemActions(loraIndex, { existsLocally, needsReconnect });

                // The Civitai link belongs to the model name (it answers
                // "what is this"), so it sits inline in the title — the same
                // pattern the versions tab uses — never in the action row.
                // Skipped for deleted models: their source page is gone.
                const titleLink = isDeleted
                    ? ''
                    : this.renderCivitaiLink(this.getResourceCivitaiUrl(lora));

                const isPreviewVideo = lora.preview_url && lora.preview_url.toLowerCase().endsWith('.mp4');
                const previewMedia = isPreviewVideo ?
                    `<video class="thumbnail-video" autoplay loop muted playsinline>
                        <source src="${lora.preview_url}" type="video/mp4">
                     </video>` :
                    `<img src="${lora.preview_url || '/loras_static/images/no-preview.png'}" alt="LoRA preview" onerror="this.onerror=null; this.src='/loras_static/images/no-preview.png'">`;

                let loraItemClass = 'recipe-lora-item';
                if (existsLocally) {
                    loraItemClass += ' exists-locally';
                } else if (isDeleted) {
                    loraItemClass += ' is-deleted';
                } else {
                    loraItemClass += ' missing-locally';
                }

                // Only in-library items are row-navigable (they open the local
                // LoRA detail); make that affordance keyboard-accessible.
                const rowA11yAttributes = existsLocally
                    ? ` role="button" tabindex="0" aria-label="${escapeHtml(translate('recipes.resources.openLoraDetails', { name: lora.modelName }, `View ${lora.modelName} in the LoRA library`))}"`
                    : '';

                // A reconnect snapshot marks a manually reconnected entry.
                // The restore icon on the info row doubles as that marker;
                // its tooltip names the previous association.
                let undoReconnectIcon = '';
                if (existsLocally && lora.reconnectSnapshot) {
                    const previousName = lora.reconnectSnapshot.file_name || lora.reconnectSnapshot.modelName || '';
                    const undoLabel = translate('recipes.resources.undoReconnect', {}, 'Undo');
                    const undoTooltip = previousName
                        ? translate('recipes.resources.undoReconnectTooltipNamed', { name: previousName }, `Restore to ${previousName} (the association before reconnecting)`)
                        : translate('recipes.resources.undoReconnectTooltip', {}, 'Restore the association this entry had before reconnecting');
                    undoReconnectIcon = `
                        <button type="button" class="lora-undo-reconnect" data-lora-index="${loraIndex}"
                            title="${escapeHtml(undoTooltip)}" aria-label="${escapeHtml(undoTooltip)}">
                            <i class="fas fa-rotate-left" aria-hidden="true"></i>
                        </button>
                    `;
                }

                return `
                    <div class="${loraItemClass}" data-lora-index="${loraIndex}"${rowA11yAttributes}>
                        <div class="recipe-lora-thumbnail">
                            ${previewMedia}
                        </div>
                        <div class="recipe-lora-content">
                            <div class="recipe-lora-header">
                                <div class="recipe-lora-title">
                                    <h4>${lora.modelName}</h4>
                                    ${titleLink}
                                </div>
                                <div class="badge-container">${statusBadge}</div>
                            </div>
                            <div class="recipe-lora-info">
                                ${lora.modelVersionName ? `<div class="recipe-lora-version">${lora.modelVersionName}</div>` : ''}
                                <div class="recipe-lora-weight">Weight: ${lora.strength || 1.0}</div>
                                ${lora.baseModel ? `<div class="base-model">${lora.baseModel}</div>` : ''}
                                ${undoReconnectIcon}
                            </div>
                            ${actionsRow}
                        </div>
                        ${needsReconnect ? `
                        <div class="lora-reconnect-container" data-lora-index="${loraIndex}">
                            <div class="reconnect-instructions">
                                <p>${escapeHtml(translate('recipes.resources.reconnectInstructions', {}, 'Enter LoRA syntax or name to reconnect:'))}</p>
                                <small>${escapeHtml(translate('recipes.resources.reconnectExample', {}, 'Example: <lora:name:1> or just the name'))}</small>
                            </div>
                            <div class="reconnect-form">
                                <input type="text" class="reconnect-input" placeholder="${escapeHtml(translate('recipes.resources.reconnectPlaceholder', {}, 'Enter LoRA name or syntax'))}">
                                <div class="reconnect-actions">
                                    <button class="reconnect-cancel-btn">${escapeHtml(translate('common.cancel', {}, 'Cancel'))}</button>
                                    <button class="reconnect-confirm-btn">${escapeHtml(translate('recipes.resources.reconnect', {}, 'Reconnect'))}</button>
                                </div>
                            </div>
                            <div class="reconnect-suggestions"></div>
                            <p class="reconnect-error" role="alert"></p>
                        </div>` : ''}
                    </div>
                `;
            }).join('');

            setTimeout(() => {
                this.setupReconnectButtons();
                this.setupLoraItemActions();
                this.setupLoraItemsClickable();
            }, 100);

            this.recipeLorasSyntax = '';
        } else if (lorasListElement) {
            this._destroyAllReconnectComboboxes();
            lorasListElement.innerHTML = this.renderNoLorasState(recipe);
            this.recipeLorasSyntax = '';
        }

        if (resourceDivider) {
            const hasCheckpoint = checkpointContainer && checkpointContainer.querySelector('.recipe-lora-item');
            const hasLoraItems = lorasListElement && lorasListElement.querySelector('.recipe-lora-item');
            resourceDivider.style.display = hasCheckpoint && hasLoraItems ? 'block' : 'none';
        }
    }

    /**
     * Render the empty LoRA list, including a collapsed "Why no LoRAs?"
     * explanation panel when the cause is known or can be inferred.
     * @param {Object} recipe
     * @returns {string}
     */
    renderNoLorasState(recipe) {
        const emptyText = translate(
            'recipes.resources.noLorasAssociated',
            {},
            'No LoRAs associated with this recipe'
        );
        const reason = this.resolveNoLorasReason(recipe);
        let html = `<div class="no-loras">${escapeHtml(emptyText)}</div>`;

        // 'no_loras_used' is the normal case — the generation simply used no
        // LoRAs, nothing to explain.
        if (!reason || reason.code === 'no_loras_used') {
            return html;
        }

        const toggle = translate('recipes.resources.noLorasWhyToggle', {}, 'Why no LoRAs?');
        const reasonText = translate(
            `recipes.resources.noLorasReasons.${reason.code}`,
            {},
            NO_LORAS_REASON_FALLBACKS[reason.code] || NO_LORAS_REASON_FALLBACKS.unknown
        );

        const bullets = [];
        if (reason.channel) {
            const channelText = translate(
                `recipes.resources.noLorasChannels.${reason.channel}`,
                {},
                NO_LORAS_CHANNEL_FALLBACKS[reason.channel] || reason.channel
            );
            bullets.push(
                `<li><span class="no-loras-bullet-label">${escapeHtml(translate('recipes.resources.noLorasImportMethod', {}, 'Import method'))}:</span> ${escapeHtml(channelText)}</li>`
            );
        }
        bullets.push(`<li>${escapeHtml(reasonText)}</li>`);
        bullets.push(...this.renderNoLorasDetailBullets(reason));
        if (reason.inferred) {
            bullets.push(
                `<li class="no-loras-inferred-note">${escapeHtml(translate('recipes.resources.noLorasInferredNote', {}, 'Possible reason (inferred) — this recipe was imported before import diagnostics were recorded.'))}</li>`
            );
        }

        html += `
            <details class="no-loras-reason">
                <summary><i class="fas fa-circle-question" aria-hidden="true"></i> ${escapeHtml(toggle)}</summary>
                <div class="no-loras-reason-body"><ul>${bullets.join('')}</ul></div>
            </details>`;
        return html;
    }

    /**
     * Resolve the no-LoRA reason: recorded import_info takes precedence;
     * legacy recipes without it fall back to heuristics on the stored data.
     * @param {Object} recipe
     * @returns {{code: string, channel: ?string, details: ?Object, inferred: boolean}|null}
     */
    resolveNoLorasReason(recipe) {
        const importInfo =
            recipe && typeof recipe.import_info === 'object' && recipe.import_info !== null
                ? recipe.import_info
                : null;
        if (importInfo && typeof importInfo.reason === 'string' && importInfo.reason) {
            return {
                code: importInfo.reason,
                channel: typeof importInfo.channel === 'string' ? importInfo.channel : null,
                details:
                    typeof importInfo.details === 'object' && importInfo.details !== null
                        ? importInfo.details
                        : null,
                inferred: false,
            };
        }
        return this.inferNoLorasReason(recipe);
    }

    /**
     * Heuristic reason for legacy recipes that predate import_info.
     * @param {Object} recipe
     * @returns {{code: string, channel: ?string, details: ?Object, inferred: boolean}}
     */
    inferNoLorasReason(recipe) {
        const sourcePath = recipe && recipe.source_path ? String(recipe.source_path).trim() : '';
        const genParams =
            recipe && recipe.gen_params && typeof recipe.gen_params === 'object'
                ? recipe.gen_params
                : {};
        const paramKeys = Object.keys(genParams).filter(
            (key) => genParams[key] !== '' && genParams[key] !== null && genParams[key] !== undefined
        );

        if (recipe && recipe.has_workflow) {
            return { code: 'workflow_metadata_limited', channel: null, details: null, inferred: true };
        }
        if (/^https?:\/\//i.test(sourcePath)) {
            // URL imports come from CivitAI; a missing LoRA list there almost
            // always means the public API did not report LoRA resources.
            return { code: 'api_meta_no_lora_resources', channel: 'url', details: null, inferred: true };
        }
        if (sourcePath) {
            return paramKeys.length === 0
                ? { code: 'no_embedded_metadata', channel: 'local', details: null, inferred: true }
                : { code: 'no_loras_used', channel: 'local', details: null, inferred: true };
        }
        if (paramKeys.length > 0) {
            return { code: 'no_loras_used', channel: null, details: null, inferred: true };
        }
        return { code: 'unknown', channel: null, details: null, inferred: true };
    }

    /**
     * Render the recorded diagnostic detail bullets (API meta shape, EXIF
     * presence). Only shown for recorded (non-inferred) import_info.
     * @param {{details: ?Object}} reason
     * @returns {string[]}
     */
    renderNoLorasDetailBullets(reason) {
        const details = reason.details;
        if (!details) {
            return [];
        }
        const bullets = [];
        if (Array.isArray(details.api_meta_keys) && details.api_meta_keys.length > 0) {
            const label = translate('recipes.resources.noLorasDetails.apiMetaFields', {}, 'API metadata fields');
            bullets.push(
                `<li><span class="no-loras-bullet-label">${escapeHtml(label)}:</span> ${escapeHtml(details.api_meta_keys.join(', '))}</li>`
            );
        }
        if (typeof details.api_model_version_ids === 'number') {
            const label = translate('recipes.resources.noLorasDetails.modelVersionIds', {}, 'Model version IDs reported');
            bullets.push(
                `<li><span class="no-loras-bullet-label">${escapeHtml(label)}:</span> ${details.api_model_version_ids}</li>`
            );
        }
        if (typeof details.exif_present === 'boolean') {
            const label = translate('recipes.resources.noLorasDetails.embeddedMetadata', {}, 'Embedded metadata');
            const value = details.exif_present
                ? translate('recipes.resources.noLorasDetails.present', {}, 'found')
                : translate('recipes.resources.noLorasDetails.absent', {}, 'none');
            bullets.push(
                `<li><span class="no-loras-bullet-label">${escapeHtml(label)}:</span> ${escapeHtml(value)}</li>`
            );
        }
        return bullets;
    }

    updateSourceUrlDisplay(sourcePath, options = {}) {
        const sourceUrlContainer = document.querySelector('.source-url-container');
        const sourceUrlEditor = document.querySelector('.source-url-editor');
        if (!sourceUrlContainer || !sourceUrlEditor) {
            return;
        }

        const sourceUrlText = sourceUrlContainer.querySelector('.source-url-text');
        const sourceUrlInput = sourceUrlEditor.querySelector('.source-url-input');
        if (!sourceUrlText || !sourceUrlInput) {
            return;
        }

        const normalizedSourcePath = typeof sourcePath === 'string' ? sourcePath.trim() : '';
        const isValidUrl = normalizedSourcePath.startsWith('http://') || normalizedSourcePath.startsWith('https://');

        sourceUrlText.textContent = normalizedSourcePath || 'No source URL';
        sourceUrlText.title = normalizedSourcePath
            ? (isValidUrl ? 'Click to open source URL' : 'No valid URL')
            : 'No valid URL';
        if (options.forceInputSync || !sourceUrlEditor.classList.contains('active') || !this.sourceUrlEditState.isDirty) {
            sourceUrlInput.value = normalizedSourcePath;
        }
    }

    // Title editing methods
    showTitleEditor() {
        const titleContainer = document.getElementById('recipeModalTitle');
        if (titleContainer) {
            titleContainer.querySelector('.editable-content').classList.add('hide');
            const editor = titleContainer.querySelector('#recipeTitleEditor');
            editor.classList.add('active');
            const input = editor.querySelector('input');
            input.oninput = () => this.markFieldDirty('title');
            input.focus();
            input.select();
        }
    }

    saveTitleEdit() {
        const titleContainer = document.getElementById('recipeModalTitle');
        if (titleContainer) {
            const editor = titleContainer.querySelector('#recipeTitleEditor');
            const input = editor.querySelector('input');
            const newTitle = input.value.trim();

            // Check if title changed
            if (newTitle && newTitle !== this.currentRecipe.title) {
                // Update title in the UI
                titleContainer.querySelector('.content-text').textContent = newTitle;

                // Update the recipe on the server
                updateRecipeMetadata(this.filePath, { title: newTitle }, this.getMetadataUpdateOptions())
                    .then(data => {
                        // Show success toast
                        showToast('toast.recipes.nameUpdated', {}, 'success');

                        // Update the current recipe object
                        this.currentRecipe.title = newTitle;
                        this.commitField('title');
                    })
                    .catch(error => {
                        // Error is handled in the API function
                        // Reset the UI if needed
                        titleContainer.querySelector('.content-text').textContent = this.currentRecipe.title || '';
                        this.clearFieldDirty('title');
                    });
            } else {
                this.clearFieldDirty('title');
            }

            // Hide editor
            editor.classList.remove('active');
            titleContainer.querySelector('.editable-content').classList.remove('hide');
        }
    }

    cancelTitleEdit() {
        const titleContainer = document.getElementById('recipeModalTitle');
        if (titleContainer) {
            // Reset input value
            const editor = titleContainer.querySelector('#recipeTitleEditor');
            const input = editor.querySelector('input');
            input.value = this.currentRecipe.title || '';
            this.clearFieldDirty('title');

            // Hide editor
            editor.classList.remove('active');
            titleContainer.querySelector('.editable-content').classList.remove('hide');
        }
    }

    setupPromptEditors() {
        const promptConfigs = [
            {
                editButtonId: 'editPromptBtn',
                contentId: 'recipePrompt',
                editorId: 'recipePromptEditor',
                inputId: 'recipePromptInput',
                field: 'prompt',
                placeholder: 'No prompt information available',
                successKey: 'toast.recipes.promptUpdated',
                successFallback: 'Prompt updated successfully',
            },
            {
                editButtonId: 'editNegativePromptBtn',
                contentId: 'recipeNegativePrompt',
                editorId: 'recipeNegativePromptEditor',
                inputId: 'recipeNegativePromptInput',
                field: 'negative_prompt',
                placeholder: 'No negative prompt information available',
                successKey: 'toast.recipes.negativePromptUpdated',
                successFallback: 'Negative prompt updated successfully',
            }
        ];

        promptConfigs.forEach((config) => {
            const editButton = document.getElementById(config.editButtonId);
            const input = document.getElementById(config.inputId);

            if (editButton) {
                editButton.addEventListener('click', () => this.showPromptEditor(config));
            }

            if (input) {
                input.addEventListener('input', () => this.markFieldDirty(config.field));
                input.addEventListener('keydown', (event) => {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        event.stopPropagation();
                        this.cancelPromptEdit(config);
                        return;
                    }

                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.stopPropagation();
                        this.promptEditorState[config.field] = {
                            ...(this.promptEditorState[config.field] || {}),
                            skipBlurSave: true,
                        };
                        this.savePromptEdit(config);
                    }
                });
                input.addEventListener('blur', () => {
                    const promptState = this.promptEditorState[config.field] || {};
                    if (promptState.skipBlurSave) {
                        this.promptEditorState[config.field] = {
                            ...promptState,
                            skipBlurSave: false,
                        };
                        return;
                    }

                    this.savePromptEdit(config);
                });
            }
        });
    }

    renderPromptContent(element, value, placeholder) {
        if (!element) {
            return;
        }

        const text = value || '';
        if (text) {
            element.textContent = text;
            element.classList.remove('is-placeholder');
        } else {
            element.textContent = placeholder;
            element.classList.add('is-placeholder');
        }
    }

    resetPromptEditors() {
        this.hidePromptEditor({ contentId: 'recipePrompt', editorId: 'recipePromptEditor' });
        this.hidePromptEditor({ contentId: 'recipeNegativePrompt', editorId: 'recipeNegativePromptEditor' });
    }

    showPromptEditor(config) {
        const content = document.getElementById(config.contentId);
        const editor = document.getElementById(config.editorId);
        const input = document.getElementById(config.inputId);

        if (!content || !editor || !input) {
            return;
        }

        const currentValue = this.currentRecipe?.gen_params?.[config.field] || '';
        input.value = currentValue;
        this.promptEditorState[config.field] = {
            initialValue: currentValue,
            skipBlurSave: false,
            isSaving: false,
        };
        content.classList.add('hide');
        editor.classList.add('active');
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    }

    async savePromptEdit(config) {
        const content = document.getElementById(config.contentId);
        const editor = document.getElementById(config.editorId);
        const input = document.getElementById(config.inputId);

        if (!content || !editor || !input || !this.currentRecipe) {
            return;
        }

        const promptState = this.promptEditorState[config.field] || {};
        if (promptState.isSaving) {
            return;
        }

        const currentGenParams = this.currentRecipe.gen_params || {};
        const nextValue = input.value.trim() === '' ? '' : input.value;
        const currentValue = this.sanitizeGenParams(currentGenParams)?.[config.field] || '';

        if (nextValue === currentValue) {
            this.clearFieldDirty(config.field);
            this.hidePromptEditor(config);
            return;
        }

        const nextGenParams = {
            ...currentGenParams,
            [config.field]: nextValue,
        };

        try {
            this.promptEditorState[config.field] = {
                ...promptState,
                isSaving: true,
            };
            await updateRecipeMetadata(this.filePath, { gen_params: nextGenParams }, this.getMetadataUpdateOptions());
            this.currentRecipe.gen_params = nextGenParams;
            this.renderPromptContent(content, nextValue, config.placeholder);
            showToast(config.successKey, {}, 'success', config.successFallback);
            this.commitField(config.field);
        } catch (error) {
            this.renderPromptContent(content, currentValue, config.placeholder);
            input.value = currentValue;
            this.clearFieldDirty(config.field);
        } finally {
            this.clearFieldDirty(config.field);
            this.hidePromptEditor(config);
        }
    }

    cancelPromptEdit(config) {
        const input = document.getElementById(config.inputId);
        if (input) {
            input.value = this.currentRecipe?.gen_params?.[config.field] || '';
        }

        this.clearFieldDirty(config.field);
        this.hidePromptEditor(config);
    }

    hidePromptEditor(config) {
        const content = document.getElementById(config.contentId);
        const editor = document.getElementById(config.editorId);

        if (content) {
            content.classList.remove('hide');
        }

        if (editor) {
            editor.classList.remove('active');
        }

        delete this.promptEditorState[config.field];
    }

    // Setup source URL handlers
    setupSourceUrlHandlers() {
        const sourceUrlContainer = document.querySelector('.source-url-container');
        const sourceUrlEditor = document.querySelector('.source-url-editor');
        if (!sourceUrlContainer || !sourceUrlEditor) {
            return;
        }
        const sourceUrlText = sourceUrlContainer.querySelector('.source-url-text');
        const sourceUrlEditBtn = sourceUrlContainer.querySelector('.source-url-edit-btn');
        const sourceUrlCancelBtn = sourceUrlEditor.querySelector('.source-url-cancel-btn');
        const sourceUrlSaveBtn = sourceUrlEditor.querySelector('.source-url-save-btn');
        const sourceUrlInput = sourceUrlEditor.querySelector('.source-url-input');

        if (!sourceUrlText || !sourceUrlEditBtn || !sourceUrlCancelBtn || !sourceUrlSaveBtn || !sourceUrlInput) {
            return;
        }

        // Show editor on edit button click
        sourceUrlEditBtn.addEventListener('click', () => {
            sourceUrlContainer.classList.add('hide');
            sourceUrlEditor.classList.add('active');
            sourceUrlInput.focus();
        });

        sourceUrlInput.addEventListener('input', () => {
            this.sourceUrlEditState.isDirty = true;
        });

        // Cancel editing
        sourceUrlCancelBtn.addEventListener('click', () => {
            sourceUrlEditor.classList.remove('active');
            sourceUrlContainer.classList.remove('hide');
            this.updateSourceUrlDisplay(this.currentRecipe.source_path || '', { forceInputSync: true });
            this.clearFieldDirty('source_path');
        });

        // Save new source URL
        sourceUrlSaveBtn.addEventListener('click', () => {
            const newSourceUrl = sourceUrlInput.value.trim();
            if (newSourceUrl !== this.currentRecipe.source_path) {
                // Update the recipe on the server
                updateRecipeMetadata(this.filePath, { source_path: newSourceUrl }, this.getMetadataUpdateOptions())
                    .then(data => {
                        // Show success toast
                        showToast('toast.recipes.sourceUrlUpdated', {}, 'success');

                        // Update source URL in the UI
                        this.commitField('source_path');
                        this.updateSourceUrlDisplay(newSourceUrl, { forceInputSync: true });
                        this.syncHeaderActions();

                        // Update the current recipe object
                        this.currentRecipe.source_path = newSourceUrl;
                    })
                    .catch(error => {
                        // Error is handled in the API function
                        this.clearFieldDirty('source_path');
                    });
            } else {
                this.clearFieldDirty('source_path');
            }

            // Hide editor
            sourceUrlEditor.classList.remove('active');
            sourceUrlContainer.classList.remove('hide');
        });

        // Open source URL in a new tab if it's valid
        sourceUrlText.addEventListener('click', () => {
            const url = sourceUrlText.textContent.trim();
            if (url.startsWith('http://') || url.startsWith('https://')) {
                window.open(url, '_blank');
            }
        });
    }

    // Setup copy buttons for prompts and send recipe button
    setupCopyButtons() {
        const copyPromptBtn = document.getElementById('copyPromptBtn');
        const copyNegativePromptBtn = document.getElementById('copyNegativePromptBtn');
        const sendRecipeBtn = document.getElementById('sendRecipeBtn');

        if (copyPromptBtn) {
            copyPromptBtn.addEventListener('click', () => {
                let promptText = this.currentRecipe?.gen_params?.prompt || '';
                if (this.shouldStripLoraOnCopy()) {
                    promptText = RecipeModal.stripLoraTags(promptText);
                }
                this.copyToClipboard(promptText, 'Prompt copied to clipboard');
            });
        }

        if (copyNegativePromptBtn) {
            copyNegativePromptBtn.addEventListener('click', () => {
                let negativePromptText = this.currentRecipe?.gen_params?.negative_prompt || '';
                if (this.shouldStripLoraOnCopy()) {
                    negativePromptText = RecipeModal.stripLoraTags(negativePromptText);
                }
                this.copyToClipboard(negativePromptText, 'Negative prompt copied to clipboard');
            });
        }

        if (sendRecipeBtn) {
            sendRecipeBtn.addEventListener('click', () => {
                // Send recipe to ComfyUI workflow
                this.sendRecipeToWorkflow();
            });
        }

        // Copy recipe syntax button (header actions)
        const copyRecipeSyntaxBtn = document.getElementById('copyRecipeSyntaxBtn');
        if (copyRecipeSyntaxBtn) {
            copyRecipeSyntaxBtn.addEventListener('click', () => {
                // Use backend API to get recipe syntax
                this.fetchAndCopyRecipeSyntax();
            });
        }

        // Send prompt to workflow buttons
        const sendPromptBtn = document.getElementById('sendPromptBtn');
        const sendNegativePromptBtn = document.getElementById('sendNegativePromptBtn');

        if (sendPromptBtn) {
            sendPromptBtn.addEventListener('click', () => {
                let promptText = this.currentRecipe?.gen_params?.prompt || '';
                if (this.shouldStripLoraOnCopy()) {
                    promptText = RecipeModal.stripLoraTags(promptText);
                }
                if (!promptText.trim()) {
                    showToast('toast.recipes.noPromptToSend', {}, 'warning');
                    return;
                }
                sendPromptToWorkflow(promptText);
            });
        }

        if (sendNegativePromptBtn) {
            sendNegativePromptBtn.addEventListener('click', () => {
                let negativePromptText = this.currentRecipe?.gen_params?.negative_prompt || '';
                if (this.shouldStripLoraOnCopy()) {
                    negativePromptText = RecipeModal.stripLoraTags(negativePromptText);
                }
                if (!negativePromptText.trim()) {
                    showToast('toast.recipes.noPromptToSend', {}, 'warning');
                    return;
                }
                sendPromptToWorkflow(negativePromptText, {
                    actionTypeText: 'Negative Prompt',
                });
            });
        }

        // Send params to workflow button
        const sendParamsBtn = document.getElementById('sendParamsBtn');
        if (sendParamsBtn) {
            sendParamsBtn.addEventListener('click', () => {
                const genParams = this.currentRecipe?.gen_params || {};
                if (!genParams || Object.keys(genParams).length === 0) {
                    showToast('No generation parameters available', {}, 'warning');
                    return;
                }
                sendGenParamsToWorkflow(genParams);
            });
        }
    }

    /**
     * Strip <lora:...> tags from prompt text and clean up residual punctuation/whitespace.
     * Handles both unescaped (<lora:...>) and HTML-escaped (&lt;lora:...&gt;) variants.
     * Cleans up artifacts like leading ", ", double commas, and extra whitespace.
     */
    static stripLoraTags(text) {
        return stripLoraTags(text);
    }

    shouldStripLoraOnCopy() {
        const toggle = document.getElementById('stripLoraOnCopyToggle');
        return toggle ? toggle.checked : false;
    }

    setupStripLoraToggle() {
        const toggle = document.getElementById('stripLoraOnCopyToggle');
        if (!toggle) return;

        const stored = getStorageItem('strip_lora_on_copy');
        if (stored !== null) {
            toggle.checked = stored === true;
        }

        toggle.addEventListener('change', () => {
            const checked = toggle.checked;
            setStorageItem('strip_lora_on_copy', checked);
            state.global.settings.strip_lora_on_copy = checked;
        });
    }

    // Helper method to copy text to clipboard
    copyToClipboard(text, successMessage) {
        copyToClipboard(text, successMessage);
    }

    // Fetch recipe syntax from backend and copy to clipboard
    async fetchAndCopyRecipeSyntax() {
        if (!this.recipeId) {
            showToast('toast.recipes.noRecipeId', {}, 'error');
            return;
        }

        try {
            // Fetch recipe syntax from backend
            const response = await fetch(`/api/lm/recipe/${this.recipeId}/syntax`);

            if (!response.ok) {
                throw new Error(`Failed to get recipe syntax: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success && data.syntax) {
                // Use the centralized copyToClipboard utility function
                await copyToClipboard(data.syntax, 'Recipe syntax copied to clipboard');
            } else {
                throw new Error(data.error || 'No syntax returned from server');
            }
        } catch (error) {
            console.error('Error fetching recipe syntax:', error);
            showToast('toast.recipes.copyFailed', { message: error.message }, 'error');
        }
    }

    // Send recipe to ComfyUI workflow
    async sendRecipeToWorkflow() {
        if (!this.recipeId) {
            showToast('toast.recipes.noRecipeId', {}, 'error');
            return;
        }

        try {
            // Fetch recipe syntax from backend
            const response = await fetch(`/api/lm/recipe/${this.recipeId}/syntax`);

            if (!response.ok) {
                throw new Error(`Failed to get recipe syntax: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success && data.syntax) {
                // Send the recipe syntax to ComfyUI workflow
                await sendLoraToWorkflow(data.syntax, false, 'recipe');
            } else {
                throw new Error(data.error || 'No syntax returned from server');
            }
        } catch (error) {
            console.error('Error sending recipe to workflow:', error);
            showToast('toast.recipes.sendToWorkflowFailed', { message: error.message }, 'error');
        }
    }

    // Add new method to handle downloading missing LoRAs
    async showDownloadMissingLorasModal() {
        console.log("currentRecipe", this.currentRecipe);
        // Get missing LoRAs from the current recipe
        const missingLoras = this.currentRecipe.loras.filter(lora => !lora.inLibrary);
        console.log("missingLoras", missingLoras);

        if (missingLoras.length === 0) {
            showToast('toast.recipes.noMissingLoras', {}, 'info');
            return;
        }

        try {
            state.loadingManager.showSimpleLoading('Getting version info for missing LoRAs...');

            // Get version info for each missing LoRA by calling the appropriate API endpoint
            const missingLorasWithVersionInfoPromises = missingLoras.map(async lora => {
                let endpoint;

                // Determine which endpoint to use based on available data
                if (lora.modelVersionId) {
                    endpoint = `/api/lm/loras/civitai/model/version/${lora.modelVersionId}`;
                } else if (lora.hash) {
                    endpoint = `/api/lm/loras/civitai/model/hash/${lora.hash}`;
                } else {
                    console.error("Missing both hash and modelVersionId for lora:", lora);
                    return null;
                }

                const response = await fetch(endpoint);
                const versionInfo = await response.json();

                // Return original lora data combined with version info
                return {
                    ...lora,
                    civitaiInfo: versionInfo
                };
            });

            // Wait for all API calls to complete
            const lorasWithVersionInfo = await Promise.all(missingLorasWithVersionInfoPromises);
            console.log("Loras with version info:", lorasWithVersionInfo);

            // Filter out null values (failed requests)
            const validLoras = lorasWithVersionInfo.filter(lora => lora !== null);

            if (validLoras.length === 0) {
                showToast('toast.recipes.missingLorasInfoFailed', {}, 'error');
                return;
            }

            // Close the recipe modal first
            modalManager.closeModal('recipeModal');

            // Prepare data for import manager using the retrieved information
            const recipeData = {
                loras: validLoras.map(lora => {
                    const civitaiInfo = lora.civitaiInfo;
                    const modelFile = civitaiInfo.files ?
                        civitaiInfo.files.find(file => isModelWeightFile(file.type)) : null;

                    return {
                        // Basic lora info
                        name: civitaiInfo.model?.name || lora.name,
                        version: civitaiInfo.name || '',
                        strength: lora.strength || 1.0,

                        // Model identifiers
                        modelId: lora.modelId || lora.model_id || civitaiInfo.modelId,
                        hash: modelFile?.hashes?.SHA256?.toLowerCase() || lora.hash,
                        id: civitaiInfo.id || lora.modelVersionId,

                        // Metadata
                        thumbnailUrl: civitaiInfo.images?.[0]?.url || '',
                        baseModel: civitaiInfo.baseModel || '',
                        downloadUrl: civitaiInfo.downloadUrl || '',
                        size: modelFile ? (modelFile.sizeKB * 1024) : 0,
                        file_name: modelFile ? modelFile.name.split('.')[0] : '',

                        // Status flags
                        existsLocally: false,
                        isDeleted: civitaiInfo.error === "Model not found",
                        isEarlyAccess: !!civitaiInfo.earlyAccessEndsAt,
                        earlyAccessEndsAt: civitaiInfo.earlyAccessEndsAt || ''
                    };
                })
            };

            console.log("recipeData for import:", recipeData);

            // Call ImportManager's download missing LoRAs method
            window.importManager.downloadMissingLoras(recipeData, this.currentRecipe.id);
        } catch (error) {
            console.error("Error downloading missing LoRAs:", error);
            showToast('toast.recipes.preparingForDownloadFailed', {}, 'error');
        } finally {
            state.loadingManager.hide();
        }
    }

    // Wire the reconnect form controls. The entry point is the explicit
    // "Reconnect" ghost button rendered for deleted LoRAs (see
    // setupLoraItemActions), keeping badges as pure status indicators.
    setupReconnectButtons() {
        // Add event listeners to reconnect cancel buttons
        const cancelButtons = document.querySelectorAll('.reconnect-cancel-btn');
        cancelButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const container = button.closest('.lora-reconnect-container');
                this.hideReconnectInput(container);
            });
        });

        // Add event listeners to reconnect confirm buttons
        const confirmButtons = document.querySelectorAll('.reconnect-confirm-btn');
        confirmButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const container = button.closest('.lora-reconnect-container');
                const input = container.querySelector('.reconnect-input');
                const loraIndex = container.getAttribute('data-lora-index');
                this.reconnectLora(loraIndex, input.value);
            });
        });

        // Add keydown handlers to reconnect inputs
        const reconnectInputs = document.querySelectorAll('.reconnect-input');
        reconnectInputs.forEach(input => {
            input.addEventListener('input', () => {
                this.clearReconnectError(input.closest('.lora-reconnect-container'));
            });
            input.addEventListener('keydown', (e) => {
                const container = input.closest('.lora-reconnect-container');
                // When a Combobox is attached it owns Enter (pick a highlighted
                // option, or commit free text via onCommit) and, while its
                // dropdown is open, Escape (close the dropdown first).
                const combobox = this._reconnectComboboxes && this._reconnectComboboxes.get(container);
                if (e.key === 'Enter') {
                    if (combobox) return;
                    const loraIndex = container.getAttribute('data-lora-index');
                    this.reconnectLora(loraIndex, input.value);
                } else if (e.key === 'Escape') {
                    if (combobox && combobox.isOpen()) return;
                    this.hideReconnectInput(container);
                }
            });
        });
    }

    showReconnectInput(loraIndex) {
        // Hide any currently active reconnect containers
        document.querySelectorAll('.lora-reconnect-container.active').forEach(active => {
            this.hideReconnectInput(active);
        });

        // Show the reconnect container for this lora
        const container = document.querySelector(`.lora-reconnect-container[data-lora-index="${loraIndex}"]`);
        if (container) {
            container.classList.add('active');
            this.clearReconnectError(container);
            const input = container.querySelector('.reconnect-input');
            input.focus();
            this._attachReconnectCombobox(container, loraIndex);
            this._loadReconnectSuggestions(container, loraIndex);
        }
    }

    hideReconnectInput(container) {
        if (container && container.classList.contains('active')) {
            container.classList.remove('active');
            this.clearReconnectError(container);
            const input = container.querySelector('.reconnect-input');
            if (input) input.value = '';
        }
        if (container) {
            this._destroyReconnectCombobox(container);
            // Invalidate any in-flight suggestions fetch for this panel
            this._reconnectSuggestionsToken = (this._reconnectSuggestionsToken || 0) + 1;
            const suggestions = container.querySelector('.reconnect-suggestions');
            if (suggestions) suggestions.innerHTML = '';
        }
    }

    _attachReconnectCombobox(container, loraIndex) {
        if (!this._reconnectComboboxes) {
            this._reconnectComboboxes = new Map();
        }
        if (this._reconnectComboboxes.has(container)) {
            return;
        }
        const input = container.querySelector('.reconnect-input');
        if (!input) {
            return;
        }
        const combobox = new Combobox(input, {
            fetchOptions: async (value) => {
                const suggestions = await this._fetchReconnectSuggestions(loraIndex, value);
                return suggestions.map(suggestion => suggestion.target_name);
            },
            // emptyText only labels the dropdown empty state; the input keeps
            // its own translated placeholder from the markup.
            emptyText: String(loraIndex) === 'checkpoint'
                ? translate('recipes.resources.checkpointReconnectSuggestionsEmpty', {}, 'No matching checkpoints in your local library')
                : translate('recipes.resources.reconnectSuggestionsEmpty', {}, 'No matching LoRAs in your local library'),
            onCommit: (value) => {
                this.reconnectLora(loraIndex, value);
            },
        });
        this._reconnectComboboxes.set(container, combobox);
    }

    _destroyReconnectCombobox(container) {
        const combobox = this._reconnectComboboxes && this._reconnectComboboxes.get(container);
        if (combobox) {
            combobox.destroy();
            this._reconnectComboboxes.delete(container);
        }
    }

    _destroyAllReconnectComboboxes() {
        if (!this._reconnectComboboxes) {
            return;
        }
        this._reconnectComboboxes.forEach(combobox => combobox.destroy());
        this._reconnectComboboxes.clear();
        this._reconnectSuggestionsToken = (this._reconnectSuggestionsToken || 0) + 1;
    }

    async _fetchReconnectSuggestions(loraIndex, query) {
        const suffix = query ? `?query=${encodeURIComponent(query)}` : '';
        const targetPath = String(loraIndex) === 'checkpoint'
            ? 'checkpoint/reconnect-suggestions'
            : `lora/${loraIndex}/reconnect-suggestions`;
        const response = await fetch(`/api/lm/recipe/${this.recipeId}/${targetPath}${suffix}`);
        if (!response.ok) {
            return [];
        }
        const result = await response.json();
        return result && result.success && Array.isArray(result.suggestions) ? result.suggestions : [];
    }

    async _loadReconnectSuggestions(container, loraIndex) {
        const listElement = container.querySelector('.reconnect-suggestions');
        if (!listElement) {
            return;
        }
        const token = (this._reconnectSuggestionsToken || 0) + 1;
        this._reconnectSuggestionsToken = token;
        listElement.innerHTML = `<div class="reconnect-suggestions-loading">${escapeHtml(translate('recipes.resources.reconnectSuggestionsLoading', {}, 'Searching local library...'))}</div>`;
        try {
            const suggestions = await this._fetchReconnectSuggestions(loraIndex);
            // Stale guard: panel closed or another item opened while fetching
            if (token !== this._reconnectSuggestionsToken || !container.classList.contains('active')) {
                return;
            }
            this._renderReconnectSuggestions(container, suggestions, loraIndex);
        } catch (error) {
            console.error('Error fetching reconnect suggestions:', error);
            if (token !== this._reconnectSuggestionsToken || !container.classList.contains('active')) {
                return;
            }
            this._renderReconnectSuggestions(container, [], loraIndex);
        }
    }

    _renderReconnectSuggestions(container, suggestions, loraIndex) {
        const listElement = container.querySelector('.reconnect-suggestions');
        if (!listElement) {
            return;
        }
        listElement.innerHTML = '';
        if (!suggestions.length) {
            const empty = document.createElement('div');
            empty.className = 'reconnect-suggestions-empty';
            empty.textContent = String(loraIndex) === 'checkpoint'
                ? translate('recipes.resources.checkpointReconnectSuggestionsEmpty', {}, 'No matching checkpoints in your local library')
                : translate('recipes.resources.reconnectSuggestionsEmpty', {}, 'No matching LoRAs in your local library');
            listElement.appendChild(empty);
            return;
        }
        const reasonLabels = {
            same_hash: translate('recipes.resources.reconnectMatchSameHash', {}, 'Same hash'),
            same_version: translate('recipes.resources.reconnectMatchSameVersion', {}, 'Same model version'),
            similar_filename: translate('recipes.resources.reconnectMatchSimilarFilename', {}, 'Similar filename'),
            similar_name: translate('recipes.resources.reconnectMatchSimilarName', {}, 'Similar name'),
        };
        suggestions.forEach(suggestion => {
            // The filename (stem) is what the match scored on and what gets
            // submitted — show it as the primary label, with the base model
            // as secondary context. The model name is omitted: it played no
            // part in the match and only adds noise.
            const stem = suggestion.target_name || suggestion.file_name || '';
            const secondaryParts = [];
            if (suggestion.base_model) {
                secondaryParts.push(suggestion.base_model);
            }
            const secondary = secondaryParts.join(' · ');
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'reconnect-suggestion';
            row.title = stem;
            row.innerHTML = `
                <img class="reconnect-suggestion-preview" src="${escapeHtml(suggestion.preview_url || '/loras_static/images/no-preview.png')}" alt="" loading="lazy" onerror="this.src='/loras_static/images/no-preview.png'">
                <span class="reconnect-suggestion-info">
                    <span class="reconnect-suggestion-name">${escapeHtml(stem)}</span>
                    ${secondary ? `<span class="reconnect-suggestion-secondary">${escapeHtml(secondary)}</span>` : ''}
                </span>
                <span class="reconnect-suggestion-reason">${escapeHtml(reasonLabels[suggestion.match_reason] || suggestion.match_reason || '')}</span>
            `;
            row.addEventListener('click', () => {
                this.reconnectLora(loraIndex, suggestion.target_name);
            });
            listElement.appendChild(row);
        });
    }

    showReconnectError(container, message) {
        const error = container && container.querySelector('.reconnect-error');
        if (error) {
            error.textContent = message;
            error.classList.add('active');
        }
    }

    clearReconnectError(container) {
        const error = container && container.querySelector('.reconnect-error');
        if (error) {
            error.textContent = '';
            error.classList.remove('active');
        }
    }

    async reconnectLora(loraIndex, inputValue) {
        // The checkpoint entry reuses the same container/combobox machinery;
        // route it to the checkpoint-specific flow (no <lora:...> syntax, no
        // lora_index in the payload).
        if (String(loraIndex) === 'checkpoint') {
            return this.reconnectCheckpoint(inputValue);
        }
        const container = document.querySelector(`.lora-reconnect-container[data-lora-index="${loraIndex}"]`);

        if (!inputValue || !inputValue.trim()) {
            this.showReconnectError(container, translate('toast.recipes.enterLoraName', {}, 'Please enter a LoRA name or syntax'));
            return;
        }

        try {
            // Parse input value to extract file_name
            let loraSyntaxMatch = inputValue.match(/<lora:([^:>]+)(?::[^>]+)?>/);
            let fileName = loraSyntaxMatch ? loraSyntaxMatch[1] : inputValue.trim();

            // Remove .safetensors extension if present
            fileName = fileName.replace(/\.safetensors$/, '');

            state.loadingManager.showSimpleLoading('Reconnecting LoRA...');

            // Call API to reconnect the LoRA
            const response = await fetch('/api/lm/recipe/lora/reconnect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: this.recipeId,
                    lora_index: loraIndex,
                    target_name: fileName
                })
            });

            const result = await response.json();

            if (result.success) {
                // Hide the reconnect input
                this.hideReconnectInput(container);

                // Update the current recipe with the updated lora data
                this.currentRecipe.loras[loraIndex] = result.updated_lora;

                // Show success message
                showToast('toast.recipes.reconnectedSuccessfully', {}, 'success');

                // Same-architecture-family reconnects (e.g. Pony ↔ Illustrious)
                // succeed but carry structured mismatch data — warn the user.
                if (result.base_model_mismatch) {
                    showToast(
                        'toast.recipes.reconnectBaseModelMismatch',
                        {
                            recipe: result.base_model_mismatch.recipe_base_model,
                            lora: result.base_model_mismatch.lora_base_model,
                        },
                        'warning'
                    );
                }

                // Refresh modal to show updated content
                setTimeout(() => {
                    this.showRecipeDetails(this.currentRecipe);
                }, 500);

                state.virtualScroller.updateSingleItem(this.listFilePath || this.currentRecipe.file_path, {
                    loras: this.currentRecipe.loras
                });
            } else {
                this.showReconnectError(container, translate('toast.recipes.reconnectFailed', { message: result.error }, `Error reconnecting LoRA: ${result.error}`));
            }
        } catch (error) {
            console.error('Error reconnecting LoRA:', error);
            this.showReconnectError(container, translate('toast.recipes.reconnectFailed', { message: error.message }, `Error reconnecting LoRA: ${error.message}`));
        } finally {
            state.loadingManager.hide();
        }
    }

    async restoreLora(loraIndex) {
        try {
            state.loadingManager.showSimpleLoading('Restoring LoRA...');

            const response = await fetch('/api/lm/recipe/lora/restore', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: this.recipeId,
                    lora_index: loraIndex
                })
            });

            const result = await response.json();

            if (result.success) {
                // Swap the entry back to its pre-reconnect state
                this.currentRecipe.loras[loraIndex] = result.updated_lora;

                showToast('toast.recipes.loraRestored', {}, 'success');

                setTimeout(() => {
                    this.showRecipeDetails(this.currentRecipe);
                }, 500);

                state.virtualScroller.updateSingleItem(this.listFilePath || this.currentRecipe.file_path, {
                    loras: this.currentRecipe.loras
                });
            } else {
                showToast('toast.recipes.loraRestoreFailed', { message: result.error }, 'error');
            }
        } catch (error) {
            console.error('Error restoring LoRA:', error);
            showToast('toast.recipes.loraRestoreFailed', { message: error.message }, 'error');
        } finally {
            state.loadingManager.hide();
        }
    }

    async reconnectCheckpoint(inputValue) {
        const container = document.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');

        if (!inputValue || !inputValue.trim()) {
            this.showReconnectError(container, translate('toast.recipes.enterCheckpointName', {}, 'Please enter a checkpoint name'));
            return;
        }

        try {
            // Remove .safetensors extension if present
            const fileName = inputValue.trim().replace(/\.safetensors$/, '');

            state.loadingManager.showSimpleLoading('Reconnecting checkpoint...');

            // Call API to reconnect the checkpoint entry
            const response = await fetch('/api/lm/recipe/checkpoint/reconnect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: this.recipeId,
                    target_name: fileName
                })
            });

            const result = await response.json();

            if (result.success) {
                // Hide the reconnect input
                this.hideReconnectInput(container);

                // Update the current recipe with the updated checkpoint data
                this.currentRecipe.checkpoint = result.updated_checkpoint;

                // Show success message
                showToast('toast.recipes.checkpointReconnectedSuccessfully', {}, 'success');

                // Same-architecture-family reconnects (e.g. Pony ↔ Illustrious)
                // succeed but carry structured mismatch data — warn the user.
                if (result.base_model_mismatch) {
                    showToast(
                        'toast.recipes.reconnectCheckpointBaseModelMismatch',
                        {
                            recipe: result.base_model_mismatch.recipe_base_model,
                            checkpoint: result.base_model_mismatch.checkpoint_base_model,
                        },
                        'warning'
                    );
                }

                // Refresh modal to show updated content
                setTimeout(() => {
                    this.showRecipeDetails(this.currentRecipe);
                }, 500);

                state.virtualScroller.updateSingleItem(this.listFilePath || this.currentRecipe.file_path, {
                    checkpoint: this.currentRecipe.checkpoint
                });
            } else {
                this.showReconnectError(container, translate('toast.recipes.checkpointReconnectFailed', { message: result.error }, `Error reconnecting checkpoint: ${result.error}`));
            }
        } catch (error) {
            console.error('Error reconnecting checkpoint:', error);
            this.showReconnectError(container, translate('toast.recipes.checkpointReconnectFailed', { message: error.message }, `Error reconnecting checkpoint: ${error.message}`));
        } finally {
            state.loadingManager.hide();
        }
    }

    async restoreCheckpoint() {
        try {
            state.loadingManager.showSimpleLoading('Restoring checkpoint...');

            const response = await fetch('/api/lm/recipe/checkpoint/restore', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: this.recipeId
                })
            });

            const result = await response.json();

            if (result.success) {
                // Swap the entry back to its pre-reconnect state
                this.currentRecipe.checkpoint = result.updated_checkpoint;

                showToast('toast.recipes.checkpointRestored', {}, 'success');

                setTimeout(() => {
                    this.showRecipeDetails(this.currentRecipe);
                }, 500);

                state.virtualScroller.updateSingleItem(this.listFilePath || this.currentRecipe.file_path, {
                    checkpoint: this.currentRecipe.checkpoint
                });
            } else {
                showToast('toast.recipes.checkpointRestoreFailed', { message: result.error }, 'error');
            }
        } catch (error) {
            console.error('Error restoring checkpoint:', error);
            showToast('toast.recipes.checkpointRestoreFailed', { message: error.message }, 'error');
        } finally {
            state.loadingManager.hide();
        }
    }

    async markCheckpointHashInvalid() {
        const recipeId =
            this.recipeId ||
            extractRecipeId(this.listFilePath || this.currentRecipe?.file_path);
        if (!recipeId) {
            return;
        }
        try {
            await fetch('/api/lm/recipe/checkpoint/mark-hash-invalid', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: recipeId,
                }),
            });
            if (this.currentRecipe?.checkpoint) {
                this.currentRecipe.checkpoint.hashInvalid = true;
                this.syncResourcesSection(this.currentRecipe);
            }
        } catch (error) {
            console.warn('Failed to mark checkpoint hash invalid:', error);
        }
    }

    renderCheckpoint(checkpoint) {
        const existsLocally = !!checkpoint.inLibrary;
        const isDeleted = !!checkpoint.isDeleted;
        const hashInvalid = !!checkpoint.hashInvalid;
        // "Broken" = cannot be restored by downloading: explicitly marked
        // deleted, an unresolvable hash, or an entry with no CivitAI
        // identifiers at all (a name-only remnant that never had a version
        // id to query — it can only be fixed by reconnecting a local model).
        const broken = isDeleted
            || hashInvalid
            || (!existsLocally && !this.canDownloadCheckpoint(checkpoint));
        const localPath = checkpoint.localPath || '';
        const previewUrl = checkpoint.preview_url || checkpoint.thumbnailUrl || '/loras_static/images/no-preview.png';
        const isPreviewVideo = typeof previewUrl === 'string' && previewUrl.toLowerCase().endsWith('.mp4');
        const checkpointName = checkpoint.name || checkpoint.modelName || checkpoint.file_name || 'Checkpoint';
        const versionLabel = checkpoint.version || checkpoint.modelVersionName || '';
        const baseModel = checkpoint.baseModel || checkpoint.base_model || '';
        const modelTypeRaw = (checkpoint.sub_type || checkpoint.type || 'checkpoint').toLowerCase();
        const modelTypeLabel = modelTypeRaw === 'diffusion_model' ? 'Diffusion Model' : 'Checkpoint';

        const previewMedia = isPreviewVideo ? `
            <video class="thumbnail-video" autoplay loop muted playsinline>
                <source src="${previewUrl}" type="video/mp4">
            </video>
        ` : `<img src="${previewUrl}" alt="Checkpoint preview" onerror="this.onerror=null; this.src='/loras_static/images/no-preview.png'">`;

        // Status badge: pure indicator with a tooltip, mirroring the LoRA
        // items and the versions-tab badge pattern. Deleted / unresolvable
        // hash states render the same fixable-broken badges as LoRA entries.
        let badge;
        if (existsLocally) {
            badge = `
                <div class="local-badge" title="${escapeHtml(translate('recipes.resources.inLibraryTooltip', {}, 'This model exists in your local library'))}">
                    <i class="fas fa-check" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.inLibrary', {}, 'In Library'))}
                </div>
            `;
        } else if (isDeleted) {
            badge = `
                <div class="deleted-badge" title="${escapeHtml(translate('recipes.resources.checkpointDeletedTooltip', {}, 'This checkpoint was deleted from the source and can no longer be downloaded - reconnect it with a local model'))}">
                    <i class="fas fa-trash-alt" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.deleted', {}, 'Deleted'))}
                </div>
            `;
        } else if (hashInvalid) {
            badge = `
                <div class="invalid-hash-badge" title="${escapeHtml(translate('recipes.resources.checkpointHashInvalidTooltip', {}, 'This checkpoint hash cannot be resolved on CivitAI - the model may have been updated'))}">
                    <i class="fas fa-question-circle" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.hashInvalid', {}, 'Unresolvable Hash'))}
                </div>
            `;
        } else {
            badge = `
                <div class="missing-badge" title="${escapeHtml(translate('recipes.resources.notInLibraryTooltip', {}, 'This model is not in your library'))}">
                    <i class="fas fa-exclamation-triangle" aria-hidden="true"></i> ${escapeHtml(translate('recipes.resources.notInLibrary', {}, 'Not in Library'))}
                </div>
            `;
        }

        // Action row: broken (deleted / unresolvable hash) entries offer the
        // reconnect affordance instead of the download button — same rule as
        // the LoRA items. A local checkpoint only exposes "Send to ComfyUI".
        const actions = [];
        if (existsLocally && localPath) {
            actions.push(`
                <button class="resource-action primary compact checkpoint-send">
                    <i class="fas fa-paper-plane"></i>
                    <span>${translate('recipes.actions.sendCheckpoint', {}, 'Send to ComfyUI')}</span>
                </button>
            `);
        } else if (broken) {
            const reconnectLabel = translate('recipes.resources.reconnectCheckpoint', {}, 'Reconnect');
            const reconnectTooltip = translate('recipes.resources.reconnectCheckpointTooltip', {}, 'Reconnect with a local checkpoint');
            actions.push(`
                <button type="button" class="resource-action ghost compact checkpoint-reconnect"
                    title="${escapeHtml(reconnectTooltip)}" aria-label="${escapeHtml(reconnectTooltip)}">
                    <i class="fas fa-link" aria-hidden="true"></i>
                    <span>${escapeHtml(reconnectLabel)}</span>
                </button>
            `);
        } else if (!existsLocally && this.canDownloadCheckpoint(checkpoint)) {
            actions.push(`
                <button class="resource-action primary compact checkpoint-download">
                    <i class="fas fa-download"></i>
                    <span>${translate('modals.model.versions.actions.download', {}, 'Download')}</span>
                </button>
            `);
        }
        const actionsMarkup = actions.filter(Boolean).join('');
        const actionsRow = actionsMarkup
            ? `<div class="recipe-lora-actions">${actionsMarkup}</div>`
            : '';

        // Civitai link lives inline with the title, same as LoRA items.
        // Skipped for deleted models: their source page is gone.
        const titleLink = isDeleted
            ? ''
            : this.renderCivitaiLink(this.getResourceCivitaiUrl(checkpoint));

        // Only in-library checkpoints are row-navigable; make it keyboard-accessible.
        const rowA11yAttributes = existsLocally
            ? ` role="button" tabindex="0" aria-label="${escapeHtml(translate('recipes.resources.openCheckpointDetails', { name: checkpointName }, `View ${checkpointName} in the model library`))}"`
            : '';

        // A reconnect snapshot marks a manually reconnected entry. The restore
        // icon on the info row doubles as that marker (mirrors LoRA entries).
        let undoReconnectIcon = '';
        if (existsLocally && checkpoint.reconnectSnapshot) {
            const previousName = checkpoint.reconnectSnapshot.name
                || checkpoint.reconnectSnapshot.file_name
                || checkpoint.reconnectSnapshot.modelName
                || '';
            const undoLabel = translate('recipes.resources.undoReconnect', {}, 'Undo');
            const undoTooltip = previousName
                ? translate('recipes.resources.undoReconnectTooltipNamed', { name: previousName }, `Restore to ${previousName} (the association before reconnecting)`)
                : translate('recipes.resources.undoReconnectTooltip', {}, 'Restore the association this entry had before reconnecting');
            undoReconnectIcon = `
                <button type="button" class="checkpoint-undo-reconnect"
                    title="${escapeHtml(undoTooltip)}" aria-label="${escapeHtml(undoTooltip)}">
                    <i class="fas fa-rotate-left" aria-hidden="true"></i>
                </button>
            `;
        }

        // Inline reconnect form for broken entries, sharing the LoRA
        // container structure/classes and the combobox interaction.
        const reconnectContainer = broken ? `
            <div class="lora-reconnect-container" data-lora-index="checkpoint">
                <div class="reconnect-instructions">
                    <p>${escapeHtml(translate('recipes.resources.checkpointReconnectInstructions', {}, 'Enter checkpoint name to reconnect:'))}</p>
                </div>
                <div class="reconnect-form">
                    <input type="text" class="reconnect-input" placeholder="${escapeHtml(translate('recipes.resources.checkpointReconnectPlaceholder', {}, 'Enter checkpoint name'))}">
                    <div class="reconnect-actions">
                        <button class="reconnect-cancel-btn">${escapeHtml(translate('common.cancel', {}, 'Cancel'))}</button>
                        <button class="reconnect-confirm-btn">${escapeHtml(translate('recipes.resources.reconnect', {}, 'Reconnect'))}</button>
                    </div>
                </div>
                <div class="reconnect-suggestions"></div>
                <p class="reconnect-error" role="alert"></p>
            </div>` : '';

        return `
            <div class="recipe-lora-item checkpoint-item ${existsLocally ? 'exists-locally' : (isDeleted ? 'is-deleted' : 'missing-locally')}"${rowA11yAttributes}>
                <div class="recipe-lora-thumbnail">
                    ${previewMedia}
                </div>
                <div class="recipe-lora-content">
                    <div class="recipe-lora-header">
                        <div class="recipe-lora-title">
                            <h4>${checkpointName}</h4>
                            ${titleLink}
                        </div>
                        <div class="badge-container">${badge}</div>
                    </div>
                    <div class="recipe-lora-info recipe-checkpoint-meta">
                        ${versionLabel ? `<div class="recipe-lora-version">${versionLabel}</div>` : ''}
                        ${baseModel ? `<div class="base-model">${baseModel}</div>` : ''}
                        ${modelTypeLabel ? `<span class="checkpoint-type-text">${modelTypeLabel}</span>` : ''}
                        ${undoReconnectIcon}
                    </div>
                    ${actionsRow}
                </div>
                ${reconnectContainer}
            </div>
        `;
    }

    setupCheckpointActions(container, checkpoint) {
        const sendBtn = container.querySelector('.checkpoint-send');
        if (sendBtn) {
            sendBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.sendCheckpointToWorkflow(checkpoint);
            });
        }

        const downloadBtn = container.querySelector('.checkpoint-download');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await this.downloadCheckpoint(checkpoint, downloadBtn);
            });
        }

        // Deferred wiring can run again after a hydration re-render while the
        // latest DOM is already in place; a data flag prevents stacking
        // duplicate handlers (same pattern as the LoRA item actions).
        const reconnectBtn = container.querySelector('.checkpoint-reconnect');
        if (reconnectBtn && reconnectBtn.dataset.wired !== 'true') {
            reconnectBtn.dataset.wired = 'true';
            reconnectBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showReconnectInput('checkpoint');
            });
        }

        const undoBtn = container.querySelector('.checkpoint-undo-reconnect');
        if (undoBtn && undoBtn.dataset.wired !== 'true') {
            undoBtn.dataset.wired = 'true';
            undoBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.restoreCheckpoint();
            });
        }
    }

    setupCheckpointNavigation(container, checkpoint) {
        // Only in-library checkpoints navigate (to the local detail view).
        // Missing checkpoints expose explicit Download / Civitai-link
        // controls instead, so a row click never has two different outcomes.
        if (!checkpoint.inLibrary) {
            return;
        }
        const checkpointItem = container.querySelector('.checkpoint-item');
        if (!checkpointItem) return;

        checkpointItem.addEventListener('click', (e) => {
            if (e.target.closest('.resource-action') || e.target.closest('.recipe-civitai-link')) {
                return;
            }
            this.navigateToCheckpointPage(checkpoint);
        });
        checkpointItem.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.navigateToCheckpointPage(checkpoint);
            }
        });
    }

    canDownloadCheckpoint(checkpoint) {
        if (!checkpoint) return false;
        const modelId = checkpoint.modelId || checkpoint.modelID || checkpoint.model_id;
        const versionId = checkpoint.id || checkpoint.modelVersionId;
        return !!(modelId && versionId);
    }

    async sendCheckpointToWorkflow(checkpoint) {
        if (!checkpoint || !checkpoint.localPath) {
            showToast('toast.recipes.missingCheckpointPath', {}, 'error');
            return;
        }

        const modelType = (checkpoint.sub_type || checkpoint.type || 'checkpoint').toLowerCase();
        const isDiffusionModel = modelType === 'diffusion_model' || modelType === 'unet';
        const widgetName = isDiffusionModel ? 'unet_name' : 'ckpt_name';

        const actionTypeText = translate(
            isDiffusionModel ? 'uiHelpers.nodeSelector.diffusionModel' : 'uiHelpers.nodeSelector.checkpoint',
            {},
            isDiffusionModel ? 'Diffusion Model' : 'Checkpoint'
        );
        const successMessage = translate(
            'uiHelpers.workflow.modelUpdated',
            {},
            'Model updated in workflow'
        );
        const failureMessage = translate(
            'uiHelpers.workflow.modelFailed',
            {},
            'Failed to update model node'
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

        await sendModelPathToWorkflow(checkpoint.localPath, {
            widgetName,
            collectionType: MODEL_TYPES.CHECKPOINT,
            actionTypeText,
            successMessage,
            failureMessage,
            missingNodesMessage,
            missingTargetMessage,
        });
    }

    async downloadCheckpoint(checkpoint, button) {
        if (!this.canDownloadCheckpoint(checkpoint)) {
            // No resolvable CivitAI identifiers for this entry. A hash-only
            // checkpoint is not downloadable through the version downloader —
            // point the user at the reconnect flow instead.
            if (this._getCheckpointHash(checkpoint)) {
                showToast('toast.recipes.checkpointDownloadUnavailable', {}, 'warning');
            } else {
                showToast('toast.recipes.missingCheckpointInfo', {}, 'error');
            }
            return;
        }

        const modelId = checkpoint.modelId || checkpoint.modelID || checkpoint.model_id;
        const versionId = checkpoint.id || checkpoint.modelVersionId;
        const versionName = checkpoint.version || checkpoint.modelVersionName || checkpoint.name || 'Checkpoint';

        if (button) {
            button.disabled = true;
        }

        try {
            const success = await downloadManager.downloadVersionWithDefaults(
                MODEL_TYPES.CHECKPOINT,
                modelId,
                versionId,
                {
                    versionName,
                    source: 'recipe-modal',
                }
            );
            if (success) {
                await this.refreshResourcesAfterDownload();
                return;
            }
            // Business-level download failure (the request completed but the
            // backend rejected it). Enroll the entry in the rematch/reconnect
            // remediation flow only when the failure is clearly unresolvable
            // (model removed or version gone on CivitAI) — the same signal
            // rule as the LoRA path. Transient failures (network, 5xx) leave
            // the entry untouched.
            if (this._isUnresolvableDownloadError(downloadManager._lastDownloadError)) {
                await this.markCheckpointHashInvalid();
            }
        } catch (error) {
            console.error('Error downloading checkpoint:', error);
            showToast('toast.recipes.downloadCheckpointFailed', { message: error.message }, 'error');
        } finally {
            if (button) {
                button.disabled = false;
            }
        }
    }

    /**
     * Decide whether a download failure means the model is unrecoverable.
     *
     * Mirrors the LoRA behaviour: the hash invalid flag (and the resulting
     * rematch/reconnect candidacy) is only set when CivitAI explicitly says
     * the model cannot be resolved — never for transient transport errors.
     */
    _isUnresolvableDownloadError(message) {
        if (!message) {
            return false;
        }
        const text = String(message).toLowerCase();
        return /(not found|no longer available|deleted|removed|404|410|gone)/.test(text);
    }

    getResourceCivitaiUrl(resource) {
        if (!resource) {
            return null;
        }
        const modelId = resource.modelId || resource.modelID || resource.model_id || null;
        const versionId = resource.id || resource.modelVersionId || null;
        const modelName = resource.modelName || resource.name || resource.file_name || null;
        return buildCivitaiUrl({
            modelId,
            versionId,
            modelName,
            host: state?.global?.settings?.civitai_host,
        });
    }

    canDownloadLora(lora) {
        if (!lora) return false;
        const modelId = lora.modelId || lora.modelID || lora.model_id;
        const versionId = lora.id || lora.modelVersionId;
        // Direct download needs both identifiers; a hash alone is enough
        // because downloadRecipeLora resolves it to a version on demand —
        // the same fallback the bulk "download missing" flow uses.
        return !!((modelId && versionId) || lora.hash);
    }

    renderCivitaiLink(url) {
        if (!url) {
            return '';
        }
        const tooltip = translate('recipes.resources.viewOnCivitai', {}, 'View on Civitai');
        return `
            <a
                class="recipe-civitai-link"
                href="${escapeHtml(url)}"
                target="_blank"
                rel="noopener noreferrer"
                title="${escapeHtml(tooltip)}"
                aria-label="${escapeHtml(tooltip)}"
            >
                <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i>
            </a>
        `;
    }

    renderLoraItemActions(loraIndex, { existsLocally, needsReconnect }) {
        // In-library LoRAs need no remediation: the badge and the local path
        // already tell the full story. (The restore affordance for manually
        // reconnected entries lives on the info row, not here.)
        if (existsLocally) {
            return '';
        }

        const controls = [];
        if (needsReconnect) {
            const reconnectLabel = translate('recipes.resources.reconnect', {}, 'Reconnect');
            const reconnectTooltip = translate('recipes.resources.reconnectTooltip', {}, 'Reconnect with a local LoRA');
            controls.push(`
                <button type="button" class="resource-action ghost compact lora-reconnect" data-lora-index="${loraIndex}"
                    title="${escapeHtml(reconnectTooltip)}" aria-label="${escapeHtml(reconnectTooltip)}">
                    <i class="fas fa-link" aria-hidden="true"></i>
                    <span>${escapeHtml(reconnectLabel)}</span>
                </button>
            `);
        } else {
            // needsReconnect already implies canDownloadLora() here, so the
            // download action is unconditional.
            const downloadLabel = translate('recipes.resources.download', {}, 'Download');
            const downloadTooltip = translate('recipes.resources.downloadLoraTooltip', {}, 'Download this LoRA');
            controls.push(`
                <button type="button" class="resource-action primary compact lora-download" data-lora-index="${loraIndex}"
                    title="${escapeHtml(downloadTooltip)}" aria-label="${escapeHtml(downloadTooltip)}">
                    <i class="fas fa-download" aria-hidden="true"></i>
                    <span>${escapeHtml(downloadLabel)}</span>
                </button>
            `);
        }

        return `<div class="recipe-lora-actions">${controls.join('')}</div>`;
    }

    setupLoraItemActions() {
        const lorasListElement = document.getElementById('recipeLorasList');
        if (!lorasListElement) {
            return;
        }

        // Deferred wiring can run again after a hydration re-render while the
        // latest DOM is already in place; a data flag prevents stacking
        // duplicate handlers (which would fire the download twice).
        lorasListElement.querySelectorAll('.lora-download').forEach(button => {
            if (button.dataset.wired === 'true') {
                return;
            }
            button.dataset.wired = 'true';
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const loraIndex = parseInt(button.dataset.loraIndex, 10);
                const lora = this.currentRecipe?.loras?.[loraIndex];
                if (lora) {
                    this.downloadRecipeLora(lora, button, loraIndex);
                }
            });
        });

        lorasListElement.querySelectorAll('.lora-reconnect').forEach(button => {
            if (button.dataset.wired === 'true') {
                return;
            }
            button.dataset.wired = 'true';
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showReconnectInput(button.dataset.loraIndex);
            });
        });

        lorasListElement.querySelectorAll('.lora-undo-reconnect').forEach(button => {
            if (button.dataset.wired === 'true') {
                return;
            }
            button.dataset.wired = 'true';
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                this.restoreLora(button.dataset.loraIndex);
            });
        });
    }

    /**
     * Resolve the Civitai model/version identifiers needed for download.
     * Recipe LoRAs parsed from PNG metadata often carry only a hash; resolve
     * it through the same endpoint the bulk "download missing" flow uses.
     */
    async resolveLoraDownloadIdentifiers(lora) {
        let modelId = lora.modelId || lora.modelID || lora.model_id;
        let versionId = lora.id || lora.modelVersionId;
        let versionName = lora.modelVersionName || lora.modelName || lora.name || 'LoRA';

        if (modelId && versionId) {
            return { modelId, versionId, versionName };
        }

        if (!lora.hash) {
            return null;
        }

        const response = await fetch(`/api/lm/loras/civitai/model/hash/${lora.hash}`);
        const versionInfo = await response.json();
        if (versionInfo?.error) {
            return null;
        }

        modelId = versionInfo.modelId || versionInfo.model?.id;
        versionId = versionInfo.id;
        versionName = versionInfo.name || versionName;

        return modelId && versionId ? { modelId, versionId, versionName } : null;
    }

    /**
     * A completed download flips inLibrary flags server-side; re-fetch the
     * recipe and reconcile both this modal's resources section and the
     * recipe card on the listing page (mirrors the bulk download flow in
     * BulkMissingLoraDownloadManager).
     */
    async refreshResourcesAfterDownload() {
        try {
            const recipeId =
                this.recipeId ||
                extractRecipeId(this.listFilePath || this.currentRecipe?.file_path);
            if (!recipeId) {
                return;
            }
            const updated = await fetchRecipeDetails(recipeId);
            if (!updated) {
                return;
            }
            this.currentRecipe.loras = updated.loras ?? this.currentRecipe.loras;
            this.currentRecipe.checkpoint = updated.checkpoint ?? this.currentRecipe.checkpoint;
            this.syncResourcesSection(this.currentRecipe);
            if (state.virtualScroller) {
                state.virtualScroller.updateSingleItem(
                    this.listFilePath || this.currentRecipe.file_path,
                    updated
                );
            }
        } catch (error) {
            console.warn('Failed to refresh recipe resources after download:', error);
        }
    }

    async downloadRecipeLora(lora, button, loraIndex) {
        if (!this.canDownloadLora(lora)) {
            showToast('toast.recipes.missingLoraDownloadInfo', {}, 'error');
            return;
        }

        if (button) {
            button.disabled = true;
        }

        // Hash-only LoRAs need a network round trip to resolve identifiers
        // before the progress UI can appear; show immediate feedback so the
        // click never feels dead.
        const hasDirectIds = !!(
            (lora.modelId || lora.modelID || lora.model_id) &&
            (lora.id || lora.modelVersionId)
        );
        if (!hasDirectIds) {
            state.loadingManager.showSimpleLoading(
                translate('recipes.resources.preparingDownload', {}, 'Preparing download...')
            );
        }

        try {
            const identifiers = await this.resolveLoraDownloadIdentifiers(lora);
            if (!hasDirectIds) {
                state.loadingManager.hide();
            }
            if (!identifiers) {
                if (!hasDirectIds && lora.hash) {
                    await this.markLoraHashInvalid(loraIndex);
                    showToast('toast.recipes.hashNotFoundOnCivitai', {}, 'error');
                } else {
                    showToast('toast.recipes.missingLoraDownloadInfo', {}, 'error');
                }
                return;
            }

            const success = await downloadManager.downloadVersionWithDefaults(
                MODEL_TYPES.LORA,
                identifiers.modelId,
                identifiers.versionId,
                {
                    versionName: identifiers.versionName,
                    source: 'recipe-modal',
                }
            );
            if (success) {
                await this.refreshResourcesAfterDownload();
                return;
            }
            // Business-level download failure (the request completed but the
            // backend rejected it). Mark the hash invalid — and thereby offer
            // the reconnect affordance — only when the failure is clearly
            // unresolvable (model removed or version gone on CivitAI), the
            // same signal rule as the checkpoint path. Transient failures
            // (network, 5xx) leave the entry untouched.
            if (this._isUnresolvableDownloadError(downloadManager._lastDownloadError)) {
                await this.markLoraHashInvalid(loraIndex);
            }
        } catch (error) {
            if (!hasDirectIds) {
                state.loadingManager.hide();
            }
            console.error('Error downloading LoRA:', error);
            showToast('toast.recipes.downloadLoraFailed', { message: error.message }, 'error');
        } finally {
            if (button) {
                button.disabled = false;
            }
        }
    }

    async markLoraHashInvalid(loraIndex) {
        const recipeId =
            this.recipeId ||
            extractRecipeId(this.listFilePath || this.currentRecipe?.file_path);
        if (!recipeId) {
            return;
        }
        try {
            await fetch('/api/lm/recipe/lora/mark-hash-invalid', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_id: recipeId,
                    lora_index: loraIndex,
                }),
            });
            if (this.currentRecipe?.loras?.[loraIndex]) {
                this.currentRecipe.loras[loraIndex].hashInvalid = true;
                this.syncResourcesSection(this.currentRecipe);
            }
        } catch (error) {
            console.warn('Failed to mark LoRA hash invalid:', error);
        }
    }

    navigateToCheckpointPage(checkpoint) {
        const checkpointHash = this._getCheckpointHash(checkpoint);

        if (!checkpointHash) {
            showToast('toast.recipes.missingCheckpointInfo', {}, 'error');
            return;
        }

        modalManager.closeModal('recipeModal');

        removeSessionItem('recipe_to_checkpoint_filterHash');
        removeSessionItem('recipe_to_checkpoint_filterHashes');
        removeSessionItem('filterCheckpointRecipeName');

        setSessionItem('recipe_to_checkpoint_filterHash', checkpointHash.toLowerCase());
        if (this.currentRecipe?.title) {
            setSessionItem('filterCheckpointRecipeName', this.currentRecipe.title);
        }

        window.location.href = '/checkpoints';
    }

    _getCheckpointHash(checkpoint) {
        if (!checkpoint) return '';
        const hash =
            checkpoint.hash ||
            checkpoint.sha256 ||
            checkpoint.sha256_hash ||
            checkpoint.sha256Hash ||
            checkpoint.SHA256;
        return hash ? hash.toString() : '';
    }

    // New method to navigate to the LoRAs page
    navigateToLorasPage(specificLoraIndex = null) {
        // Close the current modal
        modalManager.closeModal('recipeModal');

        // Clear any previous filters first
        removeSessionItem('recipe_to_lora_filterLoraHash');
        removeSessionItem('recipe_to_lora_filterLoraHashes');
        removeSessionItem('filterRecipeName');
        removeSessionItem('viewLoraDetail');

        if (specificLoraIndex !== null) {
            // If a specific LoRA index is provided, navigate to view just that one LoRA
            const lora = this.currentRecipe.loras[specificLoraIndex];

            if (lora && lora.hash) {
                // Set session storage to open the LoRA modal directly
                setSessionItem('recipe_to_lora_filterLoraHash', lora.hash.toLowerCase());
                setSessionItem('viewLoraDetail', 'true');
                setSessionItem('filterRecipeName', this.currentRecipe.title);
            }
        } else {
            // If no specific LoRA index is provided, show all LoRAs from this recipe
            // Collect all hashes from the recipe's LoRAs
            const loraHashes = this.currentRecipe.loras
                .filter(lora => lora.hash)
                .map(lora => lora.hash.toLowerCase());

            if (loraHashes.length > 0) {
                // Store the LoRA hashes and recipe name in sessionStorage
                setSessionItem('recipe_to_lora_filterLoraHashes', JSON.stringify(loraHashes));
                setSessionItem('filterRecipeName', this.currentRecipe.title);
            }
        }

        // Navigate to the LoRAs page
        window.location.href = '/loras';
    }

    // Only in-library LoRA items are row-navigable: the row opens the local
    // LoRA detail. Missing/deleted rows expose explicit action buttons
    // instead (download / reconnect / Civitai link), so a single gesture
    // never produces two different outcomes.
    setupLoraItemsClickable() {
        const loraItems = document.querySelectorAll('.recipe-lora-item.exists-locally:not(.checkpoint-item)');
        loraItems.forEach(item => {
            // Guard against duplicate wiring from deferred re-runs (see
            // setupLoraItemActions).
            if (item.dataset.navigationWired === 'true') {
                return;
            }
            item.dataset.navigationWired = 'true';

            // Get the lora index from the data attribute
            const loraIndex = parseInt(item.dataset.loraIndex);

            item.addEventListener('click', (e) => {
                // The inline Civitai link inside the title keeps its own
                // navigation; don't let it trigger the row navigation.
                if (e.target.closest('.recipe-civitai-link')) {
                    return;
                }
                this.navigateToLorasPage(loraIndex);
            });
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.navigateToLorasPage(loraIndex);
                }
            });
        });
    }
}

export { RecipeModal };
