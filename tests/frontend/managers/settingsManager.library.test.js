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
            default_other_roots: {},
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
import { bannerService } from '../../../static/js/managers/BannerService.js';
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

describe('SettingsManager root selects', () => {
    const rootCases = [
        {
            method: 'loadLoraRoots',
            selectId: 'defaultLoraRoot',
            endpoint: '/api/lm/loras/roots',
            errorKey: 'toast.settings.loraRootsFailed',
        },
        {
            method: 'loadCheckpointRoots',
            selectId: 'defaultCheckpointRoot',
            endpoint: '/api/lm/checkpoints/checkpoints_roots',
            errorKey: 'toast.settings.checkpointRootsFailed',
        },
        {
            method: 'loadUnetRoots',
            selectId: 'defaultUnetRoot',
            endpoint: '/api/lm/checkpoints/unet_roots',
            errorKey: 'toast.settings.unetRootsFailed',
        },
        {
            method: 'loadEmbeddingRoots',
            selectId: 'defaultEmbeddingRoot',
            endpoint: '/api/lm/embeddings/roots',
            errorKey: 'toast.settings.embeddingRootsFailed',
        },
    ];

    const appendRootSelect = (id) => {
        const select = document.createElement('select');
        select.id = id;
        document.body.appendChild(select);
        return select;
    };

    it.each(rootCases)(
        'populates the $method select with roots and keeps it enabled',
        async ({ method, selectId, endpoint }) => {
            const manager = createManager();
            const select = appendRootSelect(selectId);
            select.disabled = true;

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({
                    success: true,
                    roots: ['/models/root-a', '/models/root-b'],
                }),
            });

            await manager[method]();

            expect(global.fetch).toHaveBeenCalledWith(endpoint);
            expect(Array.from(select.options).map(option => option.value)).toEqual([
                '/models/root-a',
                '/models/root-b',
            ]);
            expect(select.disabled).toBe(false);
            expect(showToast).not.toHaveBeenCalled();
        }
    );

    it.each(rootCases)(
        'shows a placeholder and no error toast when $method has empty roots',
        async ({ method, selectId, endpoint }) => {
            const manager = createManager();
            const select = appendRootSelect(selectId);

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({
                    success: true,
                    roots: [],
                }),
            });

            await manager[method]();

            expect(global.fetch).toHaveBeenCalledWith(endpoint);
            expect(select.options).toHaveLength(1);
            expect(select.options[0].value).toBe('');
            expect(select.options[0].textContent).toBe('No Default');
            expect(select.disabled).toBe(true);
            expect(showToast).not.toHaveBeenCalled();
        }
    );

    it.each(rootCases)(
        'shows an error toast when the $method roots request fails',
        async ({ method, selectId, errorKey }) => {
            const manager = createManager();
            const select = appendRootSelect(selectId);

            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
            });

            await manager[method]();

            expect(select.options).toHaveLength(1);
            expect(select.options[0].value).toBe('');
            expect(select.disabled).toBe(true);
            expect(showToast).toHaveBeenCalledWith(
                errorKey,
                expect.objectContaining({ message: expect.any(String) }),
                'error',
            );
        }
    );
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

    it('loads download backend settings and toggles the aria2 path field', () => {
        const manager = createManager();
        document.body.innerHTML = `
            <select id="downloadBackend">
                <option value="python">Python</option>
                <option value="aria2">aria2</option>
            </select>
            <div id="aria2PathSetting" style="display: none;"></div>
            <input id="aria2cPath" />
        `;

        state.global.settings = {
            download_backend: 'aria2',
            aria2c_path: '/usr/bin/aria2c',
        };

        const saveSpy = vi.spyOn(manager, 'saveSelectSetting').mockResolvedValue();

        manager.loadDownloadBackendSettings();

        const backendSelect = document.getElementById('downloadBackend');
        const aria2PathSetting = document.getElementById('aria2PathSetting');
        const aria2cPath = document.getElementById('aria2cPath');

        expect(backendSelect.value).toBe('aria2');
        expect(aria2cPath.value).toBe('/usr/bin/aria2c');
        expect(aria2PathSetting.style.display).toBe('block');

        backendSelect.value = 'python';
        backendSelect.onchange();

        expect(aria2PathSetting.style.display).toBe('none');
        expect(saveSpy).toHaveBeenCalledWith('downloadBackend', 'download_backend');
    });

    it('loads example image remote-open settings and updates field visibility', async () => {
        const manager = createManager();
        document.body.innerHTML = `
            <select id="exampleImagesOpenMode">
                <option value="system">System</option>
                <option value="clipboard">Clipboard</option>
                <option value="uri_template">URI</option>
            </select>
            <div id="exampleImagesLocalRootSetting" style="display: none;"></div>
            <div id="exampleImagesUriTemplateSetting" style="display: none;"></div>
            <input id="exampleImagesLocalRoot" />
            <input id="exampleImagesOpenUriTemplate" />
        `;

        vi.spyOn(manager, 'loadMetadataArchiveSettings').mockResolvedValue();
        vi.spyOn(manager, 'loadBackupSettings').mockResolvedValue();
        vi.spyOn(manager, 'loadLibraries').mockResolvedValue();
        vi.spyOn(manager, 'loadLoraRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadCheckpointRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadUnetRoots').mockResolvedValue();
        vi.spyOn(manager, 'loadEmbeddingRoots').mockResolvedValue();

        state.global.settings = {
            example_images_open_mode: 'uri_template',
            example_images_local_root: '/Volumes/ComfyUI/examples',
            example_images_open_uri_template: 'shortcuts://run-shortcut?text={{encoded_local_path}}',
        };

        await manager.loadSettingsToUI();

        expect(document.getElementById('exampleImagesOpenMode').value).toBe('uri_template');
        expect(document.getElementById('exampleImagesLocalRoot').value).toBe('/Volumes/ComfyUI/examples');
        expect(document.getElementById('exampleImagesOpenUriTemplate').value)
            .toBe('shortcuts://run-shortcut?text={{encoded_local_path}}');
        expect(document.getElementById('exampleImagesLocalRootSetting').style.display).toBe('block');
        expect(document.getElementById('exampleImagesUriTemplateSetting').style.display).toBe('block');

        state.global.settings.example_images_open_mode = 'clipboard';
        manager.updateExampleImagesOpenSettingsVisibility();
        expect(document.getElementById('exampleImagesLocalRootSetting').style.display).toBe('block');
        expect(document.getElementById('exampleImagesUriTemplateSetting').style.display).toBe('none');

        state.global.settings.example_images_open_mode = 'system';
        manager.updateExampleImagesOpenSettingsVisibility();
        expect(document.getElementById('exampleImagesLocalRootSetting').style.display).toBe('none');
        expect(document.getElementById('exampleImagesUriTemplateSetting').style.display).toBe('none');
    });
});

describe('SettingsManager other-model root selects', () => {
    const appendOtherRootSelects = (...subTypes) => {
        const selects = {};
        subTypes.forEach((subType) => {
            const select = document.createElement('select');
            select.dataset.otherRootSubtype = subType;
            document.body.appendChild(select);
            selects[subType] = select;
        });
        return selects;
    };

    describe('loadOtherRoots', () => {
        it('populates each sub_type select from the grouped roots and preselects defaults', async () => {
            const manager = createManager();
            const selects = appendOtherRootSelects('vae', 'upscaler');
            selects.vae.disabled = true;

            state.global.settings = {
                default_other_roots: { vae: '/models/vae-b' },
            };

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({
                    success: true,
                    roots_by_subtype: {
                        vae: ['/models/vae-a', '/models/vae-b'],
                        upscaler: ['/models/upscale'],
                    },
                }),
            });

            await manager.loadOtherRoots();

            expect(global.fetch).toHaveBeenCalledWith('/api/lm/other/roots_by_subtype');
            expect(Array.from(selects.vae.options).map(o => o.value)).toEqual([
                '/models/vae-a',
                '/models/vae-b',
            ]);
            expect(selects.vae.value).toBe('/models/vae-b');
            expect(selects.vae.disabled).toBe(false);
            expect(Array.from(selects.upscaler.options).map(o => o.value)).toEqual([
                '/models/upscale',
            ]);
            // No configured default: first root wins
            expect(selects.upscaler.value).toBe('/models/upscale');
            expect(showToast).not.toHaveBeenCalled();
        });

        it('shows a placeholder on selects whose sub_type has no roots', async () => {
            const manager = createManager();
            const selects = appendOtherRootSelects('vae', 'controlnet');

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({
                    success: true,
                    roots_by_subtype: { vae: ['/models/vae-a'] },
                }),
            });

            await manager.loadOtherRoots();

            expect(selects.controlnet.options).toHaveLength(1);
            expect(selects.controlnet.options[0].value).toBe('');
            expect(selects.controlnet.options[0].textContent).toBe('No Default');
            expect(selects.controlnet.disabled).toBe(true);
            expect(selects.vae.disabled).toBe(false);
            expect(showToast).not.toHaveBeenCalled();
        });

        it('shows an error toast and placeholders when the request fails', async () => {
            const manager = createManager();
            const selects = appendOtherRootSelects('vae', 'upscaler');

            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
            });

            await manager.loadOtherRoots();

            expect(selects.vae.disabled).toBe(true);
            expect(selects.upscaler.disabled).toBe(true);
            expect(showToast).toHaveBeenCalledWith(
                'toast.settings.otherRootsFailed',
                expect.objectContaining({ message: expect.any(String) }),
                'error',
            );
        });

        it('does not call the API when no sub_type selects exist', async () => {
            const manager = createManager();
            global.fetch = vi.fn();

            await manager.loadOtherRoots();

            expect(global.fetch).not.toHaveBeenCalled();
        });
    });

    describe('updateOtherModelsControls', () => {
        const appendToggles = (...subTypes) => {
            const container = document.createElement('div');
            container.id = 'otherSubTypeToggles';
            document.body.appendChild(container);
            subTypes.forEach((subType) => {
                const input = document.createElement('input');
                input.type = 'checkbox';
                input.value = subType;
                input.dataset.otherSubtypeToggle = subType;
                container.appendChild(input);
            });
            return container;
        };

        it('disables every toggle and select while the feature is off', () => {
            const manager = createManager();
            const container = appendToggles('vae', 'upscaler');
            const selects = appendOtherRootSelects('vae', 'upscaler');

            state.global.settings = {
                enable_other_models: false,
                enabled_other_sub_types: ['vae'],
            };

            manager.updateOtherModelsControls();

            const vaeToggle = document.querySelector('[data-other-subtype-toggle="vae"]');
            const upscalerToggle = document.querySelector('[data-other-subtype-toggle="upscaler"]');
            expect(vaeToggle.checked).toBe(true);
            expect(upscalerToggle.checked).toBe(false);
            expect(vaeToggle.disabled).toBe(true);
            expect(upscalerToggle.disabled).toBe(true);
            expect(selects.vae.disabled).toBe(true);
            expect(selects.upscaler.disabled).toBe(true);
            expect(container.classList.contains('is-disabled')).toBe(true);
        });

        it('leaves enabled sub_types interactive and disables the rest', () => {
            const manager = createManager();
            const container = appendToggles('vae', 'upscaler');
            const selects = appendOtherRootSelects('vae', 'upscaler');

            state.global.settings = {
                enable_other_models: true,
                enabled_other_sub_types: ['vae'],
            };

            manager.updateOtherModelsControls();

            const vaeToggle = document.querySelector('[data-other-subtype-toggle="vae"]');
            const upscalerToggle = document.querySelector('[data-other-subtype-toggle="upscaler"]');
            expect(vaeToggle.disabled).toBe(false);
            expect(upscalerToggle.disabled).toBe(false);
            expect(selects.vae.disabled).toBe(false);
            expect(selects.upscaler.disabled).toBe(true);
            expect(container.classList.contains('is-disabled')).toBe(false);
        });

        it('restores the master toggle checked state from settings', () => {
            const manager = createManager();
            const masterToggle = document.createElement('input');
            masterToggle.type = 'checkbox';
            masterToggle.id = 'enableOtherModels';
            document.body.appendChild(masterToggle);

            state.global.settings = { enable_other_models: true };
            manager.updateOtherModelsControls();
            expect(masterToggle.checked).toBe(true);

            state.global.settings = { enable_other_models: false };
            manager.updateOtherModelsControls();
            expect(masterToggle.checked).toBe(false);
        });

        it('persists the checked sub_types as the whole allow-list', async () => {
            const manager = createManager();
            appendToggles('vae', 'upscaler', 'controlnet');
            document.querySelector('[data-other-subtype-toggle="vae"]').checked = true;
            document.querySelector('[data-other-subtype-toggle="controlnet"]').checked = true;

            state.global.settings = {
                enable_other_models: true,
                enabled_other_sub_types: [],
            };
            const saveSpy = vi.spyOn(manager, 'saveSetting').mockResolvedValue();
            const loadSpy = vi.spyOn(manager, 'loadOtherRoots').mockResolvedValue();

            await manager.saveEnabledOtherSubTypes();

            expect(saveSpy).toHaveBeenCalledWith('enabled_other_sub_types', [
                'vae',
                'controlnet',
            ]);
            expect(loadSpy).toHaveBeenCalled();
            expect(showToast).toHaveBeenCalledWith(
                'toast.settings.settingsUpdated',
                expect.objectContaining({ setting: 'other model types' }),
                'success',
            );
        });
    });

    describe('saveOtherRootSetting', () => {
        it('read-modify-writes the default_other_roots dict and posts it whole', async () => {
            const manager = createManager();
            state.global.settings = {
                default_other_roots: { vae: '/models/vae-a' },
            };

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({ success: true }),
            });

            await manager.saveOtherRootSetting('upscaler', '/models/upscale');

            expect(state.global.settings.default_other_roots).toEqual({
                vae: '/models/vae-a',
                upscaler: '/models/upscale',
            });
            expect(global.fetch).toHaveBeenCalledWith('/api/lm/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    default_other_roots: {
                        vae: '/models/vae-a',
                        upscaler: '/models/upscale',
                    },
                }),
            });
            expect(showToast).toHaveBeenCalledWith(
                'toast.settings.settingsUpdated',
                expect.objectContaining({ setting: expect.any(String) }),
                'success',
            );
        });

        it('removes the sub_type key when the value is empty', async () => {
            const manager = createManager();
            state.global.settings = {
                default_other_roots: { vae: '/models/vae-a' },
            };

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({ success: true }),
            });

            await manager.saveOtherRootSetting('vae', '');

            expect(state.global.settings.default_other_roots).toEqual({});
            expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
                default_other_roots: {},
            });
        });

        it('shows an error toast when the backend save fails', async () => {
            const manager = createManager();
            state.global.settings = { default_other_roots: {} };

            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
            });

            await manager.saveOtherRootSetting('vae', '/models/vae-a');

            expect(showToast).toHaveBeenCalledWith(
                'toast.settings.settingSaveFailed',
                expect.objectContaining({ message: expect.any(String) }),
                'error',
            );
        });
    });
});

describe('SettingsManager Other Models nav and banner sync', () => {
    it('shows or hides the Other Models nav entry', () => {
        const manager = createManager();
        const navItem = document.createElement('a');
        navItem.id = 'otherNavItem';
        document.body.appendChild(navItem);

        manager.updateOtherModelsNavVisibility(false);
        expect(navItem.classList.contains('nav-item--hidden')).toBe(true);

        manager.updateOtherModelsNavVisibility(true);
        expect(navItem.classList.contains('nav-item--hidden')).toBe(false);
    });

    it('drops the announcement banner only when enabling', () => {
        const manager = createManager();
        const spy = vi
            .spyOn(bannerService, 'removeOtherModelsAnnouncement')
            .mockImplementation(() => {});

        manager.removeOtherModelsAnnouncement(false);
        expect(spy).not.toHaveBeenCalled();

        manager.removeOtherModelsAnnouncement(true);
        expect(spy).toHaveBeenCalledTimes(1);

        spy.mockRestore();
    });
});

describe('SettingsManager recipes layout switch', () => {
    it('dispatches lm:recipes-layout-changed without recalculating the old scroller', async () => {
        const manager = createManager();
        const select = document.createElement('select');
        select.id = 'recipesLayout';
        const option = document.createElement('option');
        option.value = 'masonry';
        select.appendChild(option);
        select.value = 'masonry';
        document.body.appendChild(select);

        const calculateLayout = vi.fn();
        state.virtualScroller = { calculateLayout };

        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

        await manager.saveSelectSetting('recipesLayout', 'recipes_layout');

        const layoutEvent = dispatchSpy.mock.calls
            .map(([event]) => event)
            .find(event => event.type === 'lm:recipes-layout-changed');
        expect(layoutEvent).toBeInstanceOf(CustomEvent);
        expect(calculateLayout).not.toHaveBeenCalled();
        expect(showToast).not.toHaveBeenCalled();

        dispatchSpy.mockRestore();
        delete state.virtualScroller;
    });

    it('saveRecipesLayout persists, dispatches the layout event, and syncs controls', async () => {
        const manager = createManager();

        const gridBtn = document.createElement('button');
        gridBtn.dataset.recipesLayout = 'grid';
        gridBtn.setAttribute('aria-pressed', 'false');
        const masonryBtn = document.createElement('button');
        masonryBtn.dataset.recipesLayout = 'masonry';
        masonryBtn.setAttribute('aria-pressed', 'false');
        masonryBtn.setAttribute('role', 'radio');
        masonryBtn.setAttribute('aria-checked', 'false');
        document.body.appendChild(gridBtn);
        document.body.appendChild(masonryBtn);

        const calculateLayout = vi.fn();
        state.virtualScroller = { calculateLayout };

        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

        await manager.saveRecipesLayout('masonry');

        expect(state.global.settings.recipes_layout).toBe('masonry');
        expect(masonryBtn.classList.contains('active')).toBe(true);
        expect(masonryBtn.getAttribute('aria-pressed')).toBe('true');
        expect(masonryBtn.getAttribute('aria-checked')).toBe('true');
        expect(gridBtn.classList.contains('active')).toBe(false);
        expect(gridBtn.getAttribute('aria-pressed')).toBe('false');

        const layoutEvent = dispatchSpy.mock.calls
            .map(([event]) => event)
            .find(event => event.type === 'lm:recipes-layout-changed');
        expect(layoutEvent).toBeInstanceOf(CustomEvent);
        expect(calculateLayout).not.toHaveBeenCalled();
        expect(showToast).not.toHaveBeenCalled();

        dispatchSpy.mockRestore();
        delete state.virtualScroller;
    });

    it('ignores invalid recipes layout values', async () => {
        const manager = createManager();
        await manager.saveRecipesLayout('bogus');
        expect(state.global.settings.recipes_layout).toBeUndefined();
    });
});
