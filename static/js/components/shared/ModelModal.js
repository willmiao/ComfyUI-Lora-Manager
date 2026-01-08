import { showToast, openCivitai } from '../../utils/uiHelpers.js';
import { modalManager } from '../../managers/ModalManager.js';
import {
    toggleShowcase,
    setupShowcaseScroll,
    scrollToTop,
    loadExampleImages
} from './showcase/ShowcaseView.js';
import { setupTabSwitching } from './ModelDescription.js';
import {
    setupModelNameEditing,
    setupBaseModelEditing,
    setupFileNameEditing
} from './ModelMetadata.js';
import { setupTagEditMode } from './ModelTags.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { renderCompactTags, setupTagTooltip, formatFileSize, escapeAttribute, escapeHtml } from './utils.js';
import { renderTriggerWords, setupTriggerWordsEditMode } from './TriggerWords.js';
import { parsePresets, renderPresetTags } from './PresetTags.js';
import { initVersionsTab } from './ModelVersionsTab.js';
import { loadRecipesForLora } from './RecipeTab.js';
import { translate } from '../../utils/i18nHelpers.js';
import { state } from '../../state/index.js';

function getModalFilePath(fallback = '') {
    const modalElement = document.getElementById('modelModal');
    if (modalElement && modalElement.dataset && modalElement.dataset.filePath) {
        return modalElement.dataset.filePath;
    }
    return fallback;
}

const COMMERCIAL_ICON_CONFIG = [
    {
        key: 'image',
        icon: 'photo-off.svg',
        titleKey: 'modals.model.license.noImageSell',
        fallback: 'No selling generated content'
    },
    {
        key: 'rentcivit',
        icon: 'brush-off.svg',
        titleKey: 'modals.model.license.noRentCivit',
        fallback: 'No Civitai generation'
    },
    {
        key: 'rent',
        icon: 'world-off.svg',
        titleKey: 'modals.model.license.noRent',
        fallback: 'No generation services'
    },
    {
        key: 'sell',
        icon: 'shopping-cart-off.svg',
        titleKey: 'modals.model.license.noSell',
        fallback: 'No selling models'
    }
];

let navigationKeyHandler = null;
let navigationModelType = null;
let navigationInProgress = false;

function hasLicenseField(license, field) {
    return Object.prototype.hasOwnProperty.call(license || {}, field);
}

function indentMarkup(markup, spaces) {
    if (!markup) {
        return '';
    }
    const padding = ' '.repeat(spaces);
    return markup
        .split('\n')
        .map(line => (line ? padding + line : line))
        .join('\n');
}

function splitAggregateCommercialValue(value) {
    const trimmed = String(value ?? '').trim();
    const looksAggregate = trimmed.includes(',') || (trimmed.startsWith('{') && trimmed.endsWith('}'));
    if (!looksAggregate) {
        return [value];
    }

    let inner = trimmed;
    if (inner.startsWith('{') && inner.endsWith('}')) {
        inner = inner.slice(1, -1);
    }

    const parts = inner
        .split(',')
        .map(part => part.trim())
        .filter(Boolean);

    return parts.length ? parts : [value];
}

function normalizeCommercialValues(value) {
    if (!value && value !== '') {
        return ['Sell'];
    }

    if (Array.isArray(value)) {
        const flattened = [];
        value.forEach(item => {
            if (item === null || item === undefined) {
                return;
            }
            if (typeof item === 'string') {
                flattened.push(...splitAggregateCommercialValue(item));
                return;
            }
            flattened.push(String(item));
        });
        if (flattened.length > 0) {
            return flattened;
        }
        if (value.length === 0) {
            return [];
        }
    }

    if (typeof value === 'string') {
        return splitAggregateCommercialValue(value);
    }

    if (value && typeof value[Symbol.iterator] === 'function') {
        const result = [];
        for (const item of value) {
            if (item === null || item === undefined) {
                continue;
            }
            if (typeof item === 'string') {
                result.push(...splitAggregateCommercialValue(item));
                continue;
            }
            result.push(String(item));
        }
        if (result.length > 0) {
            return result;
        }
    }

    return ['Sell'];
}

function sanitiseCommercialValue(value) {
    if (!value && value !== '') {
        return '';
    }
    return String(value)
        .trim()
        .toLowerCase()
        .replace(/[\s_-]+/g, '')
        .replace(/[^a-z]/g, '');
}

function resolveCommercialRestrictions(value) {
    const normalizedValues = normalizeCommercialValues(value);
    const allowed = new Set();
    normalizedValues.forEach(item => {
        const cleaned = sanitiseCommercialValue(item);
        if (!cleaned) {
            return;
        }
        allowed.add(cleaned);
    });

    if (allowed.has('sell')) {
        allowed.add('rent');
        allowed.add('rentcivit');
        allowed.add('image');
    }
    if (allowed.has('rent')) {
        allowed.add('rentcivit');
    }

    const disallowed = [];
    COMMERCIAL_ICON_CONFIG.forEach(config => {
        if (!allowed.has(config.key)) {
            disallowed.push(config);
        }
    });
    return disallowed;
}

function createLicenseIconMarkup(icon, label) {
    const safeLabel = escapeAttribute(label);
    const iconPath = `/loras_static/images/tabler/${icon}`;
    return `<span class="license-icon" role="img" aria-label="${safeLabel}" title="${safeLabel}" style="--license-icon-image: url('${iconPath}')"></span>`;
}

function renderLicenseIcons(modelData) {
    const license = modelData?.civitai?.model;
    if (!license) {
        return '';
    }

    const icons = [];
    if (hasLicenseField(license, 'allowNoCredit') && license.allowNoCredit === false) {
        const label = translate('modals.model.license.creditRequired', {}, 'Creator credit required');
        icons.push(createLicenseIconMarkup('user-check.svg', label));
    }

    if (hasLicenseField(license, 'allowCommercialUse')) {
        const restrictions = resolveCommercialRestrictions(license.allowCommercialUse);
        restrictions.forEach(({ icon, titleKey, fallback }) => {
            const label = translate(titleKey, {}, fallback);
            icons.push(createLicenseIconMarkup(icon, label));
        });
    }

    if (hasLicenseField(license, 'allowDerivatives') && license.allowDerivatives === false) {
        const label = translate('modals.model.license.noDerivatives', {}, 'No sharing merges');
        icons.push(createLicenseIconMarkup('exchange-off.svg', label));
    }

    if (hasLicenseField(license, 'allowDifferentLicense') && license.allowDifferentLicense === false) {
        const label = translate('modals.model.license.noReLicense', {}, 'Same permissions required');
        icons.push(createLicenseIconMarkup('rotate-2.svg', label));
    }

    if (!icons.length) {
        return '';
    }

    const containerLabel = translate('modals.model.license.restrictionsLabel', {}, 'License restrictions');
    const safeContainerLabel = escapeAttribute(containerLabel);
    return `<div class="license-restrictions" aria-label="${safeContainerLabel}" role="group">
        ${icons.join('\n        ')}
    </div>`;
}

/**
 * Display the model modal with the given model data
 * @param {Object} model - Model data object
 * @param {string} modelType - Type of model ('lora' or 'checkpoint')
 */
export async function showModelModal(model, modelType) {
    const modalId = 'modelModal';
    const modalTitle = model.model_name;
    cleanupNavigationShortcuts();
    detachModalHandlers(modalId);

    // Fetch complete civitai metadata
    let completeCivitaiData = model.civitai || {};
    if (model.file_path) {
        try {
            const fullMetadata = await getModelApiClient().fetchModelMetadata(model.file_path);
            completeCivitaiData = fullMetadata || model.civitai || {};
        } catch (error) {
            console.warn('Failed to fetch complete metadata, using existing data:', error);
            // Continue with existing data if fetch fails
        }
    }

    // Update model with complete civitai data
    const modelWithFullData = {
        ...model,
        civitai: completeCivitaiData
    };
    const escapedFilePathAttr = escapeAttribute(modelWithFullData.file_path || '');
    const escapedFolderPath = escapeHtml((modelWithFullData.file_path || '').replace(/[^/]+$/, '') || 'N/A');
    const licenseIcons = renderLicenseIcons(modelWithFullData);
    const viewOnCivitaiAction = modelWithFullData.from_civitai ? `
<div class="civitai-view" title="${translate('modals.model.actions.viewOnCivitai', {}, 'View on Civitai')}" data-action="view-civitai" data-filepath="${escapedFilePathAttr}">
    <i class="fas fa-globe"></i> ${translate('modals.model.actions.viewOnCivitaiText', {}, 'View on Civitai')}
</div>`.trim() : '';
    const creatorInfoAction = modelWithFullData.civitai?.creator ? `
<div class="creator-info" data-username="${modelWithFullData.civitai.creator.username}" data-action="view-creator" title="${translate('modals.model.actions.viewCreatorProfile', {}, 'View Creator Profile')}">
    ${modelWithFullData.civitai.creator.image ?
            `<div class="creator-avatar">
            <img src="${modelWithFullData.civitai.creator.image}" alt="${modelWithFullData.civitai.creator.username}" onerror="this.onerror=null; this.src='/loras_static/icons/user-placeholder.png';">
        </div>` :
            `<div class="creator-avatar creator-placeholder">
            <i class="fas fa-user"></i>
        </div>`
        }
    <span class="creator-username">${modelWithFullData.civitai.creator.username}</span>
</div>`.trim() : '';
    const creatorActionItems = [];
    if (viewOnCivitaiAction) {
        creatorActionItems.push(indentMarkup(viewOnCivitaiAction, 24));
    }
    if (creatorInfoAction) {
        creatorActionItems.push(indentMarkup(creatorInfoAction, 24));
    }
    const creatorActionsMarkup = creatorActionItems.length
        ? [
            '                    <div class="creator-actions">',
            creatorActionItems.join('\n'),
            '                    </div>'
        ].join('\n')
        : '';
    const headerActionItems = [];
    if (creatorActionsMarkup) {
        headerActionItems.push(creatorActionsMarkup);
    }
    if (licenseIcons) {
        headerActionItems.push(indentMarkup(licenseIcons.trim(), 20));
    }
    const headerActionsMarkup = headerActionItems.length
        ? [
            '                <div class="modal-header-actions">',
            headerActionItems.join('\n'),
            '                </div>'
        ].join('\n')
        : '';
    const hasUpdateAvailable = Boolean(modelWithFullData.update_available);
    const updateAvailabilityState = { hasUpdateAvailable };
    const updateBadgeTooltip = translate('modelCard.badges.updateAvailable', {}, 'Update available');

    // Prepare LoRA specific data with complete civitai data
    const escapedWords = (modelType === 'loras' || modelType === 'embeddings') && modelWithFullData.civitai?.trainedWords?.length ?
        modelWithFullData.civitai.trainedWords : [];

    // Generate model type specific content
    let typeSpecificContent;
    if (modelType === 'loras') {
        typeSpecificContent = renderLoraSpecificContent(modelWithFullData, escapedWords);
    } else if (modelType === 'embeddings') {
        typeSpecificContent = renderEmbeddingSpecificContent(modelWithFullData, escapedWords);
    } else {
        typeSpecificContent = '';
    }

    // Generate tabs based on model type
    const examplesText = translate('modals.model.tabs.examples', {}, 'Examples');
    const descriptionText = translate('modals.model.tabs.description', {}, 'Model Description');
    const recipesText = translate('modals.model.tabs.recipes', {}, 'Recipes');
    const versionsText = translate('modals.model.tabs.versions', {}, 'Versions');
    const versionsBadgeLabel = translate('modelCard.badges.update', {}, 'Update');
    const versionsTabBadge = hasUpdateAvailable
        ? `<span class="tab-badge tab-badge--update">${versionsBadgeLabel}</span>`
        : '';
    const versionsTabClasses = ['tab-btn'];
    if (hasUpdateAvailable) {
        versionsTabClasses.push('tab-btn--has-update');
    }
    const versionsTabButton = `<button class="${versionsTabClasses.join(' ')}" data-tab="versions">
                <span class="tab-label">${versionsText}</span>
                ${versionsTabBadge}
            </button>`.trim();

    const tabsContent = modelType === 'loras' ?
        `<button class="tab-btn active" data-tab="showcase">${examplesText}</button>
            <button class="tab-btn" data-tab="description">${descriptionText}</button>
            ${versionsTabButton}
            <button class="tab-btn" data-tab="recipes">${recipesText}</button>` :
        `<button class="tab-btn active" data-tab="showcase">${examplesText}</button>
            <button class="tab-btn" data-tab="description">${descriptionText}</button>
            ${versionsTabButton}`;

    const loadingExampleImagesText = translate('modals.model.loading.exampleImages', {}, 'Loading example images...');
    const loadingDescriptionText = translate('modals.model.loading.description', {}, 'Loading model description...');
    const loadingRecipesText = translate('modals.model.loading.recipes', {}, 'Loading recipes...');
    const loadingExamplesText = translate('modals.model.loading.examples', {}, 'Loading examples...');

    const loadingVersionsText = translate('modals.model.loading.versions', {}, 'Loading versions...');
    const civitaiModelId = modelWithFullData.civitai?.modelId || '';
    const civitaiVersionId = modelWithFullData.civitai?.id || '';
    const navAriaLabel = translate('modals.model.navigation.label', {}, 'Model navigation');
    const previousTitle = translate('modals.model.navigation.previousWithShortcut', {}, 'Previous model (←)');
    const nextTitle = translate('modals.model.navigation.nextWithShortcut', {}, 'Next model (→)');
    const navigationControls = `
                <div class="modal-nav-controls" role="group" aria-label="${navAriaLabel}">
                    <button class="modal-nav-btn" data-action="nav-prev" title="${previousTitle}" aria-label="${previousTitle}">
                        <i class="fas fa-chevron-left" aria-hidden="true"></i>
                    </button>
                    <button class="modal-nav-btn" data-action="nav-next" title="${nextTitle}" aria-label="${nextTitle}">
                        <i class="fas fa-chevron-right" aria-hidden="true"></i>
                    </button>
                </div>`.trim();

    const tabPanesContent = modelType === 'loras' ?
        `<div id="showcase-tab" class="tab-pane active">
            <div class="example-images-loading">
                <i class="fas fa-spinner fa-spin"></i> ${loadingExampleImagesText}
            </div>
        </div>
        
        <div id="description-tab" class="tab-pane">
            <div class="model-description-container">
                <div class="model-description-loading">
                    <i class="fas fa-spinner fa-spin"></i> ${loadingDescriptionText}
                </div>
                <div class="model-description-content hidden">
                </div>
            </div>
        </div>

        <div id="versions-tab" class="tab-pane">
            <div class="model-versions-tab" data-model-id="${civitaiModelId}" data-model-type="${modelType}" data-current-version-id="${civitaiVersionId}">
                <div class="versions-loading-state">
                    <i class="fas fa-spinner fa-spin"></i> ${loadingVersionsText}
                </div>
            </div>
        </div>

        <div id="recipes-tab" class="tab-pane">
            <div class="recipes-loading">
                <i class="fas fa-spinner fa-spin"></i> ${loadingRecipesText}
            </div>
        </div>` :
        `<div id="showcase-tab" class="tab-pane active">
            <div class="recipes-loading">
                <i class="fas fa-spinner fa-spin"></i> ${loadingExamplesText}
            </div>
        </div>
        
        <div id="description-tab" class="tab-pane">
            <div class="model-description-container">
                <div class="model-description-loading">
                    <i class="fas fa-spinner fa-spin"></i> ${loadingDescriptionText}
                </div>
                <div class="model-description-content hidden">
                </div>
            </div>
        </div>

        <div id="versions-tab" class="tab-pane">
            <div class="model-versions-tab" data-model-id="${civitaiModelId}" data-model-type="${modelType}" data-current-version-id="${civitaiVersionId}">
                <div class="versions-loading-state">
                    <i class="fas fa-spinner fa-spin"></i> ${loadingVersionsText}
                </div>
            </div>
        </div>`;

    const content = `
        <div class="modal-content">
            <button class="close" onclick="modalManager.closeModal('${modalId}')">&times;</button>
            <header class="modal-header">
                <div class="modal-header-row">
                    <div class="model-name-header">
                        <h2 class="model-name-content">${modalTitle}</h2>
                        <button class="edit-model-name-btn" title="${translate('modals.model.actions.editModelName', {}, 'Edit model name')}">
                            <i class="fas fa-pencil-alt"></i>
                        </button>
                    </div>

                    ${navigationControls}
                </div>

                ${headerActionsMarkup}

                ${renderCompactTags(modelWithFullData.tags || [], modelWithFullData.file_path)}
            </header>

            <div class="modal-body">
                <div class="info-section">
                    <div class="info-grid">
                        <div class="info-item">
                            <label>${translate('modals.model.metadata.version', {}, 'Version')}</label>
                            <span>${modelWithFullData.civitai?.name || 'N/A'}</span>
                        </div>
                        <div class="info-item">
                            <label>${translate('modals.model.metadata.fileName', {}, 'File Name')}</label>
                            <div class="file-name-wrapper">
                                <span id="file-name" class="file-name-content">${modelWithFullData.file_name || 'N/A'}</span>
                                <button class="edit-file-name-btn" title="${translate('modals.model.actions.editFileName', {}, 'Edit file name')}">
                                    <i class="fas fa-pencil-alt"></i>
                                </button>
                            </div>
                        </div>
                        <div class="info-item">
                            <div class="location-wrapper">
                                <label>${translate('modals.model.metadata.location', {}, 'Location')}</label>
                                <span class="file-path" title="${translate('modals.model.actions.openFileLocation', {}, 'Open file location')}"
                                    data-action="open-file-location"
                                    data-filepath="${escapedFilePathAttr}">
                                    ${escapedFolderPath}
                                </span>
                            </div>
                        </div>
                        <div class="info-item base-size">
                            <div class="base-wrapper">
                                <label>${translate('modals.model.metadata.baseModel', {}, 'Base Model')}</label>
                                <div class="base-model-display">
                                    <span class="base-model-content">${modelWithFullData.base_model || translate('modals.model.metadata.unknown', {}, 'Unknown')}</span>
                                    <button class="edit-base-model-btn" title="${translate('modals.model.actions.editBaseModel', {}, 'Edit base model')}">
                                        <i class="fas fa-pencil-alt"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="size-wrapper">
                                <label>${translate('modals.model.metadata.size', {}, 'Size')}</label>
                                <span>${formatFileSize(modelWithFullData.file_size)}</span>
                            </div>
                        </div>
                        ${typeSpecificContent}
                        <div class="info-item notes">
                            <label>${translate('modals.model.metadata.additionalNotes', {}, 'Additional Notes')} <i class="fas fa-info-circle notes-hint" title="${translate('modals.model.metadata.notesHint', {}, 'Press Enter to save, Shift+Enter for new line')}"></i></label>
                            <div class="editable-field">
                                <div class="notes-content" contenteditable="true" spellcheck="false">${modelWithFullData.notes || translate('modals.model.metadata.addNotesPlaceholder', {}, 'Add your notes here...')}</div>
                            </div>
                        </div>
                        <div class="info-item full-width">
                            <label>${translate('modals.model.metadata.aboutThisVersion', {}, 'About this version')}</label>
                            <div class="description-text">${modelWithFullData.civitai?.description || 'N/A'}</div>
                        </div>
                    </div>
                </div>

                <div class="showcase-section" data-model-hash="${modelWithFullData.sha256 || ''}" data-filepath="${escapedFilePathAttr}">
                    <div class="showcase-tabs">
                        ${tabsContent}
                    </div>
                    
                    <div class="tab-content">
                        ${tabPanesContent}
                    </div>
                    
                    <button class="back-to-top" data-action="scroll-to-top">
                        <i class="fas fa-arrow-up"></i>
                    </button>
                </div>
            </div>
        </div>
    `;

    function updateVersionsTabBadge(hasUpdate) {
        const modalElement = document.getElementById(modalId);
        if (!modalElement) return;

        const tabButton = modalElement.querySelector('.tab-btn[data-tab="versions"]');
        if (!tabButton) return;

        tabButton.classList.toggle('tab-btn--has-update', hasUpdate);

        let badge = tabButton.querySelector('.tab-badge--update');
        if (hasUpdate) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'tab-badge tab-badge--update';
                badge.textContent = versionsBadgeLabel;
                badge.title = updateBadgeTooltip;
                tabButton.appendChild(badge);
            } else {
                badge.textContent = versionsBadgeLabel;
                badge.title = updateBadgeTooltip;
            }
        } else if (badge) {
            badge.remove();
        }
    }

    function updateCardUpdateAvailability(hasUpdate) {
        const filePath = modelWithFullData.file_path;
        if (!filePath) return;

        let updatedViaScroller = false;
        if (state.virtualScroller?.updateSingleItem) {
            updatedViaScroller = state.virtualScroller.updateSingleItem(filePath, {
                update_available: hasUpdate,
            });
        }

        if (updatedViaScroller) {
            return;
        }

        const escapedPath = window.CSS && typeof window.CSS.escape === 'function'
            ? window.CSS.escape(filePath)
            : filePath.replace(/["\\]/g, '\\$&');
        const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
        if (!card) return;

        card.dataset.update_available = hasUpdate ? 'true' : 'false';
        card.classList.toggle('has-update', hasUpdate);

        const headerInfo = card.querySelector('.card-header-info');
        if (!headerInfo) return;

        let badge = headerInfo.querySelector('.model-update-badge');
        if (hasUpdate) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'model-update-badge';
                badge.title = updateBadgeTooltip;
                badge.textContent = versionsBadgeLabel;
                headerInfo.appendChild(badge);
            }
        } else if (badge) {
            badge.remove();
        }
    }

    function handleUpdateStatusChange(hasUpdate) {
        if (updateAvailabilityState.hasUpdateAvailable === hasUpdate) {
            return;
        }
        updateAvailabilityState.hasUpdateAvailable = hasUpdate;
        updateVersionsTabBadge(hasUpdate);
        updateCardUpdateAvailability(hasUpdate);
    }

    let showcaseCleanup;

    const onCloseCallback = function () {
        // Clean up all handlers when modal closes for LoRA
        const modalElement = document.getElementById(modalId);
        if (modalElement && modalElement._clickHandler) {
            modalElement.removeEventListener('click', modalElement._clickHandler);
            delete modalElement._clickHandler;
        }
        if (showcaseCleanup) {
            showcaseCleanup();
            showcaseCleanup = null;
        }
        cleanupNavigationShortcuts();
    };

    modalManager.showModal(modalId, content, null, onCloseCallback);
    const activeModalElement = document.getElementById(modalId);
    if (activeModalElement) {
        activeModalElement.dataset.filePath = modelWithFullData.file_path || '';
    }
    updateVersionsTabBadge(updateAvailabilityState.hasUpdateAvailable);
    const versionsTabController = initVersionsTab({
        modalId,
        modelType,
        modelId: civitaiModelId,
        currentVersionId: civitaiVersionId,
        currentBaseModel: modelWithFullData.base_model,
        onUpdateStatusChange: handleUpdateStatusChange,
    });
    setupEditableFields(modelWithFullData.file_path, modelType);
    showcaseCleanup = setupShowcaseScroll(modalId);
    setupTabSwitching({
        onTabChange: async (tab) => {
            if (tab === 'versions') {
                await versionsTabController.load();
            }
        },
    });
    versionsTabController.load({ eager: true });
    setupTagTooltip();
    setupTagEditMode(modelType);
    setupModelNameEditing(modelWithFullData.file_path);
    setupBaseModelEditing(modelWithFullData.file_path);
    setupFileNameEditing(modelWithFullData.file_path);
    setupEventHandlers(modelWithFullData.file_path, modelType);
    setupNavigationShortcuts(modelType);
    updateNavigationControls();

    // LoRA specific setup
    if (modelType === 'loras' || modelType === 'embeddings') {
        setupTriggerWordsEditMode();

        if (modelType == 'loras') {
            // Load recipes for this LoRA
            loadRecipesForLora(modelWithFullData.model_name, modelWithFullData.sha256);
        }
    }

    // Load example images asynchronously - merge regular and custom images
    const regularImages = modelWithFullData.civitai?.images || [];
    const customImages = modelWithFullData.civitai?.customImages || [];
    // Combine images - regular images first, then custom images
    const allImages = [...regularImages, ...customImages];
    loadExampleImages(allImages, modelWithFullData.sha256);
}

function renderLoraSpecificContent(lora, escapedWords) {
    return `
        <div class="info-item usage-tips">
            <label>${translate('modals.model.metadata.usageTips', {}, 'Usage Tips')}</label>
            <div class="editable-field">
                <div class="preset-controls">
                    <select id="preset-selector">
                        <option value="">${translate('modals.model.usageTips.addPresetParameter', {}, 'Add preset parameter...')}</option>
                        <option value="strength_min">${translate('modals.model.usageTips.strengthMin', {}, 'Strength Min')}</option>
                        <option value="strength_max">${translate('modals.model.usageTips.strengthMax', {}, 'Strength Max')}</option>
                        <option value="strength_range">${translate('modals.model.usageTips.strengthRange', {}, 'Strength Range')}</option>
                        <option value="strength">${translate('modals.model.usageTips.strength', {}, 'Strength')}</option>
                        <option value="clip_strength">${translate('modals.model.usageTips.clipStrength', {}, 'Clip Strength')}</option>
                        <option value="clip_skip">${translate('modals.model.usageTips.clipSkip', {}, 'Clip Skip')}</option>
                    </select>
                    <input type="number" id="preset-value" step="0.01" placeholder="${translate('modals.model.usageTips.valuePlaceholder', {}, 'Value')}" style="display:none;">
                    <button class="add-preset-btn">${translate('modals.model.usageTips.add', {}, 'Add')}</button>
                </div>
                <div class="preset-tags">
                    ${renderPresetTags(parsePresets(lora.usage_tips))}
                </div>
            </div>
        </div>
        ${renderTriggerWords(escapedWords, lora.file_path)}
    `;
}

function renderEmbeddingSpecificContent(embedding, escapedWords) {
    return `${renderTriggerWords(escapedWords, embedding.file_path)}`;
}

function detachModalHandlers(modalId) {
    const modalElement = document.getElementById(modalId);
    if (modalElement && modalElement._clickHandler) {
        modalElement.removeEventListener('click', modalElement._clickHandler);
        delete modalElement._clickHandler;
    }
}

/**
 * Sets up event handlers using event delegation for LoRA modal
 * @param {string} filePath - Path to the model file
 * @param {string} modelType - Current model type
 */
function setupEventHandlers(filePath, modelType) {
    const modalElement = document.getElementById('modelModal');

    // Remove existing event listeners first
    modalElement.removeEventListener('click', handleModalClick);

    // Create and store the handler function
    function handleModalClick(event) {
        const target = event.target.closest('[data-action]');
        if (!target) return;

        const action = target.dataset.action;

        switch (action) {
            case 'close-modal':
                modalManager.closeModal('modelModal');
                break;
            case 'scroll-to-top':
                scrollToTop(target);
                break;
            case 'view-civitai':
                openCivitai(target.dataset.filepath);
                break;
            case 'view-creator':
                const username = target.dataset.username;
                if (username) {
                    window.open(`https://civitai.com/user/${username}`, '_blank');
                }
                break;
            case 'open-file-location':
                const filePath = target.dataset.filepath || getModalFilePath();
                if (filePath) {
                    openFileLocation(filePath);
                }
                break;
            case 'nav-prev':
                handleDirectionalNavigation('prev', modelType);
                break;
            case 'nav-next':
                handleDirectionalNavigation('next', modelType);
                break;
        }
    }

    // Add the event listener with the named function
    modalElement.addEventListener('click', handleModalClick);

    // Store reference to the handler on the element for potential cleanup
    modalElement._clickHandler = handleModalClick;
}

/**
 * Set up editable fields (notes and usage tips) in the model modal
 * @param {string} filePath - The full file path of the model
 * @param {string} modelType - Type of model ('loras' or 'checkpoints' or 'embeddings')
 */
function setupEditableFields(filePath, modelType) {
    const editableFields = document.querySelectorAll('.editable-field [contenteditable]');

    editableFields.forEach(field => {
        field.addEventListener('focus', function () {
            if (this.textContent === 'Add your notes here...') {
                this.textContent = '';
            }
        });

        field.addEventListener('blur', function () {
            if (this.textContent.trim() === '') {
                if (this.classList.contains('notes-content')) {
                    this.textContent = 'Add your notes here...';
                }
            }
        });
    });

    // Add keydown event listeners for notes
    const notesContent = document.querySelector('.notes-content');
    if (notesContent) {
        notesContent.addEventListener('keydown', async function (e) {
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    // Allow shift+enter for new line
                    return;
                }
                e.preventDefault();
                await saveNotes();
            }
        });
    }

    // LoRA specific field setup
    if (modelType === 'loras') {
        setupLoraSpecificFields(filePath);
    }
}

function setupLoraSpecificFields(filePath) {
    const presetSelector = document.getElementById('preset-selector');
    const presetValue = document.getElementById('preset-value');
    const addPresetBtn = document.querySelector('.add-preset-btn');
    const presetTags = document.querySelector('.preset-tags');
    const resolveFilePath = () => getModalFilePath(filePath);

    if (!presetSelector || !presetValue || !addPresetBtn || !presetTags) return;

    presetSelector.addEventListener('change', function () {
        const selected = this.value;
        if (selected) {
            presetValue.style.display = 'inline-block';
            if (selected === 'strength_range') {
                presetValue.type = 'text';
                presetValue.placeholder = 'e.g. 0.8-1.2';
                presetValue.removeAttribute('min');
                presetValue.removeAttribute('max');
                presetValue.removeAttribute('step');
            } else {
                presetValue.type = 'number';
                presetValue.placeholder = translate('modals.model.usageTips.valuePlaceholder', {}, 'Value');
                presetValue.min = selected.includes('strength') ? -10 : 0;
                presetValue.max = selected.includes('strength') ? 10 : 10;
                presetValue.step = 0.5;
                if (selected === 'clip_skip') {
                    presetValue.step = 1;
                }
            }
            // Add auto-focus
            setTimeout(() => presetValue.focus(), 0);
        } else {
            presetValue.style.display = 'none';
        }
    });

    addPresetBtn.addEventListener('click', async function () {
        const key = presetSelector.value;
        const value = presetValue.value;

        if (!key || !value) return;

        const currentPath = resolveFilePath();
        if (!currentPath) return;
        const loraCard = document.querySelector(`.model-card[data-filepath="${currentPath}"]`) ||
            document.querySelector(`.model-card[data-filepath="${filePath}"]`);
        const currentPresets = parsePresets(loraCard?.dataset.usage_tips);

        if (key === 'strength_range') {
            const rangeMatch = value.match(/^(-?\d*\.?\d+)\s*[-~]\s*(-?\d*\.?\d+)$/);
            if (rangeMatch) {
                currentPresets['strength_min'] = parseFloat(rangeMatch[1]);
                currentPresets['strength_max'] = parseFloat(rangeMatch[2]);
            } else {
                showToast('modals.model.usageTips.invalidRange', {}, 'error', 'Invalid range format. Use x.x-y.y');
                return;
            }
        } else {
            currentPresets[key] = parseFloat(value);
        }
        const newPresetsJson = JSON.stringify(currentPresets);

        await getModelApiClient().saveModelMetadata(currentPath, { usage_tips: newPresetsJson });

        presetTags.innerHTML = renderPresetTags(currentPresets);

        presetSelector.value = '';
        presetValue.value = '';
        presetValue.style.display = 'none';
    });

    // Add keydown event for preset value
    presetValue.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            addPresetBtn.click();
        }
    });
}

/**
 * Save model notes using the current modal file path.
 */
async function saveNotes() {
    const filePath = getModalFilePath();
    if (!filePath) {
        return;
    }
    const content = document.querySelector('.notes-content').textContent;
    try {
        await getModelApiClient().saveModelMetadata(filePath, { notes: content });

        showToast('modals.model.notes.saved', {}, 'success');
    } catch (error) {
        showToast('modals.model.notes.saveFailed', {}, 'error');
    }
}

function shouldIgnoreNavigationKey(event) {
    const target = event.target;
    if (!target) return false;
    const tagName = target.tagName ? target.tagName.toLowerCase() : '';
    return target.isContentEditable || ['input', 'textarea', 'select', 'button'].includes(tagName);
}

function updateNavigationControls() {
    const modalElement = document.getElementById('modelModal');
    if (!modalElement) return;

    const prevBtn = modalElement.querySelector('[data-action="nav-prev"]');
    const nextBtn = modalElement.querySelector('[data-action="nav-next"]');
    if (!prevBtn || !nextBtn) return;

    const scroller = state.virtualScroller;
    if (!scroller || typeof scroller.getNavigationState !== 'function') {
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
    }

    const { hasPrev, hasNext } = scroller.getNavigationState(modalElement.dataset.filePath || '');
    prevBtn.disabled = navigationInProgress || !hasPrev;
    nextBtn.disabled = navigationInProgress || !hasNext;
}

function cleanupNavigationShortcuts() {
    if (navigationKeyHandler) {
        document.removeEventListener('keydown', navigationKeyHandler);
        navigationKeyHandler = null;
    }
    navigationModelType = null;
    navigationInProgress = false;
}

function setupNavigationShortcuts(modelType) {
    const modalElement = document.getElementById('modelModal');
    if (!modalElement) return;

    navigationModelType = modelType;
    cleanupNavigationShortcuts();

    navigationKeyHandler = (event) => {
        if (shouldIgnoreNavigationKey(event)) return;

        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            handleDirectionalNavigation('prev', navigationModelType);
        } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            handleDirectionalNavigation('next', navigationModelType);
        }
    };

    document.addEventListener('keydown', navigationKeyHandler);
}

async function handleDirectionalNavigation(direction, modelType) {
    if (navigationInProgress) return;

    const modalElement = document.getElementById('modelModal');
    const scroller = state.virtualScroller;
    const filePath = modalElement?.dataset?.filePath || '';

    if (!modalElement || !filePath || !scroller || typeof scroller.getAdjacentItemByFilePath !== 'function') {
        return;
    }

    navigationInProgress = true;
    updateNavigationControls();

    try {
        const adjacent = await scroller.getAdjacentItemByFilePath(filePath, direction);
        if (!adjacent || !adjacent.item) {
            const toastKey = direction === 'prev' ? 'modals.model.navigation.noPrevious' : 'modals.model.navigation.noNext';
            const toastFallback = direction === 'prev' ? 'No previous model available' : 'No next model available';
            showToast(toastKey, {}, 'info', toastFallback);
            return;
        }

        navigationModelType = modelType || navigationModelType;
        await showModelModal(adjacent.item, navigationModelType || modelType);
    } finally {
        navigationInProgress = false;
        updateNavigationControls();
    }
}

/**
 * Call backend to open file location and select the file
 * @param {string} filePath
 */
async function openFileLocation(filePath) {
    try {
        const resp = await fetch('/api/lm/open-file-location', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 'file_path': filePath })
        });
        if (!resp.ok) throw new Error('Failed to open file location');
        showToast('modals.model.openFileLocation.success', {}, 'success');
    } catch (err) {
        showToast('modals.model.openFileLocation.failed', {}, 'error');
    }
}

// Export the model modal API
const modelModal = {
    show: showModelModal,
    toggleShowcase,
    scrollToTop
};

export { modelModal };
