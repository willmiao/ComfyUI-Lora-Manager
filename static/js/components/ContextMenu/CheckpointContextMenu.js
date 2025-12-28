import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { showDeleteModal, showExcludeModal } from '../../utils/modalUtils.js';
import { moveManager } from '../../managers/MoveManager.js';
import { i18n } from '../../i18n/index.js';

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

        // Update the "Move to other root" label based on current model type
        const moveOtherItem = this.menu.querySelector('[data-action="move-other"]');
        if (moveOtherItem) {
            const currentType = card.dataset.model_type || 'checkpoint';
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
            case 'refresh-metadata':
                // Refresh metadata from CivitAI
                apiClient.refreshSingleModelMetadata(this.currentCard.dataset.filepath);
                break;
            case 'move':
                moveManager.showMoveModal(this.currentCard.dataset.filepath, this.currentCard.dataset.model_type);
                break;
            case 'move-other':
                {
                    const currentType = this.currentCard.dataset.model_type || 'checkpoint';
                    const otherType = currentType === 'checkpoint' ? 'diffusion_model' : 'checkpoint';
                    moveManager.showMoveModal(this.currentCard.dataset.filepath, otherType);
                }
                break;
            case 'exclude':
                showExcludeModal(this.currentCard.dataset.filepath);
                break;
        }
    }
}

// Mix in shared methods
Object.assign(CheckpointContextMenu.prototype, ModelContextMenuMixin);
