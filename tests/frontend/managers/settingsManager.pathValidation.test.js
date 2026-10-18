import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
    modalManager: {
        closeModal: vi.fn(),
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));

vi.mock('../../../static/js/state/index.js', () => ({
    state: {
        global: {
            settings: {},
        },
        loadingManager: {
            showSimpleLoading: vi.fn(),
            hide: vi.fn(),
        },
    },
    createDefaultSettings: () => ({
        language: 'en',
    }),
}));

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

vi.mock('../../../static/js/components/DirectoryPickerModal.js', () => ({
    directoryPickerModal: {
        open: vi.fn(),
        close: vi.fn(),
    },
}));

import { SettingsManager } from '../../../static/js/managers/SettingsManager.js';
import { directoryPickerModal } from '../../../static/js/components/DirectoryPickerModal.js';

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

const appendPathInput = (id = 'recipesPath') => {
    const wrapper = document.createElement('div');
    wrapper.className = 'text-input-wrapper';
    const input = document.createElement('input');
    input.type = 'text';
    input.id = id;
    wrapper.appendChild(input);
    document.body.appendChild(wrapper);
    return input;
};

const validResponse = (path) => ({
    ok: true,
    json: async () => ({
        success: true,
        path,
        exists: true,
        is_directory: true,
        readable: true,
        writable: true,
        error_code: null,
    }),
});

const invalidResponse = (errorCode) => ({
    ok: true,
    json: async () => ({
        success: true,
        path: '/missing',
        exists: false,
        is_directory: false,
        readable: false,
        writable: false,
        error_code: errorCode,
        error: `server: ${errorCode}`,
    }),
});

beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
});

afterEach(() => {
    vi.useRealTimers();
    delete global.fetch;
});

describe('SettingsManager.attachPathField', () => {
    it('keeps the input in its wrapper and injects an inset browse button and a status element', () => {
        const manager = createManager();
        const input = appendPathInput();

        manager.attachPathField('recipesPath');

        const wrapper = input.parentElement;
        expect(wrapper.classList.contains('text-input-wrapper')).toBe(true);
        const browseBtn = wrapper.querySelector('.browse-path-btn.inset');
        expect(browseBtn).not.toBeNull();
        expect(browseBtn.querySelector('i.fas.fa-folder-open')).not.toBeNull();
        expect(input.classList.contains('has-inset-browse')).toBe(true);
        expect(wrapper.querySelector('.path-validation')).not.toBeNull();
    });

    it('is idempotent — a second call does not duplicate the button', () => {
        const manager = createManager();
        const input = appendPathInput();

        manager.attachPathField('recipesPath');
        manager.attachPathField('recipesPath');

        expect(document.querySelectorAll('.browse-path-btn')).toHaveLength(1);
        expect(document.querySelectorAll('.path-validation')).toHaveLength(1);
        expect(input.dataset.pathFieldAttached).toBe('1');
    });

    it('wraps only the input for insetting when inside .path-control, leaving siblings in place', () => {
        const manager = createManager();
        const container = document.createElement('div');
        container.className = 'setting-control path-control';
        const input = document.createElement('input');
        input.type = 'text';
        input.id = 'exampleImagesPath';
        const downloadBtn = document.createElement('button');
        downloadBtn.id = 'exampleImagesDownloadBtn';
        container.appendChild(input);
        container.appendChild(downloadBtn);
        document.body.appendChild(container);

        manager.attachPathField('exampleImagesPath');

        const wrapper = input.parentElement;
        expect(wrapper.classList.contains('text-input-wrapper')).toBe(true);
        expect(wrapper.parentElement).toBe(container);
        const browseBtn = wrapper.querySelector('.browse-path-btn.inset');
        expect(browseBtn).not.toBeNull();
        expect(wrapper.nextElementSibling).toBe(downloadBtn);
        expect(container.querySelector('.path-validation')).not.toBeNull();
    });

    it('warns and no-ops when the input is missing', () => {
        const manager = createManager();
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

        manager.attachPathField('doesNotExist');

        expect(warnSpy).toHaveBeenCalled();
        warnSpy.mockRestore();
    });
});

describe('SettingsManager.validatePath', () => {
    it('posts to /api/lm/validate-path on blur with expect directory', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/data/recipes';
        global.fetch = vi.fn().mockResolvedValue(validResponse('/data/recipes'));

        manager.attachPathField('recipesPath');
        input.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));

        const [url, options] = global.fetch.mock.calls[0];
        expect(url).toBe('/api/lm/validate-path');
        expect(options.method).toBe('POST');
        expect(JSON.parse(options.body)).toEqual({ path: '/data/recipes', expect: 'directory' });
    });

    it('debounces rapid input events into a single validation call', async () => {
        vi.useFakeTimers();
        const manager = createManager();
        const input = appendPathInput();
        global.fetch = vi.fn().mockResolvedValue(validResponse('/data'));

        manager.attachPathField('recipesPath');
        input.value = '/d';
        input.dispatchEvent(new Event('input'));
        input.value = '/da';
        input.dispatchEvent(new Event('input'));
        input.value = '/data';
        input.dispatchEvent(new Event('input'));

        await vi.advanceTimersByTimeAsync(499);
        expect(global.fetch).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1);
        expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it('renders a valid status for a valid path', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/data/recipes';
        global.fetch = vi.fn().mockResolvedValue(validResponse('/data/recipes'));

        manager.attachPathField('recipesPath');
        input.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(document.querySelector('.path-validation').classList.contains('visible')).toBe(true);
        });

        const statusEl = document.querySelector('.path-validation');
        expect(statusEl.classList.contains('valid')).toBe(true);
        expect(statusEl.textContent).toContain('Path is valid');
        expect(statusEl.querySelector('i.fas.fa-check-circle')).not.toBeNull();
    });

    it('renders an error status mapped from error_code', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/missing';
        global.fetch = vi.fn().mockResolvedValue(invalidResponse('path_not_found'));

        manager.attachPathField('recipesPath');
        input.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(document.querySelector('.path-validation').classList.contains('visible')).toBe(true);
        });

        const statusEl = document.querySelector('.path-validation');
        expect(statusEl.classList.contains('valid')).toBe(false);
        expect(statusEl.textContent).toContain('Path does not exist');
    });

    it('ignores stale responses overtaken by a newer value', async () => {
        const manager = createManager();
        const input = appendPathInput();

        const deferreds = [];
        global.fetch = vi.fn().mockImplementation(() => new Promise((resolve) => {
            deferreds.push(resolve);
        }));

        manager.attachPathField('recipesPath');

        input.value = '/old-path';
        input.dispatchEvent(new Event('blur'));
        input.value = '/new-path';
        input.dispatchEvent(new Event('blur'));
        expect(global.fetch).toHaveBeenCalledTimes(2);

        // Newer request resolves first and renders valid status.
        deferreds[1](validResponse('/new-path'));
        await vi.waitFor(() => {
            expect(document.querySelector('.path-validation').classList.contains('valid')).toBe(true);
        });

        // Older request resolves late and must not overwrite the status.
        deferreds[0](invalidResponse('path_not_found'));
        await Promise.resolve();
        await Promise.resolve();

        const statusEl = document.querySelector('.path-validation');
        expect(statusEl.classList.contains('valid')).toBe(true);
        expect(statusEl.textContent).toContain('Path is valid');
    });

    it('clears the status and skips fetch when the value is empty', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/data';
        global.fetch = vi.fn().mockResolvedValue(validResponse('/data'));

        manager.attachPathField('recipesPath');
        input.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(document.querySelector('.path-validation').classList.contains('visible')).toBe(true);
        });

        global.fetch.mockClear();
        input.value = '';
        input.dispatchEvent(new Event('blur'));
        await Promise.resolve();

        const statusEl = document.querySelector('.path-validation');
        expect(global.fetch).not.toHaveBeenCalled();
        expect(statusEl.classList.contains('visible')).toBe(false);
        expect(statusEl.textContent).toBe('');
    });

    it('clears the status silently on network failure', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/data';
        global.fetch = vi.fn().mockRejectedValue(new Error('network down'));

        manager.attachPathField('recipesPath');
        input.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
        await Promise.resolve();
        await Promise.resolve();

        const statusEl = document.querySelector('.path-validation');
        expect(statusEl.classList.contains('visible')).toBe(false);
    });
});

describe('SettingsManager.browseForPath', () => {
    it('opens the picker with the current value and applies the selection', async () => {
        const manager = createManager();
        const input = appendPathInput();
        input.value = '/initial';
        const onAfterSelect = vi.fn();
        global.fetch = vi.fn().mockResolvedValue(validResponse('/picked'));

        manager.attachPathField('recipesPath', { onAfterSelect });
        manager.browseForPath('recipesPath');

        expect(directoryPickerModal.open).toHaveBeenCalledTimes(1);
        const openArgs = directoryPickerModal.open.mock.calls[0][0];
        expect(openArgs.initialPath).toBe('/initial');

        openArgs.onSelect('/picked');

        expect(input.value).toBe('/picked');
        expect(onAfterSelect).toHaveBeenCalledWith('/picked');
        await vi.waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
        expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({
            path: '/picked',
            expect: 'directory',
        });
    });
});

describe('SettingsManager dynamic path rows', () => {
    const appendExtraFolderContainer = (modelType = 'loras') => {
        const container = document.createElement('div');
        container.id = `extraFolderPaths-${modelType}`;
        document.body.appendChild(container);
        return container;
    };

    it('renders a browse button in extra folder path rows', () => {
        const manager = createManager();
        appendExtraFolderContainer('loras');

        manager.addExtraFolderPathRow('loras', '/models/loras', false);

        const row = document.querySelector('.extra-folder-path-row');
        const browseBtn = row.querySelector('.browse-path-btn');
        expect(browseBtn).not.toBeNull();
        expect(browseBtn.querySelector('i.fas.fa-folder-open')).not.toBeNull();
        // Browse button sits before the remove button.
        expect(browseBtn.nextElementSibling.classList.contains('remove-path-btn')).toBe(true);
    });

    it('picker selection routes through updateExtraFolderPaths', () => {
        const manager = createManager();
        appendExtraFolderContainer('loras');
        const updateSpy = vi
            .spyOn(manager, 'updateExtraFolderPaths')
            .mockResolvedValue();

        manager.addExtraFolderPathRow('loras', '/models/loras', false);
        const row = document.querySelector('.extra-folder-path-row');
        const input = row.querySelector('.extra-folder-path-input');
        const browseBtn = row.querySelector('.browse-path-btn');

        manager.browseForPathRow(browseBtn, 'loras');

        expect(directoryPickerModal.open).toHaveBeenCalledTimes(1);
        const openArgs = directoryPickerModal.open.mock.calls[0][0];
        expect(openArgs.initialPath).toBe('/models/loras');

        openArgs.onSelect('/picked/loras');

        expect(input.value).toBe('/picked/loras');
        expect(updateSpy).toHaveBeenCalledWith('loras');
    });

    it('model path rows route through updateModelFolderPaths', () => {
        const manager = createManager();
        const container = document.createElement('div');
        container.id = 'modelFolderPaths-loras';
        document.body.appendChild(container);
        const updateSpy = vi
            .spyOn(manager, 'updateModelFolderPaths')
            .mockResolvedValue();

        manager.addModelFolderPathRow('loras', '/models/loras', false);
        const row = container.querySelector('.extra-folder-path-row');
        const input = row.querySelector('.extra-folder-path-input');
        const browseBtn = row.querySelector('.browse-path-btn');
        expect(browseBtn).not.toBeNull();

        manager.browseForPathRow(browseBtn, 'loras', true);
        const openArgs = directoryPickerModal.open.mock.calls[0][0];
        openArgs.onSelect('/picked/loras');

        expect(input.value).toBe('/picked/loras');
        expect(updateSpy).toHaveBeenCalledWith('loras');
    });
});
