import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Same dependency mocks as FilterManager.tagLogic.test.js: the manager touches
// storage, toasts, the API factory and the preset manager on construction.
vi.mock('../../../static/js/state/index.js', () => ({
    getCurrentPageState: vi.fn(() => ({
        filters: {},
    })),
    state: {
        currentPageType: 'loras',
        loadingManager: {
            showSimpleLoading: vi.fn(),
            hide: vi.fn(),
        },
    },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
    updatePanelPositions: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    getModelApiClient: vi.fn(() => ({
        loadMoreWithVirtualScroll: vi.fn().mockResolvedValue(),
    })),
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getStorageItem: vi.fn(),
    setStorageItem: vi.fn(),
    removeStorageItem: vi.fn(),
}));

vi.mock('../../../static/js/managers/FilterPresetManager.js', () => ({
    FilterPresetManager: vi.fn().mockImplementation(() => ({
        renderPresets: vi.fn(),
        saveActivePreset: vi.fn(),
        restoreActivePreset: vi.fn(),
        updateAddButtonState: vi.fn(),
        hasEmptyWildcardResult: vi.fn(() => false),
    })),
    EMPTY_WILDCARD_MARKER: '__EMPTY_WILDCARD_RESULT__',
}));

import { FilterManager } from '../../../static/js/managers/FilterManager.js';
import { i18n } from '../../../static/js/i18n/index.js';

const BASE_MODELS = [
    { name: 'Illustrious', count: 19876 },
    { name: 'Pony', count: 5210 },
    { name: 'SD 1.5', count: 7 },
];

const MODEL_TYPES = [
    { type: 'lora', count: 19876 },
    { type: 'locon', count: 12 },
];

function jsonResponse(payload) {
    return { ok: true, json: async () => payload };
}

/**
 * Build a manager whose filter panel sections are populated from the mocked
 * endpoints, i.e. through the real render path rather than by hand.
 */
async function createManagerWithChips() {
    global.fetch = vi.fn(async (url) => {
        const target = String(url);
        if (target.includes('/base-models')) {
            return jsonResponse({ success: true, base_models: BASE_MODELS });
        }
        if (target.includes('/model-types')) {
            return jsonResponse({ success: true, model_types: MODEL_TYPES });
        }
        return jsonResponse({ success: false });
    });

    const manager = new FilterManager({ page: 'loras' });
    // createBaseModelTags/createModelTypeTags are fire-and-forget fetches.
    await vi.waitFor(() => {
        expect(document.querySelectorAll('.model-type-tag').length).toBe(MODEL_TYPES.length);
    });
    return manager;
}

let originalLocale;

beforeEach(() => {
    originalLocale = i18n.currentLocale;
    i18n.currentLocale = 'en';

    // translate() resolves through window.i18n. Stubbing it lets the tests see
    // which key a call site picked (the recipes page uses its own sentence);
    // unknown keys fall back to the caller's English string, as in production.
    window.i18n = {
        t: (key, params) => {
            if (key === 'header.filter.countTitle') {
                return `${params.name} — ${params.count} models`;
            }
            if (key === 'recipes.filter.countTitle') {
                return `${params.name} — ${params.count} recipes`;
            }
            return key;
        },
    };

    document.body.innerHTML = `
        <button id="filterButton"></button>
        <div id="filterPanel" class="hidden">
            <input id="baseModelSearchInput">
            <input id="modelTagsSearchInput">
            <div class="filter-tags" id="baseModelTags"></div>
            <div id="baseModelEmptyState" hidden></div>
            <div class="filter-tags" id="modelTagsFilter"></div>
            <div id="modelTagsEmptyState" hidden></div>
            <div class="filter-tags" id="modelTypeTags"></div>
            <div id="tagLogicToggle">
                <button class="tag-logic-option" data-value="any"></button>
                <button class="tag-logic-option" data-value="all"></button>
            </div>
        </div>
    `;
});

afterEach(() => {
    i18n.currentLocale = originalLocale;
    delete window.i18n;
    delete global.fetch;
    document.body.innerHTML = '';
});

describe('FilterManager chip counts', () => {
    it('renders base model and model type chips as name + count slots', async () => {
        await createManagerWithChips();

        const baseModelChip = document.querySelector('.base-model-tag');
        expect(baseModelChip.querySelector('.tag-name').textContent).toBe('Illustrious');
        expect(baseModelChip.querySelector('.tag-count').textContent).toBe('19.9K');
        expect(baseModelChip.title).toBe('Illustrious — 19,876 models');
        expect(baseModelChip.getAttribute('aria-label')).toBe('Illustrious — 19,876 models');

        const typeChip = document.querySelector('.model-type-tag');
        expect(typeChip.querySelector('.tag-name').textContent).toBe('LoRA');
        expect(typeChip.querySelector('.tag-count').textContent).toBe('19.9K');
        expect(typeChip.title).toBe('LoRA — 19,876 models');
    });

    it('keeps the tooltip on every chip, abbreviated or not', async () => {
        await createManagerWithChips();

        const ponyChip = [...document.querySelectorAll('.base-model-tag')]
            .find((chip) => chip.dataset.baseModel === 'Pony');
        // The pill is already exact — the tooltip still exists, so hovering a
        // count does not depend on the magnitude (or on the library size).
        expect(ponyChip.querySelector('.tag-count').textContent).toBe('5,210');
        expect(ponyChip.title).toBe('Pony — 5,210 models');
    });

    it('renders tag chips with the same structure and count formatting', async () => {
        const manager = await createManagerWithChips();

        manager.createTagFilterElements([
            { tag: 'character', count: 19876 },
            { tag: 'style', count: 42 },
        ]);

        const chips = document.querySelectorAll('#modelTagsFilter .tag-filter');
        expect(chips[0].querySelector('.tag-name').textContent).toBe('character');
        expect(chips[0].querySelector('.tag-count').textContent).toBe('19.9K');
        expect(chips[0].title).toBe('character — 19,876 models');

        expect(chips[1].querySelector('.tag-name').textContent).toBe('style');
        expect(chips[1].querySelector('.tag-count').textContent).toBe('42');
        expect(chips[1].title).toBe('style — 42 models');
        // Trailing "No tags" chip carries no count.
        expect(chips[2].querySelector('.tag-count')).toBeNull();
    });

    it('counts recipes, not models, on the recipes page', async () => {
        global.fetch = vi.fn(async (url) => {
            const target = String(url);
            if (target.includes('/base-models')) {
                return jsonResponse({ success: true, base_models: BASE_MODELS });
            }
            return jsonResponse({ success: false });
        });

        new FilterManager({ page: 'recipes' });
        await vi.waitFor(() => {
            expect(document.querySelectorAll('.base-model-tag').length).toBe(BASE_MODELS.length);
        });

        const chip = document.querySelector('.base-model-tag');
        expect(chip.querySelector('.tag-count').textContent).toBe('19.9K');
        expect(chip.title).toBe('Illustrious — 19,876 recipes');
    });

    it('treats tag names as text, never as markup', async () => {
        const manager = await createManagerWithChips();

        manager.createTagFilterElements([{ tag: '<img src=x onerror=alert(1)>', count: 5 }]);

        const chip = document.querySelector('#modelTagsFilter .tag-filter');
        expect(chip.querySelector('.tag-name').textContent).toBe('<img src=x onerror=alert(1)>');
        expect(chip.querySelector('img')).toBeNull();
    });
});
