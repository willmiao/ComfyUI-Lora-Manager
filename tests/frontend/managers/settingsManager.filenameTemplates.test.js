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
            download_filename_templates: { lora: '', checkpoint: '', embedding: '' },
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
    PATH_TEMPLATE_PLACEHOLDERS: [],
    FILENAME_TEMPLATE_PLACEHOLDERS: [
        '{model_name}',
        '{version_name}',
        '{base_model}',
        '{author}',
        '{first_tag}',
        '{hash_short}',
        '{original_name}',
    ],
    DEFAULT_FILENAME_TEMPLATES: { lora: '', checkpoint: '', embedding: '' },
    DEFAULT_PRIORITY_TAG_CONFIG: {
        lora: 'character, style',
        checkpoint: 'base, guide',
        embedding: 'hint',
    },
    getMappableBaseModelsDynamic: () => [],
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: (key, params, fallback) => {
        if (params && fallback) {
            return fallback.replace(/\{(\w+)\}/g, (match, name) => params[name] ?? match);
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
import { resetAndReload, getModelApiClient } from '../../../static/js/api/modelApiFactory.js';

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

const appendFilenameTemplateUi = (modelType = 'lora') => {
    document.body.innerHTML = `
        <input id="${modelType}FilenameTemplate" />
        <div id="${modelType}FilenameValidation"></div>
        <div id="${modelType}FilenamePreview"></div>
        <button id="${modelType}ApplyFilenameTemplate" type="button"></button>
    `;
};

const appendConfirmModal = () => {
    document.body.insertAdjacentHTML('beforeend', `
        <div id="filenameTemplateConfirmModal" class="modal delete-modal">
            <h2 data-role="title"></h2>
            <p data-role="message"></p>
            <button data-action="cancel-filename-template"></button>
            <button data-action="confirm-filename-template"></button>
        </div>
    `);
};

describe('SettingsManager filename templates', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_filename_templates: { lora: '', checkpoint: '', embedding: '' },
        };
    });

    it('treats an empty template as valid (restores original filenames)', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        expect(manager.validateFilenameTemplate('lora', '')).toBe(true);

        const validation = document.getElementById('loraFilenameValidation');
        expect(validation.classList.contains('valid')).toBe(true);
        expect(validation.textContent).toContain('restores original filenames');
    });

    it('rejects templates with path separators or OS-illegal characters', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        expect(manager.validateFilenameTemplate('lora', '{base_model}/{model_name}')).toBe(false);
        expect(manager.validateFilenameTemplate('lora', 'a:b')).toBe(false);

        const validation = document.getElementById('loraFilenameValidation');
        expect(validation.classList.contains('invalid')).toBe(true);
    });

    it('rejects unknown placeholders', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        expect(manager.validateFilenameTemplate('lora', '{bogus}-{model_name}')).toBe(false);

        const validation = document.getElementById('loraFilenameValidation');
        expect(validation.textContent).toContain('{bogus}');
    });

    it('accepts a template using only known placeholders', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        const template = '{base_model}-{model_name}-{version_name}-{hash_short}';
        expect(manager.validateFilenameTemplate('lora', template)).toBe(true);
        expect(document.getElementById('loraFilenameValidation').classList.contains('valid')).toBe(true);
    });

    it('saves a valid template via saveSetting with the merged dict', () => {
        appendFilenameTemplateUi();
        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();

        manager.updateFilenameTemplate('lora', '{model_name}');

        expect(state.global.settings.download_filename_templates.lora).toBe('{model_name}');
        expect(manager.saveSetting).toHaveBeenCalledWith(
            'download_filename_templates',
            { lora: '{model_name}', checkpoint: '', embedding: '' },
        );
    });

    it('does not save an invalid template', () => {
        appendFilenameTemplateUi();
        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();

        manager.updateFilenameTemplate('lora', '{unknown_placeholder}');

        expect(state.global.settings.download_filename_templates.lora).toBe('');
        expect(manager.saveSetting).not.toHaveBeenCalled();
    });

    it('previews the recorded original filename when the template is empty', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        manager.updateFilenamePreview('lora', '');

        expect(document.getElementById('loraFilenamePreview').textContent).toBe('V1.safetensors');
    });

    it('renders a preview with example placeholder values', () => {
        appendFilenameTemplateUi();
        const manager = createManager();

        manager.updateFilenamePreview('lora', '{base_model}-{model_name}-{version_name}-{hash_short}');

        expect(document.getElementById('loraFilenamePreview').textContent)
            .toBe('Flux.1 D-model-name-v3-a1b2c3d4e5.safetensors');
    });

    it('applies an empty template as a revert after modal confirmation', async () => {
        appendFilenameTemplateUi();
        appendConfirmModal();
        const manager = createManager();
        const apiClient = { applyFilenameTemplate: vi.fn().mockResolvedValue() };
        getModelApiClient.mockReturnValue(apiClient);

        const applyPromise = manager.applyFilenameTemplate('lora');

        const modal = document.getElementById('filenameTemplateConfirmModal');
        expect(modal.classList.contains('show')).toBe(true);
        expect(modal.querySelector('[data-role="title"]').textContent)
            .toBe('Restore original filenames?');
        expect(modal.querySelector('[data-role="message"]').textContent)
            .toContain('Restore the recorded original filename');
        expect(modal.querySelector('[data-action="confirm-filename-template"]').textContent)
            .toBe('Restore Original Filenames');

        modal.querySelector('[data-action="confirm-filename-template"]').click();
        await applyPromise;

        expect(getModelApiClient).toHaveBeenCalledWith('loras');
        expect(apiClient.applyFilenameTemplate).toHaveBeenCalledWith();
        expect(resetAndReload).toHaveBeenCalledWith(true);
        expect(modal.classList.contains('show')).toBe(false);
    });

    it('does not revert when the modal is cancelled', async () => {
        appendFilenameTemplateUi();
        appendConfirmModal();
        const manager = createManager();

        const applyPromise = manager.applyFilenameTemplate('lora');
        document.querySelector('[data-action="cancel-filename-template"]').click();
        await applyPromise;

        expect(getModelApiClient).not.toHaveBeenCalled();
        expect(resetAndReload).not.toHaveBeenCalled();
    });

    it('merges backend download_filename_templates over defaults', () => {
        const manager = createManager();

        const merged = manager.mergeSettingsWithDefaults({
            download_filename_templates: { lora: '{model_name}' },
        });
        expect(merged.download_filename_templates).toEqual({
            lora: '{model_name}',
            checkpoint: '',
            embedding: '',
        });

        const fromString = manager.mergeSettingsWithDefaults({
            download_filename_templates: '{"checkpoint":"{hash_short}"}',
        });
        expect(fromString.download_filename_templates).toEqual({
            lora: '',
            checkpoint: '{hash_short}',
            embedding: '',
        });
    });

    it('applies the template through the model API client and reloads', async () => {
        appendFilenameTemplateUi();
        state.global.settings.download_filename_templates.lora = '{model_name}';
        const manager = createManager();
        const apiClient = { applyFilenameTemplate: vi.fn().mockResolvedValue() };
        getModelApiClient.mockReturnValue(apiClient);

        await manager.applyFilenameTemplate('lora');

        expect(getModelApiClient).toHaveBeenCalledWith('loras');
        expect(apiClient.applyFilenameTemplate).toHaveBeenCalledWith();
        expect(resetAndReload).toHaveBeenCalledWith(true);
    });

    it('shows the apply wording for a non-empty template and honours cancellation', async () => {
        appendFilenameTemplateUi();
        appendConfirmModal();
        state.global.settings.download_filename_templates.lora = '{model_name}';
        const manager = createManager();

        const applyPromise = manager.applyFilenameTemplate('lora');

        const modal = document.getElementById('filenameTemplateConfirmModal');
        expect(modal.classList.contains('show')).toBe(true);
        expect(modal.querySelector('[data-role="title"]').textContent)
            .toBe('Apply filename template to library?');
        expect(modal.querySelector('[data-role="message"]').textContent)
            .toContain('Rename all existing files');

        modal.querySelector('[data-action="cancel-filename-template"]').click();
        await applyPromise;

        expect(getModelApiClient).not.toHaveBeenCalled();
        expect(resetAndReload).not.toHaveBeenCalled();
        expect(modal.classList.contains('show')).toBe(false);
    });
});
