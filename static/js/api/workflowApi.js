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
}
