/**
 * First Run Component
 * Shows a welcome screen before the initial library scan and starts the scan
 * only after the user confirms.
 */
import { appCore } from '../core.js';
import { translate } from '../utils/i18nHelpers.js';
import { formatFileSize } from '../utils/formatters.js';
import { setStorageItem } from '../utils/storageHelpers.js';
import { state } from '../state/index.js';
import { escapeHtml } from './shared/utils.js';

const LIBRARY_ORDER = ['loras', 'checkpoints', 'embeddings', 'other'];

class FirstRunManager {
    constructor() {
        this.websocket = null;
        this.info = null;
    }

    /**
     * Initialize the component
     */
    async initialize() {
        // Initialize core application for theme and header functionality
        appCore.initialize().then(() => {
            console.log('Core application initialized for first-run component');
            this.setupLanguageSelector();
        });

        this.setupSidecarOptions();
        this.setupActions();
        this.connectWebSocket();

        await this.loadFirstRunInfo();
    }

    /**
     * Let the user pick the UI language before the first scan. The welcome
     * page is server-rendered, so changing the language reloads the page to
     * re-render it in the new locale. The onboarding language modal is
     * skipped afterwards via the onboarding_language_set flag.
     */
    setupLanguageSelector() {
        const select = document.getElementById('firstRunLanguage');
        if (!select) return;

        const current = state.global.settings.language || 'en';
        select.value = current;
        if (select.value !== current) {
            // Unknown language in settings: fall back to English
            select.value = 'en';
        }

        select.addEventListener('change', async () => {
            const language = select.value;
            try {
                const response = await fetch('/api/lm/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ language })
                });
                if (response.ok) {
                    setStorageItem('onboarding_language_set', true);
                    window.location.reload();
                }
            } catch (error) {
                console.error('Failed to change language:', error);
            }
        });
    }

    /**
     * Fetch first-run info from the backend and render it
     */
    async loadFirstRunInfo() {
        try {
            const response = await fetch('/api/lm/first-run-info');
            const data = await response.json();

            // Another client may have already started the scan: reload so the
            // page renders the initialization progress view instead.
            if (!data || data.status !== 'awaiting_first_scan') {
                window.location.reload();
                return;
            }

            this.info = data;
            this.renderLibraries(data);
            this.renderEstimate(data);
            this.applySidecarSettings(data);
        } catch (error) {
            console.error('Failed to load first-run info:', error);
            this.showError(translate('firstRun.errors.loadFailed', {}, 'Failed to load library information.'));
        }
    }

    /**
     * Render per-library roots, file counts and sizes
     */
    renderLibraries(data) {
        const container = document.getElementById('firstRunLibraries');
        if (!container) return;

        container.innerHTML = '';
        // The backend returns each library as a top-level key
        // (loras/checkpoints/embeddings/other), not nested.
        const libraries = {};
        LIBRARY_ORDER.forEach((key) => {
            if (data[key]) libraries[key] = data[key];
        });
        let hasValidRoot = false;

        LIBRARY_ORDER.forEach((libraryKey) => {
            const library = libraries[libraryKey];
            if (!library) return;

            const roots = library.roots || [];
            const libraryEl = document.createElement('div');
            libraryEl.className = 'first-run-library';

            const title = translate(`firstRun.libraries.${libraryKey}`, {}, libraryKey);
            const stats = translate('firstRun.libraryStats', {
                count: library.file_count || 0,
                size: this.formatSize(library.total_bytes)
            }, `${library.file_count || 0} models, ${this.formatSize(library.total_bytes)}`);

            const rootsHtml = roots.map((root) => {
                if (root.exists) {
                    hasValidRoot = true;
                    return `<li class="first-run-root">${escapeHtml(root.path)}</li>`;
                }
                return `<li class="first-run-root first-run-root-missing" title="${escapeHtml(translate('firstRun.rootMissing', {}, 'Directory not found'))}">` +
                    `<i class="fas fa-exclamation-triangle"></i> ${escapeHtml(root.path)}</li>`;
            }).join('');

            libraryEl.innerHTML = `
                <div class="first-run-library-header">
                    <span class="first-run-library-name">${escapeHtml(title)}</span>
                    <span class="first-run-library-stats">${escapeHtml(stats)}</span>
                </div>
                <ul class="first-run-roots">${rootsHtml}</ul>
            `;
            container.appendChild(libraryEl);
        });

        const noRootsEl = document.getElementById('firstRunNoRoots');
        const startBtn = document.getElementById('firstRunStart');
        if (!hasValidRoot) {
            const noRootsText = document.getElementById('firstRunNoRootsText');
            if (noRootsText) {
                const key = data.standalone ? 'firstRun.noRoots.standalone' : 'firstRun.noRoots.plugin';
                noRootsText.textContent = translate(key, {}, 'No model folders configured yet.');
            }
            if (noRootsEl) noRootsEl.hidden = false;
            if (startBtn) startBtn.disabled = true;
        } else {
            if (noRootsEl) noRootsEl.hidden = true;
            if (startBtn) startBtn.disabled = false;
        }
    }

    /**
     * Render the "N models / X GB / ~Y minutes" estimate line
     */
    renderEstimate(data) {
        const estimateEl = document.getElementById('firstRunEstimate');
        const estimateText = document.getElementById('firstRunEstimateText');
        if (!estimateEl || !estimateText) return;

        const totalFiles = data.file_count || 0;
        const minutes = Math.max(1, Math.ceil((data.estimated_seconds || 0) / 60));

        estimateText.textContent = translate('firstRun.estimate', {
            count: totalFiles,
            size: this.formatSize(data.total_bytes),
            minutes: minutes
        }, `${totalFiles} models, ${this.formatSize(data.total_bytes)}, about ${minutes} minute(s)`);
        estimateEl.hidden = false;
    }

    /**
     * Pre-select the current sidecar storage settings reported by the backend
     */
    applySidecarSettings(data) {
        const mode = data.sidecar_storage_mode === 'centralized' ? 'centralized' : 'alongside';
        const radio = document.querySelector(`input[name="sidecarStorageMode"][value="${mode}"]`);
        if (radio) {
            radio.checked = true;
        }
        const pathInput = document.getElementById('firstRunSidecarPath');
        if (pathInput && data.sidecar_storage_path) {
            pathInput.value = data.sidecar_storage_path;
        }
        this.updateSidecarPathState();
    }

    /**
     * Wire up the sidecar storage radio options and path input
     */
    setupSidecarOptions() {
        document.querySelectorAll('input[name="sidecarStorageMode"]').forEach((radio) => {
            radio.addEventListener('change', () => this.updateSidecarPathState());
        });
    }

    /**
     * Enable the centralized path input only when that mode is selected
     */
    updateSidecarPathState() {
        const selected = document.querySelector('input[name="sidecarStorageMode"]:checked');
        const pathRow = document.getElementById('firstRunSidecarPathRow');
        const pathInput = document.getElementById('firstRunSidecarPath');
        const isCentralized = selected && selected.value === 'centralized';

        if (pathRow) pathRow.hidden = !isCentralized;
        if (pathInput) pathInput.disabled = !isCentralized;
    }

    /**
     * Wire up the start / defer buttons
     */
    setupActions() {
        const startBtn = document.getElementById('firstRunStart');
        const deferBtn = document.getElementById('firstRunDefer');

        if (startBtn) {
            startBtn.addEventListener('click', () => this.startScan());
        }
        if (deferBtn) {
            deferBtn.addEventListener('click', () => this.deferScan());
        }
    }

    /**
     * Build the request payload from the selected sidecar options
     */
    buildPayload(defer = false) {
        const selected = document.querySelector('input[name="sidecarStorageMode"]:checked');
        const mode = selected ? selected.value : 'alongside';
        const pathInput = document.getElementById('firstRunSidecarPath');
        const path = pathInput ? pathInput.value.trim() : '';

        return {
            sidecar_storage_mode: mode,
            sidecar_storage_path: mode === 'centralized' ? path : '',
            defer: defer
        };
    }

    /**
     * Start the initial scan
     */
    async startScan() {
        const payload = this.buildPayload(false);

        if (payload.sidecar_storage_mode === 'centralized' && !payload.sidecar_storage_path) {
            this.showError(translate('firstRun.errors.pathRequired', {}, 'Please enter a storage directory for centralized metadata.'));
            return;
        }

        this.setActionsEnabled(false);
        this.hideError();

        try {
            await this.postFirstScan(payload);
            // The scanners are now initializing; reload to render the
            // initialization progress view.
            window.location.reload();
        } catch (error) {
            this.setActionsEnabled(true);
            this.showError(error.message);
        }
    }

    /**
     * Defer the initial scan
     */
    async deferScan() {
        const payload = this.buildPayload(true);

        this.setActionsEnabled(false);
        this.hideError();

        try {
            await this.postFirstScan(payload);
            window.location.reload();
        } catch (error) {
            this.setActionsEnabled(true);
            this.showError(error.message);
        }
    }

    /**
     * POST the first-scan request, throwing on error responses
     */
    async postFirstScan(payload) {
        const response = await fetch('/api/lm/first-scan/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            // Non-JSON error response
        }

        if (!response.ok || (data && data.success === false)) {
            const message = (data && (data.error || data.details))
                || translate('firstRun.errors.startFailed', {}, 'Failed to start the scan.');
            throw new Error(message);
        }

        return data;
    }

    /**
     * Connect to the init-progress WebSocket for multi-client sync
     */
    connectWebSocket() {
        try {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            this.websocket = new WebSocket(`${wsProtocol}${window.location.host}/ws/init-progress`);

            this.websocket.onmessage = (event) => {
                try {
                    this.handleProgressUpdate(JSON.parse(event.data));
                } catch (e) {
                    console.error('Failed to parse init-progress message:', e);
                }
            };
        } catch (error) {
            console.error('Failed to connect to WebSocket:', error);
        }
    }

    /**
     * Reload when another client starts the scan
     */
    handleProgressUpdate(data) {
        if (!data) return;

        if (data.stage === 'scan_started') {
            window.location.reload();
        }
    }

    /**
     * Format a byte count, tolerating zero
     */
    formatSize(bytes) {
        if (!bytes) return '0 B';
        return formatFileSize(bytes);
    }

    /**
     * Enable/disable the action buttons
     */
    setActionsEnabled(enabled) {
        const startBtn = document.getElementById('firstRunStart');
        const deferBtn = document.getElementById('firstRunDefer');
        if (startBtn) startBtn.disabled = !enabled;
        if (deferBtn) deferBtn.disabled = !enabled;
    }

    /**
     * Show an error message
     */
    showError(message) {
        const errorEl = document.getElementById('firstRunError');
        const errorText = document.getElementById('firstRunErrorText');
        if (errorText) errorText.textContent = message;
        if (errorEl) errorEl.hidden = false;
    }

    /**
     * Hide the error message
     */
    hideError() {
        const errorEl = document.getElementById('firstRunError');
        if (errorEl) errorEl.hidden = true;
    }

    /**
     * Clean up resources when the component is destroyed
     */
    cleanup() {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.close();
        }
    }
}

// Create and export the first-run manager
export const firstRunManager = new FirstRunManager();

// Initialize the component when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're in first-run mode
    const container = document.getElementById('firstRunContainer');
    if (container) {
        firstRunManager.initialize();
    }
});

// Clean up when the page is unloaded
window.addEventListener('beforeunload', () => {
    firstRunManager.cleanup();
});
