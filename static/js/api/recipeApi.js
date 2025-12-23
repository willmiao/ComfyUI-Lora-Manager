import { RecipeCard } from '../components/RecipeCard.js';
import { state, getCurrentPageState } from '../state/index.js';
import { showToast } from '../utils/uiHelpers.js';

const RECIPE_ENDPOINTS = {
    list: '/api/lm/recipes',
    detail: '/api/lm/recipe',
    scan: '/api/lm/recipes/scan',
    update: '/api/lm/recipe',
    roots: '/api/lm/recipes/roots',
    folders: '/api/lm/recipes/folders',
    folderTree: '/api/lm/recipes/folder-tree',
    unifiedFolderTree: '/api/lm/recipes/unified-folder-tree',
    move: '/api/lm/recipe/move',
    moveBulk: '/api/lm/recipes/move-bulk',
    bulkDelete: '/api/lm/recipes/bulk-delete',
};

const RECIPE_SIDEBAR_CONFIG = {
    config: {
        displayName: 'Recipe',
        supportsMove: true,
    },
    endpoints: RECIPE_ENDPOINTS,
};

export function extractRecipeId(filePath) {
    if (!filePath) return null;
    const basename = filePath.split('/').pop().split('\\').pop();
    const dotIndex = basename.lastIndexOf('.');
    return dotIndex > 0 ? basename.substring(0, dotIndex) : basename;
}

/**
 * Fetch recipes with pagination for virtual scrolling
 * @param {number} page - Page number to fetch
 * @param {number} pageSize - Number of items per page
 * @returns {Promise<Object>} Object containing items, total count, and pagination info
 */
export async function fetchRecipesPage(page = 1, pageSize = 100) {
    const pageState = getCurrentPageState();

    try {
        const params = new URLSearchParams({
            page: page,
            page_size: pageSize || pageState.pageSize || 20,
            sort_by: pageState.sortBy
        });

        if (pageState.showFavoritesOnly) {
            params.append('favorite', 'true');
        }

        if (pageState.activeFolder) {
            params.append('folder', pageState.activeFolder);
            params.append('recursive', pageState.searchOptions?.recursive !== false);
        } else if (pageState.searchOptions?.recursive !== undefined) {
            params.append('recursive', pageState.searchOptions.recursive);
        }

        // If we have a specific recipe ID to load
        if (pageState.customFilter?.active && pageState.customFilter?.recipeId) {
            // Special case: load specific recipe
            const response = await fetch(`${RECIPE_ENDPOINTS.detail}/${pageState.customFilter.recipeId}`);

            if (!response.ok) {
                throw new Error(`Failed to load recipe: ${response.statusText}`);
            }

            const recipe = await response.json();

            // Return in expected format
            return {
                items: [recipe],
                totalItems: 1,
                totalPages: 1,
                currentPage: 1,
                hasMore: false
            };
        }

        // Add custom filter for Lora if present
        if (pageState.customFilter?.active && pageState.customFilter?.loraHash) {
            params.append('lora_hash', pageState.customFilter.loraHash);
            params.append('bypass_filters', 'true');
        } else {
            // Normal filtering logic

            // Add search filter if present
            if (pageState.filters?.search) {
                params.append('search', pageState.filters.search);

                // Add search option parameters
                if (pageState.searchOptions) {
                    params.append('search_title', pageState.searchOptions.title.toString());
                    params.append('search_tags', pageState.searchOptions.tags.toString());
                    params.append('search_lora_name', pageState.searchOptions.loraName.toString());
                    params.append('search_lora_model', pageState.searchOptions.loraModel.toString());
                    params.append('fuzzy', 'true');
                }
            }

            // Add base model filters
            if (pageState.filters?.baseModel && pageState.filters.baseModel.length) {
                params.append('base_models', pageState.filters.baseModel.join(','));
            }

            // Add tag filters
            if (pageState.filters?.tags && Object.keys(pageState.filters.tags).length) {
                Object.entries(pageState.filters.tags).forEach(([tag, state]) => {
                    if (state === 'include') {
                        params.append('tag_include', tag);
                    } else if (state === 'exclude') {
                        params.append('tag_exclude', tag);
                    }
                });
            }
        }

        // Fetch recipes
        const response = await fetch(`${RECIPE_ENDPOINTS.list}?${params.toString()}`);

        if (!response.ok) {
            throw new Error(`Failed to load recipes: ${response.statusText}`);
        }

        const data = await response.json();

        return {
            items: data.items,
            totalItems: data.total,
            totalPages: data.total_pages,
            currentPage: page,
            hasMore: page < data.total_pages
        };
    } catch (error) {
        console.error('Error fetching recipes:', error);
        showToast('toast.recipes.fetchFailed', { message: error.message }, 'error');
        throw error;
    }
}

/**
 * Reset and reload models using virtual scrolling
 * @param {Object} options - Operation options
 * @returns {Promise<Object>} The fetch result
 */
export async function resetAndReloadWithVirtualScroll(options = {}) {
    const {
        modelType = 'lora',
        updateFolders = false,
        fetchPageFunction
    } = options;

    const pageState = getCurrentPageState();

    try {
        pageState.isLoading = true;

        // Reset page counter
        pageState.currentPage = 1;

        // Fetch the first page
        const result = await fetchPageFunction(1, pageState.pageSize || 50);

        // Update the virtual scroller
        state.virtualScroller.refreshWithData(
            result.items,
            result.totalItems,
            result.hasMore
        );

        // Update state
        pageState.hasMore = result.hasMore;
        pageState.currentPage = 2; // Next page will be 2

        return result;
    } catch (error) {
        console.error(`Error reloading ${modelType}s:`, error);
        showToast('toast.recipes.reloadFailed', { modelType: modelType, message: error.message }, 'error');
        throw error;
    } finally {
        pageState.isLoading = false;
    }
}

/**
 * Load more models using virtual scrolling
 * @param {Object} options - Operation options
 * @returns {Promise<Object>} The fetch result
 */
export async function loadMoreWithVirtualScroll(options = {}) {
    const {
        modelType = 'lora',
        resetPage = false,
        updateFolders = false,
        fetchPageFunction
    } = options;

    const pageState = getCurrentPageState();

    try {
        // Start loading state
        pageState.isLoading = true;

        // Reset to first page if requested
        if (resetPage) {
            pageState.currentPage = 1;
        }

        // Fetch the first page of data
        const result = await fetchPageFunction(pageState.currentPage, pageState.pageSize || 50);

        // Update virtual scroller with the new data
        state.virtualScroller.refreshWithData(
            result.items,
            result.totalItems,
            result.hasMore
        );

        // Update state
        pageState.hasMore = result.hasMore;
        pageState.currentPage = 2; // Next page to load would be 2

        return result;
    } catch (error) {
        console.error(`Error loading ${modelType}s:`, error);
        showToast('toast.recipes.loadFailed', { modelType: modelType, message: error.message }, 'error');
        throw error;
    } finally {
        pageState.isLoading = false;
    }
}

/**
 * Reset and reload recipes using virtual scrolling
 * @param {boolean} updateFolders - Whether to update folder tags
 * @returns {Promise<Object>} The fetch result
 */
export async function resetAndReload(updateFolders = false) {
    return resetAndReloadWithVirtualScroll({
        modelType: 'recipe',
        updateFolders,
        fetchPageFunction: fetchRecipesPage
    });
}

/**
 * Refreshes the recipe list by first rebuilding the cache and then loading recipes
 */
export async function refreshRecipes() {
    try {
        state.loadingManager.showSimpleLoading('Refreshing recipes...');

        // Call the API endpoint to rebuild the recipe cache
        const response = await fetch(RECIPE_ENDPOINTS.scan);

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to refresh recipe cache');
        }

        // After successful cache rebuild, reload the recipes
        await resetAndReload();

        showToast('toast.recipes.refreshComplete', {}, 'success');
    } catch (error) {
        console.error('Error refreshing recipes:', error);
        showToast('toast.recipes.refreshFailed', { message: error.message }, 'error');
    } finally {
        state.loadingManager.hide();
        state.loadingManager.restoreProgressBar();
    }
}

/**
 * Load more recipes with pagination - updated to work with VirtualScroller
 * @param {boolean} resetPage - Whether to reset to the first page
 * @returns {Promise<void>}
 */
export async function loadMoreRecipes(resetPage = false) {
    const pageState = getCurrentPageState();

    // Use virtual scroller if available
    if (state.virtualScroller) {
        return loadMoreWithVirtualScroll({
            modelType: 'recipe',
            resetPage,
            updateFolders: false,
            fetchPageFunction: fetchRecipesPage
        });
    }
}

/**
 * Create a recipe card instance from recipe data
 * @param {Object} recipe - Recipe data
 * @returns {HTMLElement} Recipe card DOM element
 */
export function createRecipeCard(recipe) {
    const recipeCard = new RecipeCard(recipe, (recipe) => {
        if (window.recipeManager) {
            window.recipeManager.showRecipeDetails(recipe);
        }
    });
    return recipeCard.element;
}

/**
 * Update recipe metadata on the server
 * @param {string} filePath - The file path of the recipe (e.g. D:/Workspace/ComfyUI/models/loras/recipes/86b4c335-ecfc-4791-89d2-3746e55a7614.webp)
 * @param {Object} updates - The metadata updates to apply
 * @returns {Promise<Object>} The updated recipe data
 */
export async function updateRecipeMetadata(filePath, updates) {
    try {
        state.loadingManager.showSimpleLoading('Saving metadata...');

        // Extract recipeId from filePath (basename without extension)
        const recipeId = extractRecipeId(filePath);
        if (!recipeId) {
            throw new Error('Unable to determine recipe ID');
        }

        const response = await fetch(`${RECIPE_ENDPOINTS.update}/${recipeId}/update`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(updates)
        });

        const data = await response.json();

        if (!data.success) {
            showToast('toast.recipes.updateFailed', { error: data.error }, 'error');
            throw new Error(data.error || 'Failed to update recipe');
        }

        state.virtualScroller.updateSingleItem(filePath, updates);

        return data;
    } catch (error) {
        console.error('Error updating recipe:', error);
        showToast('toast.recipes.updateError', { message: error.message }, 'error');
        throw error;
    } finally {
        state.loadingManager.hide();
    }
}

export class RecipeSidebarApiClient {
    constructor() {
        this.apiConfig = RECIPE_SIDEBAR_CONFIG;
    }

    async fetchUnifiedFolderTree() {
        const response = await fetch(this.apiConfig.endpoints.unifiedFolderTree);
        if (!response.ok) {
            throw new Error('Failed to fetch recipe folder tree');
        }
        return response.json();
    }

    async fetchModelRoots() {
        const response = await fetch(this.apiConfig.endpoints.roots);
        if (!response.ok) {
            throw new Error('Failed to fetch recipe roots');
        }
        return response.json();
    }

    async fetchModelFolders() {
        const response = await fetch(this.apiConfig.endpoints.folders);
        if (!response.ok) {
            throw new Error('Failed to fetch recipe folders');
        }
        return response.json();
    }

    async moveBulkModels(filePaths, targetPath) {
        if (!this.apiConfig.config.supportsMove) {
            showToast('toast.api.bulkMoveNotSupported', { type: this.apiConfig.config.displayName }, 'warning');
            return [];
        }

        const recipeIds = filePaths
            .map((path) => extractRecipeId(path))
            .filter((id) => !!id);

        if (recipeIds.length === 0) {
            showToast('toast.models.noModelsSelected', {}, 'warning');
            return [];
        }

        const response = await fetch(this.apiConfig.endpoints.moveBulk, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                recipe_ids: recipeIds,
                target_path: targetPath,
            }),
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || `Failed to move ${this.apiConfig.config.displayName}s`);
        }

        if (result.failure_count > 0) {
            showToast(
                'toast.api.bulkMovePartial',
                {
                    successCount: result.success_count,
                    type: this.apiConfig.config.displayName,
                    failureCount: result.failure_count,
                },
                'warning'
            );

            const failedFiles = (result.results || [])
                .filter((item) => !item.success)
                .map((item) => item.message || 'Unknown error');

            if (failedFiles.length > 0) {
                const failureMessage =
                    failedFiles.length <= 3
                        ? failedFiles.join('\n')
                        : `${failedFiles.slice(0, 3).join('\n')}\n(and ${failedFiles.length - 3} more)`;
                showToast('toast.api.bulkMoveFailures', { failures: failureMessage }, 'warning', 6000);
            }
        } else {
            showToast(
                'toast.api.bulkMoveSuccess',
                {
                    successCount: result.success_count,
                    type: this.apiConfig.config.displayName,
                },
                'success'
            );
        }

        return result.results || [];
    }

    async moveSingleModel(filePath, targetPath) {
        if (!this.apiConfig.config.supportsMove) {
            showToast('toast.api.moveNotSupported', { type: this.apiConfig.config.displayName }, 'warning');
            return null;
        }

        const recipeId = extractRecipeId(filePath);
        if (!recipeId) {
            showToast('toast.api.moveFailed', { message: 'Recipe ID missing' }, 'error');
            return null;
        }

        const response = await fetch(this.apiConfig.endpoints.move, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                recipe_id: recipeId,
                target_path: targetPath,
            }),
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || `Failed to move ${this.apiConfig.config.displayName}`);
        }

        if (result.message) {
            showToast('toast.api.moveInfo', { message: result.message }, 'info');
        } else {
            showToast('toast.api.moveSuccess', { type: this.apiConfig.config.displayName }, 'success');
        }

        return {
            original_file_path: result.original_file_path || filePath,
            new_file_path: result.new_file_path || filePath,
            folder: result.folder || '',
            message: result.message,
        };
    }

    async bulkDeleteModels(filePaths) {
        if (!filePaths || filePaths.length === 0) {
            throw new Error('No file paths provided');
        }

        const recipeIds = filePaths
            .map((path) => extractRecipeId(path))
            .filter((id) => !!id);

        if (recipeIds.length === 0) {
            throw new Error('No recipe IDs could be derived from file paths');
        }

        try {
            state.loadingManager?.showSimpleLoading('Deleting recipes...');

            const response = await fetch(this.apiConfig.endpoints.bulkDelete, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    recipe_ids: recipeIds,
                }),
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Failed to delete recipes');
            }

            return {
                success: true,
                deleted_count: result.total_deleted,
                failed_count: result.total_failed || 0,
                errors: result.failed || [],
            };
        } finally {
            state.loadingManager?.hide();
        }
    }
}
