import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
import { state } from '../../state/index.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { copyLoraSyntax, sendLoraToWorkflow, buildLoraSyntax, showToast } from '../../utils/uiHelpers.js';
import { showExcludeModal, showDeleteModal } from '../../utils/modalUtils.js';
import { moveManager } from '../../managers/MoveManager.js';

export class LoraContextMenu extends BaseContextMenu {
    constructor() {
        super('loraContextMenu', '.model-card');
        this.nsfwSelector = document.getElementById('nsfwLevelSelector');
        this.modelType = 'lora';
        this.resetAndReload = resetAndReload;
        
        this.initNSFWSelector();
    }

    // Use the saveModelMetadata implementation from loraApi
    async saveModelMetadata(filePath, data) {
        return getModelApiClient().saveModelMetadata(filePath, data);
    }

    showMenu(x, y, card) {
        super.showMenu(x, y, card);
        this.updateExcludeMenuItem();
    }

    handleMenuAction(action, menuItem) {
        // First try to handle with common actions
        if (ModelContextMenuMixin.handleCommonMenuActions.call(this, action)) {
            return;
        }

        // Otherwise handle lora-specific actions
        switch(action) {
            case 'detail':
                // Trigger the main card click which shows the modal
                this.currentCard.click();
                break;
            case 'copyname':
                // Generate and copy LoRA syntax
                copyLoraSyntax(this.currentCard);
                break;
            case 'sendappend':
                // Send LoRA to workflow (append mode)
                this.sendLoraToWorkflow(false);
                break;
            case 'sendreplace':
                // Send LoRA to workflow (replace mode)
                this.sendLoraToWorkflow(true);
                break;
            case 'replace-preview':
                // Add a new action for replacing preview images
                getModelApiClient().replaceModelPreview(this.currentCard.dataset.filepath);
                break;
            case 'delete':
                // Call showDeleteModal directly instead of clicking the trash button
                showDeleteModal(this.currentCard.dataset.filepath);
                break;
            case 'move':
                moveManager.showMoveModal(this.currentCard.dataset.filepath);
                break;
            case 'refresh-metadata':
                getModelApiClient().refreshSingleModelMetadata(this.currentCard.dataset.filepath);
                break;
            case 'enrich-hf-llm':
                this.enrichWithAgent(this.currentCard.dataset.filepath);
                break;
            case 'exclude':
                showExcludeModal(this.currentCard.dataset.filepath);
                break;
            case 'restore':
                this.restoreExcludedModel(this.currentCard.dataset.filepath);
                break;
        }
    }

    async enrichWithAgent(filePath) {
        const { agentManager } = await import('../../managers/AgentManager.js');

        const configured = await agentManager.isLlmConfigured();
        if (!configured) {
            showToast('toast.agent.llmNotConfigured', {}, 'warning');
            return;
        }

        agentManager.connect();

        const progressUI = state.loadingManager.showEnhancedProgress(
            'Enriching metadata with AI...'
        );

        const onProgress = (data) => {
            if (data.status === 'processing' && data.current_path && data.updated_data && Object.keys(data.updated_data).length > 0) {
                if (state.virtualScroller?.updateSingleItem) {
                    state.virtualScroller.updateSingleItem(data.current_path, data.updated_data);
                }
                const pct = data.total > 0 ? Math.floor((data.processed / data.total) * 100) : 0;
                const name = data.current_path.split('/').pop();
                progressUI.updateProgress(pct, name, `Processing ${name}`);
            }
        };
        agentManager.onProgress(onProgress);

        const onComplete = (data) => {
            const pIdx = agentManager.progressCallbacks.indexOf(onProgress);
            if (pIdx >= 0) agentManager.progressCallbacks.splice(pIdx, 1);
            const cIdx = agentManager.completeCallbacks.indexOf(onComplete);
            if (cIdx >= 0) agentManager.completeCallbacks.splice(cIdx, 1);

            if (data.status === 'completed') {
                progressUI.complete(data.summary || 'Enrich complete');
                showToast('toast.agent.enrichComplete', { summary: data.summary || 'Done' }, 'success');
            } else if (data.status === 'error') {
                state.loadingManager.hide();
                showToast('toast.agent.enrichFailed', { error: data.error || 'Unknown error' }, 'error');
            }
        };
        agentManager.onComplete(onComplete);

        try {
            await agentManager.executeSkill('enrich_hf_metadata', [filePath]);
        } catch (error) {
            const pIdx = agentManager.progressCallbacks.indexOf(onProgress);
            if (pIdx >= 0) agentManager.progressCallbacks.splice(pIdx, 1);
            const cIdx = agentManager.completeCallbacks.indexOf(onComplete);
            if (cIdx >= 0) agentManager.completeCallbacks.splice(cIdx, 1);
            state.loadingManager.hide();
            showToast('toast.agent.enrichFailed', { error: error.message }, 'error');
        }
    }

    sendLoraToWorkflow(replaceMode) {
        const card = this.currentCard;
        const usageTips = JSON.parse(card.dataset.usage_tips || '{}');
        const loraSyntax = buildLoraSyntax(card.dataset.file_name, usageTips);

        sendLoraToWorkflow(loraSyntax, replaceMode, 'lora');
    }
}

// Mix in shared methods
Object.assign(LoraContextMenu.prototype, ModelContextMenuMixin);
