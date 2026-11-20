import { BaseModelApiClient } from './baseModelApi.js';

export class WildcardApiClient extends BaseModelApiClient {
    async activate(filePath, namespace = '', aliases = {}) {
        return this._activationRequest('activate', { file_path: filePath, namespace, aliases });
    }

    async deactivate(filePath) {
        return this._activationRequest('deactivate', { file_path: filePath });
    }

    async _activationRequest(action, body) {
        const response = await fetch(this.apiConfig.endpoints.specific[action], {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            const error = new Error(data.error || `HTTP ${response.status}`);
            error.payload = data;
            throw error;
        }
        return data;
    }

    async fetchSource(filePath, sourcePath) {
        const query = new URLSearchParams({ file_path: filePath, source_path: sourcePath });
        const response = await fetch(`${this.apiConfig.endpoints.specific.content}?${query}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
    }

    async fetchEntryValues(filePath, key) {
        const query = new URLSearchParams({ file_path: filePath, key, limit: 200 });
        const response = await fetch(`${this.apiConfig.endpoints.specific.entries}?${query}`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.error || `HTTP ${response.status}`);
        return data;
    }
}
