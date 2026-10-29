import { MODEL_TYPES } from '../api/apiConfig.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { state } from '../state/index.js';
import { copyToClipboard, showToast } from './uiHelpers.js';
import { translate } from './i18nHelpers.js';
import { showConfirmationModal } from './modalUtils.js';

/**
 * Push a library workflow into the running ComfyUI graph (plugin mode only;
 * the backend rejects standalone mode since there is no graph to push into).
 * @param {string} filePath
 */
export async function sendWorkflowToComfy(filePath) {
    try {
        await getModelApiClient(MODEL_TYPES.WORKFLOW).sendToComfy(filePath);
        showToast('workflows.sendToComfy.success', {}, 'success');
    } catch (error) {
        console.error('Failed to send workflow to ComfyUI:', error);
        showToast('workflows.sendToComfy.failed', { message: error.message }, 'error');
    }
}

/**
 * Copy the extracted workflow document to the clipboard so the user can
 * paste it into ComfyUI (Ctrl+V) to load it. Works in standalone mode too.
 * @param {string} filePath
 */
export async function copyWorkflowToClipboard(filePath) {
    try {
        const workflow = await getModelApiClient(MODEL_TYPES.WORKFLOW).fetchWorkflowContent(filePath);
        await copyToClipboard(JSON.stringify(workflow));
    } catch (error) {
        console.error('Failed to copy workflow:', error);
        showToast('workflows.copyWorkflow.failed', { message: error.message }, 'error');
    }
}

/**
 * Ask the ComfyUI tab that has this workflow open (and edited) to write its
 * current graph back into the managed library document.
 * @param {string} filePath
 */
export async function updateWorkflowFromComfy(filePath) {
    try {
        const result = await getModelApiClient(MODEL_TYPES.WORKFLOW).updateFromComfy(filePath);
        showToast('workflows.updateFromComfy.success', {}, 'success');
        // Re-render the card in place: the scroller shows its shared
        // "Updated" cue and the item picks up the new document hash.
        const updateData = result && result.sha256 ? { sha256: result.sha256 } : {};
        state.virtualScroller?.updateSingleItem(filePath, updateData);
    } catch (error) {
        const kind = error.kind || 'unknown';
        if (kind === 'no_changes' || kind === 'cancelled') {
            const key = kind === 'no_changes' ? 'noChanges' : 'cancelled';
            showToast(`workflows.updateFromComfy.${key}`, {}, 'info');
        } else {
            console.error('Failed to update workflow from ComfyUI:', error);
            showToast('workflows.updateFromComfy.failed', { message: error.message }, 'error');
        }
    }
}

/**
 * Restore a workflow to its downloaded state, discarding local edits. Bare
 * .json artifacts are re-downloaded from the recorded CivitAI version;
 * container artifacts (.zip/images) are re-extracted from the pristine file.
 * @param {string} filePath
 */
export async function restoreWorkflow(filePath) {
    const confirmed = await showConfirmationModal({
        title: translate('workflows.restoreDownloaded.title', {}),
        message: translate('workflows.restoreDownloaded.message', {}),
        confirmText: translate('workflows.restoreDownloaded.confirmButton', {}),
        danger: true,
    });
    if (!confirmed) {
        return;
    }
    // .json restores re-download from CivitAI, which can take a moment; keep
    // a blocking indicator up so the wait does not look like a dead click.
    state.loadingManager?.showSimpleLoading(translate('workflows.restoreDownloaded.restoring', {}));
    try {
        const result = await getModelApiClient(MODEL_TYPES.WORKFLOW).restore(filePath);
        showToast('workflows.restoreDownloaded.success', {}, 'success');
        // Re-render the card in place: the scroller shows its shared
        // "Updated" cue and the item picks up the restored document hash.
        const updateData = result && result.sha256 ? { sha256: result.sha256 } : {};
        state.virtualScroller?.updateSingleItem(filePath, updateData);
    } catch (error) {
        console.error('Failed to restore workflow:', error);
        showToast('workflows.restoreDownloaded.failed', { message: error.message }, 'error');
    } finally {
        state.loadingManager?.hide();
    }
}
