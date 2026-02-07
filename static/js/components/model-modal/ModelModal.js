/**
 * ModelModal - Main Controller for Split-View Overlay
 * 
 * Architecture:
 * - Overlay container (split-view grid)
 * - Left: Showcase (ExampleShowcase component)
 * - Right: Metadata + Tabs (MetadataPanel component)
 * - Global keyboard navigation (↑↓ for model, ←→ for examples)
 */

import { Showcase } from './Showcase.js';
import { MetadataPanel } from './MetadataPanel.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { state } from '../../state/index.js';
import { translate } from '../../utils/i18nHelpers.js';

export class ModelModal {
  static instance = null;
  static overlayElement = null;
  static currentModel = null;
  static currentModelType = null;
  static showcase = null;
  static metadataPanel = null;
  static isNavigating = false;
  static keyboardHandler = null;
  static hasShownHint = false;

  /**
   * Show the model modal with split-view overlay
   * @param {Object} model - Model data object
   * @param {string} modelType - Type of model ('loras', 'checkpoints', 'embeddings')
   */
  static async show(model, modelType) {
    // If already open, animate transition to new model
    if (this.isOpen()) {
      await this.transitionToModel(model, modelType);
      return;
    }

    this.currentModel = model;
    this.currentModelType = modelType;
    this.isNavigating = false;

    // Fetch complete metadata
    let completeCivitaiData = model.civitai || {};
    if (model.file_path) {
      try {
        const fullMetadata = await getModelApiClient().fetchModelMetadata(model.file_path);
        completeCivitaiData = fullMetadata || model.civitai || {};
      } catch (error) {
        console.warn('Failed to fetch complete metadata:', error);
      }
    }

    this.currentModel = {
      ...model,
      civitai: completeCivitaiData
    };

    // Create overlay
    this.createOverlay();
    
    // Initialize components
    this.showcase = new Showcase(this.overlayElement.querySelector('.showcase'));
    this.metadataPanel = new MetadataPanel(this.overlayElement.querySelector('.metadata'));

    // Render content
    await this.render();

    // Setup keyboard navigation
    this.setupKeyboardNavigation();

    // Lock body scroll
    document.body.classList.add('modal-open');

    // Show hint on first use
    if (!this.hasShownHint) {
      this.showKeyboardHint();
      this.hasShownHint = true;
    }
  }

  /**
   * Create the overlay DOM structure
   */
  static createOverlay() {
    // Check sidebar state for layout adjustment
    const sidebar = document.querySelector('.folder-sidebar');
    const isSidebarCollapsed = sidebar?.classList.contains('collapsed');

    this.overlayElement = document.createElement('div');
    this.overlayElement.className = `model-overlay ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`;
    this.overlayElement.id = 'modelModal';
    this.overlayElement.innerHTML = `
      <button class="model-overlay__close" title="${translate('common.close', {}, 'Close')}">
        <i class="fas fa-times"></i>
      </button>
      <div class="model-overlay__hint">
        ↑↓ ${translate('modals.model.navigation.switchModel', {}, 'Switch model')} | 
        ←→ ${translate('modals.model.navigation.browseExamples', {}, 'Browse examples')} | 
        ESC ${translate('common.close', {}, 'Close')}
      </div>
      <div class="showcase"></div>
      <div class="metadata"></div>
    `;

    // Close button handler
    this.overlayElement.querySelector('.model-overlay__close').addEventListener('click', () => {
      this.close();
    });

    // Click outside to close
    this.overlayElement.addEventListener('click', (e) => {
      if (e.target === this.overlayElement) {
        this.close();
      }
    });

    document.body.appendChild(this.overlayElement);
  }

  /**
   * Render content into components
   */
  static async render() {
    if (!this.currentModel) return;

    // Prepare images data
    const regularImages = this.currentModel.civitai?.images || [];
    const customImages = this.currentModel.civitai?.customImages || [];
    const allImages = [...regularImages, ...customImages];

    // Render showcase
    this.showcase.render({
      images: allImages,
      modelHash: this.currentModel.sha256,
      filePath: this.currentModel.file_path
    });

    // Render metadata panel
    this.metadataPanel.render({
      model: this.currentModel,
      modelType: this.currentModelType
    });
  }

  /**
   * Transition to a different model with animation
   */
  static async transitionToModel(model, modelType) {
    // Ensure components are initialized
    if (!this.showcase || !this.metadataPanel) {
      console.warn('Showcase or MetadataPanel not initialized, falling back to show()');
      await this.show(model, modelType);
      return;
    }

    // Fade out current content
    this.showcase?.element?.classList.add('transitioning');
    this.metadataPanel?.element?.classList.add('transitioning');

    await new Promise(resolve => setTimeout(resolve, 150));

    // Fetch complete metadata for new model
    let completeCivitaiData = model.civitai || {};
    if (model.file_path) {
      try {
        const fullMetadata = await getModelApiClient().fetchModelMetadata(model.file_path);
        completeCivitaiData = fullMetadata || model.civitai || {};
      } catch (error) {
        console.warn('Failed to fetch complete metadata:', error);
      }
    }

    // Update model data in-place
    this.currentModel = {
      ...model,
      civitai: completeCivitaiData
    };
    this.currentModelType = modelType;

    // Render new content in-place
    await this.render();

    // Fade in new content
    this.showcase?.element?.classList.remove('transitioning');
    this.metadataPanel?.element?.classList.remove('transitioning');
  }

  /**
   * Close the modal
   */
  static close(animate = true) {
    if (!this.overlayElement) return;

    // Cleanup keyboard handler
    this.cleanupKeyboardNavigation();

    // Animate out
    if (animate) {
      this.overlayElement.classList.add('closing');
      setTimeout(() => {
        this.removeOverlay();
      }, 200);
    } else {
      this.removeOverlay();
    }

    // Unlock body scroll
    document.body.classList.remove('modal-open');
  }

  /**
   * Remove overlay from DOM
   */
  static removeOverlay() {
    if (this.overlayElement) {
      this.overlayElement.remove();
      this.overlayElement = null;
    }
    this.showcase = null;
    this.metadataPanel = null;
    this.currentModel = null;
    this.currentModelType = null;
  }

  /**
   * Check if modal is currently open
   */
  static isOpen() {
    return !!this.overlayElement;
  }

  /**
   * Setup global keyboard navigation
   */
  static setupKeyboardNavigation() {
    this.keyboardHandler = (e) => {
      // Ignore if user is typing in an input
      if (this.isUserTyping()) return;

      switch (e.key) {
        case 'ArrowUp':
          e.preventDefault();
          this.navigateModel('prev');
          break;
        case 'ArrowDown':
          e.preventDefault();
          this.navigateModel('next');
          break;
        case 'ArrowLeft':
          e.preventDefault();
          this.showcase?.prevImage();
          break;
        case 'ArrowRight':
          e.preventDefault();
          this.showcase?.nextImage();
          break;
        case 'Escape':
          e.preventDefault();
          this.close();
          break;
        case 'i':
        case 'I':
          if (!this.isUserTyping()) {
            e.preventDefault();
            this.showcase?.toggleParams();
          }
          break;
        case 'c':
        case 'C':
          if (!this.isUserTyping()) {
            e.preventDefault();
            this.showcase?.copyPrompt();
          }
          break;
      }
    };

    document.addEventListener('keydown', this.keyboardHandler);
  }

  /**
   * Cleanup keyboard navigation
   */
  static cleanupKeyboardNavigation() {
    if (this.keyboardHandler) {
      document.removeEventListener('keydown', this.keyboardHandler);
      this.keyboardHandler = null;
    }
  }

  /**
   * Check if user is currently typing in an input/editable field
   */
  static isUserTyping() {
    const activeElement = document.activeElement;
    if (!activeElement) return false;
    
    const tagName = activeElement.tagName?.toLowerCase();
    const isEditable = activeElement.isContentEditable;
    const isInput = ['input', 'textarea', 'select'].includes(tagName);
    
    return isEditable || isInput;
  }

  /**
   * Navigate to previous/next model using virtual scroller
   */
  static async navigateModel(direction) {
    if (this.isNavigating || !this.currentModel?.file_path) return;
    
    const scroller = state.virtualScroller;
    if (!scroller || typeof scroller.getAdjacentItemByFilePath !== 'function') {
      return;
    }

    this.isNavigating = true;

    try {
      const adjacent = await scroller.getAdjacentItemByFilePath(
        this.currentModel.file_path, 
        direction
      );
      
      if (!adjacent?.item) {
        const toastKey = direction === 'prev' 
          ? 'modals.model.navigation.noPrevious' 
          : 'modals.model.navigation.noNext';
        const fallback = direction === 'prev' 
          ? 'No previous model available' 
          : 'No next model available';
        // Show toast notification (imported from utils)
        import('../../utils/uiHelpers.js').then(({ showToast }) => {
          showToast(toastKey, {}, 'info', fallback);
        });
        return;
      }

      await this.transitionToModel(adjacent.item, this.currentModelType);
    } finally {
      this.isNavigating = false;
    }
  }

  /**
   * Show keyboard shortcut hint
   */
  static showKeyboardHint() {
    const hint = this.overlayElement?.querySelector('.model-overlay__hint');
    if (hint) {
      // Animation is handled by CSS, just ensure it's visible
      hint.classList.remove('hidden');
    }
  }

  /**
   * Update sidebar state when sidebar is toggled
   */
  static updateSidebarState(collapsed) {
    if (!this.overlayElement) return;
    
    if (collapsed) {
      this.overlayElement.classList.add('sidebar-collapsed');
    } else {
      this.overlayElement.classList.remove('sidebar-collapsed');
    }
  }
}

// Listen for sidebar toggle events
document.addEventListener('sidebar-toggle', (e) => {
  ModelModal.updateSidebarState(e.detail.collapsed);
});
