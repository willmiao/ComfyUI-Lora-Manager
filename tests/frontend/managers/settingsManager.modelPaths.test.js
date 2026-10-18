import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
    modalManager: {
        closeModal: vi.fn(),
        showModal: vi.fn(),
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));

vi.mock('../../../static/js/state/index.js', () => {
    return {
        state: {
            global: {
                settings: {},
            },
        },
        createDefaultSettings: () => ({
            language: 'en',
            standalone_mode: false,
            folder_paths: {},
            folder_path_schema: [],
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
    FILENAME_TEMPLATE_PLACEHOLDERS: [],
    DEFAULT_FILENAME_TEMPLATES: { lora: '', checkpoint: '', embedding: '' },
    DEFAULT_PRIORITY_TAG_CONFIG: {},
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
import { state } from '../../../static/js/state/index.js';

const CORE_SCHEMA = [
    { key: 'loras', category: 'core', sub_type: null },
    { key: 'checkpoints', category: 'core', sub_type: null },
    { key: 'unet', category: 'core', sub_type: null },
    { key: 'embeddings', category: 'core', sub_type: null },
];

const OTHER_SCHEMA = [
    { key: 'vae', category: 'other', sub_type: 'vae' },
    { key: 'controlnet', category: 'other', sub_type: 'controlnet' },
];

const createManager = () => {
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

const buildModalDom = () => {
    document.body.innerHTML = `
        <nav class="settings-nav">
            <ul class="settings-nav-list">
                <li class="settings-nav-group">
                    <button type="button" class="settings-nav-item active" data-section="general">General</button>
                </li>
            </ul>
        </nav>
        <div class="settings-form">
            <div class="settings-section active" id="section-general" data-section="general"></div>
        </div>
    `;
};

const setStandaloneSettings = (overrides = {}) => {
    state.global.settings = {
        standalone_mode: true,
        folder_paths: {},
        folder_path_schema: [...CORE_SCHEMA, ...OTHER_SCHEMA],
        enable_other_models: false,
        enabled_other_sub_types: [],
        ...overrides,
    };
};

beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
    bannerService.banners.clear();
});

afterEach(() => {
    delete global.fetch;
});

describe('SettingsManager Model Paths section', () => {
    it('does not create the section in plugin mode', () => {
        buildModalDom();
        state.global.settings = { standalone_mode: false };

        const manager = createManager();
        manager.setupModelPathsSection();

        expect(document.querySelector('.settings-nav-item[data-section="modelPaths"]')).toBeNull();
        expect(document.getElementById('section-modelPaths')).toBeNull();
    });

    it('creates nav item and section in standalone mode', () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.setupModelPathsSection();

        expect(document.querySelector('.settings-nav-item[data-section="modelPaths"]')).not.toBeNull();
        expect(document.getElementById('section-modelPaths')).not.toBeNull();
    });

    it('switches sections when the nav item is clicked', () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.setupModelPathsSection();

        document.querySelector('.settings-nav-item[data-section="modelPaths"]').click();

        expect(document.getElementById('section-modelPaths').classList.contains('active')).toBe(true);
        expect(document.getElementById('section-general').classList.contains('active')).toBe(false);
    });

    it('static nav clicks clear the Model Paths active state (regression)', () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.setupModelPathsSection();
        // Static nav items were bound before the Model Paths button existed;
        // their handler must still clear its active state.
        manager.initializeNavigation();

        const modelPathsNav = document.querySelector('.settings-nav-item[data-section="modelPaths"]');
        modelPathsNav.click();
        expect(modelPathsNav.classList.contains('active')).toBe(true);

        document.querySelector('.settings-nav-item[data-section="general"]').click();

        expect(modelPathsNav.classList.contains('active')).toBe(false);
        expect(document.getElementById('section-modelPaths').classList.contains('active')).toBe(false);
        expect(document.getElementById('section-general').classList.contains('active')).toBe(true);
    });

    it('renders core editors and only enabled other-model editors', () => {
        buildModalDom();
        setStandaloneSettings({
            enable_other_models: true,
            enabled_other_sub_types: ['vae'],
            folder_paths: { loras: ['/models/loras'] },
        });

        const manager = createManager();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        // Core editors always rendered
        CORE_SCHEMA.forEach(({ key }) => {
            expect(document.getElementById(`modelFolderPaths-${key}`)).not.toBeNull();
        });

        // Only the enabled other-model sub-type is rendered
        expect(document.getElementById('modelFolderPaths-vae')).not.toBeNull();
        expect(document.getElementById('modelFolderPaths-controlnet')).toBeNull();
        expect(document.getElementById('modelPathsOtherEmpty').style.display).toBe('none');

        // Existing values populate rows
        const loraInput = document.querySelector('#modelFolderPaths-loras .extra-folder-path-input');
        expect(loraInput.value).toBe('/models/loras');
    });

    it('shows the empty hint when no other-model types are enabled', () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        expect(document.getElementById('modelPathsOtherEmpty').style.display).toBe('block');
        expect(document.getElementById('modelFolderPaths-vae')).toBeNull();
    });

    it('renders inline enable controls synced with current settings', () => {
        buildModalDom();
        setStandaloneSettings({
            enable_other_models: true,
            enabled_other_sub_types: ['vae'],
        });

        const manager = createManager();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        const master = document.getElementById('modelPathsEnableOtherModels');
        expect(master).not.toBeNull();
        expect(master.checked).toBe(true);

        const vaeBox = document.querySelector('[data-model-paths-subtype="vae"]');
        const controlnetBox = document.querySelector('[data-model-paths-subtype="controlnet"]');
        expect(vaeBox.checked).toBe(true);
        expect(vaeBox.disabled).toBe(false);
        expect(controlnetBox.checked).toBe(false);
    });

    it('inline master toggle saves the setting and re-renders editors', async () => {
        buildModalDom();
        setStandaloneSettings({
            enable_other_models: true,
            enabled_other_sub_types: ['vae'],
        });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockImplementation(async (key, value) => {
            state.global.settings[key] = value;
        });
        manager.loadOtherRoots = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        expect(document.getElementById('modelFolderPaths-vae')).not.toBeNull();

        const master = document.getElementById('modelPathsEnableOtherModels');
        master.checked = false;
        await manager.handleModelPathsEnableOtherModels();

        expect(manager.saveSetting).toHaveBeenCalledWith('enable_other_models', false);
        expect(state.global.settings.enable_other_models).toBe(false);
        // Editors removed in place, empty hint back
        expect(document.getElementById('modelFolderPaths-vae')).toBeNull();
        expect(document.getElementById('modelPathsOtherEmpty').style.display).toBe('block');
    });

    it('inline sub-type checkboxes save the allow-list and re-render editors', async () => {
        buildModalDom();
        setStandaloneSettings({
            enable_other_models: true,
            enabled_other_sub_types: ['vae'],
        });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockImplementation(async (key, value) => {
            state.global.settings[key] = value;
        });
        manager.loadOtherRoots = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        document.querySelector('[data-model-paths-subtype="controlnet"]').checked = true;
        await manager.handleModelPathsSubTypeToggles();

        expect(manager.saveSetting).toHaveBeenCalledWith('enabled_other_sub_types', ['vae', 'controlnet']);
        expect(document.getElementById('modelFolderPaths-controlnet')).not.toBeNull();
    });

    it('saves collected folder paths via saveSetting', async () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        // No rows exist until the user clicks Add
        expect(document.querySelector('#modelFolderPaths-loras .extra-folder-path-input')).toBeNull();

        manager.addModelFolderPathRow('loras');
        document.querySelector('#modelFolderPaths-loras .extra-folder-path-input').value = '/data/loras';

        await manager.updateModelFolderPaths('loras');

        expect(manager.saveSetting).toHaveBeenCalledWith('folder_paths', {
            loras: ['/data/loras'],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
        expect(state.global.settings.folder_paths.loras).toEqual(['/data/loras']);
    });

    it('blocks saving when checkpoints and unet share a path', async () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        manager.addModelFolderPathRow('checkpoints');
        manager.addModelFolderPathRow('unet');
        document.querySelector('#modelFolderPaths-checkpoints .extra-folder-path-input').value = '/same/dir';
        document.querySelector('#modelFolderPaths-unet .extra-folder-path-input').value = '/same/dir';

        await manager.updateModelFolderPaths('checkpoints');

        expect(manager.saveSetting).not.toHaveBeenCalled();
        const ckptInput = document.querySelector('#modelFolderPaths-checkpoints .extra-folder-path-input');
        expect(ckptInput.classList.contains('has-error')).toBe(true);
    });

    it('appends a trailing empty row after filling one, but not after a removal', async () => {
        buildModalDom();
        setStandaloneSettings({ folder_paths: { loras: ['/data/a'] } });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        // Fill the trailing empty row -> save appends a fresh empty row
        manager.addModelFolderPathRow('loras');
        const rows = () => document.querySelectorAll('#modelFolderPaths-loras .extra-folder-path-row');
        expect(rows()).toHaveLength(2);
        rows()[1].querySelector('.extra-folder-path-input').value = '/data/b';
        await manager.updateModelFolderPaths('loras');
        expect(rows()).toHaveLength(3);

        // Removing a row never resurrects an empty row
        const removeBtn = rows()[0].querySelector('.remove-path-btn');
        manager.removeModelFolderPathRow(removeBtn, 'loras');
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalledTimes(2);
        });
        // Two rows left: the saved '/data/b' plus the pre-existing trailing
        // empty row — removal must not append yet another empty row.
        expect(rows()).toHaveLength(2);
        const emptyRows = Array.from(rows()).filter(
            (row) => row.querySelector('.extra-folder-path-input').value === '',
        );
        expect(emptyRows).toHaveLength(1);
    });

    it('restores previous state when saving fails', async () => {
        buildModalDom();
        setStandaloneSettings({ folder_paths: { loras: ['/original'] } });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockRejectedValue(new Error('nope'));
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        const input = document.querySelector('#modelFolderPaths-loras .extra-folder-path-input');
        input.value = '/changed';

        await manager.updateModelFolderPaths('loras');

        expect(state.global.settings.folder_paths).toEqual({ loras: ['/original'] });
        // Rows reloaded from restored state
        const reloaded = document.querySelector('#modelFolderPaths-loras .extra-folder-path-input');
        expect(reloaded.value).toBe('/original');
    });

    it('marks pending-restart cues after a successful save', async () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        const navItem = document.querySelector('.settings-nav-item[data-section="modelPaths"]');
        expect(navItem.classList.contains('has-pending-restart')).toBe(false);

        manager.addModelFolderPathRow('loras');
        document.querySelector('#modelFolderPaths-loras .extra-folder-path-input').value = '/data/loras';
        await manager.updateModelFolderPaths('loras');

        expect(navItem.classList.contains('has-pending-restart')).toBe(true);
        expect(document.getElementById('modelPathsRestartNotice').classList.contains('visible')).toBe(true);

        // A unique-per-change banner id: dismissing it once must not mute
        // future reminders (dismissed ids persist across restarts).
        const restartBanners = Array.from(bannerService.banners.keys())
            .filter((id) => id.startsWith('model-paths-restart-'));
        expect(restartBanners).toHaveLength(1);
    });

    it('gives the restart banner a higher priority than startup warnings', async () => {
        buildModalDom();
        setStandaloneSettings();

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        manager.addModelFolderPathRow('loras');
        document.querySelector('#modelFolderPaths-loras .extra-folder-path-input').value = '/data/loras';
        await manager.updateModelFolderPaths('loras');

        const restartBanner = Array.from(bannerService.banners.values())
            .find((banner) => banner.id.startsWith('model-paths-restart-'));
        // Startup warnings map to 60; the restart cue must outrank them so it
        // preempts the "model folders need setup" prompt in the banner pager.
        expect(restartBanner.priority).toBeGreaterThan(60);
    });

    it('removes the "model folders need setup" startup banner once a path is saved', async () => {
        buildModalDom();
        setStandaloneSettings();

        bannerService.registerBanner('startup-missing-model-paths', {
            id: 'startup-missing-model-paths',
            title: 'Model folders need setup',
            content: 'stub',
            dismissible: false,
            priority: 60,
        });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        manager.addModelFolderPathRow('loras');
        document.querySelector('#modelFolderPaths-loras .extra-folder-path-input').value = '/data/loras';
        await manager.updateModelFolderPaths('loras');

        expect(bannerService.banners.has('startup-missing-model-paths')).toBe(false);
    });

    it('keeps the setup banner when the saved paths are all empty', async () => {
        buildModalDom();
        setStandaloneSettings({ folder_paths: { loras: ['/data/loras'] } });

        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.setupModelPathsSection();
        manager.loadModelPaths();

        bannerService.registerBanner('startup-missing-model-paths', {
            id: 'startup-missing-model-paths',
            title: 'Model folders need setup',
            content: 'stub',
            dismissible: false,
            priority: 60,
        });

        // Clear every row and save: an all-empty path set must not retire the
        // setup prompt.
        document.querySelectorAll('#modelFolderPaths-loras .extra-folder-path-input')
            .forEach((input) => { input.value = ''; });
        await manager.updateModelFolderPaths('loras');

        expect(manager.saveSetting).toHaveBeenCalled();
        expect(bannerService.banners.has('startup-missing-model-paths')).toBe(true);
    });
});
