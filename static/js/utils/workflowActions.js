import { MODEL_TYPES } from '../api/apiConfig.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { copyToClipboard, showToast } from './uiHelpers.js';

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
