import { BaseContextMenu } from './BaseContextMenu.js';
import { state } from '../../state/index.js';
import { bulkManager } from '../../managers/BulkManager.js';
import { updateElementText, translate } from '../../utils/i18nHelpers.js';
import { bulkMissingLoraDownloadManager } from '../../managers/BulkMissingLoraDownloadManager.js';
import { showToast } from '../../utils/uiHelpers.js';

export class BulkContextMenu extends BaseContextMenu {
    constructor() {
        super('bulkContextMenu', '.model-card.selected');
        this.setupBulkMenuItems();
    }

    setupBulkMenuItems() {
        if (!this.menu) return;

        // Update menu items visibility based on current model type
        this.updateMenuItemsForModelType();
        
        // Update selected count in header
        this.updateSelectedCountHeader();
    }

    updateMenuItemsForModelType() {
        const currentModelType = state.currentPageType;
        const config = bulkManager.actionConfig[currentModelType];
        
        if (!config) return;

        // Update button visibility based on model type
        const addTagsItem = this.menu.querySelector('[data-action="add-tags"]');
        const setBaseModelItem = this.menu.querySelector('[data-action="set-base-model"]');
        const setContentRatingItem = this.menu.querySelector('[data-action="set-content-rating"]');
        const sendToWorkflowAppendItem = this.menu.querySelector('[data-action="send-to-workflow-append"]');
        const sendToWorkflowReplaceItem = this.menu.querySelector('[data-action="send-to-workflow-replace"]');
        const copyAllItem = this.menu.querySelector('[data-action="copy-all"]');
        const refreshAllItem = this.menu.querySelector('[data-action="refresh-all"]');
        const checkUpdatesItem = this.menu.querySelector('[data-action="check-updates"]');
        const moveAllItem = this.menu.querySelector('[data-action="move-all"]');
        const autoOrganizeItem = this.menu.querySelector('[data-action="auto-organize"]');
        const deleteAllItem = this.menu.querySelector('[data-action="delete-all"]');
        const downloadMissingLorasItem = this.menu.querySelector('[data-action="download-missing-loras"]');

        if (sendToWorkflowAppendItem) {
            sendToWorkflowAppendItem.style.display = config.sendToWorkflow ? 'flex' : 'none';
        }
        if (sendToWorkflowReplaceItem) {
            sendToWorkflowReplaceItem.style.display = config.sendToWorkflow ? 'flex' : 'none';
        }
        if (copyAllItem) {
            copyAllItem.style.display = config.copyAll ? 'flex' : 'none';
        }
        if (refreshAllItem) {
            refreshAllItem.style.display = config.refreshAll ? 'flex' : 'none';
        }
        if (checkUpdatesItem) {
            checkUpdatesItem.style.display = config.checkUpdates ? 'flex' : 'none';
        }
        if (moveAllItem) {
            moveAllItem.style.display = config.moveAll ? 'flex' : 'none';
        }
        if (autoOrganizeItem) {
            autoOrganizeItem.style.display = config.autoOrganize ? 'flex' : 'none';
        }
        if (deleteAllItem) {
            deleteAllItem.style.display = config.deleteAll ? 'flex' : 'none';
        }
        if (addTagsItem) {
            addTagsItem.style.display = config.addTags ? 'flex' : 'none';
        }
        if (setBaseModelItem) {
            setBaseModelItem.style.display = 'flex'; // Base model editing is available for all model types
        }
        if (setContentRatingItem) {
            setContentRatingItem.style.display = config.setContentRating ? 'flex' : 'none';
        }

        const setFavoriteItem = this.menu.querySelector('[data-action="set-favorite"]');

        if (setFavoriteItem && config.setFavorite) {
            setFavoriteItem.style.display = 'flex';

            const total = state.selectedModels.size;
            const favoritedCount = this.countFavoritedInSelection();
            const allFavorited = total > 0 && favoritedCount === total;

            const icon = setFavoriteItem.querySelector('i');
            const label = setFavoriteItem.querySelector('span');

            if (allFavorited) {
                if (icon) { icon.className = 'far fa-star'; }
                if (label) { label.textContent = translate('loras.bulkOperations.unfavorite'); }
            } else {
                if (icon) { icon.className = 'fas fa-star'; }
                if (label) {
                    label.textContent = favoritedCount > 0
                        ? translate('loras.bulkOperations.setFavoriteCount', { favorited: favoritedCount, total })
                        : translate('loras.bulkOperations.setFavorite');
                }
            }
        } else if (setFavoriteItem) {
            setFavoriteItem.style.display = 'none';
        }

        if (downloadMissingLorasItem) {
            // Only show for recipes page
            downloadMissingLorasItem.style.display = currentModelType === 'recipes' ? 'flex' : 'none';
        }

        const skipMetadataRefreshItem = this.menu.querySelector('[data-action="skip-metadata-refresh"]');
        const resumeMetadataRefreshItem = this.menu.querySelector('[data-action="resume-metadata-refresh"]');

        if (skipMetadataRefreshItem && resumeMetadataRefreshItem) {
            const skipCount = this.countSkipStatus(true);
            const resumeCount = this.countSkipStatus(false);
            const totalCount = skipCount + resumeCount;

            if (skipCount === totalCount) {
                skipMetadataRefreshItem.style.display = 'none';
                resumeMetadataRefreshItem.style.display = 'flex';
                resumeMetadataRefreshItem.querySelector('span').textContent = translate(
                    'loras.bulkOperations.resumeMetadataRefresh'
                );
            } else if (resumeCount === totalCount) {
                skipMetadataRefreshItem.style.display = 'flex';
                resumeMetadataRefreshItem.style.display = 'none';
                skipMetadataRefreshItem.querySelector('span').textContent = translate(
                    'loras.bulkOperations.skipMetadataRefresh'
                );
            } else {
                skipMetadataRefreshItem.style.display = 'flex';
                resumeMetadataRefreshItem.style.display = 'flex';
                skipMetadataRefreshItem.querySelector('span').textContent = translate(
                    'loras.bulkOperations.skipMetadataRefreshCount',
                    { count: resumeCount }
                );
                resumeMetadataRefreshItem.querySelector('span').textContent = translate(
                    'loras.bulkOperations.resumeMetadataRefreshCount',
                    { count: skipCount }
                );
            }
        }
    }

    updateSelectedCountHeader() {
        const headerElement = this.menu.querySelector('.bulk-context-header');
        if (headerElement) {
            updateElementText(headerElement, 'loras.bulkOperations.selected', { count: state.selectedModels.size });
        }
    }

    countSkipStatus(skipState) {
        let count = 0;
        for (const filePath of state.selectedModels) {
            const escapedPath = window.CSS && typeof window.CSS.escape === 'function'
                ? window.CSS.escape(filePath)
                : filePath.replace(/["\\]/g, '\\$&');
            const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
            if (card) {
                const isSkipped = card.dataset.skip_metadata_refresh === 'true';
                if (isSkipped === skipState) {
                    count++;
                }
            }
        }
        return count;
    }

    countFavoritedInSelection() {
        let count = 0;
        for (const filePath of state.selectedModels) {
            const escapedPath = window.CSS && typeof window.CSS.escape === 'function'
                ? window.CSS.escape(filePath)
                : filePath.replace(/["\\]/g, '\\$&');
            const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
            if (card && card.dataset.favorite === 'true') {
                count++;
            }
        }
        return count;
    }

    showMenu(x, y, card) {
        this.updateMenuItemsForModelType();
        this.updateSelectedCountHeader();
        super.showMenu(x, y, card);
    }

    handleMenuAction(action, menuItem) {
        switch (action) {
            case 'add-tags':
                bulkManager.showBulkAddTagsModal();
                break;
            case 'set-base-model':
                bulkManager.showBulkBaseModelModal();
                break;
            case 'set-content-rating':
                bulkManager.showBulkContentRatingSelector();
                break;
            case 'send-to-workflow-append':
                bulkManager.sendAllModelsToWorkflow(false);
                break;
            case 'send-to-workflow-replace':
                bulkManager.sendAllModelsToWorkflow(true);
                break;
            case 'copy-all':
                bulkManager.copyAllModelsSyntax();
                break;
            case 'refresh-all':
                bulkManager.refreshAllMetadata();
                break;
            case 'check-updates':
                bulkManager.checkUpdatesForSelectedModels();
                break;
            case 'move-all':
                window.moveManager.showMoveModal('bulk');
                break;
            case 'auto-organize':
                bulkManager.autoOrganizeSelectedModels();
                break;
            case 'skip-metadata-refresh':
                bulkManager.setSkipMetadataRefresh(true);
                break;
            case 'resume-metadata-refresh':
                bulkManager.setSkipMetadataRefresh(false);
                break;
            case 'delete-all':
                bulkManager.showBulkDeleteModal();
                break;
            case 'set-favorite': {
                const allFavorited = this.countFavoritedInSelection() === state.selectedModels.size;
                bulkManager.setBulkFavorites(!allFavorited);
                break;
            }
            case 'download-missing-loras':
                this.handleDownloadMissingLoras();
                break;
            case 'clear':
                bulkManager.clearSelection();
                break;
            default:
                console.warn(`Unknown bulk action: ${action}`);
        }
    }

    /**
     * Handle downloading missing LoRAs for selected recipes
     */
    async handleDownloadMissingLoras() {
        if (state.selectedModels.size === 0) {
            return;
        }

        // Get selected recipes from the virtual scroller
        const selectedRecipes = [];
        state.selectedModels.forEach(filePath => {
            const card = document.querySelector(`.model-card[data-filepath="${CSS.escape(filePath)}"]`);
            if (card && card.recipeData) {
                selectedRecipes.push(card.recipeData);
            }
        });

        if (selectedRecipes.length === 0) {
            // Try to get recipes from virtual scroller state
            const items = state.virtualScroller?.items || [];
            items.forEach(recipe => {
                if (recipe.file_path && state.selectedModels.has(recipe.file_path)) {
                    selectedRecipes.push(recipe);
                }
            });
        }

        if (selectedRecipes.length === 0) {
            showToast('toast.recipes.noRecipesSelected', {}, 'warning');
            return;
        }

        await bulkMissingLoraDownloadManager.downloadMissingLoras(selectedRecipes);
    }
}
