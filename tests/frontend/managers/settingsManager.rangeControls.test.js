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
    },
    createDefaultSettings: () => ({
        language: 'en',
    }),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    resetAndReload: vi.fn(),
    getModelApiClient: () => ({}),
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

// Call the range helpers on a bare prototype object: constructing the manager
// would run its full initialization against the module mocks.
const createManager = () => Object.create(SettingsManager.prototype);

function appendRange({ min, max, value, step = '0.5', format = 'seconds' } = {}) {
    const displayId = 'rangeValueDisplay';
    const input = document.createElement('input');
    input.type = 'range';
    input.id = 'rangeInput';
    input.min = min;
    input.max = max;
    input.step = step;
    input.value = value;
    input.dataset.rangeDisplay = displayId;
    input.dataset.rangeFormat = format;

    const display = document.createElement('span');
    display.id = displayId;

    document.body.append(input, display);
    return { input, display };
}

beforeEach(() => {
    document.body.innerHTML = '';
    window.i18n = { getCurrentLocale: () => 'en' };
});

afterEach(() => {
    delete window.i18n;
});

describe('SettingsManager range controls', () => {
    it('formats the interval in locale-aware seconds', () => {
        const manager = createManager();
        const { input, display } = appendRange({ min: '0.5', max: '3', value: '2' });

        manager.updateRangeControl(input);

        expect(display.textContent).toBe('2s');
    });

    it('uses the current locale for the unit', () => {
        window.i18n = { getCurrentLocale: () => 'zh-CN' };
        const manager = createManager();
        const { input, display } = appendRange({ min: '0.5', max: '3', value: '2' });

        manager.updateRangeControl(input);

        expect(display.textContent).toBe('2秒');
    });

    it('fills the track relative to the slider min and max', () => {
        const manager = createManager();

        const low = appendRange({ min: '0.5', max: '3', value: '0.5' });
        manager.updateRangeControl(low.input);
        expect(parseFloat(low.input.style.getPropertyValue('--range-fill'))).toBe(0);

        const mid = appendRange({ min: '0.5', max: '3', value: '2' });
        manager.updateRangeControl(mid.input);
        expect(parseFloat(mid.input.style.getPropertyValue('--range-fill'))).toBeCloseTo(60, 1);

        const high = appendRange({ min: '0.5', max: '3', value: '3' });
        manager.updateRangeControl(high.input);
        expect(parseFloat(high.input.style.getPropertyValue('--range-fill'))).toBe(100);
    });

    it('keeps the px label for sliders without a seconds format', () => {
        const manager = createManager();
        const { input, display } = appendRange({
            min: '0', max: '20', value: '8', step: '1', format: 'px',
        });

        manager.updateRangeControl(input);

        expect(display.textContent).toBe('8px');
        expect(parseFloat(input.style.getPropertyValue('--range-fill'))).toBe(40);
    });

    it('saves sub-second intervals as numbers instead of truncating them', async () => {
        const manager = createManager();
        manager.saveSetting = vi.fn().mockResolvedValue();
        manager.applyFrontendSettings = vi.fn();
        const { input } = appendRange({ min: '0.5', max: '3', value: '1.5' });

        await manager.saveRangeSetting('rangeInput', 'card_preview_cycle_interval');

        expect(manager.saveSetting).toHaveBeenCalledWith('card_preview_cycle_interval', 1.5);
    });
});
