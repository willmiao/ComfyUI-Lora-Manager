import { BaseModelApiClient } from './baseModelApi.js';

/**
 * Workflow-specific API client (ComfyUI workflow JSON resources)
 */
export class WorkflowApiClient extends BaseModelApiClient {
    /**
     * Push a library workflow into the running ComfyUI graph.
     * POST /api/lm/workflows/send-to-comfy { file_path }
     */
    async sendToComfy(filePath) {
        const response = await fetch(this.apiConfig.endpoints.specific.sendToComfy, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || `HTTP ${response.status}`);
        }
        return data;
    }

    /**
     * Fetch the extracted workflow document for a library entry.
     * GET /api/lm/workflows/content?file_path=... (works in standalone mode).
     * @returns {Promise<object>} The workflow JSON document.
     */
    async fetchWorkflowContent(filePath) {
        const url = `${this.apiConfig.endpoints.specific.content}?file_path=${encodeURIComponent(filePath)}`;
        const response = await fetch(url);
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || `HTTP ${response.status}`);
        }
        return data.workflow;
    }

    /**
     * List LM-managed workflows currently open in live ComfyUI tabs.
     * GET /api/lm/workflows/comfyui-state
     * @returns {Promise<Array>} [{client_id, file_path, sha256, dirty}, ...]
     */
    async fetchComfyuiState() {
        const response = await fetch(this.apiConfig.endpoints.specific.comfyuiState);
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || `HTTP ${response.status}`);
        }
        return data.states || [];
    }

    /**
     * Ask the ComfyUI tab holding this workflow to write its graph back.
     * POST /api/lm/workflows/update-from-comfy { file_path }
     * The request resolves with the write-back outcome; `error` carries the
     * failure kind ('not_open', 'no_changes', 'cancelled', 'timeout', ...).
     */
    async updateFromComfy(filePath) {
        const response = await fetch(this.apiConfig.endpoints.specific.updateFromComfy, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            const error = new Error(data.message || data.error || `HTTP ${response.status}`);
            error.kind = data.error || 'unknown';
            throw error;
        }
        return data;
    }

    /**
     * Restore a workflow to its downloaded state, discarding local edits.
     * POST /api/lm/workflows/restore { file_path }
     * `error` carries the failure kind ('no_source', 'download_failed', ...).
     */
    async restore(filePath) {
        const response = await fetch(this.apiConfig.endpoints.specific.restore, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            const error = new Error(data.message || data.error || `HTTP ${response.status}`);
            error.kind = data.error || 'unknown';
            throw error;
        }
        return data;
    }
}
