import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { showDeleteModal, showExcludeModal } from '../../utils/modalUtils.js';
import { moveManager } from '../../managers/MoveManager.js';
import { i18n } from '../../i18n/index.js';
import { sendModelPathToWorkflow } from '../../utils/uiHelpers.js';
import { MODEL_TYPES } from '../../api/apiConfig.js';

export class CheckpointContextMenu extends BaseContextMenu {
    constructor() {
        super('checkpointContextMenu', '.model-card');
        this.nsfwSelector = document.getElementById('nsfwLevelSelector');
        this.modelType = 'checkpoint';
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

        // Update the "Move to other root" label based on current model type
        const moveOtherItem = this.menu.querySelector('[data-action="move-other"]');
        if (moveOtherItem) {
            const currentType = card.dataset.sub_type || 'checkpoint';
            const otherType = currentType === 'checkpoint' ? 'diffusion_model' : 'checkpoint';
            const typeLabel = i18n.t(`checkpoints.modelTypes.${otherType}`);
            moveOtherItem.innerHTML = `<i class="fas fa-exchange-alt"></i> ${i18n.t('checkpoints.contextMenu.moveToOtherTypeFolder', { otherType: typeLabel })}`;
        }
    }

    handleMenuAction(action) {
        // First try to handle with common actions
        if (ModelContextMenuMixin.handleCommonMenuActions.call(this, action)) {
            return;
        }

        const apiClient = getModelApiClient();

        // Otherwise handle checkpoint-specific actions
        switch (action) {
            case 'details':
                // Show checkpoint details
                this.currentCard.click();
                break;
            case 'replace-preview':
                // Add new action for replacing preview images
                apiClient.replaceModelPreview(this.currentCard.dataset.filepath);
                break;
            case 'delete':
                showDeleteModal(this.currentCard.dataset.filepath);
                break;
            case 'copyname':
                // Copy checkpoint name
                if (this.currentCard.querySelector('.fa-copy')) {
                    this.currentCard.querySelector('.fa-copy').click();
                }
                break;
            case 'sendworkflow':
                // Send checkpoint to workflow (always replace mode)
                this.sendCheckpointToWorkflow();
                break;
            case 'refresh-metadata':
                // Refresh metadata from CivitAI
                apiClient.refreshSingleModelMetadata(this.currentCard.dataset.filepath);
                break;
            case 'move':
                moveManager.showMoveModal(this.currentCard.dataset.filepath, this.currentCard.dataset.sub_type);
                break;
            case 'move-other':
                {
                    const currentType = this.currentCard.dataset.sub_type || 'checkpoint';
                    const otherType = currentType === 'checkpoint' ? 'diffusion_model' : 'checkpoint';
                    moveManager.showMoveModal(this.currentCard.dataset.filepath, otherType);
                }
                break;
            case 'exclude':
                showExcludeModal(this.currentCard.dataset.filepath);
                break;
            case 'restore':
                this.restoreExcludedModel(this.currentCard.dataset.filepath);
                break;
        }
    }

    async sendCheckpointToWorkflow() {
        const modelPath = this.currentCard.dataset.filepath;
        if (!modelPath) {
            return;
        }

        const subtype = (this.currentCard.dataset.sub_type || 'checkpoint').toLowerCase();
        const isDiffusionModel = subtype === 'diffusion_model';
        const widgetName = isDiffusionModel ? 'unet_name' : 'ckpt_name';
        const actionTypeText = i18n.t(
            isDiffusionModel ? 'uiHelpers.nodeSelector.diffusionModel' : 'uiHelpers.nodeSelector.checkpoint',
            {},
            isDiffusionModel ? 'Diffusion Model' : 'Checkpoint'
        );
        const successMessage = i18n.t(
            'uiHelpers.workflow.modelUpdated',
            {},
            'Model updated in workflow'
        );
        const failureMessage = i18n.t(
            'uiHelpers.workflow.modelFailed',
            {},
            'Failed to update model node'
        );
        const missingNodesMessage = i18n.t(
            'uiHelpers.workflow.noMatchingNodes',
            {},
            'No compatible nodes available in the current workflow'
        );
        const missingTargetMessage = i18n.t(
            'uiHelpers.workflow.noTargetNodeSelected',
            {},
            'No target node selected'
        );

        await sendModelPathToWorkflow(modelPath, {
            widgetName,
            collectionType: MODEL_TYPES.CHECKPOINT,
            actionTypeText,
            successMessage,
            failureMessage,
            missingNodesMessage,
            missingTargetMessage,
        });
    }
}

// Mix in shared methods
Object.assign(CheckpointContextMenu.prototype, ModelContextMenuMixin);
