import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { readTemplate } from '../utils/domFixtures.js';

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: (key, params = {}, fallback = null) => fallback ?? key,
}));

const ENV_PANEL_MODULE = new URL(
    '../../../static/js/components/EnvironmentPanel.js',
    import.meta.url
).pathname;

const ENVIRONMENT_PAYLOAD = {
    success: true,
    environment: {
        app_version: '1.2.8-server',
        comfyui_version: '0.37.0',
        frontend_version: '1.53.6',
        python_version: '3.11.16',
        platform: 'Linux-6.11.0-test-x86_64',
        standalone: false,
    },
};

function setupDom() {
    document.body.dataset.appVersion = '1.2.8-client';
    document.body.innerHTML = `
        <div class="settings-content">
            <div id="section-about">
                <div class="env-panel" id="settingsEnvironmentPanel">
                    <button type="button" id="copyEnvironmentBtn"></button>
                    <dl>
                        <dd data-env-field="app"></dd>
                        <dd data-env-field="comfyui"></dd>
                        <dd data-env-field="frontend"></dd>
                        <dd data-env-field="python"></dd>
                        <dd data-env-field="os"></dd>
                        <dd data-env-field="browser"></dd>
                    </dl>
                </div>
            </div>
        </div>
    `;
}

function field(name) {
    return document.querySelector(`[data-env-field="${name}"]`);
}

function stubEnvironment(payload = ENVIRONMENT_PAYLOAD) {
    const fetchMock = vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => payload,
    }));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

describe('EnvironmentPanel (Settings -> About)', () => {
    let EnvironmentPanel;

    beforeEach(async () => {
        ({ EnvironmentPanel } = await import(ENV_PANEL_MODULE));
        setupDom();
        vi.spyOn(console, 'debug').mockImplementation(() => {});
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        delete document.body.dataset.appVersion;
        delete navigator.clipboard;
        delete document.execCommand;
        document.body.innerHTML = '';
    });

    it('renders the environment payload from the backend', async () => {
        const fetchMock = stubEnvironment();
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();

        expect(fetchMock).toHaveBeenCalledWith(
            '/api/lm/environment',
            { headers: { Accept: 'application/json' } }
        );
        expect(field('app').textContent).toBe('1.2.8-server');
        expect(field('comfyui').textContent).toBe('0.37.0');
        expect(field('frontend').textContent).toBe('1.53.6');
        expect(field('python').textContent).toBe('3.11.16');
        expect(field('os').textContent).toBe('Linux-6.11.0-test-x86_64');
        expect(field('browser').textContent).toBe(navigator.userAgent);
        expect(field('pytorch')).toBeNull();
    });

    it('still shows Python and OS in standalone mode', async () => {
        stubEnvironment({
            success: true,
            environment: {
                app_version: '1.2.8-server',
                comfyui_version: null,
                frontend_version: null,
                python_version: '3.11.16',
                platform: 'Windows-10-10.0.19045-SP0',
                standalone: true,
            },
        });
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();

        expect(field('comfyui').textContent).toBe('Unavailable');
        expect(field('frontend').textContent).toBe('Unavailable');
        expect(field('python').textContent).toBe('3.11.16');
        expect(field('os').textContent).toBe('Windows-10-10.0.19045-SP0');
    });

    it('falls back to the app version in the page when the endpoint fails', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: false,
            status: 404,
            json: async () => ({}),
        })));
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();

        expect(field('app').textContent).toBe('1.2.8-client');
        expect(field('browser').textContent).toBe(navigator.userAgent);
        expect(field('comfyui').textContent).toBe('Unavailable');
        expect(field('frontend').textContent).toBe('Unavailable');
        expect(field('python').textContent).toBe('Unavailable');
        expect(field('os').textContent).toBe('Unavailable');
    });

    it('fetches the environment only once', async () => {
        const fetchMock = stubEnvironment();
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();
        await panel.ensureLoaded();

        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('copies a Markdown environment block to the clipboard', async () => {
        stubEnvironment();
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText },
            configurable: true,
        });
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();
        await panel.copyEnvironmentInfo();

        expect(writeText).toHaveBeenCalledTimes(1);
        const text = writeText.mock.calls[0][0];
        expect(text).toContain('**Environment**');
        expect(text).toContain('- LoRA Manager: 1.2.8-server');
        expect(text).toContain('- ComfyUI: 0.37.0');
        expect(text).toContain('- ComfyUI Frontend: 1.53.6');
        expect(text).toContain('- Python: 3.11.16');
        expect(text).toContain('- OS: Linux-6.11.0-test-x86_64');
        expect(text).toContain(`- Browser: ${navigator.userAgent}`);
    });

    it('binds the copy button when the panel is initialized', async () => {
        stubEnvironment();
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText },
            configurable: true,
        });
        const panel = new EnvironmentPanel();
        await panel.ensureLoaded();

        document.getElementById('copyEnvironmentBtn').click();

        await vi.waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    });

    it('falls back to execCommand when the clipboard API is unavailable', async () => {
        stubEnvironment();
        const execCommand = vi.fn(() => true);
        document.execCommand = execCommand;
        const panel = new EnvironmentPanel();

        await panel.ensureLoaded();
        await panel.copyEnvironmentInfo();

        expect(execCommand).toHaveBeenCalledWith('copy');
        expect(document.querySelector('textarea')).toBeNull();
    });

    it('renders in Settings -> About instead of the Help modal', () => {
        const aboutTemplate = readTemplate('components/modals/settings/about.html');
        const helpTemplate = readTemplate('components/modals/help_modal.html');

        expect(aboutTemplate).toContain('id="settingsEnvironmentPanel"');
        expect(aboutTemplate).toContain('data-env-field="frontend"');
        expect(aboutTemplate).toContain('issues/new');
        expect(aboutTemplate).toContain('/wiki');
        expect(aboutTemplate).toContain('discord.gg');
        expect(helpTemplate).not.toContain('settingsEnvironmentPanel');
    });
});
