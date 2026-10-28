import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { moveManager } from '../../managers/MoveManager.js';
import { showDeleteModal, showExcludeModal } from '../../utils/modalUtils.js';
import { copyToClipboard, showToast } from '../../utils/uiHelpers.js';
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

    showMenu(x, y, card) {
        super.showMenu(x, y, card);
        this.updateExcludeMenuItem();
        // Standalone has no running ComfyUI to push a workflow into; the
        // copy-to-clipboard action covers that mode instead.
        const sendItem = this.menu?.querySelector('[data-action="send-to-comfy"]');
        if (sendItem) {
            sendItem.style.display = state?.global?.settings?.standalone_mode ? 'none' : '';
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
                this.sendToComfy(this.currentCard.dataset.filepath);
                break;
            case 'copy-workflow':
                this.copyWorkflowToClipboard(this.currentCard.dataset.filepath);
                break;
            case 'replace-preview':
                // Add new action for replacing preview images
                apiClient.replaceModelPreview(this.currentCard.dataset.filepath);
                break;
            case 'delete':
                showDeleteModal(this.currentCard.dataset.filepath);
                break;
            case 'copyname':
                // Copy workflow name
                if (this.currentCard.querySelector('.fa-copy')) {
                    this.currentCard.querySelector('.fa-copy').click();
                }
                break;
            case 'refresh-metadata':
                // Refresh metadata from CivitAI
                apiClient.refreshSingleModelMetadata(this.currentCard.dataset.filepath);
                break;
            case 'move':
                moveManager.showMoveModal(this.currentCard.dataset.filepath);
                break;
            case 'exclude':
                showExcludeModal(this.currentCard.dataset.filepath);
                break;
            case 'restore':
                this.restoreExcludedModel(this.currentCard.dataset.filepath);
                break;
        }
    }

    async sendToComfy(filePath) {
        try {
            await getModelApiClient().sendToComfy(filePath);
            showToast('workflows.sendToComfy.success', {}, 'success');
        } catch (error) {
            console.error('Failed to send workflow to ComfyUI:', error);
            showToast('workflows.sendToComfy.failed', { message: error.message }, 'error');
        }
    }

    async copyWorkflowToClipboard(filePath) {
        try {
            const workflow = await getModelApiClient().fetchWorkflowContent(filePath);
            await copyToClipboard(JSON.stringify(workflow));
        } catch (error) {
            console.error('Failed to copy workflow:', error);
            showToast('workflows.copyWorkflow.failed', { message: error.message }, 'error');
        }
    }
}

// Mix in shared methods
Object.assign(WorkflowContextMenu.prototype, ModelContextMenuMixin);
