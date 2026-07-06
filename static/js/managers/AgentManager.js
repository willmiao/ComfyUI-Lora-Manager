/**
 * AgentManager — WebSocket listener for agent skill progress events.
 *
 * Connects to the generic WebSocket endpoint and filters for
 * `type: "agent_progress"` messages.  Dispatches progress and completion
 * events to registered callbacks.
 */
class AgentManager {
    constructor() {
        this.websocket = null;
        this.progressCallbacks = [];
        this.completeCallbacks = [];
        this.errorCallbacks = [];
        this.connected = false;
    }

    /**
     * Connect to the WebSocket endpoint for agent progress events.
     * Safe to call multiple times — won't reconnect if already connected.
     */
    connect() {
        if (this.connected && this.websocket?.readyState === WebSocket.OPEN) {
            return;
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        try {
            this.websocket = new WebSocket(
                `${wsProtocol}${window.location.host}/ws/fetch-progress`
            );
        } catch (e) {
            console.error('AgentManager: Failed to create WebSocket:', e);
            return;
        }

        this.websocket.onopen = () => {
            this.connected = true;
            console.debug('AgentManager: WebSocket connected');
        };

        this.websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type !== 'agent_progress') return;
                this._dispatch(data);
            } catch (e) {
                // Not JSON or wrong format — ignore
            }
        };

        this.websocket.onerror = (error) => {
            console.error('AgentManager: WebSocket error:', error);
            this.connected = false;
        };

        this.websocket.onclose = () => {
            this.connected = false;
            console.debug('AgentManager: WebSocket closed');
        };
    }

    /**
     * Dispatch a parsed agent event to the appropriate callbacks.
     * @param {Object} data - The parsed WebSocket message
     */
    _dispatch(data) {
        const { status, skill } = data;

        if (status === 'error') {
            this.errorCallbacks.forEach((cb) => {
                try {
                    cb(data);
                } catch (e) {
                    console.error('AgentManager error callback failed:', e);
                }
            });
            return;
        }

        if (status === 'completed') {
            this.completeCallbacks.forEach((cb) => {
                try {
                    cb(data);
                } catch (e) {
                    console.error('AgentManager complete callback failed:', e);
                }
            });
            return;
        }

        // started, processing — general progress
        this.progressCallbacks.forEach((cb) => {
            try {
                cb(data);
            } catch (e) {
                console.error('AgentManager progress callback failed:', e);
            }
        });
    }

    /**
     * Register a callback for progress events (started, processing).
     * @param {Function} callback - Receives the event data
     */
    onProgress(callback) {
        this.progressCallbacks.push(callback);
    }

    /**
     * Register a callback for completion events.
     * @param {Function} callback - Receives the event data
     */
    onComplete(callback) {
        this.completeCallbacks.push(callback);
    }

    /**
     * Register a callback for error events.
     * @param {Function} callback - Receives the event data
     */
    onError(callback) {
        this.errorCallbacks.push(callback);
    }

    /**
     * Clear all registered callbacks.
     */
    clearCallbacks() {
        this.progressCallbacks = [];
        this.completeCallbacks = [];
        this.errorCallbacks = [];
    }

    /**
     * Execute an agent skill on the provided model paths.
     *
     * @param {string} skillName - The skill to execute
     * @param {string[]} modelPaths - Model file paths to process
     * @returns {Promise<Object>} The response JSON
     */
    async executeSkill(skillName, modelPaths) {
        const response = await fetch(
            `/api/lm/agent/execute/${encodeURIComponent(skillName)}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_paths: modelPaths }),
            }
        );

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(
                errorData.error || `HTTP ${response.status}: ${response.statusText}`
            );
        }

        return response.json();
    }

    /**
     * Check if the LLM provider is configured.
     *
     * Returns true when both an API key and a model name are set.
     *
     * @returns {Promise<boolean>}
     */
    _readProviderRequiresKey(providerId) {
        const script = document.getElementById('llmProviderPresets');
        if (!script) return true; // safe default
        try {
            const presets = JSON.parse(script.textContent);
            const preset = presets[providerId];
            return preset ? preset.requires_key !== false : true;
        } catch {
            return true;
        }
    }

    async isLlmConfigured() {
        try {
            const response = await fetch('/api/lm/settings');
            if (!response.ok) return false;
            const data = await response.json();
            const provider = data.settings?.llm_provider;
            const hasModel = !!data.settings?.llm_model;
            const hasKey = !!(data.settings?.llm_api_key_set || data.settings?.llm_api_key);
            const needsKey = this._readProviderRequiresKey(provider);
            return hasModel && (hasKey || !needsKey);
        } catch {
            return false;
        }
    }

    /**
     * Get the list of available agent skills.
     *
     * @returns {Promise<Array>}
     */
    async listSkills() {
        const response = await fetch('/api/lm/agent/skills');
        if (!response.ok) return [];
        const data = await response.json();
        return data.skills || [];
    }
}

// Export as singleton
export const agentManager = new AgentManager();
