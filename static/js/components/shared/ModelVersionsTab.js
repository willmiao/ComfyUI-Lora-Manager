import { getModelApiClient } from '../../api/modelApiFactory.js';
import { downloadManager } from '../../managers/DownloadManager.js';
import { modalManager } from '../../managers/ModalManager.js';
import { openCivitaiUrl, showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';
import { state } from '../../state/index.js';
import { buildCivitaiModelUrl } from '../../utils/civitaiUtils.js';
import { formatFileSize } from './utils.js';

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.mkv'];
const PREVIEW_PLACEHOLDER_URL = '/loras_static/images/no-preview.png';

function buildCivitaiVersionUrl(modelId, versionId) {
    return buildCivitaiModelUrl(
        modelId,
        versionId,
        state?.global?.settings?.civitai_host
    );
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

/**
 * Format EA end time as smart relative time
 * - < 1 day: "in Xh" (hours)
 * - 1-7 days: "in Xd" (days)
 * - > 7 days: "Jan 15" (short date)
 */
function formatEarlyAccessTime(endsAt) {
    if (!endsAt) {
        return null;
    }
    const endDate = new Date(endsAt);
    if (Number.isNaN(endDate.getTime())) {
        return null;
    }

    const now = new Date();
    const diffMs = endDate.getTime() - now.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    const diffDays = diffHours / 24;

    if (diffHours < 1) {
        return translate('modals.model.versions.eaTime.endingSoon', {}, 'ending soon');
    }
    if (diffHours < 24) {
        const hours = Math.ceil(diffHours);
        return translate(
            'modals.model.versions.eaTime.hours',
            { count: hours },
            `in ${hours}h`
        );
    }
    if (diffDays <= 7) {
        const days = Math.ceil(diffDays);
        return translate(
            'modals.model.versions.eaTime.days',
            { count: days },
            `in ${days}d`
        );
    }
    // More than 7 days: show short date
    return endDate.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
    });
}

function isEarlyAccessActive(version) {
    // Two-phase detection:
    // 1. Use pre-computed isEarlyAccess flag if available (from backend)
    // 2. Otherwise check exact end time if available
    if (typeof version.isEarlyAccess === 'boolean') {
        return version.isEarlyAccess;
    }
    if (!version.earlyAccessEndsAt) {
        return false;
    }
    try {
        return new Date(version.earlyAccessEndsAt) > new Date();
    } catch {
        return false;
    }
}

function isDownloadAllowed(version) {
    if (!version.usageControl) {
        return true;
    }
    return version.usageControl === 'Download';
}

function buildMetaMarkup(version, options = {}) {
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

    // Add early access info if applicable
    if (options.showEarlyAccess && isEarlyAccessActive(version)) {
        const eaTime = formatEarlyAccessTime(version.earlyAccessEndsAt);
        if (eaTime) {
            segments.push(`<span class="version-meta-ea"><i class="fas fa-clock"></i> ${escapeHtml(eaTime)}</span>`);
        }
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

function buildBadge(label, tone, options = {}) {
    const attributes = [];
    if (options.title) {
        attributes.push(`title="${escapeHtml(options.title)}"`);
    }
    if (options.ariaLabel) {
        attributes.push(`aria-label="${escapeHtml(options.ariaLabel)}"`);
    }
    const suffix = attributes.length ? ` ${attributes.join(' ')}` : '';
    return `<span class="version-badge version-badge-${tone}"${suffix}>${escapeHtml(label)}</span>`;
}

function buildActionButton(label, variant, action, options = {}) {
    const attributes = [
        `class="version-action ${variant}"`,
    ];
    if (action) {
        attributes.push(`data-version-action="${escapeHtml(action)}"`);
    }
    if (options.title) {
        attributes.push(`title="${escapeHtml(options.title)}"`);
        attributes.push(`aria-label="${escapeHtml(options.title)}"`);
    }
    if (options.disabled) {
        attributes.push('disabled');
    }
    if (options.extraAttributes) {
        attributes.push(options.extraAttributes);
    }
    return `<button ${attributes.join(' ')}>${options.iconMarkup || ''}${escapeHtml(label)}</button>`;
}

const DISPLAY_FILTER_MODES = Object.freeze({
    SAME_BASE: 'same_base',
    ANY: 'any',
});

const FILTER_LABEL_KEY = 'modals.model.versions.filters.label';
const FILTER_STATE_KEYS = {
    [DISPLAY_FILTER_MODES.SAME_BASE]: 'modals.model.versions.filters.state.showSameBase',
    [DISPLAY_FILTER_MODES.ANY]: 'modals.model.versions.filters.state.showAll',
};
const FILTER_TOOLTIP_KEYS = {
    [DISPLAY_FILTER_MODES.SAME_BASE]: 'modals.model.versions.filters.tooltip.showAllVersions',
    [DISPLAY_FILTER_MODES.ANY]: 'modals.model.versions.filters.tooltip.showSameBaseVersions',
};

function normalizeBaseModelName(value) {
    if (typeof value !== 'string') {
        return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
        return null;
    }
    return trimmed.toLowerCase();
}

function getToggleLabelText() {
    return translate(FILTER_LABEL_KEY, {}, 'Base filter');
}

function getToggleStateText(mode) {
    const key = FILTER_STATE_KEYS[mode] || FILTER_STATE_KEYS[DISPLAY_FILTER_MODES.ANY];
    const fallback =
        mode === DISPLAY_FILTER_MODES.SAME_BASE ? 'Same base' : 'All versions';
    return translate(key, {}, fallback);
}

function getToggleTooltipText(mode) {
    const key =
        FILTER_TOOLTIP_KEYS[mode] || FILTER_TOOLTIP_KEYS[DISPLAY_FILTER_MODES.ANY];
    const fallback =
        mode === DISPLAY_FILTER_MODES.SAME_BASE
            ? 'Switch to showing all versions'
            : 'Switch to showing only versions with the current base model';
    return translate(key, {}, fallback);
}

function getDefaultDisplayMode() {
    const strategy = state?.global?.settings?.update_flag_strategy;
    return strategy === DISPLAY_FILTER_MODES.SAME_BASE
        ? DISPLAY_FILTER_MODES.SAME_BASE
        : DISPLAY_FILTER_MODES.ANY;
}

function getCurrentVersionBaseModel(record, versionId) {
    if (!record || typeof versionId !== 'number' || !Array.isArray(record.versions)) {
        return {
            normalized: null,
            raw: null,
        };
    }
    const currentVersion = record.versions.find(v => v.versionId === versionId);
    if (!currentVersion) {
        return {
            normalized: null,
            raw: null,
        };
    }
    const baseModelRaw = currentVersion.baseModel ?? null;
    return {
        normalized: normalizeBaseModelName(baseModelRaw),
        raw: baseModelRaw,
    };
}

function resolveUpdateAvailability(record, baseModel, currentVersionId) {
    if (!record) {
        return false;
    }

    const strategy = state?.global?.settings?.update_flag_strategy;
    const sameBaseMode = strategy === DISPLAY_FILTER_MODES.SAME_BASE;
    const hideEarlyAccess = state?.global?.settings?.hide_early_access_updates;

    if (!sameBaseMode) {
        return Boolean(record?.hasUpdate);
    }

    const normalizedBase = normalizeBaseModelName(baseModel);
    if (!normalizedBase || !Array.isArray(record.versions)) {
        return false;
    }

    const normalizedCurrentVersionId =
        typeof currentVersionId === 'number'
            ? currentVersionId
            : currentVersionId
            ? Number(currentVersionId)
            : null;

    let threshold = null;
    for (const version of record.versions) {
        if (!version.isInLibrary) {
            continue;
        }
        const versionBase = normalizeBaseModelName(version.baseModel);
        if (versionBase !== normalizedBase) {
            continue;
        }
        if (threshold === null || version.versionId > threshold) {
            threshold = version.versionId;
        }
    }

    if (threshold === null) {
        threshold = normalizedCurrentVersionId;
    }

    if (threshold === null) {
        return false;
    }

    return record.versions.some(version => {
        if (version.isInLibrary || version.shouldIgnore) {
            return false;
        }
        if (hideEarlyAccess && isEarlyAccessActive(version)) {
            return false;
        }
        if (!isDownloadAllowed(version)) {
            return false;
        }
        const versionBase = normalizeBaseModelName(version.baseModel);
        if (versionBase !== normalizedBase) {
            return false;
        }
        return typeof version.versionId === 'number' && version.versionId > threshold;
    });
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

function renderDeletePreview(version, versionName) {
    const previewUrl = version?.previewUrl;
    if (previewUrl && isVideoUrl(previewUrl)) {
        return `
            <video
                src="${escapeHtml(previewUrl)}"
                controls
                muted
                loop
                playsinline
                preload="metadata"
            ></video>
        `;
    }

    const imageUrl = previewUrl || PREVIEW_PLACEHOLDER_URL;
    return `<img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(versionName)}" onerror="this.src='${PREVIEW_PLACEHOLDER_URL}'">`;
}

function renderRow(version, options) {
    const { latestLibraryVersionId, currentVersionId, modelId: parentModelId } = options;
    const isCurrent = currentVersionId && version.versionId === currentVersionId;
    const isNewer =
        typeof latestLibraryVersionId === 'number' &&
        version.versionId > latestLibraryVersionId;
    const isEarlyAccess = isEarlyAccessActive(version);
    const badges = [];
    const openedBadgeLabel = translate('modals.model.versions.badges.current', {}, 'Opened Version');
    const inLibraryBadgeLabel = translate('modals.model.versions.badges.inLibrary', {}, 'In Library');
    const downloadedBadgeLabel = translate('modals.model.versions.badges.downloaded', {}, 'Downloaded');
    const newerBadgeLabel = translate('modals.model.versions.badges.newer', {}, 'Newer Version');
    const earlyAccessBadgeLabel = translate('modals.model.versions.badges.earlyAccess', {}, 'Early Access');
    const ignoredBadgeLabel = translate('modals.model.versions.badges.ignored', {}, 'Ignored');
    const versionName = version.name || translate('modals.model.versions.labels.unnamed', {}, 'Untitled Version');

    if (isCurrent) {
        badges.push(buildBadge(openedBadgeLabel, 'current', {
            title: translate(
                'modals.model.versions.badges.currentTooltip',
                {},
                'This is the version you opened this modal from'
            ),
        }));
    }

    if (version.isInLibrary) {
        badges.push(buildBadge(inLibraryBadgeLabel, 'success', {
            title: translate(
                'modals.model.versions.badges.inLibraryTooltip',
                {},
                'This version exists in your local library'
            ),
        }));
    }

    if (!version.isInLibrary && version.hasBeenDownloaded) {
        badges.push(buildBadge(downloadedBadgeLabel, 'info', {
            title: translate(
                'modals.model.versions.badges.downloadedTooltip',
                {},
                'This version was downloaded before, but is not currently in your library'
            ),
        }));
    }

    if (!version.isInLibrary && isNewer && !version.shouldIgnore) {
        badges.push(buildBadge(newerBadgeLabel, 'info', {
            title: translate(
                'modals.model.versions.badges.newerTooltip',
                {},
                'This version is newer than your latest local version'
            ),
        }));
    }

    if (isEarlyAccess) {
        badges.push(buildBadge(earlyAccessBadgeLabel, 'early-access', {
            title: translate(
                'modals.model.versions.badges.earlyAccessTooltip',
                {},
                'This version currently requires Civitai early access'
            ),
        }));
    }

    if (!isDownloadAllowed(version)) {
        const onSiteOnlyBadgeLabel = translate('modals.model.versions.badges.onSiteOnly', {}, 'On-Site Only');
        badges.push(buildBadge(onSiteOnlyBadgeLabel, 'info', {
            title: translate(
                'modals.model.versions.badges.onSiteOnlyTooltip',
                {},
                'This version is only available for on-site generation on Civitai'
            ),
        }));
    }

    if (version.shouldIgnore) {
        badges.push(buildBadge(ignoredBadgeLabel, 'muted', {
            title: translate(
                'modals.model.versions.badges.ignoredTooltip',
                {},
                'Update notifications are disabled for this version'
            ),
        }));
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
        const canDownload = isDownloadAllowed(version);
        const downloadIcon = isEarlyAccess ? '<i class="fas fa-bolt"></i> ' : '';
        let downloadTitle;
        if (!canDownload) {
            downloadTitle = translate(
                'modals.model.versions.actions.downloadNotAllowedTooltip',
                {},
                'This version is only available for on-site generation on Civitai'
            );
        } else if (isEarlyAccess) {
            downloadTitle = translate(
                'modals.model.versions.actions.downloadEarlyAccessTooltip',
                {},
                'Download this early access version from Civitai'
            );
        } else {
            downloadTitle = translate(
                'modals.model.versions.actions.downloadTooltip',
                {},
                'Download this version'
            );
        }
        actions.push(buildActionButton(
            downloadLabel,
            canDownload ? 'version-action-primary' : 'version-action-disabled',
            canDownload ? 'download' : '',
            {
                title: downloadTitle,
                iconMarkup: downloadIcon,
                disabled: !canDownload,
            }
        ));
    } else if (version.filePath) {
        actions.push(buildActionButton(
            deleteLabel,
            'version-action-danger',
            'delete',
            {
                title: translate(
                    'modals.model.versions.actions.deleteTooltip',
                    {},
                    'Delete this local version'
                ),
            }
        ));
    }
    actions.push(buildActionButton(
        ignoreLabel,
        'version-action-ghost',
        'toggle-ignore',
        {
            title: version.shouldIgnore
                ? translate(
                    'modals.model.versions.actions.unignoreTooltip',
                    {},
                    'Resume update notifications for this version'
                )
                : translate(
                    'modals.model.versions.actions.ignoreTooltip',
                    {},
                    'Ignore update notifications for this version'
                ),
            extraAttributes: `data-ignore-state="${version.shouldIgnore ? 'ignored' : 'active'}"`,
        }
    ));

    const linkTarget = buildCivitaiVersionUrl(
        version.modelId || parentModelId,
        version.versionId
    );
    const civitaiTooltip = translate(
        'modals.model.versions.actions.viewVersionOnCivitai',
        {},
        'View version on Civitai'
    );
    const civitaiLinkMarkup = linkTarget
        ? `
            <a
                class="version-civitai-link"
                href="${escapeHtml(linkTarget)}"
                target="_blank"
                rel="noopener noreferrer"
                title="${escapeHtml(civitaiTooltip)}"
                aria-label="${escapeHtml(civitaiTooltip)}"
            >
                <i class="fas fa-arrow-up-right-from-square" aria-hidden="true"></i>
            </a>
        `
        : '';

    const rowAttributes = [
        `class="model-version-row${isCurrent ? ' is-current' : ''}${linkTarget ? ' is-clickable' : ''}${isEarlyAccess ? ' is-early-access' : ''}"`,
        `data-version-id="${escapeHtml(version.versionId)}"`,
    ];
    if (linkTarget) {
        rowAttributes.push(`data-civitai-url="${escapeHtml(linkTarget)}"`);
    }

    return `
        <div ${rowAttributes.join(' ')}>
            ${renderMediaMarkup(version)}
            <div class="version-details">
                <div class="version-title">
                    <span class="versions-tab-version-name">${escapeHtml(versionName)}</span>
                    ${civitaiLinkMarkup}
                </div>
                <div class="version-badges">${badges.join('')}</div>
                <div class="version-meta">
                    ${buildMetaMarkup(version, { showEarlyAccess: true })}
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

function renderToolbar(record, toolbarState = {}) {
    const ignoreText = record.shouldIgnore
        ? translate('modals.model.versions.actions.resumeModelUpdates', {}, 'Resume updates for this model')
        : translate('modals.model.versions.actions.ignoreModelUpdates', {}, 'Ignore updates for this model');
    const viewLocalText = translate('modals.model.versions.actions.viewLocalVersions', {}, 'View all local versions');
    const infoText = translate(
        'modals.model.versions.copy',
        { count: record.versions.length },
        'Track and manage every version of this model in one place.'
    );

    const displayMode = toolbarState.displayMode || DISPLAY_FILTER_MODES.ANY;
    const toggleLabel = getToggleLabelText();
    const toggleState = getToggleStateText(displayMode);
    const toggleTooltip = getToggleTooltipText(displayMode);
    const filterActive = toolbarState.isFilteringActive ? 'true' : 'false';
    const screenReaderText = [toggleLabel, toggleState].filter(Boolean).join(': ');

    return `
        <header class="versions-toolbar">
            <div class="versions-toolbar-info">
                <div class="versions-toolbar-info-heading">
                    <h3>${translate('modals.model.versions.heading', {}, 'Model versions')}</h3>
                    <button class="versions-filter-toggle" data-versions-action="toggle-version-display-mode" type="button" title="${escapeHtml(toggleTooltip)}" aria-label="${escapeHtml(toggleTooltip)}" data-filter-active="${filterActive}" aria-pressed="${filterActive}">
                        <i class="fas fa-th-list" aria-hidden="true"></i>
                        <span class="sr-only">${escapeHtml(screenReaderText)}</span>
                    </button>
                </div>
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

function renderFilteredEmptyState(baseModelLabel) {
    const message = translate(
        'modals.model.versions.filters.empty',
        { baseModel: baseModelLabel },
        'No versions match the current base model filter.'
    );
    return `
        <div class="versions-empty versions-empty-filter">
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
    currentBaseModel,
    onUpdateStatusChange,
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

    const updateStatusChangeHandler =
        typeof onUpdateStatusChange === 'function' ? onUpdateStatusChange : null;
    let lastNotifiedUpdateState = null;

    let displayMode = getDefaultDisplayMode();

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
        const { normalized: currentBaseModelNormalized, raw: currentBaseModelLabel } =
            getCurrentVersionBaseModel(record, normalizedCurrentVersionId);
        const isFilteringActive =
            displayMode === DISPLAY_FILTER_MODES.SAME_BASE &&
            Boolean(currentBaseModelNormalized);

        const sortedVersions = [...record.versions].sort(
            (a, b) => Number(b.versionId) - Number(a.versionId)
        );

        const filteredVersions = sortedVersions.filter(version => {
            if (!isFilteringActive) {
                return true;
            }
            return normalizeBaseModelName(version.baseModel) === currentBaseModelNormalized;
        });

        const dividerThresholdVersionId = (() => {
            if (!isFilteringActive) {
                return latestLibraryVersionId;
            }
            const baseLocalVersionIds = record.versions
                .filter(
                    version =>
                        version.isInLibrary &&
                        normalizeBaseModelName(version.baseModel) === currentBaseModelNormalized &&
                        typeof version.versionId === 'number'
                )
                .map(version => version.versionId);
            if (!baseLocalVersionIds.length) {
                return null;
            }
            return Math.max(...baseLocalVersionIds);
        })();

        let dividerInserted = false;

        const rowsMarkup = filteredVersions
            .map(version => {
                let markup = '';
                if (
                    !dividerInserted &&
                    typeof dividerThresholdVersionId === 'number' &&
                    !(version.versionId > dividerThresholdVersionId)
                ) {
                    dividerInserted = true;
                    markup += '<div class="version-divider" role="presentation"></div>';
                }
                markup += renderRow(version, {
                    latestLibraryVersionId: dividerThresholdVersionId,
                    currentVersionId: normalizedCurrentVersionId,
                    modelId: record?.modelId ?? modelId,
                });
                return markup;
            })
            .join('');

        const listContent =
            rowsMarkup || renderFilteredEmptyState(currentBaseModelLabel);

        container.innerHTML = `
        ${renderToolbar(record, {
            displayMode,
            isFilteringActive,
        })}
        <div class="versions-list">
            ${listContent}
        </div>
    `;

        setupMediaHoverInteractions(container);

        if (updateStatusChangeHandler) {
            const resolvedFlag = resolveUpdateAvailability(
                record,
                currentBaseModel,
                normalizedCurrentVersionId
            );
            if (resolvedFlag !== lastNotifiedUpdateState) {
                lastNotifiedUpdateState = resolvedFlag;
                updateStatusChangeHandler(resolvedFlag, record);
            }
        }
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

    function handleToggleVersionDisplayMode() {
        displayMode =
            displayMode === DISPLAY_FILTER_MODES.SAME_BASE
                ? DISPLAY_FILTER_MODES.ANY
                : DISPLAY_FILTER_MODES.SAME_BASE;
        if (!controller.record) {
            return;
        }
        render(controller.record);
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
        const metaMarkup = buildMetaMarkup(version);
        const previewMarkup = renderDeletePreview(version, versionName);

        const modalElement = modalRecord.element;
        const originalMarkup = modalElement.innerHTML;

        const content = `
            <div class="modal-content delete-modal-content version-delete-modal">
                <h2>${escapeHtml(title)}</h2>
                <p class="delete-message">${escapeHtml(confirmMessage)}</p>
                <div class="delete-model-info">
                    <div class="delete-preview">
                        ${previewMarkup}
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

    async function resolveDownloadPathFromCurrentVersion() {
        if (!normalizedCurrentVersionId || !controller.record?.versions) {
            return null;
        }

        const currentVersion = controller.record.versions.find(
            v => v.versionId === normalizedCurrentVersionId && v.isInLibrary && v.filePath
        );
        if (!currentVersion?.filePath) {
            return null;
        }

        try {
            const client = ensureClient();
            const rootsData = await client.fetchModelRoots();
            const roots = rootsData?.roots;
            if (!Array.isArray(roots) || roots.length === 0) {
                return null;
            }

            const normalizedFilePath = currentVersion.filePath.replace(/\\/g, '/');
            let matchedRoot = null;
            let relativePath = null;

            for (const root of roots) {
                const normalizedRoot = root.replace(/\\/g, '/');
                if (normalizedFilePath.startsWith(normalizedRoot)) {
                    matchedRoot = root;
                    relativePath = normalizedFilePath.slice(normalizedRoot.length);
                    if (relativePath.startsWith('/')) {
                        relativePath = relativePath.slice(1);
                    }
                    break;
                }
            }

            if (!matchedRoot || !relativePath) {
                return null;
            }

            const lastSlash = relativePath.lastIndexOf('/');
            const targetFolder = lastSlash > 0 ? relativePath.slice(0, lastSlash) : '';

            return { modelRoot: matchedRoot, targetFolder };
        } catch (error) {
            console.debug('Failed to resolve download path from current version:', error);
            return null;
        }
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
            const pathInfo = await resolveDownloadPathFromCurrentVersion();
            const success = await downloadManager.downloadVersionWithDefaults(modelType, modelId, versionId, {
                versionName: version.name || `#${version.versionId}`,
                modelRoot: pathInfo?.modelRoot || '',
                targetFolder: pathInfo?.targetFolder || '',
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
            switch (action) {
                case 'toggle-model-ignore':
                    event.preventDefault();
                    await handleToggleModelIgnore(toolbarAction);
                    break;
                case 'toggle-version-display-mode':
                    event.preventDefault();
                    handleToggleVersionDisplayMode();
                    break;
                default:
                    break;
            }
            return;
        }

        const actionButton = event.target.closest('[data-version-action]');
        if (actionButton) {
            // Check if browser extension has already handled this action
            if (actionButton.dataset.lmExtensionHandled === 'true') {
                return;
            }
            
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
        const civitaiLink = event.target.closest('.version-civitai-link');
        if (civitaiLink) {
            event.preventDefault();
            openCivitaiUrl(civitaiLink.href);
            return;
        }

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
        openCivitaiUrl(targetUrl);
    });

    // Listen for extension-triggered refresh requests
    container.addEventListener('lm:refreshVersions', async () => {
        await refresh();
    });

    return {
        load: options => loadVersions(options),
        refresh,
    };
}
