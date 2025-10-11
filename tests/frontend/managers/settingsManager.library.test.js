import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
    modalManager: {
        closeModal: vi.fn(),
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));

vi.mock('../../../static/js/state/index.js', () => {
    const settings = {};
    return {
        state: {
            global: {
                settings,
            },
            loadingManager: {
                showSimpleLoading: vi.fn(),
                hide: vi.fn(),
            },
        },
        createDefaultSettings: () => ({
            language: 'en',
        }),
    };
});

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    resetAndReload: vi.fn(),
}));

vi.mock('../../../static/js/utils/constants.js', () => ({
    DOWNLOAD_PATH_TEMPLATES: {},
    DEFAULT_PATH_TEMPLATES: {},
    MAPPABLE_BASE_MODELS: [],
    PATH_TEMPLATE_PLACEHOLDERS: {},
    DEFAULT_PRIORITY_TAG_CONFIG: {
        lora: 'character, style',
        checkpoint: 'base, guide',
        embedding: 'hint',
    },
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: (_key, _params, fallback) => fallback ?? '',
}));

vi.mock('../../../static/js/i18n/index.js', () => ({
    i18n: {
        getCurrentLocale: () => 'en',
        setLanguage: vi.fn().mockResolvedValue(),
    },
}));

vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
    configureModelCardVideo: vi.fn(),
}));

import { SettingsManager } from '../../../static/js/managers/SettingsManager.js';
import { showToast } from '../../../static/js/utils/uiHelpers.js';
import { state } from '../../../static/js/state/index.js';

const originalLocation = window.location;

const createManager = () => {
    state.global.settings = {};
    const initSettingsSpy = vi
        .spyOn(SettingsManager.prototype, 'initializeSettings')
        .mockResolvedValue();
    const initializeSpy = vi
        .spyOn(SettingsManager.prototype, 'initialize')
        .mockImplementation(() => {});

    const manager = new SettingsManager();

    initSettingsSpy.mockRestore();
    initializeSpy.mockRestore();

    return manager;
};

const appendLibrarySelect = () => {
    const select = document.createElement('select');
    select.id = 'librarySelect';
    document.body.appendChild(select);
    return select;
};

beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
});

afterEach(() => {
    delete global.fetch;
    delete document.hidden;
    Object.defineProperty(window, 'location', {
        value: originalLocation,
        configurable: true,
        writable: true,
    });
});

describe('SettingsManager library controls', () => {
    it('loads libraries and populates the select', async () => {
        const manager = createManager();
        const select = appendLibrarySelect();

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                success: true,
                libraries: {
                    beta: { display_name: 'Beta' },
                    alpha: { metadata: { display_name: 'Alpha' } },
                },
                active_library: 'beta',
            }),
        });

        await manager.loadLibraries();

        expect(manager.availableLibraries).toEqual({
            beta: { display_name: 'Beta' },
            alpha: { metadata: { display_name: 'Alpha' } },
        });
        expect(manager.activeLibrary).toBe('beta');
        expect(select.options).toHaveLength(2);
        expect(Array.from(select.options).map(option => option.value)).toEqual([
            'alpha',
            'beta',
        ]);
        expect(select.value).toBe('beta');
        expect(select.disabled).toBe(false);
    });

    it('handles load errors by disabling the select and showing a toast', async () => {
        const manager = createManager();
        const select = appendLibrarySelect();

        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 500,
        });

        await manager.loadLibraries();

        expect(select.options).toHaveLength(1);
        expect(select.options[0].value).toBe('');
        expect(select.disabled).toBe(true);
        expect(manager.availableLibraries).toEqual({});
        expect(manager.activeLibrary).toBe('');
        expect(showToast).toHaveBeenCalledWith(
            'toast.settings.libraryLoadFailed',
            expect.objectContaining({ message: 'Failed to fetch library registry' }),
            'error',
        );
    });

    it('activates a newly selected library and reloads the page', async () => {
        const manager = createManager();
        const select = appendLibrarySelect();
        select.appendChild(new Option('Alpha', 'alpha'));
        select.appendChild(new Option('Beta', 'beta'));
        select.value = 'beta';
        manager.activeLibrary = 'alpha';

        Object.defineProperty(document, 'hidden', {
            value: false,
            configurable: true,
        });

        const reloadMock = vi.fn();
        Object.defineProperty(window, 'location', {
            value: { reload: reloadMock },
            configurable: true,
        });

        const activateSpy = vi
            .spyOn(manager, 'activateLibrary')
            .mockResolvedValue({ success: true, active_library: 'beta' });

        await manager.handleLibraryChange();

        expect(activateSpy).toHaveBeenCalledWith('beta');
        expect(reloadMock).toHaveBeenCalledTimes(1);
        expect(select.disabled).toBe(false);
    });

    it('ignores changes when selecting the active library', async () => {
        const manager = createManager();
        const select = appendLibrarySelect();
        select.appendChild(new Option('Alpha', 'alpha'));
        select.value = 'alpha';
        manager.activeLibrary = 'alpha';

        const activateSpy = vi.spyOn(manager, 'activateLibrary');

        await manager.handleLibraryChange();

        expect(select.value).toBe('alpha');
        expect(activateSpy).not.toHaveBeenCalled();
    });
});
