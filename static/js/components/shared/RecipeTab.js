/**
 * RecipeTab - Handles the recipes tab in model modals.
 */
import { showToast, copyToClipboard } from '../../utils/uiHelpers.js';
import { setSessionItem, removeSessionItem } from '../../utils/storageHelpers.js';

/**
 * Loads recipes that use the specified model and renders them in the tab.
 * @param {Object} options
 * @param {'lora'|'checkpoint'} options.modelKind - Model kind for copy and endpoint selection
 * @param {string} options.displayName - The display name of the model
 * @param {string} options.sha256 - The SHA256 hash of the model
 */
export function loadRecipesForModel({ modelKind, displayName, sha256 }) {
    const recipeTab = document.getElementById('recipes-tab');
    if (!recipeTab) return;

    const normalizedHash = sha256?.toLowerCase?.() || '';
    const modelLabel = getModelLabel(modelKind);

    // Show loading state
    recipeTab.innerHTML = `
        <div class="recipes-loading">
            <i class="fas fa-spinner fa-spin"></i> Loading recipes...
        </div>
    `;

    // Fetch recipes that use this model by hash
    fetch(`${getRecipesEndpoint(modelKind)}?hash=${encodeURIComponent(normalizedHash)}`)
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                throw new Error(data.error || 'Failed to load recipes');
            }

            renderRecipes(recipeTab, data.recipes, {
                modelKind,
                displayName,
                modelHash: normalizedHash,
                modelLabel,
            });
        })
        .catch(error => {
            console.error(`Error loading recipes for ${modelLabel}:`, error);
            recipeTab.innerHTML = `
                <div class="recipes-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Failed to load recipes. Please try again later.</p>
                </div>
            `;
        });
}

/**
 * Renders the recipe cards in the tab
 * @param {HTMLElement} tabElement - The tab element to render into
 * @param {Array} recipes - Array of recipe objects
 * @param {Object} options - Render options
 */
function renderRecipes(tabElement, recipes, options) {
    const {
        modelKind,
        displayName,
        modelHash,
        modelLabel,
    } = options;

    if (!recipes || recipes.length === 0) {
        tabElement.innerHTML = `
            <div class="recipes-empty">
                <i class="fas fa-book-open"></i>
                <p>No recipes found that use this ${modelLabel}.</p>
            </div>
        `;

        return;
    }

    const headerElement = document.createElement('div');
    headerElement.className = 'recipes-header';

    const headerText = document.createElement('div');
    headerText.className = 'recipes-header__text';

    const eyebrow = document.createElement('span');
    eyebrow.className = 'recipes-header__eyebrow';
    eyebrow.textContent = 'Linked recipes';
    headerText.appendChild(eyebrow);

    const title = document.createElement('h3');
    title.textContent = `${recipes.length} recipe${recipes.length > 1 ? 's' : ''} using this ${modelLabel}`;
    headerText.appendChild(title);

    const description = document.createElement('p');
    description.className = 'recipes-header__description';
    description.textContent = displayName ?
        `Discover workflows crafted for ${displayName}.` :
        'Discover workflows crafted for this model.';
    headerText.appendChild(description);

    headerElement.appendChild(headerText);

    const viewAllButton = document.createElement('button');
    viewAllButton.className = 'recipes-header__view-all';
    viewAllButton.type = 'button';
    viewAllButton.title = 'View all recipes in Recipes page';

    const viewAllIcon = document.createElement('i');
    viewAllIcon.className = 'fas fa-external-link-alt';
    viewAllIcon.setAttribute('aria-hidden', 'true');

    const viewAllLabel = document.createElement('span');
    viewAllLabel.textContent = 'View all recipes';

    viewAllButton.append(viewAllIcon, viewAllLabel);
    headerElement.appendChild(viewAllButton);

    viewAllButton.addEventListener('click', () => {
        navigateToRecipesPage({
            modelKind,
            displayName,
            modelHash,
        });
    });

    const cardGrid = document.createElement('div');
    cardGrid.className = 'card-grid recipes-card-grid';
    
    recipes.forEach(recipe => {
        const baseModel = recipe.base_model || '';
        const loras = recipe.loras || [];
        const lorasCount = loras.length;
        // Missing = still downloadable; unavailable = deleted from the source
        // or unresolvable hash, silently skipped when the recipe is used.
        const availableLorasCount = loras.filter(lora => lora.inLibrary).length;
        const missingLorasCount = loras.filter(lora => !lora.inLibrary && !lora.isDeleted && !lora.hashInvalid).length;
        const unavailableLorasCount = lorasCount - availableLorasCount - missingLorasCount;
        const statusClass = lorasCount === 0 ? 'empty'
            : (availableLorasCount === lorasCount ? 'ready'
            : (missingLorasCount > 0 ? 'missing'
            : (availableLorasCount > 0 ? 'partial' : 'unavailable')));
        let statusLabel;

        if (lorasCount === 0) {
            statusLabel = 'No linked LoRAs';
        } else if (statusClass === 'ready') {
            statusLabel = `${lorasCount} LoRA${lorasCount > 1 ? 's' : ''} ready`;
        } else if (statusClass === 'missing') {
            statusLabel = unavailableLorasCount > 0
                ? `Missing ${missingLorasCount}, ${unavailableLorasCount} of ${lorasCount} unavailable`
                : `Missing ${missingLorasCount} of ${lorasCount}`;
        } else if (statusClass === 'partial') {
            statusLabel = `${unavailableLorasCount} of ${lorasCount} unavailable - skipped when used`;
        } else {
            statusLabel = 'No usable LoRAs';
        }
        
        const imageUrl = recipe.file_url || 
                         (recipe.file_path ? `/loras_static/root1/preview/${recipe.file_path.split('/').pop()}` : 
                         '/loras_static/images/no-preview.png');

        const card = document.createElement('article');
        card.className = 'recipe-card';
        card.dataset.filePath = recipe.file_path || '';
        card.dataset.title = recipe.title || '';
        card.dataset.created = recipe.created_date || '';
        card.dataset.id = recipe.id || '';

        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', recipe.title ? `View recipe ${recipe.title}` : 'View recipe details');

        const media = document.createElement('div');
        media.className = 'recipe-card__media';

        const image = document.createElement('img');
        image.loading = 'lazy';
        image.src = imageUrl;
        image.alt = recipe.title ? `${recipe.title} preview` : 'Recipe preview';
        media.appendChild(image);

        const mediaTop = document.createElement('div');
        mediaTop.className = 'recipe-card__media-top';

        const copyButton = document.createElement('button');
        copyButton.className = 'recipe-card__copy';
        copyButton.type = 'button';
        copyButton.title = 'Copy recipe syntax';
        copyButton.setAttribute('aria-label', 'Copy recipe syntax');

        const copyIcon = document.createElement('i');
        copyIcon.className = 'fas fa-copy';
        copyIcon.setAttribute('aria-hidden', 'true');
        copyButton.appendChild(copyIcon);

        mediaTop.appendChild(copyButton);
        media.appendChild(mediaTop);

        const body = document.createElement('div');
        body.className = 'recipe-card__body';

        const titleElement = document.createElement('h4');
        titleElement.className = 'recipe-card__title';
        titleElement.textContent = recipe.title || 'Untitled recipe';
        titleElement.title = recipe.title || 'Untitled recipe';
        body.appendChild(titleElement);

        const meta = document.createElement('div');
        meta.className = 'recipe-card__meta';

        if (baseModel) {
            const baseBadge = document.createElement('span');
            baseBadge.className = 'recipe-card__badge recipe-card__badge--base';
            baseBadge.textContent = baseModel;
            baseBadge.title = baseModel;
            meta.appendChild(baseBadge);
        }

        const statusBadge = document.createElement('span');
        statusBadge.className = `recipe-card__badge recipe-card__badge--${statusClass}`;

        // Icon switches by state so status never relies on color alone.
        const statusIcons = {
            ready: 'fa-check',
            missing: 'fa-exclamation-triangle',
            partial: 'fa-circle-minus',
            unavailable: 'fa-ban',
            empty: 'fa-layer-group',
        };
        const statusIcon = document.createElement('i');
        statusIcon.className = `fas ${statusIcons[statusClass] || 'fa-layer-group'}`;
        statusIcon.setAttribute('aria-hidden', 'true');
        statusBadge.appendChild(statusIcon);

        const statusText = document.createElement('span');
        statusText.textContent = statusLabel;
        statusBadge.appendChild(statusText);

        statusBadge.title = getLoraStatusTitle(lorasCount, availableLorasCount, missingLorasCount, unavailableLorasCount);
        meta.appendChild(statusBadge);

        body.appendChild(meta);

        const cta = document.createElement('div');
        cta.className = 'recipe-card__cta';

        const ctaText = document.createElement('span');
        ctaText.textContent = 'View details';

        const ctaIcon = document.createElement('i');
        ctaIcon.className = 'fas fa-arrow-right';
        ctaIcon.setAttribute('aria-hidden', 'true');

        cta.append(ctaText, ctaIcon);
        body.appendChild(cta);

        copyButton.addEventListener('click', (event) => {
            event.stopPropagation();
            copyRecipeSyntax(recipe.id);
        });

        card.addEventListener('click', () => {
            navigateToRecipeDetails(recipe.id);
        });

        card.addEventListener('keydown', (event) => {
            if (event.target !== card) return;
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                navigateToRecipeDetails(recipe.id);
            }
        });

        card.append(media, body);
        cardGrid.appendChild(card);
    });
    
    // Clear loading indicator and append content
    tabElement.innerHTML = '';
    tabElement.appendChild(headerElement);
    tabElement.appendChild(cardGrid);
}

/**
 * Returns a descriptive title for the LoRA status indicator
 * @param {number} totalCount - Total number of LoRAs in recipe
 * @param {number} availableCount - Number of LoRAs present in the library
 * @param {number} missingCount - Number of missing LoRAs (still downloadable)
 * @param {number} unavailableCount - Number of unobtainable LoRAs (deleted
 *   from the source or unresolvable hash)
 * @returns {string} Status title text
 */
function getLoraStatusTitle(totalCount, availableCount, missingCount, unavailableCount) {
    if (totalCount === 0) return "No LoRAs in this recipe";
    if (availableCount === totalCount) return "All LoRAs available - Ready to use";
    if (missingCount > 0 && unavailableCount > 0) {
        return `${missingCount} of ${totalCount} LoRAs missing, ${unavailableCount} unavailable (deleted from source or unresolvable hash)`;
    }
    if (missingCount > 0) return `${missingCount} of ${totalCount} LoRAs missing`;
    if (availableCount > 0) {
        return `${unavailableCount} of ${totalCount} LoRAs unavailable (deleted from source or unresolvable hash) - skipped when recipe is used`;
    }
    return `No usable LoRAs - ${unavailableCount} of ${totalCount} deleted from source or unresolvable hash`;
}

/**
 * Copies recipe syntax to clipboard
 * @param {string} recipeId - The recipe ID
 */
function copyRecipeSyntax(recipeId) {
    if (!recipeId) {
        showToast('toast.recipes.noRecipeId', {}, 'error');
        return;
    }

    fetch(`/api/lm/recipe/${recipeId}/syntax`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.syntax) {
                return copyToClipboard(data.syntax, 'Recipe syntax copied to clipboard');
            } else {
                throw new Error(data.error || 'No syntax returned');
            }
        })
        .catch(err => {
            console.error('Failed to copy: ', err);
            showToast('toast.recipes.copyFailed', { message: err.message }, 'error');
        });
}

/**
 * Navigates to the recipes page with filter for the current model
 * @param {Object} options - Navigation options
 */
function navigateToRecipesPage({ modelKind, displayName, modelHash }) {
    // Close the current modal
    if (window.modalManager) {
        modalManager.closeModal('modelModal');
    }

    // Clear any previous filters first
    removeSessionItem('lora_to_recipe_filterLoraName');
    removeSessionItem('lora_to_recipe_filterLoraHash');
    removeSessionItem('checkpoint_to_recipe_filterCheckpointName');
    removeSessionItem('checkpoint_to_recipe_filterCheckpointHash');
    removeSessionItem('viewRecipeId');

    if (modelKind === 'checkpoint') {
        // Store the checkpoint name and hash filter in sessionStorage
        setSessionItem('checkpoint_to_recipe_filterCheckpointName', displayName);
        setSessionItem('checkpoint_to_recipe_filterCheckpointHash', modelHash);
    } else {
        // Store the LoRA name and hash filter in sessionStorage
        setSessionItem('lora_to_recipe_filterLoraName', displayName);
        setSessionItem('lora_to_recipe_filterLoraHash', modelHash);
    }

    // Directly navigate to recipes page
    window.location.href = '/loras/recipes';
}

/**
 * Navigates directly to a specific recipe's details
 * @param {string} recipeId - The recipe ID to view
 */
function navigateToRecipeDetails(recipeId) {
    // Close the current modal
    if (window.modalManager) {
        modalManager.closeModal('modelModal');
    }
    
    // Clear any previous filters first
    removeSessionItem('filterLoraName');
    removeSessionItem('filterLoraHash');
    removeSessionItem('viewRecipeId');
    
    // Store the recipe ID in sessionStorage to load on recipes page
    setSessionItem('viewRecipeId', recipeId);

    // Directly navigate to recipes page
    window.location.href = '/loras/recipes';
}

function getRecipesEndpoint(modelKind) {
    if (modelKind === 'checkpoint') {
        return '/api/lm/recipes/for-checkpoint';
    }
    return '/api/lm/recipes/for-lora';
}

function getModelLabel(modelKind) {
    return modelKind === 'checkpoint' ? 'checkpoint' : 'LoRA';
}
