import { describe, it, expect, beforeEach, vi } from 'vitest';

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
        },
        createDefaultSettings: () => ({
            language: 'en',
            download_skip_base_models: [],
        }),
    };
});

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    resetAndReload: vi.fn(),
}));

vi.mock('../../../static/js/utils/constants.js', () => ({
    DOWNLOAD_PATH_TEMPLATES: {},
    DEFAULT_PATH_TEMPLATES: {},
    MAPPABLE_BASE_MODELS: ['Flux.1 D', 'Pony', 'SDXL 1.0', 'Other'],
    PATH_TEMPLATE_PLACEHOLDERS: {},
    DEFAULT_PRIORITY_TAG_CONFIG: {
        lora: 'character, style',
        checkpoint: 'base, guide',
        embedding: 'hint',
    },
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: (key, params, fallback) => {
        if (key === 'settings.downloadSkipBaseModels.summary.none') {
            return 'None selected';
        }
        if (key === 'settings.downloadSkipBaseModels.summary.count') {
            return `${params?.count ?? 0} selected`;
        }
        return fallback ?? '';
    },
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

vi.mock('../../../static/js/managers/BannerService.js', () => ({
    bannerService: {
        registerBanner: vi.fn(),
    },
}));

vi.mock('../../../static/js/components/SidebarManager.js', () => ({
    sidebarManager: {
        setSidebarEnabled: vi.fn().mockResolvedValue(),
    },
}));

import { SettingsManager } from '../../../static/js/managers/SettingsManager.js';
import { state } from '../../../static/js/state/index.js';

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

const appendDownloadSkipUi = () => {
    document.body.innerHTML = `
        <button id="downloadSkipBaseModelsToggle" aria-expanded="false">
            <span id="downloadSkipBaseModelsSummary"></span>
            <span class="base-model-skip-toggle-label"></span>
        </button>
        <div id="downloadSkipBaseModelsPanel" hidden>
            <input id="downloadSkipBaseModelsSearch" />
            <button id="downloadSkipBaseModelsClear" type="button">Clear</button>
            <div id="downloadSkipBaseModelsContainer"></div>
            <div id="downloadSkipBaseModelsEmpty" hidden></div>
        </div>
        <div id="downloadSkipBaseModelsError"></div>
    `;
};

describe('SettingsManager download skip base models UI', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_skip_base_models: [],
        };
    });

    it('renders a compact summary for selected base models', () => {
        appendDownloadSkipUi();
        state.global.settings.download_skip_base_models = ['Flux.1 D', 'Pony'];
        const manager = createManager();

        manager.renderDownloadSkipBaseModels();

        expect(document.getElementById('downloadSkipBaseModelsSummary').textContent).toBe('Flux.1 D, Pony');
        expect(document.querySelectorAll('#downloadSkipBaseModelsContainer input')).toHaveLength(3);
    });

    it('filters the list using the search input and shows an empty state', () => {
        appendDownloadSkipUi();
        state.global.settings.download_skip_base_models = ['Flux.1 D'];
        const manager = createManager();
        const searchInput = document.getElementById('downloadSkipBaseModelsSearch');

        searchInput.value = 'pony';
        manager.renderDownloadSkipBaseModels();

        expect(document.querySelectorAll('#downloadSkipBaseModelsContainer input')).toHaveLength(1);
        expect(document.querySelector('#downloadSkipBaseModelsContainer input').value).toBe('Pony');

        searchInput.value = 'zzz';
        manager.renderDownloadSkipBaseModels();

        expect(document.querySelectorAll('#downloadSkipBaseModelsContainer input')).toHaveLength(0);
        expect(document.getElementById('downloadSkipBaseModelsEmpty').hidden).toBe(false);
    });
});
