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
    getMappableBaseModelsDynamic: () => [],
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
    vi.useRealTimers();
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

    it('loads recipes_path into the settings input', async () => {
        const manager = createManager();
        const input = document.createElement('input');
        input.id = 'recipesPath';
        document.body.appendChild(input);

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                success: true,
                isAvailable: false,
                isEnabled: false,
                databaseSize: 0,
            }),
        });

        state.global.settings = {
            recipes_path: '/custom/recipes',
        };

        await manager.loadSettingsToUI();

        expect(input.value).toBe('/custom/recipes');
    });

    it('does not autofocus empty extra folder path rows during initial settings load', async () => {
        vi.useFakeTimers();

        const manager = createManager();
        document.body.innerHTML = `
            <div id="extraFolderPaths-loras"></div>
            <div id="extraFolderPaths-checkpoints"></div>
            <div id="extraFolderPaths-unet"></div>
            <div id="extraFolderPaths-embeddings"></div>
        `;

        vi.spyOn(manager, 'loadMetadataArchiveSettings').mockResolvedValue();
        vi.spyOn(manager, 'loadBackupSettings').mockResolvedValue();
        vi.spyOn(manager, 'loadLibraries').mockResolvedValue();
        vi.spyOn(manager, 'loadLoraRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadCheckpointRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadUnetRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadEmbeddingRoots').mockResolvedValue();

        const focusSpy = vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(() => {});

        state.global.settings = {
            extra_folder_paths: {},
        };

        await manager.loadSettingsToUI();
        await vi.runAllTimersAsync();

        expect(focusSpy).not.toHaveBeenCalled();
    });

    it('still focuses an extra folder path row when it is added explicitly', async () => {
        vi.useFakeTimers();

        const manager = createManager();
        document.body.innerHTML = '<div id="extraFolderPaths-embeddings"></div>';

        const focusSpy = vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(() => {});

        manager.addExtraFolderPathRow('embeddings', '');
        await vi.runAllTimersAsync();

        expect(focusSpy).toHaveBeenCalledTimes(1);
    });

    it('shows loading while saving recipes_path', async () => {
        const manager = createManager();
        const input = document.createElement('input');
        input.id = 'recipesPath';
        input.value = '/custom/recipes';
        document.body.appendChild(input);

        state.global.settings = {
            recipes_path: '',
        };

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        await manager.saveInputSetting('recipesPath', 'recipes_path');

        expect(state.loadingManager.showSimpleLoading).toHaveBeenCalledWith(
            'Migrating recipes...'
        );
        expect(state.loadingManager.hide).toHaveBeenCalledTimes(1);
        expect(showToast).toHaveBeenCalledWith(
            'toast.settings.recipesPathUpdated',
            {},
            'success',
        );
    });
});
