/**
 * MetadataPanel - Right panel for model metadata and tabs
 * Features:
 * - Fixed header with model info
 * - Compact metadata grid
 * - Editable fields (usage tips, trigger words, notes)
 * - Tabs with accordion content
 */

import { escapeHtml, formatFileSize } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';

export class MetadataPanel {
  constructor(container) {
    this.element = container;
    this.model = null;
    this.modelType = null;
    this.activeTab = 'description';
  }

  /**
   * Render the metadata panel
   */
  render({ model, modelType }) {
    this.model = model;
    this.modelType = modelType;

    this.element.innerHTML = this.getTemplate();
    this.bindEvents();
  }

  /**
   * Get the HTML template
   */
  getTemplate() {
    const m = this.model;
    const civitai = m.civitai || {};
    const creator = civitai.creator || {};
    
    return `
      <div class="metadata__header">
        <div class="metadata__title-row">
          <h2 class="metadata__name">${escapeHtml(m.model_name || 'Unknown')}</h2>
          <button class="metadata__edit-btn" data-action="edit-name" title="${translate('modals.model.actions.editName', {}, 'Edit name')}">
            <i class="fas fa-pencil-alt"></i>
          </button>
        </div>
        
        <div class="metadata__actions">
          ${creator.username ? `
            <div class="metadata__creator" data-action="view-creator" data-username="${escapeHtml(creator.username)}">
              ${creator.image ? `
                <div class="metadata__creator-avatar">
                  <img src="${creator.image}" alt="${escapeHtml(creator.username)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                  <i class="fas fa-user" style="display: none;"></i>
                </div>
              ` : `
                <div class="metadata__creator-avatar">
                  <i class="fas fa-user"></i>
                </div>
              `}
              <span class="metadata__creator-name">${escapeHtml(creator.username)}</span>
            </div>
          ` : ''}
          
          ${m.from_civitai ? `
            <a class="metadata__civitai-link" href="https://civitai.com/models/${civitai.modelId}" target="_blank" rel="noopener">
              <i class="fas fa-globe"></i>
              <span>${translate('modals.model.actions.viewOnCivitai', {}, 'Civitai')}</span>
            </a>
          ` : ''}
          
          ${this.renderLicenseIcons()}
        </div>
        
        ${this.renderTags(m.tags)}
      </div>
      
      <div class="metadata__info">
        <div class="metadata__info-grid">
          <div class="metadata__info-item">
            <span class="metadata__info-label">${translate('modals.model.metadata.version', {}, 'Version')}</span>
            <span class="metadata__info-value">${escapeHtml(civitai.name || 'N/A')}</span>
          </div>
          
          <div class="metadata__info-item">
            <span class="metadata__info-label">${translate('modals.model.metadata.size', {}, 'Size')}</span>
            <span class="metadata__info-value metadata__info-value--mono">${formatFileSize(m.file_size)}</span>
          </div>
          
          <div class="metadata__info-item">
            <span class="metadata__info-label">${translate('modals.model.metadata.baseModel', {}, 'Base Model')}</span>
            <span class="metadata__info-value">${escapeHtml(m.base_model || translate('modals.model.metadata.unknown', {}, 'Unknown'))}</span>
          </div>
          
          <div class="metadata__info-item">
            <span class="metadata__info-label">${translate('modals.model.metadata.fileName', {}, 'File Name')}</span>
            <span class="metadata__info-value metadata__info-value--mono">${escapeHtml(m.file_name || 'N/A')}</span>
          </div>
          
          <div class="metadata__info-item metadata__info-item--full">
            <span class="metadata__info-label">${translate('modals.model.metadata.location', {}, 'Location')}</span>
            <span class="metadata__info-value metadata__info-value--path" data-action="open-location" title="${translate('modals.model.actions.openLocation', {}, 'Open file location')}">
              ${escapeHtml((m.file_path || '').replace(/[^/]+$/, '') || 'N/A')}
            </span>
          </div>
        </div>
      </div>
      
      ${this.modelType === 'loras' ? this.renderLoraSpecific() : ''}
      
      ${this.renderNotes(m.notes)}
      
      <div class="metadata__content">
        ${this.renderTabs()}
        ${this.renderTabPanels()}
      </div>
    `;
  }

  /**
   * Render license icons
   */
  renderLicenseIcons() {
    const license = this.model.civitai?.model;
    if (!license) return '';

    const icons = [];
    
    if (license.allowNoCredit === false) {
      icons.push({ icon: 'user-check', title: translate('modals.model.license.creditRequired', {}, 'Creator credit required') });
    }
    
    if (license.allowCommercialUse) {
      const restrictions = this.resolveCommercialRestrictions(license.allowCommercialUse);
      restrictions.forEach(r => {
        icons.push({ icon: r.icon, title: r.title });
      });
    }
    
    if (license.allowDerivatives === false) {
      icons.push({ icon: 'exchange-off', title: translate('modals.model.license.noDerivatives', {}, 'No sharing merges') });
    }
    
    if (license.allowDifferentLicense === false) {
      icons.push({ icon: 'rotate-2', title: translate('modals.model.license.noReLicense', {}, 'Same permissions required') });
    }

    if (icons.length === 0) return '';

    return `
      <div class="metadata__licenses">
        ${icons.map(icon => `
          <span class="metadata__license-icon" 
                style="--license-icon-image: url('/loras_static/images/tabler/${icon.icon}.svg')"
                title="${escapeHtml(icon.title)}"
                role="img"
                aria-label="${escapeHtml(icon.title)}">
          </span>
        `).join('')}
      </div>
    `;
  }

  /**
   * Resolve commercial restrictions
   */
  resolveCommercialRestrictions(value) {
    const COMMERCIAL_CONFIG = [
      { key: 'image', icon: 'photo-off', title: translate('modals.model.license.noImageSell', {}, 'No selling generated content') },
      { key: 'rentcivit', icon: 'brush-off', title: translate('modals.model.license.noRentCivit', {}, 'No Civitai generation') },
      { key: 'rent', icon: 'world-off', title: translate('modals.model.license.noRent', {}, 'No generation services') },
      { key: 'sell', icon: 'shopping-cart-off', title: translate('modals.model.license.noSell', {}, 'No selling models') },
    ];

    // Parse and normalize values
    let allowed = new Set();
    const values = Array.isArray(value) ? value : [value];
    
    values.forEach(v => {
      if (!v && v !== '') return;
      const cleaned = String(v).trim().toLowerCase().replace(/[\s_-]+/g, '').replace(/[^a-z]/g, '');
      if (cleaned) allowed.add(cleaned);
    });

    // Apply hierarchy
    if (allowed.has('sell')) {
      allowed.add('rent');
      allowed.add('rentcivit');
      allowed.add('image');
    }
    if (allowed.has('rent')) {
      allowed.add('rentcivit');
    }

    // Return disallowed items
    return COMMERCIAL_CONFIG.filter(config => !allowed.has(config.key));
  }

  /**
   * Render tags
   */
  renderTags(tags) {
    if (!tags || tags.length === 0) return '';
    
    const visibleTags = tags.slice(0, 8);
    const remaining = tags.length - visibleTags.length;
    
    return `
      <div class="metadata__tags">
        ${visibleTags.map(tag => `
          <span class="metadata__tag">${escapeHtml(tag)}</span>
        `).join('')}
        ${remaining > 0 ? `<span class="metadata__tag">+${remaining}</span>` : ''}
      </div>
    `;
  }

  /**
   * Render LoRA specific sections
   */
  renderLoraSpecific() {
    const m = this.model;
    const usageTips = m.usage_tips ? JSON.parse(m.usage_tips) : {};
    const triggerWords = m.civitai?.trainedWords || [];

    return `
      <div class="metadata__section">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.metadata.usageTips', {}, 'Usage Tips')}</span>
          <button class="metadata__section-edit" data-action="edit-usage-tips">
            <i class="fas fa-pencil-alt"></i>
          </button>
        </div>
        <div class="metadata__tags--editable">
          ${Object.entries(usageTips).map(([key, value]) => `
            <span class="metadata__tag metadata__tag--editable" data-key="${escapeHtml(key)}" data-value="${escapeHtml(String(value))}">
              ${escapeHtml(key)}: ${escapeHtml(String(value))}
            </span>
          `).join('')}
          <span class="metadata__tag metadata__tag--add" data-action="add-usage-tip">
            <i class="fas fa-plus"></i>
          </span>
        </div>
      </div>
      
      <div class="metadata__section">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.metadata.triggerWords', {}, 'Trigger Words')}</span>
          <button class="metadata__section-edit" data-action="edit-trigger-words">
            <i class="fas fa-pencil-alt"></i>
          </button>
        </div>
        <div class="metadata__tags--editable">
          ${triggerWords.map(word => `
            <span class="metadata__tag metadata__tag--editable" data-word="${escapeHtml(word)}">
              ${escapeHtml(word)}
            </span>
          `).join('')}
          <span class="metadata__tag metadata__tag--add" data-action="add-trigger-word">
            <i class="fas fa-plus"></i>
          </span>
        </div>
      </div>
    `;
  }

  /**
   * Render notes section
   */
  renderNotes(notes) {
    return `
      <div class="metadata__section">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.metadata.additionalNotes', {}, 'Notes')}</span>
          <button class="metadata__section-edit" data-action="edit-notes">
            <i class="fas fa-pencil-alt"></i>
          </button>
        </div>
        <textarea class="metadata__notes" 
                  placeholder="${translate('modals.model.metadata.addNotesPlaceholder', {}, 'Add your notes here...')}"
                  data-action="save-notes">${escapeHtml(notes || '')}</textarea>
      </div>
    `;
  }

  /**
   * Render tabs
   */
  renderTabs() {
    const tabs = [
      { id: 'description', label: translate('modals.model.tabs.description', {}, 'Description') },
      { id: 'versions', label: translate('modals.model.tabs.versions', {}, 'Versions') },
    ];
    
    if (this.modelType === 'loras') {
      tabs.push({ id: 'recipes', label: translate('modals.model.tabs.recipes', {}, 'Recipes') });
    }

    return `
      <div class="tabs">
        ${tabs.map(tab => `
          <button class="tab ${tab.id === this.activeTab ? 'active' : ''}" 
                  data-tab="${tab.id}"
                  data-action="switch-tab">
            <span class="tab__label">${tab.label}</span>
            ${tab.id === 'versions' && this.model.update_available ? `
              <span class="tab__badge tab__badge--pulse">${translate('modals.model.tabs.update', {}, 'Update')}</span>
            ` : ''}
          </button>
        `).join('')}
      </div>
    `;
  }

  /**
   * Render tab panels
   */
  renderTabPanels() {
    const civitai = this.model.civitai || {};
    
    return `
      <div class="tab-panels">
        <div class="tab-panel ${this.activeTab === 'description' ? 'active' : ''}" data-panel="description">
          <div class="accordion expanded">
            <div class="accordion__header" data-action="toggle-accordion">
              <span class="accordion__title">${translate('modals.model.accordion.aboutVersion', {}, 'About this version')}</span>
              <i class="accordion__icon fas fa-chevron-down"></i>
            </div>
            <div class="accordion__content">
              <div class="accordion__body">
                ${civitai.description ? `
                  <div class="markdown-content">${civitai.description}</div>
                ` : `
                  <p class="text-muted">${translate('modals.model.description.empty', {}, 'No description available')}</p>
                `}
              </div>
            </div>
          </div>
          
          <div class="accordion">
            <div class="accordion__header" data-action="toggle-accordion">
              <span class="accordion__title">${translate('modals.model.accordion.modelDescription', {}, 'Model Description')}</span>
              <i class="accordion__icon fas fa-chevron-down"></i>
            </div>
            <div class="accordion__content">
              <div class="accordion__body">
                ${civitai.model?.description ? `
                  <div class="markdown-content">${civitai.model.description}</div>
                ` : `
                  <p class="text-muted">${translate('modals.model.description.empty', {}, 'No description available')}</p>
                `}
              </div>
            </div>
          </div>
        </div>
        
        <div class="tab-panel ${this.activeTab === 'versions' ? 'active' : ''}" data-panel="versions">
          <div class="versions-loading">
            <i class="fas fa-spinner fa-spin"></i>
            <span>${translate('modals.model.loading.versions', {}, 'Loading versions...')}</span>
          </div>
        </div>
        
        ${this.modelType === 'loras' ? `
          <div class="tab-panel ${this.activeTab === 'recipes' ? 'active' : ''}" data-panel="recipes">
            <div class="recipes-loading">
              <i class="fas fa-spinner fa-spin"></i>
              <span>${translate('modals.model.loading.recipes', {}, 'Loading recipes...')}</span>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  /**
   * Bind event listeners
   */
  bindEvents() {
    this.element.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;

      const action = target.dataset.action;
      
      switch (action) {
        case 'switch-tab':
          const tabId = target.dataset.tab;
          this.switchTab(tabId);
          break;
        case 'toggle-accordion':
          target.closest('.accordion')?.classList.toggle('expanded');
          break;
        case 'open-location':
          this.openFileLocation();
          break;
        case 'view-creator':
          const username = target.dataset.username;
          if (username) {
            window.open(`https://civitai.com/user/${username}`, '_blank');
          }
          break;
        case 'edit-name':
        case 'edit-usage-tips':
        case 'edit-trigger-words':
        case 'edit-notes':
          // TODO: Implement edit modes
          console.log('Edit:', action);
          break;
      }
    });

    // Notes textarea auto-save
    const notesTextarea = this.element.querySelector('.metadata__notes');
    if (notesTextarea) {
      notesTextarea.addEventListener('blur', () => {
        this.saveNotes(notesTextarea.value);
      });
    }
  }

  /**
   * Switch active tab
   */
  switchTab(tabId) {
    this.activeTab = tabId;
    
    // Update tab buttons
    this.element.querySelectorAll('.tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.tab === tabId);
    });
    
    // Update panels
    this.element.querySelectorAll('.tab-panel').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.panel === tabId);
    });

    // Load tab-specific data
    if (tabId === 'versions') {
      this.loadVersions();
    } else if (tabId === 'recipes') {
      this.loadRecipes();
    }
  }

  /**
   * Load versions data
   */
  async loadVersions() {
    // TODO: Implement versions loading
    console.log('Load versions');
  }

  /**
   * Load recipes data
   */
  async loadRecipes() {
    // TODO: Implement recipes loading
    console.log('Load recipes');
  }

  /**
   * Save notes
   */
  async saveNotes(notes) {
    if (!this.model?.file_path) return;
    
    try {
      const { getModelApiClient } = await import('../../api/modelApiFactory.js');
      await getModelApiClient().saveModelMetadata(this.model.file_path, { notes });
      
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.notes.saved', {}, 'success');
    } catch (err) {
      console.error('Failed to save notes:', err);
      const { showToast } = await import('../../utils/i18nHelpers.js');
      showToast('modals.model.notes.saveFailed', {}, 'error');
    }
  }

  /**
   * Open file location
   */
  async openFileLocation() {
    if (!this.model?.file_path) return;
    
    try {
      const response = await fetch('/api/lm/open-file-location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: this.model.file_path })
      });
      
      if (!response.ok) throw new Error('Failed to open file location');
      
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.openFileLocation.success', {}, 'success');
    } catch (err) {
      console.error('Failed to open file location:', err);
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.openFileLocation.failed', {}, 'error');
    }
  }
}
