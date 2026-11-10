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
            auto_organize_exclusions: [],
            metadata_refresh_skip_paths: [],
            send_to_workflow_exclusions: { node_classes: [], title_patterns: [] },
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
import { showToast } from '../../../static/js/utils/uiHelpers.js';
import { state } from '../../../static/js/state/index.js';

const flushPromises = () => new Promise(resolve => setTimeout(resolve, 0));

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

const appendExclusionUi = () => {
    document.body.innerHTML = `
        <textarea id="autoOrganizeExclusions"></textarea>
        <div id="autoOrganizeExclusionsError"></div>
        <textarea id="metadataRefreshSkipPaths"></textarea>
        <div id="metadataRefreshSkipPathsError"></div>
        <textarea id="sendToWorkflowExcludedClasses"></textarea>
        <div id="sendToWorkflowExcludedClassesError"></div>
        <textarea id="sendToWorkflowExcludedTitles"></textarea>
        <div id="sendToWorkflowExcludedTitlesError"></div>
    `;
};

const stubSaveSetting = (manager, implementation = () => Promise.resolve()) => {
    const saveSetting = vi.fn(implementation);
    manager.saveSetting = saveSetting;
    return saveSetting;
};

const typeAndBlur = async (input, value) => {
    input.value = value;
    input.dispatchEvent(new Event('blur'));
    await flushPromises();
};

const pressKey = (input, key, options = {}) => {
    const event = new KeyboardEvent('keydown', {
        key,
        bubbles: true,
        cancelable: true,
        ...options,
    });
    input.dispatchEvent(event);
    return event;
};

describe('SettingsManager exclusion textareas commit on blur', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            auto_organize_exclusions: [],
            metadata_refresh_skip_paths: [],
            send_to_workflow_exclusions: { node_classes: [], title_patterns: [] },
        };
    });

    it('saves auto-organize exclusions when the textarea loses focus', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('autoOrganizeExclusions'), 'curated/*; */backups/*');

        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(saveSetting).toHaveBeenCalledWith(
            'auto_organize_exclusions',
            ['curated/*', '*/backups/*']
        );
        expect(showToast).toHaveBeenCalledWith(
            'toast.settings.settingsUpdated',
            expect.anything(),
            'success'
        );
    });

    it('saves metadata refresh skip paths when the textarea loses focus', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('metadataRefreshSkipPaths'), 'temp, archived/old');

        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(saveSetting).toHaveBeenCalledWith(
            'metadata_refresh_skip_paths',
            ['temp', 'archived/old']
        );
    });

    it('saves both send-to-workflow lists from either textarea', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        document.getElementById('sendToWorkflowExcludedClasses').value = 'CheckpointLoaderSimple, MyCustomNode';
        await typeAndBlur(document.getElementById('sendToWorkflowExcludedTitles'), 'negative; preview');

        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(saveSetting).toHaveBeenCalledWith('send_to_workflow_exclusions', {
            node_classes: ['CheckpointLoaderSimple', 'MyCustomNode'],
            title_patterns: ['negative', 'preview'],
        });
    });

    it('does not save when the normalized value is already stored', async () => {
        appendExclusionUi();
        state.global.settings.auto_organize_exclusions = ['curated/*'];
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('autoOrganizeExclusions'), 'curated/* , curated/*');

        expect(saveSetting).not.toHaveBeenCalled();
        expect(showToast).not.toHaveBeenCalled();
    });

    it('reports the validation error instead of saving an empty pattern list', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('autoOrganizeExclusions'), ' , ');

        expect(saveSetting).not.toHaveBeenCalled();
        expect(document.getElementById('autoOrganizeExclusionsError').textContent).not.toBe('');
    });

    it('does not attach duplicate handlers when setup runs twice', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('autoOrganizeExclusions'), 'curated/*');

        expect(saveSetting).toHaveBeenCalledTimes(1);
    });
});

describe('SettingsManager exclusion textareas commit on Enter', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            auto_organize_exclusions: [],
            metadata_refresh_skip_paths: [],
            send_to_workflow_exclusions: { node_classes: [], title_patterns: [] },
        };
    });

    it('blurs the field and commits once on Enter', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        const input = document.getElementById('autoOrganizeExclusions');
        input.focus();
        input.value = 'curated/*';

        const event = pressKey(input, 'Enter');
        await flushPromises();

        expect(event.defaultPrevented).toBe(true);
        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(saveSetting).toHaveBeenCalledWith('auto_organize_exclusions', ['curated/*']);
    });

    it('keeps Shift+Enter as a newline and does not commit', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        const input = document.getElementById('autoOrganizeExclusions');
        input.focus();
        input.value = 'curated/*';

        const event = pressKey(input, 'Enter', { shiftKey: true });
        await flushPromises();

        expect(event.defaultPrevented).toBe(false);
        expect(saveSetting).not.toHaveBeenCalled();
    });

    it('commits on Escape before the modal closes', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        const input = document.getElementById('metadataRefreshSkipPaths');
        input.focus();
        input.value = 'temp';

        const event = pressKey(input, 'Escape');
        await flushPromises();

        // Escape must still reach the modal manager and close the modal.
        expect(event.defaultPrevented).toBe(false);
        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(saveSetting).toHaveBeenCalledWith('metadata_refresh_skip_paths', ['temp']);
    });
});

describe('SettingsManager exclusion textareas write-back race', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            auto_organize_exclusions: [],
            metadata_refresh_skip_paths: [],
            send_to_workflow_exclusions: { node_classes: [], title_patterns: [] },
        };
    });

    it('does not overwrite the field the user re-entered while saving', async () => {
        appendExclusionUi();
        const manager = createManager();
        let releaseSave;
        const saveSetting = stubSaveSetting(manager, () => new Promise(resolve => {
            releaseSave = resolve;
        }));
        manager.setupExclusionTextareaHandlers();

        const input = document.getElementById('autoOrganizeExclusions');
        input.value = 'curated/*';
        input.dispatchEvent(new Event('blur'));

        input.focus();
        input.value = 'curated/*, extra/*';

        releaseSave();
        await flushPromises();

        expect(saveSetting).toHaveBeenCalledTimes(1);
        expect(input.value).toBe('curated/*, extra/*');
    });

    it('normalizes the field once the save completes while it is unfocused', async () => {
        appendExclusionUi();
        const manager = createManager();
        const saveSetting = stubSaveSetting(manager);
        manager.setupExclusionTextareaHandlers();

        await typeAndBlur(document.getElementById('autoOrganizeExclusions'), 'a;b,a');

        expect(saveSetting).toHaveBeenCalledWith('auto_organize_exclusions', ['a', 'b']);
        expect(document.getElementById('autoOrganizeExclusions').value).toBe('a, b');
    });
});
