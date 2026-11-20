import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { moveManager } from '../../managers/MoveManager.js';
import { showDeleteModal } from '../../utils/modalUtils.js';
import { deactivateWildcard, openWildcardModel } from '../../utils/wildcardActions.js';
import { translate } from '../../utils/i18nHelpers.js';

export class WildcardContextMenu extends BaseContextMenu {
    constructor() {
        super('wildcardContextMenu', '.model-card');
        this.nsfwSelector = document.getElementById('nsfwLevelSelector');
        this.modelType = 'wildcards';
        this.initNSFWSelector();
    }

    async saveModelMetadata(filePath, data) {
        return getModelApiClient().saveModelMetadata(filePath, data);
    }

    prepareMenu(card) {
        this.updateExcludeMenuItem();
        const active = card.dataset.active === 'true';
        const label = this.menu?.querySelector('[data-active-label]');
        if (label) {
            label.textContent = translate(
                active ? 'wildcards.actions.deactivate' : 'wildcards.actions.activateWithOptions',
                {},
                active ? 'Deactivate' : 'Activate…',
            );
        }
    }

    handleMenuAction(action) {
        if (ModelContextMenuMixin.handleCommonMenuActions.call(this, action)) return;
        const filePath = this.currentCard.dataset.filepath;
        const apiClient = getModelApiClient();
        switch (action) {
            case 'wildcard-details':
                openWildcardModel(filePath, { openWildcardsTab: true });
                break;
            case 'toggle-active':
                if (this.currentCard.dataset.active === 'true') deactivateWildcard(filePath);
                else openWildcardModel(filePath, { openWildcardsTab: true });
                break;
            case 'replace-preview':
                apiClient.replaceModelPreview(filePath);
                break;
            case 'delete':
                showDeleteModal(filePath);
                break;
            case 'refresh-metadata':
                apiClient.refreshSingleModelMetadata(filePath);
                break;
            case 'move':
                moveManager.showMoveModal(filePath);
                break;
        }
    }
}

Object.assign(WildcardContextMenu.prototype, ModelContextMenuMixin);
