import { getModelApiClient } from '../../api/modelApiFactory.js';
import { downloadManager } from '../../managers/DownloadManager.js';
import { modalManager } from '../../managers/ModalManager.js';
import { showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';
import { state } from '../../state/index.js';
import { formatFileSize } from './utils.js';

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.mkv'];

function buildCivitaiVersionUrl(modelId, versionId) {
    if (modelId == null || versionId == null) {
        return null;
    }
    const normalizedModelId = String(modelId).trim();
    const normalizedVersionId = String(versionId).trim();
    if (!normalizedModelId || !normalizedVersionId) {
        return null;
    }
    const encodedModelId = encodeURIComponent(normalizedModelId);
    const encodedVersionId = encodeURIComponent(normalizedVersionId);
    return `https://civitai.com/models/${encodedModelId}?modelVersionId=${encodedVersionId}`;
}

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

function extractExtension(value) {
    if (value == null) {
        return '';
    }
    const targets = [];
    const stringValue = String(value);
    if (stringValue) {
        targets.push(stringValue);
        stringValue.split(/[?&=]/).forEach(fragment => {
            if (fragment) {
                targets.push(fragment);
            }
        });
    }

    for (const target of targets) {
        let candidate = target;
        try {
            candidate = decodeURIComponent(candidate);
        } catch (error) {
            // ignoring malformed sequences, fallback to raw value
        }
        const lastDot = candidate.lastIndexOf('.');
        if (lastDot === -1) {
            continue;
        }
        const extension = candidate.slice(lastDot).toLowerCase();
        if (extension.includes('/') || extension.includes('\\')) {
            continue;
        }
        return extension;
    }

    return '';
}

function isVideoUrl(url) {
    if (!url || typeof url !== 'string') {
        return false;
    }

    const candidates = new Set();
    const addCandidate = value => {
        if (value == null) {
            return;
        }
        const stringValue = String(value);
        if (!stringValue) {
            return;
        }
        candidates.add(stringValue);
    };

    addCandidate(url);

    try {
        const parsed = new URL(url, window.location.origin);
        addCandidate(parsed.pathname);
        parsed.searchParams.forEach(value => addCandidate(value));
    } catch (error) {
        // ignore parse errors and rely on fallbacks below
    }

    for (const candidate of candidates) {
        const extension = extractExtension(candidate);
        if (extension && VIDEO_EXTENSIONS.includes(extension)) {
            return true;
        }
    }

    return false;
}

function formatDateLabel(value) {
    if (!value) {
        return null;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return null;
    }
    return parsed.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

function buildMetaMarkup(version) {
    const segments = [];
    if (version.baseModel) {
        segments.push(
            `<span class="version-meta-primary">${escapeHtml(version.baseModel)}</span>`
        );
    }
    const releaseLabel = formatDateLabel(version.releasedAt);
    if (releaseLabel) {
        segments.push(escapeHtml(releaseLabel));
    }
    if (typeof version.sizeBytes === 'number' && version.sizeBytes > 0) {
        segments.push(escapeHtml(formatFileSize(version.sizeBytes)));
    }

    if (!segments.length) {
        return escapeHtml(
            translate('modals.model.versions.labels.noDetails', {}, 'No additional details')
        );
    }

    return segments
        .map(segment => `<span class="version-meta-item">${segment}</span>`)
        .join('<span class="version-meta-separator">•</span>');
}

function buildBadge(label, tone) {
    return `<span class="version-badge version-badge-${tone}">${escapeHtml(label)}</span>`;
}

function getAutoplaySetting() {
    try {
        return Boolean(state?.global?.settings?.autoplay_on_hover);
    } catch (error) {
        return false;
    }
}

function renderMediaMarkup(version) {
    if (!version.previewUrl) {
        const placeholderText = translate('modals.model.versions.media.placeholder', {}, 'No preview');
        return `<div class="version-media version-media-placeholder">${escapeHtml(placeholderText)}</div>`;
    }

    if (isVideoUrl(version.previewUrl)) {
        const autoplayOnHover = getAutoplaySetting();
        return `
            <div class="version-media">
                <video
                    src="${escapeHtml(version.previewUrl)}"
                    ${autoplayOnHover ? '' : 'controls'}
                    muted
                    loop
                    playsinline
                    preload="metadata"
                    data-autoplay-on-hover="${autoplayOnHover ? 'true' : 'false'}"
                ></video>
            </div>
        `;
    }

    return `
        <div class="version-media">
            <img src="${escapeHtml(version.previewUrl)}" alt="${escapeHtml(version.name || 'preview')}">
        </div>
    `;
}

function renderRow(version, options) {
    const { latestLibraryVersionId, currentVersionId, modelId: parentModelId } = options;
    const isCurrent = currentVersionId && version.versionId === currentVersionId;
    const isNewer =
        typeof latestLibraryVersionId === 'number' &&
        version.versionId > latestLibraryVersionId;
    const badges = [];

    if (isCurrent) {
        badges.push(buildBadge(translate('modals.model.versions.badges.current', {}, 'Current Version'), 'current'));
    }

    if (version.isInLibrary) {
        badges.push(buildBadge(translate('modals.model.versions.badges.inLibrary', {}, 'In Library'), 'success'));
    } else if (isNewer && !version.shouldIgnore) {
        badges.push(buildBadge(translate('modals.model.versions.badges.newer', {}, 'Newer Version'), 'info'));
    }

    if (version.shouldIgnore) {
        badges.push(buildBadge(translate('modals.model.versions.badges.ignored', {}, 'Ignored'), 'muted'));
    }

    const downloadLabel = translate('modals.model.versions.actions.download', {}, 'Download');
    const deleteLabel = translate('modals.model.versions.actions.delete', {}, 'Delete');
    const ignoreLabel = translate(
        version.shouldIgnore
        ? 'modals.model.versions.actions.unignore'
        : 'modals.model.versions.actions.ignore',
        {},
        version.shouldIgnore ? 'Unignore' : 'Ignore'
    );

    const actions = [];
    if (!version.isInLibrary) {
        actions.push(
            `<button class="version-action version-action-primary" data-version-action="download">${escapeHtml(downloadLabel)}</button>`
        );
    } else if (version.filePath) {
        actions.push(
            `<button class="version-action version-action-danger" data-version-action="delete">${escapeHtml(deleteLabel)}</button>`
        );
    }
    actions.push(
        `<button class="version-action version-action-ghost" data-version-action="toggle-ignore" data-ignore-state="${
            version.shouldIgnore ? 'ignored' : 'active'
        }">${escapeHtml(ignoreLabel)}</button>`
    );

    const linkTarget = buildCivitaiVersionUrl(
        version.modelId || parentModelId,
        version.versionId
    );
    const civitaiTooltip = translate(
        'modals.model.actions.viewOnCivitai',
        {},
        'View on Civitai'
    );

    const rowAttributes = [
        `class="model-version-row${isCurrent ? ' is-current' : ''}${linkTarget ? ' is-clickable' : ''}"`,
        `data-version-id="${escapeHtml(version.versionId)}"`,
    ];
    if (linkTarget) {
        rowAttributes.push(`data-civitai-url="${escapeHtml(linkTarget)}"`);
        rowAttributes.push(`title="${escapeHtml(civitaiTooltip)}"`);
    }

    return `
        <div ${rowAttributes.join(' ')}>
            ${renderMediaMarkup(version)}
            <div class="version-details">
                <div class="version-title">
                    <span class="versions-tab-version-name">${escapeHtml(version.name || translate('modals.model.versions.labels.unnamed', {}, 'Untitled Version'))}</span>
                </div>
                <div class="version-badges">${badges.join('')}</div>
                <div class="version-meta">
                    ${buildMetaMarkup(version)}
                </div>
            </div>
            <div class="version-actions">
                ${actions.join('')}
            </div>
        </div>
    `;
}

function setupMediaHoverInteractions(container) {
    const autoplayOnHover = getAutoplaySetting();
    if (!autoplayOnHover) {
        return;
    }
    container.querySelectorAll('.version-media video').forEach(video => {
        if (video.dataset.autoplayOnHover !== 'true') {
            return;
        }
        const play = () => {
            try {
                video.currentTime = 0;
                const promise = video.play();
                if (promise && typeof promise.catch === 'function') {
                    promise.catch(() => {});
                }
            } catch (error) {
                console.debug('Failed to autoplay preview video:', error);
            }
        };
        const stop = () => {
            video.pause();
            video.currentTime = 0;
        };
        video.addEventListener('mouseenter', play);
        video.addEventListener('focus', play);
        video.addEventListener('mouseleave', stop);
        video.addEventListener('blur', stop);
    });
}

function getLatestLibraryVersionId(record) {
    if (!record || !Array.isArray(record.inLibraryVersionIds) || !record.inLibraryVersionIds.length) {
        return null;
    }
    return Math.max(...record.inLibraryVersionIds);
}

function renderToolbar(record) {
    const ignoreText = record.shouldIgnore
        ? translate('modals.model.versions.actions.resumeModelUpdates', {}, 'Resume updates for this model')
        : translate('modals.model.versions.actions.ignoreModelUpdates', {}, 'Ignore updates for this model');
    const viewLocalText = translate('modals.model.versions.actions.viewLocalVersions', {}, 'View all local versions');
    const infoText = translate(
        'modals.model.versions.copy',
        { count: record.versions.length },
        'Track and manage every version of this model in one place.'
    );

    return `
        <header class="versions-toolbar">
            <div class="versions-toolbar-info">
                <h3>${translate('modals.model.versions.heading', {}, 'Model versions')}</h3>
                <p>${escapeHtml(infoText)}</p>
            </div>
            <div class="versions-toolbar-actions">
                <button class="versions-toolbar-btn versions-toolbar-btn-primary" data-versions-action="toggle-model-ignore">
                    ${escapeHtml(ignoreText)}
                </button>
                <button class="versions-toolbar-btn versions-toolbar-btn-secondary" data-versions-action="view-local" title="${escapeHtml(translate('modals.model.versions.actions.viewLocalTooltip', {}, 'Coming soon'))}" disabled>
                    ${escapeHtml(viewLocalText)}
                </button>
            </div>
        </header>
    `;
}

function renderEmptyState(container) {
    const message = translate('modals.model.versions.empty', {}, 'No version history available for this model yet.');
    container.innerHTML = `
        <div class="versions-empty">
            <i class="fas fa-info-circle"></i>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

function renderErrorState(container, message) {
    const fallback = translate('modals.model.versions.error', {}, 'Failed to load versions.');
    container.innerHTML = `
        <div class="versions-error">
            <i class="fas fa-exclamation-triangle"></i>
            <p>${escapeHtml(message || fallback)}</p>
        </div>
    `;
}

export function initVersionsTab({
    modalId,
    modelType,
    modelId,
    currentVersionId,
}) {
    const pane = document.querySelector(`#${modalId} #versions-tab`);
    const container = pane ? pane.querySelector('.model-versions-tab') : null;
    const normalizedCurrentVersionId =
        typeof currentVersionId === 'number'
            ? currentVersionId
            : currentVersionId
            ? Number(currentVersionId)
            : null;

    if (!container) {
        return {
            async load() {},
            async refresh() {},
        };
    }

    let controller = {
        isLoading: false,
        hasLoaded: false,
        record: null,
    };

    let apiClient;

    function ensureClient() {
        if (apiClient) {
            return apiClient;
        }
        try {
            apiClient = getModelApiClient(modelType);
        } catch (error) {
            apiClient = getModelApiClient();
        }
        return apiClient;
    }

    function showLoading() {
        const loadingText = translate('modals.model.loading.versions', {}, 'Loading versions...');
        container.innerHTML = `
            <div class="versions-loading-state">
                <i class="fas fa-spinner fa-spin"></i> ${escapeHtml(loadingText)}
            </div>
        `;
    }

    function render(record) {
        controller.record = record;
        controller.hasLoaded = true;

        if (!record || !Array.isArray(record.versions) || record.versions.length === 0) {
            renderEmptyState(container);
            return;
        }

        const latestLibraryVersionId = getLatestLibraryVersionId(record);
        let dividerInserted = false;

        const sortedVersions = [...record.versions].sort(
            (a, b) => Number(b.versionId) - Number(a.versionId)
        );

        const rowsMarkup = sortedVersions
            .map(version => {
                const isNewer =
                    typeof latestLibraryVersionId === 'number' &&
                    version.versionId > latestLibraryVersionId;
                let markup = '';
                if (
                    !dividerInserted &&
                    typeof latestLibraryVersionId === 'number' &&
                    !isNewer
                ) {
                    dividerInserted = true;
                markup += '<div class="version-divider" role="presentation"></div>';
                }
                markup += renderRow(version, {
                    latestLibraryVersionId,
                    currentVersionId: normalizedCurrentVersionId,
                    modelId: record?.modelId ?? modelId,
                });
                return markup;
            })
            .join('');

        container.innerHTML = `
            ${renderToolbar(record)}
            <div class="versions-list">
                ${rowsMarkup}
            </div>
        `;

        setupMediaHoverInteractions(container);
    }

    async function loadVersions({ forceRefresh = false, eager = false } = {}) {
        if (controller.isLoading) {
            return;
        }
        if (!modelId) {
            renderErrorState(container, translate('modals.model.versions.missingModelId', {}, 'This model is missing a Civitai model id.'));
            return;
        }
        if (controller.hasLoaded && !forceRefresh) {
            return;
        }

        controller.isLoading = true;
        if (!eager) {
            showLoading();
        }

        try {
            const client = ensureClient();
            const response = await client.fetchModelUpdateVersions(modelId, {
                refresh: false,
            });
            if (!response?.success) {
                throw new Error(response?.error || 'Request failed');
            }
            render(response.record);
        } catch (error) {
            console.error('Failed to load model versions:', error);
            renderErrorState(container, error?.message);
        } finally {
            controller.isLoading = false;
        }
    }

    async function refresh() {
        await loadVersions({ forceRefresh: true });
    }

    async function handleToggleModelIgnore(button) {
        if (!controller.record) {
            return;
        }
        const client = ensureClient();
        const nextValue = !controller.record.shouldIgnore;
        button.disabled = true;
        try {
            const response = await client.setModelUpdateIgnore(modelId, nextValue);
            if (!response?.success) {
                throw new Error(response?.error || 'Request failed');
            }
            render(response.record);
            const toastKey = nextValue
                ? 'modals.model.versions.toast.modelIgnored'
                : 'modals.model.versions.toast.modelResumed';
            const toastMessage = translate(
                toastKey,
                {},
                nextValue ? 'Updates ignored for this model' : 'Update tracking resumed'
            );
            showToast(toastMessage, {}, 'success');
        } catch (error) {
            console.error('Failed to update model ignore state:', error);
            showToast(error?.message || 'Failed to update ignore preference', {}, 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function handleToggleVersionIgnore(button, versionId) {
        if (!controller.record) {
            return;
        }
        const client = ensureClient();
        const targetVersion = controller.record.versions.find(v => v.versionId === versionId);
        const nextValue = targetVersion ? !targetVersion.shouldIgnore : true;
        button.disabled = true;
        try {
            const response = await client.setVersionUpdateIgnore(
                modelId,
                versionId,
                nextValue
            );
            if (!response?.success) {
                throw new Error(response?.error || 'Request failed');
            }
            render(response.record);
            const updatedVersion = response.record.versions.find(v => v.versionId === versionId);
            const toastKey = updatedVersion?.shouldIgnore
                ? 'modals.model.versions.toast.versionIgnored'
                : 'modals.model.versions.toast.versionUnignored';
            const toastMessage = translate(
                toastKey,
                {},
                updatedVersion?.shouldIgnore ? 'Updates ignored for this version' : 'Version re-enabled'
            );
            showToast(toastMessage, {}, 'success');
        } catch (error) {
            console.error('Failed to toggle version ignore state:', error);
            showToast(error?.message || 'Failed to update version preference', {}, 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function performDeleteVersion({
        triggerButton,
        confirmButton,
        closeModal,
        version,
    }) {
        if (!version?.filePath) {
            console.warn('Missing file path for deletion.');
            return;
        }

        if (triggerButton) {
            triggerButton.disabled = true;
        }

        let confirmOriginalText = '';
        if (confirmButton) {
            confirmOriginalText = confirmButton.textContent;
            confirmButton.disabled = true;
        }

        let deletionSucceeded = false;

        try {
            const client = ensureClient();
            await client.deleteModel(version.filePath);
            deletionSucceeded = true;
            showToast(
                translate('modals.model.versions.toast.versionDeleted', {}, 'Version deleted'),
                {},
                'success'
            );
        } catch (error) {
            console.error('Failed to delete version:', error);
            showToast(error?.message || 'Failed to delete version', {}, 'error');
        } finally {
            if (triggerButton && document.body.contains(triggerButton)) {
                triggerButton.disabled = false;
            }

            if (
                confirmButton &&
                document.body.contains(confirmButton) &&
                !deletionSucceeded
            ) {
                confirmButton.disabled = false;
                if (confirmOriginalText) {
                    confirmButton.textContent = confirmOriginalText;
                }
            }
        }

        if (!deletionSucceeded) {
            return;
        }

        if (typeof closeModal === 'function') {
            closeModal();
        }

        await refresh();
    }

    function showDeleteVersionModal(version, triggerButton) {
        const modalRecord = modalManager?.getModal?.('deleteModal');
        if (!modalRecord?.element) {
            return false;
        }

        const deleteLabel = translate('modals.model.versions.actions.delete', {}, 'Delete');
        const cancelLabel = translate('common.actions.cancel', {}, 'Cancel');
        const title = translate('modals.model.versions.actions.delete', {}, 'Delete');
        const confirmMessage = translate(
            'modals.model.versions.confirm.delete',
            {},
            'Delete this version from your library?'
        );
        const versionName =
            version.name ||
            translate('modals.model.versions.labels.unnamed', {}, 'Untitled Version');
        const previewUrl =
            version.previewUrl || '/loras_static/images/no-preview.png';
        const metaMarkup = buildMetaMarkup(version);

        const modalElement = modalRecord.element;
        const originalMarkup = modalElement.innerHTML;

        const content = `
            <div class="modal-content delete-modal-content version-delete-modal">
                <h2>${escapeHtml(title)}</h2>
                <p class="delete-message">${escapeHtml(confirmMessage)}</p>
                <div class="delete-model-info">
                    <div class="delete-preview">
                        <img src="${escapeHtml(previewUrl)}" alt="${escapeHtml(versionName)}" onerror="this.src='/loras_static/images/no-preview.png'">
                    </div>
                    <div class="delete-info">
                        <h3>${escapeHtml(versionName)}</h3>
                        ${
                            version.baseModel
                                ? `<p class="version-base-model">${escapeHtml(version.baseModel)}</p>`
                                : ''
                        }
                        ${metaMarkup ? `<div class="version-meta">${metaMarkup}</div>` : ''}
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="cancel-btn">${escapeHtml(cancelLabel)}</button>
                    <button class="delete-btn">${escapeHtml(deleteLabel)}</button>
                </div>
            </div>
        `;

        const cleanupHandlers = [];

        modalManager.showModal(
            'deleteModal',
            content,
            null,
            () => {
                cleanupHandlers.forEach(handler => {
                    try {
                        handler();
                    } catch (error) {
                        console.error('Failed to cleanup delete modal handler:', error);
                    }
                });
                cleanupHandlers.length = 0;
                modalElement.innerHTML = originalMarkup;
                delete modalElement.dataset.versionId;
            }
        );

        modalElement.dataset.versionId = String(version.versionId ?? '');

        const cancelButton = modalElement.querySelector('.cancel-btn');
        const confirmButton = modalElement.querySelector('.delete-btn');

        const closeModal = () => modalManager.closeModal('deleteModal');

        if (cancelButton) {
            const handleCancel = event => {
                event.preventDefault();
                closeModal();
            };
            cancelButton.addEventListener('click', handleCancel);
            cleanupHandlers.push(() => {
                cancelButton.removeEventListener('click', handleCancel);
            });
        }

        if (confirmButton) {
            const handleConfirm = async event => {
                event.preventDefault();
                await performDeleteVersion({
                    triggerButton,
                    confirmButton,
                    closeModal,
                    version,
                });
            };
            confirmButton.addEventListener('click', handleConfirm);
            cleanupHandlers.push(() => {
                confirmButton.removeEventListener('click', handleConfirm);
            });
        }

        return true;
    }

    async function handleDeleteVersion(button, versionId) {
        if (!controller.record) {
            return;
        }
        const version = controller.record.versions.find(item => item.versionId === versionId);
        if (!version) {
            console.warn('Target version missing from record for delete:', versionId);
            return;
        }

        if (showDeleteVersionModal(version, button)) {
            return;
        }

        const confirmText = translate(
            'modals.model.versions.confirm.delete',
            {},
            'Delete this version from your library?'
        );
        if (!window.confirm(confirmText)) {
            return;
        }

        await performDeleteVersion({
            triggerButton: button,
            version,
        });
    }

    async function handleDownloadVersion(button, versionId) {
        if (!controller.record) {
            return;
        }

        const version = controller.record.versions.find(item => item.versionId === versionId);
        if (!version) {
            console.warn('Target version missing from record for download:', versionId);
            return;
        }

        button.disabled = true;

        try {
            const success = await downloadManager.downloadVersionWithDefaults(modelType, modelId, versionId, {
                versionName: version.name || `#${version.versionId}`,
            });

            if (success) {
                await refresh();
            }
        } catch (error) {
            console.error('Failed to start direct download for version:', error);
        } finally {
            if (document.body.contains(button)) {
                button.disabled = false;
            }
        }
    }

    container.addEventListener('click', async event => {
        const toolbarAction = event.target.closest('[data-versions-action]');
        if (toolbarAction) {
            const action = toolbarAction.dataset.versionsAction;
            if (action === 'toggle-model-ignore') {
                event.preventDefault();
                await handleToggleModelIgnore(toolbarAction);
            }
            return;
        }

        const actionButton = event.target.closest('[data-version-action]');
        if (actionButton) {
            const row = actionButton.closest('.model-version-row');
            if (!row) {
                return;
            }
            const versionId = Number(row.dataset.versionId);
            const action = actionButton.dataset.versionAction;

            switch (action) {
                case 'download':
                    event.preventDefault();
                    await handleDownloadVersion(actionButton, versionId);
                    break;
                case 'delete':
                    event.preventDefault();
                    await handleDeleteVersion(actionButton, versionId);
                    break;
                case 'toggle-ignore':
                    event.preventDefault();
                    await handleToggleVersionIgnore(actionButton, versionId);
                    break;
                default:
                    break;
            }
            return;
        }

        const row = event.target.closest('.model-version-row.is-clickable');
        if (!row) {
            return;
        }
        if (event.target.closest('button')) {
            return;
        }
        if (event.target.closest('.version-actions')) {
            return;
        }
        if (event.target.closest('a')) {
            return;
        }

        const targetUrl = row.dataset.civitaiUrl;
        if (!targetUrl) {
            return;
        }
        event.preventDefault();
        window.open(targetUrl, '_blank', 'noopener,noreferrer');
    });

    return {
        load: options => loadVersions(options),
        refresh,
    };
}
