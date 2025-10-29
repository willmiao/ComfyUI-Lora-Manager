import { BaseContextMenu } from './BaseContextMenu.js';
import { state } from '../../state/index.js';
import { bulkManager } from '../../managers/BulkManager.js';
import { updateElementText } from '../../utils/i18nHelpers.js';

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
    }

    updateSelectedCountHeader() {
        const headerElement = this.menu.querySelector('.bulk-context-header');
        if (headerElement) {
            updateElementText(headerElement, 'loras.bulkOperations.selected', { count: state.selectedModels.size });
        }
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
            case 'delete-all':
                bulkManager.showBulkDeleteModal();
                break;
            case 'clear':
                bulkManager.clearSelection();
                break;
            default:
                console.warn(`Unknown bulk action: ${action}`);
        }
    }
}
