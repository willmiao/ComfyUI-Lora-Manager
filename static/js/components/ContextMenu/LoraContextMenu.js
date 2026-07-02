import { BaseContextMenu } from './BaseContextMenu.js';
import { ModelContextMenuMixin } from './ModelContextMenuMixin.js';
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
            case 'enrich-hf-agent':
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

        // Check if LLM is configured
        const configured = await agentManager.isLlmConfigured();
        if (!configured) {
            showToast('toast.agent.llmNotConfigured', {}, 'warning');
            return;
        }

        // Connect WebSocket for progress
        agentManager.connect();

        // Set up one-time completion handler
        const onComplete = (data) => {
            const idx = agentManager.completeCallbacks.indexOf(onComplete);
            if (idx >= 0) agentManager.completeCallbacks.splice(idx, 1);

            if (data.status === 'completed') {
                showToast('toast.agent.enrichComplete', { summary: data.summary || 'Done' }, 'success');
                // Soft reload to reflect updated metadata
                if (typeof resetAndReload === 'function') {
                    resetAndReload();
                }
            } else if (data.status === 'error') {
                showToast('toast.agent.enrichFailed', { error: data.error || 'Unknown error' }, 'error');
            }
        };
        agentManager.onComplete(onComplete);

        // Show progress toast
        showToast('toast.agent.enrichStarted', {}, 'info');

        try {
            await agentManager.executeSkill('enrich_hf_metadata', [filePath]);
        } catch (error) {
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
