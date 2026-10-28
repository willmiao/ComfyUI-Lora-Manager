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
}
