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
            skip_previously_downloaded_model_versions: false,
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
    FILENAME_TEMPLATE_PLACEHOLDERS: [],
    DEFAULT_FILENAME_TEMPLATES: { lora: '', checkpoint: '', embedding: '' },
    DEFAULT_PRIORITY_TAG_CONFIG: {
        lora: 'character, style',
        checkpoint: 'base, guide',
        embedding: 'hint',
    },
    getMappableBaseModelsDynamic: () => ['Flux.1 D', 'Pony', 'SDXL 1.0', 'Other'],
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

const appendAuthorTemplatesUi = () => {
    document.body.innerHTML = '<div id="authorPathTemplatesContainer"></div>';
};

const rows = () => Array.from(document.querySelectorAll('#authorPathTemplatesContainer .mapping-row'));

describe('SettingsManager author path templates UI', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = { author_path_templates: { reijlita: '{base_model}/reijlita' } };
    });

    it('renders saved templates plus an empty row, with values set as text', () => {
        appendAuthorTemplatesUi();
        state.global.settings.author_path_templates['<b>x</b>'] = '{author}';
        const manager = createManager();

        manager.loadAuthorPathTemplates();

        expect(rows()).toHaveLength(3);
        expect(rows()[0].querySelector('.author-input').value).toBe('reijlita');
        expect(rows()[0].querySelector('.path-value-input').value).toBe('{base_model}/reijlita');
        expect(rows()[1].querySelector('.author-input').value).toBe('<b>x</b>');
        expect(document.querySelector('#authorPathTemplatesContainer b')).toBeNull();
    });

    it('saves complete rows only and keeps one empty row', () => {
        appendAuthorTemplatesUi();
        const manager = createManager();
        const saveSpy = vi.spyOn(manager, 'saveSetting').mockResolvedValue();
        manager.loadAuthorPathTemplates();

        const empty = rows()[1];
        empty.querySelector('.author-input').value = ' someone ';
        empty.querySelector('.path-value-input').value = 'Flux/someone';
        manager.updateAuthorPathTemplates();

        expect(saveSpy).toHaveBeenCalledWith('author_path_templates', {
            reijlita: '{base_model}/reijlita',
            someone: 'Flux/someone',
        });
        expect(rows()).toHaveLength(3);

        rows()[0].querySelector('.remove-mapping-btn').click();

        expect(saveSpy).toHaveBeenLastCalledWith('author_path_templates', { someone: 'Flux/someone' });
    });
});
