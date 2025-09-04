import { BaseContextMenu } from './BaseContextMenu.js';
import { state } from '../../state/index.js';
import { bulkManager } from '../../managers/BulkManager.js';
import { translate, updateElementText } from '../../utils/i18nHelpers.js';
import { MODEL_TYPES } from '../../api/apiConfig.js';

export class BulkContextMenu extends BaseContextMenu {
    constructor() {
        super('bulkContextMenu', '.model-card.selected');
        this.setupBulkMenuItems();
    }

    init() {
        // Override parent init to handle bulk-specific context menu logic
        document.addEventListener('click', () => this.hideMenu());
        
        document.addEventListener('contextmenu', (e) => {
            const card = e.target.closest('.model-card');
            if (!card || !state.bulkMode) {
                this.hideMenu();
                return;
            }
            
            // Show bulk menu only if right-clicking on a selected card
            if (card.classList.contains('selected')) {
                e.preventDefault();
                this.showMenu(e.clientX, e.clientY, card);
            } else {
                this.hideMenu();
            }
        });

        // Handle menu item clicks
        this.menu.addEventListener('click', (e) => {
            const menuItem = e.target.closest('.context-menu-item');
            if (!menuItem || !this.currentCard) return;

            const action = menuItem.dataset.action;
            if (!action) return;
            
            this.handleMenuAction(action, menuItem);
            this.hideMenu();
        });
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
        const sendToWorkflowItem = this.menu.querySelector('[data-action="send-to-workflow"]');
        const copyAllItem = this.menu.querySelector('[data-action="copy-all"]');
        const refreshAllItem = this.menu.querySelector('[data-action="refresh-all"]');
        const moveAllItem = this.menu.querySelector('[data-action="move-all"]');
        const deleteAllItem = this.menu.querySelector('[data-action="delete-all"]');

        if (sendToWorkflowItem) {
            sendToWorkflowItem.style.display = config.sendToWorkflow ? 'flex' : 'none';
        }
        if (copyAllItem) {
            copyAllItem.style.display = config.copyAll ? 'flex' : 'none';
        }
        if (refreshAllItem) {
            refreshAllItem.style.display = config.refreshAll ? 'flex' : 'none';
        }
        if (moveAllItem) {
            moveAllItem.style.display = config.moveAll ? 'flex' : 'none';
        }
        if (deleteAllItem) {
            deleteAllItem.style.display = config.deleteAll ? 'flex' : 'none';
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
            case 'send-to-workflow':
                bulkManager.sendAllModelsToWorkflow();
                break;
            case 'copy-all':
                bulkManager.copyAllModelsSyntax();
                break;
            case 'refresh-all':
                bulkManager.refreshAllMetadata();
                break;
            case 'move-all':
                window.moveManager.showMoveModal('bulk');
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
