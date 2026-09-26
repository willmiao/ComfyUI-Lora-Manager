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
            sidecar_storage_mode: 'alongside',
            sidecar_storage_path: '',
        }),
    };
});

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    resetAndReload: vi.fn(),
    getModelApiClient: vi.fn(),
}));

vi.mock('../../../static/js/utils/constants.js', () => ({
    DOWNLOAD_PATH_TEMPLATES: {},
    DEFAULT_PATH_TEMPLATES: {},
    MAPPABLE_BASE_MODELS: [],
    PATH_TEMPLATE_PLACEHOLDERS: {},
    FILENAME_TEMPLATE_PLACEHOLDERS: [],
    DEFAULT_FILENAME_TEMPLATES: { lora: '', checkpoint: '', embedding: '' },
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
import { resetAndReload } from '../../../static/js/api/modelApiFactory.js';
import { state } from '../../../static/js/state/index.js';

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

const appendSidecarControls = () => {
    const select = document.createElement('select');
    select.id = 'sidecarStorageMode';
    ['alongside', 'centralized'].forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        select.appendChild(option);
    });

    const pathSetting = document.createElement('div');
    pathSetting.id = 'sidecarStoragePathSetting';
    pathSetting.style.display = 'none';

    const pathInput = document.createElement('input');
    pathInput.id = 'sidecarStoragePath';

    const migrateBtn = document.createElement('button');
    migrateBtn.id = 'migrateSidecarsBtn';

    document.body.append(select, pathSetting, pathInput, migrateBtn);
    return { select, pathSetting, pathInput, migrateBtn };
};

const appendMigrationModal = () => {
    const modal = document.createElement('div');
    modal.id = 'sidecarMigrationConfirmModal';
    modal.innerHTML = `
        <h2 data-role="title"></h2>
        <p data-role="message"></p>
        <button data-action="confirm-sidecar-migration"></button>
        <button data-action="cancel-sidecar-migration"></button>`;
    document.body.appendChild(modal);
    return modal;
};

const mockFetchOk = (payload = { success: true }) => {
    global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
    });
};

beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
});

afterEach(() => {
    delete global.fetch;
});

describe('SettingsManager sidecar storage', () => {
    describe('loadSidecarStorageSettings', () => {
        it('loads alongside mode and hides the centralized path input', () => {
            const manager = createManager();
            const { select, pathSetting, pathInput } = appendSidecarControls();
            state.global.settings = { sidecar_storage_mode: 'alongside', sidecar_storage_path: '/data/sidecars' };

            manager.loadSidecarStorageSettings();

            expect(select.value).toBe('alongside');
            expect(pathInput.value).toBe('/data/sidecars');
            expect(pathSetting.style.display).toBe('none');
            expect(manager._loadedSidecarStorageMode).toBe('alongside');
        });

        it('loads centralized mode and shows the path input', () => {
            const manager = createManager();
            const { select, pathSetting } = appendSidecarControls();
            state.global.settings = { sidecar_storage_mode: 'centralized' };

            manager.loadSidecarStorageSettings();

            expect(select.value).toBe('centralized');
            expect(pathSetting.style.display).toBe('block');
            expect(manager._loadedSidecarStorageMode).toBe('centralized');
        });

        it('falls back to alongside for unknown stored modes', () => {
            const manager = createManager();
            const { select } = appendSidecarControls();
            state.global.settings = { sidecar_storage_mode: 'bogus' };

            manager.loadSidecarStorageSettings();

            expect(select.value).toBe('alongside');
        });
    });

    describe('handleSidecarStorageModeChange', () => {
        it('does not prompt for migration when the mode is unchanged', async () => {
            const manager = createManager();
            const { select } = appendSidecarControls();
            appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'alongside' };
            manager._loadedSidecarStorageMode = 'alongside';
            select.value = 'alongside';
            mockFetchOk();

            await manager.handleSidecarStorageModeChange();

            expect(global.fetch).not.toHaveBeenCalledWith(
                '/api/lm/sidecars/migrate',
                expect.anything()
            );
            expect(showToast).toHaveBeenCalledWith(
                'toast.settings.settingsUpdated',
                expect.anything(),
                'success'
            );
        });

        it('migrates to centralized after the user confirms the prompt', async () => {
            const manager = createManager();
            const { select, pathSetting } = appendSidecarControls();
            const modal = appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'alongside' };
            manager._loadedSidecarStorageMode = 'alongside';
            select.value = 'centralized';
            mockFetchOk();

            const changePromise = manager.handleSidecarStorageModeChange();

            await vi.waitFor(() => expect(modal.classList.contains('show')).toBe(true));
            modal.querySelector('[data-action="confirm-sidecar-migration"]').click();
            await changePromise;

            expect(state.global.settings.sidecar_storage_mode).toBe('centralized');
            expect(pathSetting.style.display).toBe('block');
            expect(global.fetch).toHaveBeenCalledWith('/api/lm/sidecars/migrate', expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ direction: 'to_centralized', force: true }),
            }));
            expect(showToast).toHaveBeenCalledWith('settings.sidecarStorage.migrateSuccess', {}, 'success');
            expect(resetAndReload).toHaveBeenCalledWith(true);
            expect(modal.classList.contains('show')).toBe(false);
        });

        it('shows a deferred notice and skips migration when the user cancels', async () => {
            const manager = createManager();
            const { select } = appendSidecarControls();
            const modal = appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'centralized' };
            manager._loadedSidecarStorageMode = 'centralized';
            select.value = 'alongside';
            mockFetchOk();

            const changePromise = manager.handleSidecarStorageModeChange();
            await vi.waitFor(() => expect(modal.classList.contains('show')).toBe(true));
            modal.querySelector('[data-action="cancel-sidecar-migration"]').click();
            await changePromise;

            const migrateCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/lm/sidecars/migrate');
            expect(migrateCalls).toHaveLength(0);
            expect(showToast).toHaveBeenCalledWith('settings.sidecarStorage.migrationDeferred', {}, 'info');
        });
    });

    describe('confirmAndMigrateSidecars', () => {
        it('derives the migration direction from the saved mode', async () => {
            const manager = createManager();
            appendSidecarControls();
            const modal = appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'centralized' };
            mockFetchOk();

            const confirmPromise = manager.confirmAndMigrateSidecars();
            await vi.waitFor(() => expect(modal.classList.contains('show')).toBe(true));
            modal.querySelector('[data-action="confirm-sidecar-migration"]').click();
            await confirmPromise;

            expect(global.fetch).toHaveBeenCalledWith('/api/lm/sidecars/migrate', expect.objectContaining({
                body: JSON.stringify({ direction: 'to_centralized', force: true }),
            }));
        });
    });

    describe('migrateSidecars', () => {
        it('surfaces backend failures as an error toast', async () => {
            const manager = createManager();
            const { migrateBtn } = appendSidecarControls();
            mockFetchOk({ success: false, error: 'disk full' });

            await manager.migrateSidecars('to_alongside');

            expect(showToast).toHaveBeenCalledWith(
                'settings.sidecarStorage.migrateFailed',
                { message: 'disk full' },
                'error'
            );
            expect(resetAndReload).not.toHaveBeenCalled();
            expect(migrateBtn.disabled).toBe(false);
        });
    });

    describe('handleSidecarStoragePathChange', () => {
        it('offers root relocation when the path changes in centralized mode', async () => {
            const manager = createManager();
            const { pathInput } = appendSidecarControls();
            const modal = appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'centralized', sidecar_storage_path: '/old/root' };
            manager._loadedSidecarStoragePath = '/old/root';
            pathInput.value = '/new/root';
            mockFetchOk();

            const changePromise = manager.handleSidecarStoragePathChange();
            await vi.waitFor(() => expect(modal.classList.contains('show')).toBe(true));
            modal.querySelector('[data-action="confirm-sidecar-migration"]').click();
            await changePromise;

            expect(global.fetch).toHaveBeenCalledWith('/api/lm/sidecars/migrate', expect.objectContaining({
                body: JSON.stringify({ direction: 'relocate_root', force: true, old_root: '/old/root' }),
            }));
            expect(manager._loadedSidecarStoragePath).toBe('/new/root');
        });

        it('does not prompt when the path changes in alongside mode', async () => {
            const manager = createManager();
            const { pathInput } = appendSidecarControls();
            appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'alongside', sidecar_storage_path: '/old/root' };
            manager._loadedSidecarStoragePath = '/old/root';
            pathInput.value = '/new/root';
            mockFetchOk();

            await manager.handleSidecarStoragePathChange();

            const migrateCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/lm/sidecars/migrate');
            expect(migrateCalls).toHaveLength(0);
        });

        it('shows a deferred notice when relocation is cancelled', async () => {
            const manager = createManager();
            const { pathInput } = appendSidecarControls();
            const modal = appendMigrationModal();
            state.global.settings = { sidecar_storage_mode: 'centralized', sidecar_storage_path: '/old/root' };
            manager._loadedSidecarStoragePath = '/old/root';
            pathInput.value = '/new/root';
            mockFetchOk();

            const changePromise = manager.handleSidecarStoragePathChange();
            await vi.waitFor(() => expect(modal.classList.contains('show')).toBe(true));
            modal.querySelector('[data-action="cancel-sidecar-migration"]').click();
            await changePromise;

            const migrateCalls = global.fetch.mock.calls.filter(([url]) => url === '/api/lm/sidecars/migrate');
            expect(migrateCalls).toHaveLength(0);
            expect(showToast).toHaveBeenCalledWith('settings.sidecarStorage.migrationDeferred', {}, 'info');
        });
    });
});
