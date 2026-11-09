import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';

/**
 * Renders the read-only environment block in Settings -> About and copies it
 * as Markdown for issue reports.
 */
export class EnvironmentPanel {
    constructor() {
        this.panel = null;
        this.copyButton = null;
        this.data = null;
        this.promise = null;
        this.initialized = false;
    }

    initialize() {
        if (this.initialized) {
            return;
        }

        this.panel = document.getElementById('settingsEnvironmentPanel');
        if (!this.panel) {
            return;
        }

        this.copyButton = document.getElementById('copyEnvironmentBtn');
        if (this.copyButton) {
            this.copyButton.addEventListener('click', () => this.copyEnvironmentInfo());
        }

        this.initialized = true;
    }

    /**
     * Load the environment snapshot once, on first visit to the About section.
     *
     * The backend reports Python/OS in both plugin and standalone mode, and
     * ComfyUI package versions when they are installed; missing values are
     * rendered as "Unavailable".
     *
     * @returns {Promise<Object|null>} The rendered environment snapshot
     */
    ensureLoaded() {
        this.initialize();
        if (!this.panel) {
            return Promise.resolve(null);
        }
        if (this.data) {
            return Promise.resolve(this.data);
        }
        if (this.promise) {
            return this.promise;
        }

        const base = this.collectBaseEnvironment();
        this.render(base, { pending: true });
        this.promise = this.load(base);
        return this.promise;
    }

    async load(base) {
        let data = base;
        try {
            const response = await fetch('/api/lm/environment', {
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const payload = await response.json();
            const environment = payload?.environment || {};
            data = {
                ...base,
                app: environment.app_version || base.app,
                comfyui: environment.comfyui_version || '',
                frontend: environment.frontend_version || '',
                python: environment.python_version || '',
                os: environment.platform || '',
            };
        } catch (error) {
            console.debug('Environment info unavailable:', error);
        }

        this.data = data;
        this.render(data);
        return data;
    }

    /**
     * Collect the environment values that are available without a fetch.
     */
    collectBaseEnvironment() {
        return {
            app: document.body?.dataset?.appVersion || '',
            browser: navigator.userAgent || '',
        };
    }

    /**
     * Render an environment snapshot into the panel fields.
     * @param {Object} data - Field values keyed by data-env-field
     * @param {{pending?: boolean}} [options] - Keep placeholders while loading
     */
    render(data, { pending = false } = {}) {
        if (!this.panel) {
            return;
        }
        const fallback = pending
            ? '\u2014'
            : translate('settings.about.unavailable', {}, 'Unavailable');
        this.panel.querySelectorAll('[data-env-field]').forEach((element) => {
            const value = data?.[element.dataset.envField] || '';
            element.textContent = value || fallback;
            element.title = value;
        });
    }

    /**
     * Copy the environment panel as Markdown for pasting into an issue.
     *
     * The copied block stays in English so issue reports remain readable for
     * maintainers regardless of the reporter's UI language.
     */
    async copyEnvironmentInfo() {
        const data = this.data || (await this.ensureLoaded()) || this.collectBaseEnvironment();
        const labels = {
            app: 'LoRA Manager',
            comfyui: 'ComfyUI',
            frontend: 'ComfyUI Frontend',
            python: 'Python',
            os: 'OS',
            browser: 'Browser',
        };
        const unavailable = 'Unavailable';
        const lines = ['**Environment**'];
        Object.entries(labels).forEach(([key, label]) => {
            lines.push(`- ${label}: ${data[key] || unavailable}`);
        });

        const copied = await this.writeToClipboard(lines.join('\n'));
        showToast(
            copied ? 'settings.about.copySuccess' : 'settings.about.copyFailed',
            {},
            copied ? 'success' : 'error'
        );
    }

    /**
     * Write text to the clipboard, falling back to execCommand on insecure
     * origins where navigator.clipboard is unavailable (LAN HTTP deployments).
     */
    async writeToClipboard(text) {
        if (navigator.clipboard?.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (error) {
                console.debug('Clipboard API write failed, using fallback:', error);
            }
        }
        return this.writeToClipboardFallback(text);
    }

    /**
     * Legacy clipboard fallback for non-secure contexts.
     */
    writeToClipboardFallback(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();

        let copied = false;
        try {
            copied = typeof document.execCommand === 'function' && document.execCommand('copy');
        } catch (error) {
            copied = false;
        } finally {
            textarea.remove();
        }
        return copied;
    }
}

export const environmentPanel = new EnvironmentPanel();
