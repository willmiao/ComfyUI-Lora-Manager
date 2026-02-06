/**
 * MetadataPanel - Right panel for model metadata and tabs
 * Features:
 * - Fixed header with model info
 * - Compact metadata grid
 * - Editable fields (usage tips, trigger words, notes)
 * - Tabs with accordion content (Description, Versions, Recipes)
 */

import { escapeHtml, formatFileSize } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { VersionsTab } from './VersionsTab.js';
import { RecipesTab } from './RecipesTab.js';

export class MetadataPanel {
  constructor(container) {
    this.element = container;
    this.model = null;
    this.modelType = null;
    this.activeTab = 'description';
    this.versionsTab = null;
    this.recipesTab = null;
    this.notesDebounceTimer = null;
    this.isEditingUsageTips = false;
    this.isEditingTriggerWords = false;
    this.editingTriggerWords = [];
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
          <button class="metadata__edit-btn" data-action="edit-name" title="${translate('modals.model.actions.editModelName', {}, 'Edit model name')}">
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
            <span class="metadata__info-value metadata__info-value--path" data-action="open-location" title="${translate('modals.model.actions.openFileLocation', {}, 'Open file location')}">
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

    let allowed = new Set();
    const values = Array.isArray(value) ? value : [value];
    
    values.forEach(v => {
      if (!v && v !== '') return;
      const cleaned = String(v).trim().toLowerCase().replace(/[\s_-]+/g, '').replace(/[^a-z]/g, '');
      if (cleaned) allowed.add(cleaned);
    });

    if (allowed.has('sell')) {
      allowed.add('rent');
      allowed.add('rentcivit');
      allowed.add('image');
    }
    if (allowed.has('rent')) {
      allowed.add('rentcivit');
    }

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
   * Render LoRA specific sections with editing
   */
  renderLoraSpecific() {
    const m = this.model;
    const usageTips = m.usage_tips ? JSON.parse(m.usage_tips) : {};
    const triggerWords = this.isEditingTriggerWords 
      ? this.editingTriggerWords 
      : (m.civitai?.trainedWords || []);

    return `
      <div class="metadata__section">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.metadata.usageTips', {}, 'Usage Tips')}</span>
          ${!this.isEditingUsageTips ? `
            <button class="metadata__section-edit" data-action="edit-usage-tips" title="${translate('modals.model.usageTips.add', {}, 'Add usage tip')}">
              <i class="fas fa-plus"></i>
            </button>
          ` : ''}
        </div>
        <div class="metadata__tags--editable">
          ${Object.entries(usageTips).map(([key, value]) => `
            <span class="metadata__tag metadata__tag--editable" data-key="${escapeHtml(key)}" data-action="remove-usage-tip" title="${translate('common.actions.delete', {}, 'Delete')}">
              ${escapeHtml(key)}: ${escapeHtml(String(value))}
            </span>
          `).join('')}
          ${this.isEditingUsageTips ? this.renderUsageTipEditor() : ''}
        </div>
      </div>
      
      <div class="metadata__section">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.triggerWords.label', {}, 'Trigger Words')}</span>
          <div class="metadata__section-actions">
            ${!this.isEditingTriggerWords ? `
              <button class="metadata__section-edit" data-action="copy-trigger-words" title="${translate('modals.model.triggerWords.copyWord', {}, 'Copy all trigger words')}">
                <i class="fas fa-copy"></i>
              </button>
              <button class="metadata__section-edit" data-action="edit-trigger-words" title="${translate('modals.model.triggerWords.edit', {}, 'Edit trigger words')}">
                <i class="fas fa-pencil-alt"></i>
              </button>
            ` : `
              <button class="metadata__section-edit" data-action="cancel-trigger-words" title="${translate('common.actions.cancel', {}, 'Cancel')}">
                <i class="fas fa-times"></i>
              </button>
              <button class="metadata__section-edit metadata__section-edit--primary" data-action="save-trigger-words" title="${translate('common.actions.save', {}, 'Save')}">
                <i class="fas fa-check"></i>
              </button>
            `}
          </div>
        </div>
        <div class="metadata__tags--editable">
          ${triggerWords.map(word => `
            <span class="metadata__tag ${this.isEditingTriggerWords ? 'metadata__tag--removable' : 'metadata__tag--editable'}" 
                  data-word="${escapeHtml(word)}"
                  ${this.isEditingTriggerWords ? 'data-action="remove-trigger-word"' : 'data-action="copy-trigger-word"'}
                  title="${this.isEditingTriggerWords ? translate('common.actions.delete', {}, 'Delete') : translate('modals.model.triggerWords.copyWord', {}, 'Copy trigger word')}">
              ${escapeHtml(word)}
              ${this.isEditingTriggerWords ? '<i class="fas fa-times"></i>' : ''}
            </span>
          `).join('')}
          ${this.isEditingTriggerWords ? `
            <input type="text" 
                   class="metadata__tag-input" 
                   placeholder="${translate('modals.model.triggerWords.addPlaceholder', {}, 'Type to add...')}" 
                   data-action="add-trigger-word-input"
                   autofocus>
          ` : triggerWords.length === 0 ? `
            <span class="metadata__tag metadata__tag--placeholder">${translate('modals.model.triggerWords.noTriggerWordsNeeded', {}, 'No trigger words needed')}</span>
          ` : ''}
        </div>
      </div>
    `;
  }

  /**
   * Render usage tip editor
   */
  renderUsageTipEditor() {
    return `
      <div class="usage-tip-editor">
        <select class="usage-tip-key" data-action="usage-tip-key-change">
          <option value="">${translate('modals.model.usageTips.addPresetParameter', {}, 'Select parameter...')}</option>
          <option value="strength">${translate('modals.model.usageTips.strength', {}, 'Strength')}</option>
          <option value="strength_min">${translate('modals.model.usageTips.strengthMin', {}, 'Strength Min')}</option>
          <option value="strength_max">${translate('modals.model.usageTips.strengthMax', {}, 'Strength Max')}</option>
          <option value="clip_strength">${translate('modals.model.usageTips.clipStrength', {}, 'Clip Strength')}</option>
          <option value="clip_skip">${translate('modals.model.usageTips.clipSkip', {}, 'Clip Skip')}</option>
        </select>
        <input type="text" 
               class="usage-tip-value" 
               placeholder="${translate('modals.model.usageTips.valuePlaceholder', {}, 'Value')}" 
               data-action="usage-tip-value-input">
        <button class="usage-tip-add" data-action="add-usage-tip">
          <i class="fas fa-check"></i>
        </button>
        <button class="usage-tip-cancel" data-action="cancel-usage-tips">
          <i class="fas fa-times"></i>
        </button>
      </div>
    `;
  }

  /**
   * Render notes section
   */
  renderNotes(notes) {
    return `
      <div class="metadata__section metadata__section--notes">
        <div class="metadata__section-header">
          <span class="metadata__section-title">${translate('modals.model.metadata.additionalNotes', {}, 'Notes')}</span>
          <span class="metadata__save-indicator" data-save-indicator style="display: none;">
            <i class="fas fa-check"></i> Saved
          </span>
        </div>
        <textarea class="metadata__notes" 
                  placeholder="${translate('modals.model.metadata.addNotesPlaceholder', {}, 'Add your notes here...')}"
                  data-action="notes-input">${escapeHtml(notes || '')}</textarea>
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
              <span class="accordion__title">${translate('modals.model.metadata.aboutThisVersion', {}, 'About this version')}</span>
              <i class="accordion__icon fas fa-chevron-down"></i>
            </div>
            <div class="accordion__content">
              <div class="accordion__body">
                ${civitai.description ? `
                  <div class="markdown-content">${civitai.description}</div>
                ` : `
                  <p class="text-muted">${translate('modals.model.description.noDescription', {}, 'No description available')}</p>
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
                  <p class="text-muted">${translate('modals.model.description.noDescription', {}, 'No description available')}</p>
                `}
              </div>
            </div>
          </div>
        </div>
        
        <div class="tab-panel ${this.activeTab === 'versions' ? 'active' : ''}" data-panel="versions">
          <div class="versions-tab-container"></div>
        </div>
        
        ${this.modelType === 'loras' ? `
          <div class="tab-panel ${this.activeTab === 'recipes' ? 'active' : ''}" data-panel="recipes">
            <div class="recipes-tab-container"></div>
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
          const username = target.dataset.username || target.closest('[data-username]')?.dataset.username;
          if (username) {
            window.open(`https://civitai.com/user/${username}`, '_blank');
          }
          break;
        case 'edit-name':
          this.editModelName();
          break;
        case 'edit-usage-tips':
          this.startEditingUsageTips();
          break;
        case 'cancel-usage-tips':
          this.cancelEditingUsageTips();
          break;
        case 'add-usage-tip':
          this.addUsageTip();
          break;
        case 'remove-usage-tip':
          const key = target.dataset.key;
          if (key) this.removeUsageTip(key);
          break;
        case 'edit-trigger-words':
          this.startEditingTriggerWords();
          break;
        case 'cancel-trigger-words':
          this.cancelEditingTriggerWords();
          break;
        case 'save-trigger-words':
          this.saveTriggerWords();
          break;
        case 'copy-trigger-words':
          this.copyAllTriggerWords();
          break;
        case 'copy-trigger-word':
          const word = target.dataset.word;
          if (word) this.copyTriggerWord(word);
          break;
        case 'remove-trigger-word':
          const wordToRemove = target.dataset.word || target.closest('[data-word]')?.dataset.word;
          if (wordToRemove) this.removeTriggerWord(wordToRemove);
          break;
      }
    });

    // Handle input events
    this.element.addEventListener('input', (e) => {
      if (e.target.dataset.action === 'notes-input') {
        this.handleNotesInput(e.target.value);
      }
    });

    this.element.addEventListener('keydown', (e) => {
      if (e.target.dataset.action === 'add-trigger-word-input' && e.key === 'Enter') {
        e.preventDefault();
        const value = e.target.value.trim();
        if (value) {
          this.addTriggerWord(value);
          e.target.value = '';
        }
      }
      
      if (e.target.dataset.action === 'usage-tip-value-input' && e.key === 'Enter') {
        e.preventDefault();
        this.addUsageTip();
      }
    });

    // Load initial tab content
    if (this.activeTab === 'versions') {
      this.loadVersionsTab();
    } else if (this.activeTab === 'recipes') {
      this.loadRecipesTab();
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
      this.loadVersionsTab();
    } else if (tabId === 'recipes') {
      this.loadRecipesTab();
    }
  }

  /**
   * Load versions tab
   */
  loadVersionsTab() {
    if (!this.versionsTab) {
      const container = this.element.querySelector('.versions-tab-container');
      if (container) {
        this.versionsTab = new VersionsTab(container);
        this.versionsTab.render({ model: this.model, modelType: this.modelType });
      }
    }
  }

  /**
   * Load recipes tab
   */
  loadRecipesTab() {
    if (!this.recipesTab) {
      const container = this.element.querySelector('.recipes-tab-container');
      if (container) {
        this.recipesTab = new RecipesTab(container);
        this.recipesTab.render({ model: this.model });
      }
    }
  }

  /**
   * Handle notes input with auto-save
   */
  handleNotesInput(value) {
    // Clear existing timer
    if (this.notesDebounceTimer) {
      clearTimeout(this.notesDebounceTimer);
    }

    // Show saving indicator
    const indicator = this.element.querySelector('[data-save-indicator]');
    if (indicator) {
      indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
      indicator.style.display = 'inline-flex';
    }

    // Debounce save
    this.notesDebounceTimer = setTimeout(() => {
      this.saveNotes(value);
    }, 800);
  }

  /**
   * Save notes to server
   */
  async saveNotes(notes) {
    if (!this.model?.file_path) return;
    
    try {
      const client = getModelApiClient(this.modelType);
      await client.saveModelMetadata(this.model.file_path, { notes });
      
      const indicator = this.element.querySelector('[data-save-indicator]');
      if (indicator) {
        indicator.innerHTML = '<i class="fas fa-check"></i> Saved';
        setTimeout(() => {
          indicator.style.display = 'none';
        }, 2000);
      }
      
      showToast('modals.model.notes.saved', {}, 'success');
    } catch (err) {
      console.error('Failed to save notes:', err);
      
      const indicator = this.element.querySelector('[data-save-indicator]');
      if (indicator) {
        indicator.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Failed';
      }
      
      showToast('modals.model.notes.saveFailed', {}, 'error');
    }
  }

  /**
   * Start editing usage tips
   */
  startEditingUsageTips() {
    this.isEditingUsageTips = true;
    this.refreshLoraSpecificSection();
  }

  /**
   * Cancel editing usage tips
   */
  cancelEditingUsageTips() {
    this.isEditingUsageTips = false;
    this.refreshLoraSpecificSection();
  }

  /**
   * Add usage tip
   */
  async addUsageTip() {
    const keySelect = this.element.querySelector('.usage-tip-key');
    const valueInput = this.element.querySelector('.usage-tip-value');
    
    const key = keySelect?.value;
    const value = valueInput?.value.trim();
    
    if (!key || !value) return;

    try {
      const usageTips = this.model.usage_tips ? JSON.parse(this.model.usage_tips) : {};
      usageTips[key] = value;
      
      const client = getModelApiClient(this.modelType);
      await client.saveModelMetadata(this.model.file_path, { usage_tips: JSON.stringify(usageTips) });
      
      this.model.usage_tips = JSON.stringify(usageTips);
      this.isEditingUsageTips = false;
      this.refreshLoraSpecificSection();
      showToast('common.actions.save', {}, 'success');
    } catch (err) {
      console.error('Failed to save usage tip:', err);
      showToast('modals.model.notes.saveFailed', {}, 'error');
    }
  }

  /**
   * Remove usage tip
   */
  async removeUsageTip(key) {
    try {
      const usageTips = this.model.usage_tips ? JSON.parse(this.model.usage_tips) : {};
      delete usageTips[key];
      
      const client = getModelApiClient(this.modelType);
      await client.saveModelMetadata(this.model.file_path, { 
        usage_tips: Object.keys(usageTips).length > 0 ? JSON.stringify(usageTips) : null 
      });
      
      this.model.usage_tips = Object.keys(usageTips).length > 0 ? JSON.stringify(usageTips) : null;
      this.refreshLoraSpecificSection();
      showToast('common.actions.delete', {}, 'success');
    } catch (err) {
      console.error('Failed to remove usage tip:', err);
      showToast('modals.model.notes.saveFailed', {}, 'error');
    }
  }

  /**
   * Start editing trigger words
   */
  startEditingTriggerWords() {
    this.isEditingTriggerWords = true;
    this.editingTriggerWords = [...(this.model.civitai?.trainedWords || [])];
    this.refreshLoraSpecificSection();
    
    // Focus input
    setTimeout(() => {
      const input = this.element.querySelector('.metadata__tag-input');
      if (input) input.focus();
    }, 0);
  }

  /**
   * Cancel editing trigger words
   */
  cancelEditingTriggerWords() {
    this.isEditingTriggerWords = false;
    this.editingTriggerWords = [];
    this.refreshLoraSpecificSection();
  }

  /**
   * Add trigger word during editing
   */
  addTriggerWord(word) {
    if (!word.trim()) return;
    if (this.editingTriggerWords.includes(word.trim())) {
      showToast('modals.model.triggerWords.validation.duplicate', {}, 'warning');
      return;
    }
    this.editingTriggerWords.push(word.trim());
    this.refreshLoraSpecificSection();
    
    // Focus input again
    setTimeout(() => {
      const input = this.element.querySelector('.metadata__tag-input');
      if (input) {
        input.value = '';
        input.focus();
      }
    }, 0);
  }

  /**
   * Remove trigger word during editing
   */
  removeTriggerWord(word) {
    this.editingTriggerWords = this.editingTriggerWords.filter(w => w !== word);
    this.refreshLoraSpecificSection();
  }

  /**
   * Save trigger words
   */
  async saveTriggerWords() {
    try {
      const client = getModelApiClient(this.modelType);
      await client.saveModelMetadata(this.model.file_path, { 
        trained_words: this.editingTriggerWords 
      });
      
      // Update local model data
      if (!this.model.civitai) this.model.civitai = {};
      this.model.civitai.trainedWords = [...this.editingTriggerWords];
      
      this.isEditingTriggerWords = false;
      this.editingTriggerWords = [];
      this.refreshLoraSpecificSection();
      showToast('common.actions.save', {}, 'success');
    } catch (err) {
      console.error('Failed to save trigger words:', err);
      showToast('modals.model.notes.saveFailed', {}, 'error');
    }
  }

  /**
   * Copy single trigger word
   */
  async copyTriggerWord(word) {
    try {
      await navigator.clipboard.writeText(word);
      showToast('modals.model.triggerWords.copyWord', {}, 'success');
    } catch (err) {
      console.error('Failed to copy trigger word:', err);
    }
  }

  /**
   * Copy all trigger words
   */
  async copyAllTriggerWords() {
    const words = this.model.civitai?.trainedWords || [];
    if (words.length === 0) return;
    
    try {
      await navigator.clipboard.writeText(words.join(', '));
      showToast('modals.model.triggerWords.copyWord', {}, 'success');
    } catch (err) {
      console.error('Failed to copy trigger words:', err);
    }
  }

  /**
   * Refresh LoRA specific section
   */
  refreshLoraSpecificSection() {
    if (this.modelType !== 'loras') return;
    
    const sections = this.element.querySelectorAll('.metadata__section');
    // First two sections are usage tips and trigger words
    if (sections.length >= 2) {
      const newHtml = this.renderLoraSpecific();
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = newHtml;
      
      const newSections = tempDiv.querySelectorAll('.metadata__section');
      if (newSections.length >= 2) {
        sections[0].replaceWith(newSections[0]);
        sections[1].replaceWith(newSections[1]);
      }
    }
  }

  /**
   * Edit model name
   */
  async editModelName() {
    const currentName = this.model.model_name || '';
    const newName = prompt(
      translate('modals.model.actions.editModelName', {}, 'Edit model name'),
      currentName
    );
    
    if (newName !== null && newName.trim() !== '' && newName !== currentName) {
      try {
        const client = getModelApiClient(this.modelType);
        await client.saveModelMetadata(this.model.file_path, { model_name: newName.trim() });
        
        this.model.model_name = newName.trim();
        this.element.querySelector('.metadata__name').textContent = newName.trim();
        showToast('common.actions.save', {}, 'success');
      } catch (err) {
        console.error('Failed to save model name:', err);
        showToast('modals.model.notes.saveFailed', {}, 'error');
      }
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
      
      showToast('modals.model.openFileLocation.success', {}, 'success');
    } catch (err) {
      console.error('Failed to open file location:', err);
      showToast('modals.model.openFileLocation.failed', {}, 'error');
    }
  }
}
