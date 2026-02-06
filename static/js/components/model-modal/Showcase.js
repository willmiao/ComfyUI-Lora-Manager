/**
 * Showcase - Left panel for displaying example images
 * Features:
 * - Main image display with navigation
 * - Thumbnail rail for quick switching
 * - Params panel for image metadata
 * - Keyboard navigation support (← →)
 */

import { escapeHtml } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';

export class Showcase {
  constructor(container) {
    this.element = container;
    this.images = [];
    this.currentIndex = 0;
    this.modelHash = '';
    this.filePath = '';
    this.paramsVisible = false;
  }

  /**
   * Render the showcase
   */
  render({ images, modelHash, filePath }) {
    this.images = images || [];
    this.modelHash = modelHash || '';
    this.filePath = filePath || '';
    this.currentIndex = 0;
    this.paramsVisible = false;

    this.element.innerHTML = this.getTemplate();
    this.bindEvents();
    
    if (this.images.length > 0) {
      this.loadImage(0);
    }
  }

  /**
   * Get the HTML template
   */
  getTemplate() {
    const hasImages = this.images.length > 0;
    
    return `
      <div class="showcase__main">
        ${hasImages ? `
          <div class="showcase__image-wrapper">
            <img class="showcase__image" alt="${translate('modals.model.examples.title', {}, 'Example')}">
            
            <div class="showcase__controls">
              <button class="showcase__control-btn" data-action="toggle-params" title="${translate('modals.model.actions.viewParams', {}, 'View parameters (I)')}">
                <i class="fas fa-info-circle"></i>
              </button>
              <button class="showcase__control-btn showcase__control-btn--primary" data-action="set-preview" title="${translate('modals.model.actions.setPreview', {}, 'Set as preview')}">
                <i class="fas fa-image"></i>
              </button>
              <button class="showcase__control-btn showcase__control-btn--danger" data-action="delete-example" title="${translate('modals.model.actions.delete', {}, 'Delete')}">
                <i class="fas fa-trash-alt"></i>
              </button>
            </div>
            
            <button class="showcase__nav showcase__nav--prev" data-action="prev-image" title="${translate('modals.model.navigation.previous', {}, 'Previous')} (←)">
              <i class="fas fa-chevron-left"></i>
            </button>
            <button class="showcase__nav showcase__nav--next" data-action="next-image" title="${translate('modals.model.navigation.next', {}, 'Next')} (→)">
              <i class="fas fa-chevron-right"></i>
            </button>
            
            <div class="showcase__params">
              <div class="showcase__params-header">
                <span class="showcase__params-title">${translate('modals.model.params.title', {}, 'Generation Parameters')}</span>
                <button class="showcase__params-close" data-action="close-params">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="showcase__params-content">
                <!-- Params will be populated here -->
              </div>
            </div>
          </div>
        ` : `
          <div class="showcase__empty">
            <i class="fas fa-images"></i>
            <p>${translate('modals.model.examples.empty', {}, 'No example images available')}</p>
          </div>
        `}
      </div>
      
      ${this.renderThumbnailRail()}
    `;
  }

  /**
   * Render the thumbnail rail
   */
  renderThumbnailRail() {
    if (this.images.length === 0) {
      return `
        <div class="thumbnail-rail">
          <button class="thumbnail-rail__add" data-action="add-example">
            <i class="fas fa-plus"></i>
            <span>${translate('modals.model.examples.add', {}, 'Add')}</span>
          </button>
        </div>
      `;
    }

    const thumbnails = this.images.map((img, index) => {
      const url = img.url || img;
      const isNsfw = img.nsfw || false;
      return `
        <div class="thumbnail-rail__item ${index === 0 ? 'active' : ''} ${isNsfw ? 'nsfw' : ''}" 
             data-index="${index}"
             data-action="select-image">
          <img src="${url}" loading="lazy" alt="">
          ${isNsfw ? '<span class="thumbnail-rail__nsfw-badge">NSFW</span>' : ''}
        </div>
      `;
    }).join('');

    return `
      <div class="thumbnail-rail">
        ${thumbnails}
        <button class="thumbnail-rail__add" data-action="add-example">
          <i class="fas fa-plus"></i>
          <span>${translate('modals.model.examples.add', {}, 'Add')}</span>
        </button>
      </div>
      <div class="thumbnail-rail__upload">
        <!-- Upload area will be expanded here -->
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
        case 'prev-image':
          this.prevImage();
          break;
        case 'next-image':
          this.nextImage();
          break;
        case 'select-image':
          const index = parseInt(target.dataset.index, 10);
          if (!isNaN(index)) {
            this.loadImage(index);
          }
          break;
        case 'toggle-params':
          this.toggleParams();
          break;
        case 'close-params':
          this.hideParams();
          break;
        case 'set-preview':
          this.setAsPreview();
          break;
        case 'delete-example':
          this.deleteExample();
          break;
        case 'add-example':
          this.showUploadArea();
          break;
        case 'copy-prompt':
          this.copyPrompt();
          break;
      }
    });
  }

  /**
   * Load and display an image by index
   */
  loadImage(index) {
    if (index < 0 || index >= this.images.length) return;
    
    this.currentIndex = index;
    const image = this.images[index];
    const url = image.url || image;
    
    // Update main image
    const imgElement = this.element.querySelector('.showcase__image');
    if (imgElement) {
      imgElement.classList.add('loading');
      imgElement.src = url;
      imgElement.onload = () => {
        imgElement.classList.remove('loading');
      };
    }

    // Update thumbnail rail active state
    this.element.querySelectorAll('.thumbnail-rail__item').forEach((item, i) => {
      item.classList.toggle('active', i === index);
    });

    // Update params
    this.updateParams(image);
  }

  /**
   * Navigate to previous image
   */
  prevImage() {
    if (this.images.length === 0) return;
    const newIndex = this.currentIndex > 0 ? this.currentIndex - 1 : this.images.length - 1;
    this.loadImage(newIndex);
  }

  /**
   * Navigate to next image
   */
  nextImage() {
    if (this.images.length === 0) return;
    const newIndex = this.currentIndex < this.images.length - 1 ? this.currentIndex + 1 : 0;
    this.loadImage(newIndex);
  }

  /**
   * Toggle params panel visibility
   */
  toggleParams() {
    this.paramsVisible = !this.paramsVisible;
    const panel = this.element.querySelector('.showcase__params');
    if (panel) {
      panel.classList.toggle('visible', this.paramsVisible);
    }
  }

  /**
   * Hide params panel
   */
  hideParams() {
    this.paramsVisible = false;
    const panel = this.element.querySelector('.showcase__params');
    if (panel) {
      panel.classList.remove('visible');
    }
  }

  /**
   * Update params panel content
   */
  updateParams(image) {
    const content = this.element.querySelector('.showcase__params-content');
    if (!content) return;

    const meta = image.meta || {};
    const prompt = meta.prompt || '';
    const negativePrompt = meta.negativePrompt || '';
    
    // Build params display
    let html = '';
    
    if (prompt) {
      html += this.renderPromptSection(
        translate('modals.model.params.prompt', {}, 'Prompt'),
        prompt,
        'prompt'
      );
    }
    
    if (negativePrompt) {
      html += this.renderPromptSection(
        translate('modals.model.params.negativePrompt', {}, 'Negative Prompt'),
        negativePrompt,
        'negative'
      );
    }

    // Add parameter tags
    const params = [];
    if (meta.sampler) params.push({ name: 'Sampler', value: meta.sampler });
    if (meta.steps) params.push({ name: 'Steps', value: meta.steps });
    if (meta.cfgScale) params.push({ name: 'CFG', value: meta.cfgScale });
    if (meta.seed) params.push({ name: 'Seed', value: meta.seed });
    if (meta.size) params.push({ name: 'Size', value: meta.size });

    if (params.length > 0) {
      html += '<div class="params-tags">';
      params.forEach(param => {
        html += `
          <span class="param-tag">
            <span class="param-name">${escapeHtml(param.name)}:</span>
            <span class="param-value">${escapeHtml(String(param.value))}</span>
          </span>
        `;
      });
      html += '</div>';
    }

    if (!prompt && !negativePrompt && params.length === 0) {
      html = `<div class="no-metadata-message">
        <i class="fas fa-info-circle"></i>
        ${translate('modals.model.params.noData', {}, 'No generation data available')}
      </div>`;
    }

    content.innerHTML = html;
  }

  /**
   * Render a prompt section
   */
  renderPromptSection(label, text, type) {
    return `
      <div class="showcase__prompt">
        <div class="showcase__prompt-label">${escapeHtml(label)}</div>
        <div class="showcase__prompt-text">${escapeHtml(text)}</div>
        <button class="showcase__prompt-copy" data-action="copy-prompt" data-type="${type}" title="${translate('common.copy', {}, 'Copy')}">
          <i class="fas fa-copy"></i>
        </button>
      </div>
    `;
  }

  /**
   * Copy current prompt to clipboard
   */
  async copyPrompt() {
    const image = this.images[this.currentIndex];
    if (!image) return;

    const meta = image.meta || {};
    const prompt = meta.prompt || '';
    
    if (!prompt) return;

    try {
      await navigator.clipboard.writeText(prompt);
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.params.promptCopied', {}, 'success');
    } catch (err) {
      console.error('Failed to copy prompt:', err);
    }
  }

  /**
   * Set current image as model preview
   */
  async setAsPreview() {
    const image = this.images[this.currentIndex];
    if (!image || !this.filePath) return;

    const url = image.url || image;
    
    try {
      const { getModelApiClient } = await import('../../api/modelApiFactory.js');
      await getModelApiClient().setModelPreview(this.filePath, url);
      
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.actions.previewSet', {}, 'success');
    } catch (err) {
      console.error('Failed to set preview:', err);
      const { showToast } = await import('../../utils/uiHelpers.js');
      showToast('modals.model.actions.previewFailed', {}, 'error');
    }
  }

  /**
   * Delete current example
   */
  async deleteExample() {
    const image = this.images[this.currentIndex];
    if (!image || !this.filePath) return;

    // TODO: Implement delete confirmation and API call
    console.log('Delete example:', image);
  }

  /**
   * Show upload area for adding new examples
   */
  showUploadArea() {
    // TODO: Implement upload area expansion
    console.log('Show upload area');
  }
}
