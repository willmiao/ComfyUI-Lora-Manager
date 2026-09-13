import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const initializeAppMock = vi.fn();
const showToastMock = vi.fn();

vi.mock('../../../static/js/core.js', () => ({
    appCore: {
        initialize: initializeAppMock,
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: showToastMock,
}));

describe('Other Models disabled page', () => {
    const originalLocation = window.location;
    let enableOtherModels;
    let initializeOtherDisabledPage;

    beforeEach(async () => {
        vi.resetModules();
        vi.clearAllMocks();
        initializeAppMock.mockResolvedValue(undefined);
        document.body.innerHTML = [
            '<button id="enableOtherModelsBtn"></button>',
            '<button id="openOtherModelsSettingsBtn"></button>',
        ].join('');

        Object.defineProperty(window, 'location', {
            value: { ...originalLocation, reload: vi.fn() },
            configurable: true,
            writable: true,
        });

        ({ enableOtherModels, initializeOtherDisabledPage } = await import(
            '../../../static/js/other_disabled.js'
        ));
        await initializeOtherDisabledPage();
    });

    afterEach(() => {
        Object.defineProperty(window, 'location', {
            value: originalLocation,
            configurable: true,
            writable: true,
        });
        delete global.fetch;
        delete window.modalManager;
    });

    it('boots the shared app core so the header stays usable', () => {
        expect(initializeAppMock).toHaveBeenCalledTimes(1);
    });

    it('opens the Library settings from the no-folders state', () => {
        const showModal = vi.fn();
        window.modalManager = { showModal };

        document.getElementById('openOtherModelsSettingsBtn').dispatchEvent(
            new MouseEvent('click', { bubbles: true }),
        );

        expect(showModal).toHaveBeenCalledWith('settingsModal');
    });

    it('enables Other Models through the settings API and reloads', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        await enableOtherModels();

        expect(global.fetch).toHaveBeenCalledWith(
            '/api/lm/settings',
            expect.objectContaining({ method: 'POST' }),
        );
        expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
            enable_other_models: true,
        });
        expect(window.location.reload).toHaveBeenCalledTimes(1);
        expect(showToastMock).not.toHaveBeenCalled();
    });

    it('re-enables the button and toasts when enabling fails', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 500,
            json: async () => ({ success: false, error: 'boom' }),
        });

        await enableOtherModels();

        expect(window.location.reload).not.toHaveBeenCalled();
        expect(showToastMock).toHaveBeenCalledWith(
            'other.disabled.enableFailed',
            expect.objectContaining({ message: 'boom' }),
            'error',
        );
        expect(document.getElementById('enableOtherModelsBtn').disabled).toBe(false);
    });
});
