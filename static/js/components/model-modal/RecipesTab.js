/**
 * RecipesTab - Recipe cards grid component for LoRA models
 * Features:
 * - Recipe cards grid layout
 * - Copy/View actions
 * - LoRA availability status badges
 */

import { escapeHtml } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast, copyToClipboard } from '../../utils/uiHelpers.js';
import { setSessionItem, removeSessionItem } from '../../utils/storageHelpers.js';

export class RecipesTab {
  constructor(container) {
    this.element = container;
    this.model = null;
    this.recipes = [];
    this.isLoading = false;
  }

  /**
   * Render the recipes tab
   */
  async render({ model }) {
    this.model = model;
    this.element.innerHTML = this.getLoadingTemplate();
    
    await this.loadRecipes();
  }

  /**
   * Get loading template
   */
  getLoadingTemplate() {
    return `
      <div class="recipes-loading">
        <i class="fas fa-spinner fa-spin"></i>
        <span>${translate('modals.model.loading.recipes', {}, 'Loading recipes...')}</span>
      </div>
    `;
  }

  /**
   * Load recipes from API
   */
  async loadRecipes() {
    const sha256 = this.model?.sha256;
    
    if (!sha256) {
      this.renderError('Missing model hash');
      return;
    }

    this.isLoading = true;

    try {
      const response = await fetch(`/api/lm/recipes/for-lora?hash=${encodeURIComponent(sha256.toLowerCase())}`);
      const data = await response.json();
      
      if (!data.success) {
        throw new Error(data.error || 'Failed to load recipes');
      }

      this.recipes = data.recipes || [];
      this.renderRecipes();
    } catch (error) {
      console.error('Failed to load recipes:', error);
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
      <div class="recipes-error">
        <i class="fas fa-exclamation-circle"></i>
        <p>${escapeHtml(message || 'Failed to load recipes. Please try again later.')}</p>
      </div>
    `;
  }

  /**
   * Render empty state
   */
  renderEmpty() {
    this.element.innerHTML = `
      <div class="recipes-empty">
        <i class="fas fa-book-open"></i>
        <p>${translate('recipes.noRecipesFound', {}, 'No recipes found that use this LoRA.')}</p>
      </div>
    `;
  }

  /**
   * Render recipes grid
   */
  renderRecipes() {
    if (!this.recipes || this.recipes.length === 0) {
      this.renderEmpty();
      return;
    }

    const loraName = this.model?.model_name || '';

    this.element.innerHTML = `
      <div class="recipes-header">
        <div class="recipes-header__text">
          <span class="recipes-header__eyebrow">Linked recipes</span>
          <h3>${this.recipes.length} recipe${this.recipes.length > 1 ? 's' : ''} using this LoRA</h3>
          <p class="recipes-header__description">
            ${loraName ? `Discover workflows crafted for ${escapeHtml(loraName)}.` : 'Discover workflows crafted for this model.'}
          </p>
        </div>
        <button class="recipes-header__view-all" data-action="view-all">
          <i class="fas fa-external-link-alt"></i>
          <span>View all recipes</span>
        </button>
      </div>
      <div class="recipes-grid">
        ${this.recipes.map(recipe => this.renderRecipeCard(recipe)).join('')}
      </div>
    `;

    this.bindEvents();
  }

  /**
   * Render a single recipe card
   */
  renderRecipeCard(recipe) {
    const baseModel = recipe.base_model || '';
    const loras = recipe.loras || [];
    const lorasCount = loras.length;
    const missingLorasCount = loras.filter(lora => !lora.inLibrary && !lora.isDeleted).length;
    const allLorasAvailable = missingLorasCount === 0 && lorasCount > 0;
    
    let statusClass = 'empty';
    let statusLabel = 'No linked LoRAs';
    let statusTitle = 'No LoRAs in this recipe';
    
    if (lorasCount > 0) {
      if (allLorasAvailable) {
        statusClass = 'ready';
        statusLabel = `${lorasCount} LoRA${lorasCount > 1 ? 's' : ''} ready`;
        statusTitle = 'All LoRAs available - Ready to use';
      } else {
        statusClass = 'missing';
        statusLabel = `Missing ${missingLorasCount} of ${lorasCount}`;
        statusTitle = `${missingLorasCount} of ${lorasCount} LoRAs missing`;
      }
    }

    const imageUrl = recipe.file_url || 
      (recipe.file_path ? `/loras_static/root1/preview/${recipe.file_path.split('/').pop()}` : 
      '/loras_static/images/no-preview.png');

    return `
      <article class="recipe-card" 
               data-recipe-id="${escapeHtml(recipe.id || '')}"
               data-file-path="${escapeHtml(recipe.file_path || '')}"
               role="button"
               tabindex="0"
               aria-label="${recipe.title ? `View recipe ${escapeHtml(recipe.title)}` : 'View recipe details'}">
        <div class="recipe-card__media">
          <img src="${escapeHtml(imageUrl)}" 
               alt="${recipe.title ? escapeHtml(recipe.title) + ' preview' : 'Recipe preview'}"
               loading="lazy">
          <div class="recipe-card__media-top">
            <button class="recipe-card__copy" data-action="copy-recipe" title="Copy recipe syntax">
              <i class="fas fa-copy"></i>
            </button>
          </div>
        </div>
        <div class="recipe-card__body">
          <h4 class="recipe-card__title" title="${escapeHtml(recipe.title || 'Untitled recipe')}">
            ${escapeHtml(recipe.title || 'Untitled recipe')}
          </h4>
          <div class="recipe-card__meta">
            ${baseModel ? `<span class="recipe-card__badge recipe-card__badge--base">${escapeHtml(baseModel)}</span>` : ''}
            <span class="recipe-card__badge recipe-card__badge--${statusClass}" title="${escapeHtml(statusTitle)}">
              <i class="fas fa-layer-group"></i>
              <span>${escapeHtml(statusLabel)}</span>
            </span>
          </div>
          <div class="recipe-card__cta">
            <span>View details</span>
            <i class="fas fa-arrow-right"></i>
          </div>
        </div>
      </article>
    `;
  }

  /**
   * Bind event listeners
   */
  bindEvents() {
    this.element.addEventListener('click', async (e) => {
      const target = e.target.closest('[data-action]');
      
      if (target) {
        const action = target.dataset.action;
        
        if (action === 'view-all') {
          await this.navigateToRecipesPage();
          return;
        }
        
        if (action === 'copy-recipe') {
          const card = target.closest('.recipe-card');
          const recipeId = card?.dataset.recipeId;
          if (recipeId) {
            e.stopPropagation();
            this.copyRecipeSyntax(recipeId);
          }
          return;
        }
      }

      // Card click - navigate to recipe
      const card = e.target.closest('.recipe-card');
      if (card && !e.target.closest('[data-action]')) {
        const recipeId = card.dataset.recipeId;
        if (recipeId) {
          await this.navigateToRecipeDetails(recipeId);
        }
      }
    });

    // Keyboard navigation for cards
    this.element.addEventListener('keydown', async (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        const card = e.target.closest('.recipe-card');
        if (card) {
          e.preventDefault();
          const recipeId = card.dataset.recipeId;
          if (recipeId) {
            await this.navigateToRecipeDetails(recipeId);
          }
        }
      }
    });
  }

  /**
   * Copy recipe syntax to clipboard
   */
  async copyRecipeSyntax(recipeId) {
    if (!recipeId) {
      showToast('toast.recipes.noRecipeId', {}, 'error');
      return;
    }

    try {
      const response = await fetch(`/api/lm/recipe/${recipeId}/syntax`);
      const data = await response.json();

      if (data.success && data.syntax) {
        await copyToClipboard(data.syntax, 'Recipe syntax copied to clipboard');
      } else {
        throw new Error(data.error || 'No syntax returned');
      }
    } catch (err) {
      console.error('Failed to copy recipe syntax:', err);
      showToast('toast.recipes.copyFailed', { message: err.message }, 'error');
    }
  }

  /**
   * Navigate to recipes page with filter
   */
  async navigateToRecipesPage() {
    // Close the modal
    const { ModelModal } = await import('./ModelModal.js');
    ModelModal.close();

    // Clear any previous filters
    removeSessionItem('filterLoraName');
    removeSessionItem('filterLoraHash');
    removeSessionItem('viewRecipeId');

    // Store the LoRA name and hash filter in sessionStorage
    setSessionItem('lora_to_recipe_filterLoraName', this.model?.model_name || '');
    setSessionItem('lora_to_recipe_filterLoraHash', this.model?.sha256 || '');

    // Navigate to recipes page
    window.location.href = '/loras/recipes';
  }

  /**
   * Navigate to specific recipe details
   */
  async navigateToRecipeDetails(recipeId) {
    // Close the modal
    const { ModelModal } = await import('./ModelModal.js');
    ModelModal.close();

    // Clear any previous filters
    removeSessionItem('filterLoraName');
    removeSessionItem('filterLoraHash');
    removeSessionItem('viewRecipeId');

    // Store the recipe ID in sessionStorage to load on recipes page
    setSessionItem('viewRecipeId', recipeId);

    // Navigate to recipes page
    window.location.href = '/loras/recipes';
  }

  /**
   * Refresh recipes
   */
  async refresh() {
    await this.loadRecipes();
  }
}
