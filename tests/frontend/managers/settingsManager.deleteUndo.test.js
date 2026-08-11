import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

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
            delete_undo_enabled: true,
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

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');

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

const appendDeleteUndoCheckbox = () => {
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'deleteUndoEnabled';
    document.body.appendChild(checkbox);
    return checkbox;
};

const stubLoadSettingsSubloaders = (manager) => {
    vi.spyOn(manager, 'loadMetadataArchiveSettings').mockResolvedValue();
    vi.spyOn(manager, 'loadBackupSettings').mockResolvedValue();
    vi.spyOn(manager, 'loadLibraries').mockResolvedValue();
    vi.spyOn(manager, 'loadLoraRoots').mockResolvedValue();
    vi.spyOn(manager, 'loadCheckpointRoots').mockResolvedValue();
    vi.spyOn(manager, 'loadUnetRoots').mockResolvedValue();
    vi.spyOn(manager, 'loadEmbeddingRoots').mockResolvedValue();
};

beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
});

afterEach(() => {
    delete global.fetch;
});

describe('SettingsManager delete undo toggle', () => {
    it('renders the checkbox markup with a resolvable i18n label', () => {
        const template = readFileSync(
            resolve(repoRoot, 'templates/components/modals/settings_modal.html'),
            'utf8',
        );
        const locales = JSON.parse(
            readFileSync(resolve(repoRoot, 'locales/en.json'), 'utf8'),
        );

        // The label must resolve to real text, not fall back to the raw key.
        expect(locales.settings.deleteUndoEnabled).toBe(
            'Keep deleted items recoverable for 30 seconds (undo)',
        );
        expect(template).toContain('id="deleteUndoEnabled"');
        expect(template).toContain("t('settings.deleteUndoEnabled')");
        expect(template).toContain(
            "settingsManager.saveToggleSetting('deleteUndoEnabled', 'delete_undo_enabled')",
        );
    });

    it('restores the checkbox as unchecked when the saved setting is false', async () => {
        const manager = createManager();
        const checkbox = appendDeleteUndoCheckbox();
        checkbox.checked = true;

        stubLoadSettingsSubloaders(manager);
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        state.global.settings = { delete_undo_enabled: false };

        await manager.loadSettingsToUI();

        expect(checkbox.checked).toBe(false);
    });

    it('restores the checkbox as checked when the saved setting is true or absent', async () => {
        const manager = createManager();
        const checkbox = appendDeleteUndoCheckbox();

        stubLoadSettingsSubloaders(manager);
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        state.global.settings = { delete_undo_enabled: true };
        await manager.loadSettingsToUI();
        expect(checkbox.checked).toBe(true);

        checkbox.checked = false;
        state.global.settings = {};
        await manager.loadSettingsToUI();
        expect(checkbox.checked).toBe(true);
    });

    it('saves delete_undo_enabled to the backend when the checkbox is toggled', async () => {
        const manager = createManager();
        const checkbox = appendDeleteUndoCheckbox();
        checkbox.checked = false;

        state.global.settings = { delete_undo_enabled: true };

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        await manager.saveToggleSetting('deleteUndoEnabled', 'delete_undo_enabled');

        expect(state.global.settings.delete_undo_enabled).toBe(false);
        expect(global.fetch).toHaveBeenCalledWith('/api/lm/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ delete_undo_enabled: false }),
        });
        expect(showToast).toHaveBeenCalledWith(
            'toast.settings.settingsUpdated',
            { setting: 'delete undo enabled' },
            'success',
        );
    });

    it('saves delete_undo_enabled as true when re-enabled', async () => {
        const manager = createManager();
        const checkbox = appendDeleteUndoCheckbox();
        checkbox.checked = true;

        state.global.settings = { delete_undo_enabled: false };

        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        await manager.saveToggleSetting('deleteUndoEnabled', 'delete_undo_enabled');

        expect(state.global.settings.delete_undo_enabled).toBe(true);
        expect(global.fetch).toHaveBeenCalledWith('/api/lm/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ delete_undo_enabled: true }),
        });
    });
});
