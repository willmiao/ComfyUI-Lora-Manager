/**
 * VersionsTab - Model versions list component
 * Features:
 * - Version cards with preview, badges, and actions
 * - Download/Delete/Ignore actions
 * - Base model filter toggle
 * - Reference: static/js/components/shared/ModelVersionsTab.js
 */

import { escapeHtml, formatFileSize } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { downloadManager } from '../../managers/DownloadManager.js';
import { modalManager } from '../../managers/ModalManager.js';

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.mkv'];
const PREVIEW_PLACEHOLDER_URL = '/loras_static/images/no-preview.png';

const DISPLAY_FILTER_MODES = Object.freeze({
  SAME_BASE: 'same_base',
  ANY: 'any',
});

export class VersionsTab {
  constructor(container) {
    this.element = container;
    this.model = null;
    this.modelType = null;
    this.versions = [];
    this.isLoading = false;
    this.displayMode = DISPLAY_FILTER_MODES.ANY;
    this.record = null;
  }

  /**
   * Render the versions tab
   */
  async render({ model, modelType }) {
    this.model = model;
    this.modelType = modelType;
    this.element.innerHTML = this.getLoadingTemplate();
    
    await this.loadVersions();
  }

  /**
   * Get loading template
   */
  getLoadingTemplate() {
    return `
      <div class="versions-loading">
        <i class="fas fa-spinner fa-spin"></i>
        <span>${translate('modals.model.loading.versions', {}, 'Loading versions...')}</span>
      </div>
    `;
  }

  /**
   * Load versions from API
   */
  async loadVersions() {
    const modelId = this.model?.civitai?.modelId;
    
    if (!modelId) {
      this.renderError(translate('modals.model.versions.missingModelId', {}, 'This model is missing a Civitai model id.'));
      return;
    }

    this.isLoading = true;

    try {
      const client = getModelApiClient(this.modelType);
      const response = await client.fetchModelUpdateVersions(modelId, { refresh: false });
      
      if (!response?.success) {
        throw new Error(response?.error || 'Failed to load versions');
      }

      this.record = response.record;
      this.renderVersions();
    } catch (error) {
      console.error('Failed to load versions:', error);
      this.renderError(error.message);
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Render error state
   */
  renderError(message) {
    this.element.innerHTML = `
      <div class="versions-error">
        <i class="fas fa-exclamation-triangle"></i>
        <p>${escapeHtml(message || translate('modals.model.versions.error', {}, 'Failed to load versions.'))}</p>
      </div>
    `;
  }

  /**
   * Render empty state
   */
  renderEmpty() {
    this.element.innerHTML = `
      <div class="versions-empty">
        <i class="fas fa-info-circle"></i>
        <p>${translate('modals.model.versions.empty', {}, 'No version history available for this model yet.')}</p>
      </div>
    `;
  }

  /**
   * Render versions list
   */
  renderVersions() {
    if (!this.record || !Array.isArray(this.record.versions) || this.record.versions.length === 0) {
      this.renderEmpty();
      return;
    }

    const currentVersionId = this.model?.civitai?.versionId;
    const sortedVersions = [...this.record.versions].sort((a, b) => Number(b.versionId) - Number(a.versionId));
    
    // Filter versions based on display mode
    const filteredVersions = this.filterVersions(sortedVersions, currentVersionId);

    if (filteredVersions.length === 0) {
      this.renderFilteredEmpty();
      return;
    }

    this.element.innerHTML = `
      ${this.renderToolbar()}
      <div class="versions-list">
        ${filteredVersions.map(version => this.renderVersionCard(version, currentVersionId)).join('')}
      </div>
    `;

    this.bindEvents();
  }

  /**
   * Filter versions based on display mode
   */
  filterVersions(versions, currentVersionId) {
    const currentVersion = versions.find(v => v.versionId === currentVersionId);
    const currentBaseModel = currentVersion?.baseModel;

    if (this.displayMode !== DISPLAY_FILTER_MODES.SAME_BASE || !currentBaseModel) {
      return versions;
    }

    return versions.filter(version => {
      const versionBase = version.baseModel?.toLowerCase().trim();
      const targetBase = currentBaseModel.toLowerCase().trim();
      return versionBase === targetBase;
    });
  }

  /**
   * Render filtered empty state
   */
  renderFilteredEmpty() {
    const currentVersion = this.record.versions.find(v => v.versionId === this.model?.civitai?.versionId);
    const baseModelLabel = currentVersion?.baseModel || translate('modals.model.metadata.unknown', {}, 'Unknown');
    
    this.element.innerHTML = `
      ${this.renderToolbar()}
      <div class="versions-empty versions-empty-filter">
        <i class="fas fa-info-circle"></i>
        <p>${translate('modals.model.versions.filters.empty', { baseModel: baseModelLabel }, 'No versions match the current base model filter.')}</p>
      </div>
    `;
    
    this.bindEvents();
  }

  /**
   * Render toolbar with actions
   */
  renderToolbar() {
    const ignoreText = this.record.shouldIgnore
      ? translate('modals.model.versions.actions.resumeModelUpdates', {}, 'Resume updates for this model')
      : translate('modals.model.versions.actions.ignoreModelUpdates', {}, 'Ignore updates for this model');

    const isFilteringActive = this.displayMode === DISPLAY_FILTER_MODES.SAME_BASE;
    const toggleTooltip = isFilteringActive
      ? translate('modals.model.versions.filters.tooltip.showAllVersions', {}, 'Switch to showing all versions')
      : translate('modals.model.versions.filters.tooltip.showSameBaseVersions', {}, 'Switch to showing only versions with the current base model');

    return `
      <header class="versions-toolbar">
        <div class="versions-toolbar-info">
          <div class="versions-toolbar-info-heading">
            <h3>${translate('modals.model.versions.heading', {}, 'Model versions')}</h3>
            <button class="versions-filter-toggle ${isFilteringActive ? 'active' : ''}" 
                    data-action="toggle-filter"
                    title="${escapeHtml(toggleTooltip)}"
                    type="button">
              <i class="fas fa-th-list"></i>
            </button>
          </div>
          <p>${translate('modals.model.versions.copy', { count: this.record.versions.length }, 'Track and manage every version of this model in one place.')}</p>
        </div>
        <div class="versions-toolbar-actions">
          <button class="versions-toolbar-btn versions-toolbar-btn-primary" data-action="toggle-model-ignore">
            ${escapeHtml(ignoreText)}
          </button>
        </div>
      </header>
    `;
  }

  /**
   * Render a single version card
   */
  renderVersionCard(version, currentVersionId) {
    const isCurrent = version.versionId === currentVersionId;
    const isInLibrary = version.isInLibrary;
    const isNewer = this.isNewerVersion(version);
    const badges = this.buildBadges(version, isCurrent, isNewer);
    const actions = this.buildActions(version);

    const metaParts = [];
    if (version.baseModel) metaParts.push(`<span class="version-meta-primary">${escapeHtml(version.baseModel)}</span>`);
    if (version.releasedAt) {
      const date = new Date(version.releasedAt);
      if (!isNaN(date.getTime())) {
        metaParts.push(escapeHtml(date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })));
      }
    }
    if (version.sizeBytes > 0) metaParts.push(escapeHtml(formatFileSize(version.sizeBytes)));

    const metaMarkup = metaParts.length > 0
      ? metaParts.map(m => `<span class="version-meta-item">${m}</span>`).join('<span class="version-meta-separator">•</span>')
      : escapeHtml(translate('modals.model.versions.labels.noDetails', {}, 'No additional details'));

    const civitaiUrl = this.buildCivitaiUrl(version.modelId, version.versionId);
    const clickAction = civitaiUrl ? `data-civitai-url="${escapeHtml(civitaiUrl)}"` : '';

    return `
      <div class="version-card ${isCurrent ? 'is-current' : ''} ${civitaiUrl ? 'is-clickable' : ''}" 
           data-version-id="${version.versionId}"
           ${clickAction}>
        ${this.renderMedia(version)}
        <div class="version-details">
          <div class="version-title">
            <span class="version-name">${escapeHtml(version.name || translate('modals.model.versions.labels.unnamed', {}, 'Untitled Version'))}</span>
          </div>
          <div class="version-badges">${badges}</div>
          <div class="version-meta">${metaMarkup}</div>
        </div>
        <div class="version-actions">
          ${actions}
        </div>
      </div>
    `;
  }

  /**
   * Check if version is newer than any in library
   */
  isNewerVersion(version) {
    if (!this.record?.inLibraryVersionIds?.length) return false;
    if (version.isInLibrary) return false;
    const maxInLibrary = Math.max(...this.record.inLibraryVersionIds);
    return version.versionId > maxInLibrary;
  }

  /**
   * Build badges HTML
   */
  buildBadges(version, isCurrent, isNewer) {
    const badges = [];

    if (isCurrent) {
      badges.push(this.createBadge(
        translate('modals.model.versions.badges.current', {}, 'Current Version'),
        'current'
      ));
    }

    if (version.isInLibrary) {
      badges.push(this.createBadge(
        translate('modals.model.versions.badges.inLibrary', {}, 'In Library'),
        'success'
      ));
    } else if (isNewer && !version.shouldIgnore) {
      badges.push(this.createBadge(
        translate('modals.model.versions.badges.newer', {}, 'Newer Version'),
        'info'
      ));
    }

    if (version.shouldIgnore) {
      badges.push(this.createBadge(
        translate('modals.model.versions.badges.ignored', {}, 'Ignored'),
        'muted'
      ));
    }

    return badges.join('');
  }

  /**
   * Create a badge element
   */
  createBadge(label, tone) {
    return `<span class="version-badge version-badge-${tone}">${escapeHtml(label)}</span>`;
  }

  /**
   * Build actions HTML
   */
  buildActions(version) {
    const actions = [];

    if (!version.isInLibrary) {
      actions.push(`
        <button class="version-action version-action-primary" data-action="download">
          ${escapeHtml(translate('modals.model.versions.actions.download', {}, 'Download'))}
        </button>
      `);
    } else if (version.filePath) {
      actions.push(`
        <button class="version-action version-action-danger" data-action="delete">
          ${escapeHtml(translate('modals.model.versions.actions.delete', {}, 'Delete'))}
        </button>
      `);
    }

    const ignoreLabel = version.shouldIgnore
      ? translate('modals.model.versions.actions.unignore', {}, 'Unignore')
      : translate('modals.model.versions.actions.ignore', {}, 'Ignore');

    actions.push(`
      <button class="version-action version-action-ghost" data-action="toggle-ignore">
        ${escapeHtml(ignoreLabel)}
      </button>
    `);

    return actions.join('');
  }

  /**
   * Render media (image/video)
   */
  renderMedia(version) {
    if (!version.previewUrl) {
      return `
        <div class="version-media version-media-placeholder">
          ${escapeHtml(translate('modals.model.versions.media.placeholder', {}, 'No preview'))}
        </div>
      `;
    }

    if (this.isVideoUrl(version.previewUrl)) {
      return `
        <div class="version-media">
          <video src="${escapeHtml(version.previewUrl)}" 
                 controls muted loop playsinline preload="metadata">
          </video>
        </div>
      `;
    }

    return `
      <div class="version-media">
        <img src="${escapeHtml(version.previewUrl)}" 
             alt="${escapeHtml(version.name || 'preview')}" 
             loading="lazy">
      </div>
    `;
  }

  /**
   * Check if URL is a video
   */
  isVideoUrl(url) {
    if (!url) return false;
    const extension = url.split('.').pop()?.toLowerCase()?.split('?')[0];
    return VIDEO_EXTENSIONS.includes(`.${extension}`);
  }

  /**
   * Build Civitai URL
   */
  buildCivitaiUrl(modelId, versionId) {
    if (!modelId || !versionId) return null;
    return `https://civitai.com/models/${encodeURIComponent(modelId)}?modelVersionId=${encodeURIComponent(versionId)}`;
  }

  /**
   * Bind event listeners
   */
  bindEvents() {
    this.element.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) {
        // Check if clicked on a clickable card
        const card = e.target.closest('.version-card.is-clickable');
        if (card && !e.target.closest('.version-actions')) {
          const url = card.dataset.civitaiUrl;
          if (url) window.open(url, '_blank', 'noopener,noreferrer');
        }
        return;
      }

      const action = target.dataset.action;
      const card = target.closest('.version-card');
      const versionId = card ? parseInt(card.dataset.versionId, 10) : null;

      switch (action) {
        case 'toggle-filter':
          this.toggleFilterMode();
          break;
        case 'toggle-model-ignore':
          this.handleToggleModelIgnore();
          break;
        case 'download':
          if (versionId) this.handleDownload(versionId, target);
          break;
        case 'delete':
          if (versionId) this.handleDelete(versionId, target);
          break;
        case 'toggle-ignore':
          if (versionId) this.handleToggleVersionIgnore(versionId, target);
          break;
      }
    });
  }

  /**
   * Toggle filter mode
   */
  toggleFilterMode() {
    this.displayMode = this.displayMode === DISPLAY_FILTER_MODES.SAME_BASE
      ? DISPLAY_FILTER_MODES.ANY
      : DISPLAY_FILTER_MODES.SAME_BASE;
    this.renderVersions();
  }

  /**
   * Handle toggle model ignore
   */
  async handleToggleModelIgnore() {
    if (!this.record) return;

    const modelId = this.record.modelId;
    const nextValue = !this.record.shouldIgnore;

    try {
      const client = getModelApiClient(this.modelType);
      const response = await client.setModelUpdateIgnore(modelId, nextValue);

      if (!response?.success) {
        throw new Error(response?.error || 'Request failed');
      }

      this.record = response.record;
      this.renderVersions();

      const toastKey = nextValue
        ? 'modals.model.versions.toast.modelIgnored'
        : 'modals.model.versions.toast.modelResumed';
      showToast(toastKey, {}, 'success');
    } catch (error) {
      console.error('Failed to toggle model ignore:', error);
      showToast(error?.message || 'Failed to update ignore preference', {}, 'error');
    }
  }

  /**
   * Handle download version
   */
  async handleDownload(versionId, button) {
    const version = this.record.versions.find(v => v.versionId === versionId);
    if (!version) return;

    button.disabled = true;

    try {
      await downloadManager.downloadVersionWithDefaults(
        this.modelType,
        this.record.modelId,
        versionId,
        { versionName: version.name || `#${versionId}` }
      );
      
      // Reload versions after download starts
      setTimeout(() => this.loadVersions(), 1000);
    } catch (error) {
      console.error('Failed to download version:', error);
    } finally {
      button.disabled = false;
    }
  }

  /**
   * Handle delete version
   */
  async handleDelete(versionId, button) {
    const version = this.record.versions.find(v => v.versionId === versionId);
    if (!version?.filePath) return;

    const confirmed = await this.showDeleteConfirmation(version);
    if (!confirmed) return;

    button.disabled = true;

    try {
      const client = getModelApiClient(this.modelType);
      await client.deleteModel(version.filePath);

      showToast('modals.model.versions.toast.versionDeleted', {}, 'success');
      await this.loadVersions();
    } catch (error) {
      console.error('Failed to delete version:', error);
      showToast(error?.message || 'Failed to delete version', {}, 'error');
      button.disabled = false;
    }
  }

  /**
   * Show delete confirmation modal
   */
  async showDeleteConfirmation(version) {
    return new Promise((resolve) => {
      const modalRecord = modalManager?.getModal?.('deleteModal');
      if (!modalRecord?.element) {
        // Fallback to browser confirm
        const message = translate('modals.model.versions.confirm.delete', {}, 'Delete this version from your library?');
        resolve(window.confirm(message));
        return;
      }

      const title = translate('modals.model.versions.actions.delete', {}, 'Delete');
      const message = translate('modals.model.versions.confirm.delete', {}, 'Delete this version from your library?');
      const versionName = version.name || translate('modals.model.versions.labels.unnamed', {}, 'Untitled Version');

      const content = `
        <div class="modal-content delete-modal-content version-delete-modal">
          <h2>${escapeHtml(title)}</h2>
          <p class="delete-message">${escapeHtml(message)}</p>
          <div class="delete-model-info">
            <div class="delete-preview">
              ${version.previewUrl ? `
                <img src="${escapeHtml(version.previewUrl)}" alt="${escapeHtml(versionName)}" 
                     onerror="this.src='${PREVIEW_PLACEHOLDER_URL}'">
              ` : `<img src="${PREVIEW_PLACEHOLDER_URL}" alt="${escapeHtml(versionName)}">`}
            </div>
            <div class="delete-info">
              <h3>${escapeHtml(versionName)}</h3>
              ${version.baseModel ? `<p class="version-base-model">${escapeHtml(version.baseModel)}</p>` : ''}
            </div>
          </div>
          <div class="modal-actions">
            <button class="cancel-btn" data-action="cancel">${escapeHtml(translate('common.actions.cancel', {}, 'Cancel'))}</button>
            <button class="delete-btn" data-action="confirm">${escapeHtml(translate('common.actions.delete', {}, 'Delete'))}</button>
          </div>
        </div>
      `;

      modalManager.showModal('deleteModal', content);

      const modalElement = modalRecord.element;
      const handleAction = (e) => {
        const action = e.target.closest('[data-action]')?.dataset.action;
        if (action === 'confirm') {
          modalManager.closeModal('deleteModal');
          resolve(true);
        } else if (action === 'cancel') {
          modalManager.closeModal('deleteModal');
          resolve(false);
        }
      };

      modalElement.addEventListener('click', handleAction, { once: true });
    });
  }

  /**
   * Handle toggle version ignore
   */
  async handleToggleVersionIgnore(versionId, button) {
    const version = this.record.versions.find(v => v.versionId === versionId);
    if (!version) return;

    const nextValue = !version.shouldIgnore;
    button.disabled = true;

    try {
      const client = getModelApiClient(this.modelType);
      const response = await client.setVersionUpdateIgnore(
        this.record.modelId,
        versionId,
        nextValue
      );

      if (!response?.success) {
        throw new Error(response?.error || 'Request failed');
      }

      this.record = response.record;
      this.renderVersions();

      const updatedVersion = response.record.versions.find(v => v.versionId === versionId);
      const toastKey = updatedVersion?.shouldIgnore
        ? 'modals.model.versions.toast.versionIgnored'
        : 'modals.model.versions.toast.versionUnignored';
      showToast(toastKey, {}, 'success');
    } catch (error) {
      console.error('Failed to toggle version ignore:', error);
      showToast(error?.message || 'Failed to update version preference', {}, 'error');
      button.disabled = false;
    }
  }

  /**
   * Refresh versions
   */
  async refresh() {
    await this.loadVersions();
  }
}
