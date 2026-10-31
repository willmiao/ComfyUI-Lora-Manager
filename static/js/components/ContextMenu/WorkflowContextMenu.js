import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { moveManager } from '../../managers/MoveManager.js';
import { showDeleteModal } from '../../utils/modalUtils.js';
import { copyWorkflowToClipboard, restoreWorkflow, sendWorkflowToComfy, updateWorkflowFromComfy } from '../../utils/workflowActions.js';
import { state } from '../../state/index.js';

export class WorkflowContextMenu extends BaseContextMenu {
    constructor() {
        super('workflowContextMenu', '.model-card');
        this.nsfwSelector = document.getElementById('nsfwLevelSelector');
        this.modelType = 'workflows';
        this.resetAndReload = resetAndReload;

        this.initNSFWSelector();
    }

    // Implementation needed by the mixin
    async saveModelMetadata(filePath, data) {
        return getModelApiClient().saveModelMetadata(filePath, data);
    }

    prepareMenu(card) {
        // Standalone has no running ComfyUI to push a workflow into; the
        // copy-to-clipboard action covers that mode instead.
        const sendItem = this.menu?.querySelector('[data-action="send-to-comfy"]');
        const updateItem = this.menu?.querySelector('[data-action="update-from-comfy"]');
        const standalone = state?.global?.settings?.standalone_mode;
        if (sendItem) {
            sendItem.style.display = standalone ? 'none' : '';
        }
        if (updateItem) {
            if (standalone) {
                updateItem.style.display = 'none';
            } else {
                updateItem.style.display = '';
                this._refreshUpdateFromComfyItem(card, updateItem);
            }
        }
        const restoreItem = this.menu?.querySelector('[data-action="restore-download"]');
        if (restoreItem) {
            restoreItem.classList.toggle('disabled', !this._isRestorable(card));
        }
    }

    /**
     * Restore is available for container artifacts (re-extracted locally from
     * the pristine archive) and for CivitAI-sourced .json artifacts
     * (re-downloaded from the recorded version). Local-only .json files have
     * no restore source; when the item is not in the loaded window we stay
     * enabled and let the backend report "no_source".
     */
    _isRestorable(card) {
        const filePath = card?.dataset?.filepath;
        if (!filePath) return false;
        if (!filePath.toLowerCase().endsWith('.json')) return true;
        const item = state.virtualScroller?.items?.find((entry) => entry.file_path === filePath);
        return item ? !!item.from_civitai : true;
    }

    /**
     * Enable "Update from ComfyUI" only when this workflow is the active
     * graph in a connected ComfyUI tab and carries unsaved edits. The state
     * is pushed by the ComfyUI-side extension; the item starts disabled and
     * flips when the answer arrives while the menu is still open.
     */
    async _refreshUpdateFromComfyItem(card, item) {
        item.classList.add('disabled');
        const filePath = card?.dataset?.filepath;
        if (!filePath) return;
        try {
            const states = await getModelApiClient().fetchComfyuiState();
            // Menu may have been closed/re-opened for another card meanwhile.
            if (this.currentCard !== card) return;
            const linked = states.some(
                (entry) => entry.file_path === filePath && entry.dirty
            );
            item.classList.toggle('disabled', !linked);
        } catch (_error) {
            // State endpoint unavailable (older backend): keep disabled.
        }
    }

    handleMenuAction(action) {
        // First try to handle with common actions
        if (ModelContextMenuMixin.handleCommonMenuActions.call(this, action)) {
            return;
        }

        const apiClient = getModelApiClient();

        // Otherwise handle workflow-specific actions
        switch(action) {
            case 'details':
                // Show workflow details
                this.currentCard.click();
                break;
            case 'send-to-comfy':
                sendWorkflowToComfy(this.currentCard.dataset.filepath);
                break;
            case 'update-from-comfy':
                updateWorkflowFromComfy(this.currentCard.dataset.filepath);
                break;
            case 'copy-workflow':
                copyWorkflowToClipboard(this.currentCard.dataset.filepath);
                break;
            case 'restore-download':
                restoreWorkflow(this.currentCard.dataset.filepath);
                break;
            case 'replace-preview':
                // Add new action for replacing preview images
                apiClient.replaceModelPreview(this.currentCard.dataset.filepath);
                break;
            case 'delete':
                showDeleteModal(this.currentCard.dataset.filepath);
                break;
            case 'refresh-metadata':
                // Refresh metadata from CivitAI
                apiClient.refreshSingleModelMetadata(this.currentCard.dataset.filepath);
                break;
            case 'move':
                moveManager.showMoveModal(this.currentCard.dataset.filepath);
                break;
        }
    }

    async sendToComfy(filePath) {
        await sendWorkflowToComfy(filePath);
    }
}

// Mix in shared methods
Object.assign(WorkflowContextMenu.prototype, ModelContextMenuMixin);
