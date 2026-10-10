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
            download_root_rules: { loras: [], checkpoints: [], unet: [], embeddings: [] },
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

const ROOTS = {
    loras: ['/models/loras-main', '/models/lora-archive'],
    checkpoints: ['/models/checkpoints'],
    unet: ['/models/unet-main', '/models/unet-archive'],
    embeddings: [],
};

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

    manager.saveSetting = vi.fn().mockResolvedValue();
    manager.downloadRootRuleRoots = ROOTS;

    return manager;
};

const appendDownloadRootRulesUi = () => {
    document.body.innerHTML = `
        <div id="downloadRootRulesContainer"></div>
        <div id="downloadRootRulesError"></div>
    `;
};

const groupRows = (typeKey) =>
    document.querySelectorAll(
        `#downloadRootRulesContainer .download-root-rule-row[data-rule-type="${typeKey}"]`
    );

describe('SettingsManager download root rules', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_root_rules: { loras: [], checkpoints: [], unet: [], embeddings: [] },
        };
    });

    it('normalizes malformed rules out of the setting', () => {
        const manager = createManager();

        const normalized = manager.normalizeDownloadRootRules({
            loras: [
                { match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' },
                { match_type: 'base_model', match: [], root: '/models/lora-archive' },
                { match_type: 'base_model', match: ['Pony'], root: '' },
                null,
                'not-a-rule',
            ],
            embeddings: 'oops',
            unknownType: [{ match_type: 'base_model', match: ['Pony'], root: '/x' }],
        });

        expect(normalized).toEqual({
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
    });

    it('renders one group per type and a hint when no roots are configured', () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D', 'Pony'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();

        manager.renderDownloadRootRules();

        expect(document.querySelectorAll('.download-root-rule-group')).toHaveLength(4);
        expect(groupRows('loras')).toHaveLength(1);
        expect(groupRows('loras')[0].querySelector('.download-root-rule-summary').textContent)
            .toBe('Flux.1 D, Pony');
        expect(groupRows('loras')[0].querySelector('select.download-root-rule-root').value)
            .toBe('/models/lora-archive');
        // embeddings has no roots configured
        const embeddingsGroup = document.querySelectorAll('.download-root-rule-group')[3];
        expect(embeddingsGroup.querySelector('.download-root-rules-hint')).not.toBeNull();
        expect(embeddingsGroup.querySelector('.add-mapping-btn')).toBeNull();
    });

    it('add rule creates a draft and the first base model selection promotes and persists it', async () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.renderDownloadRootRules();

        manager.addDownloadRootRule('loras');

        expect(manager.downloadRootRuleDrafts.loras).toEqual({
            match_type: 'base_model',
            match: [],
            root: '/models/loras-main',
        });
        expect(groupRows('loras')).toHaveLength(1);
        // A second add while a draft exists is a no-op
        manager.addDownloadRootRule('loras');
        expect(groupRows('loras')).toHaveLength(1);

        // The draft row panel is open; tick a base model checkbox
        const checkbox = groupRows('loras')[0].querySelector(
            '.download-root-rule-panel input[value="Flux.1 D"]'
        );
        checkbox.checked = true;
        checkbox.dispatchEvent(new Event('change'));
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.downloadRootRuleDrafts.loras).toBeUndefined();
        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/loras-main' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
        expect(state.global.settings.download_root_rules.loras).toHaveLength(1);
    });

    it('removing a rule persists the updated list', async () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [
                { match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' },
                { match_type: 'base_model', match: ['Pony'], root: '/models/loras-main' },
            ],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        manager.removeDownloadRootRule('loras', 0, false);
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [{ match_type: 'base_model', match: ['Pony'], root: '/models/loras-main' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
    });

    it('move down swaps rule order and persists', async () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [
                { match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' },
                { match_type: 'base_model', match: ['Pony'], root: '/models/loras-main' },
            ],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        manager.moveDownloadRootRule('loras', 0, 1);
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [
                { match_type: 'base_model', match: ['Pony'], root: '/models/loras-main' },
                { match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' },
            ],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });

        // Out-of-range moves are no-ops
        manager.saveSetting.mockClear();
        manager.moveDownloadRootRule('loras', 1, 1);
        expect(manager.saveSetting).not.toHaveBeenCalled();
    });

    it('unchecking the last base model of a persisted rule removes the rule', async () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        const row = groupRows('loras')[0];
        const checkbox = row.querySelector('.download-root-rule-panel input[value="Flux.1 D"]');
        expect(checkbox.checked).toBe(true);
        checkbox.checked = false;
        checkbox.dispatchEvent(new Event('change'));
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
        expect(groupRows('loras')).toHaveLength(0);
    });

    it('loadDownloadRootRules fetches roots for every type and renders', async () => {
        appendDownloadRootRulesUi();
        const fetchMock = vi.fn().mockImplementation(async (url) => ({
            ok: true,
            json: async () => {
                if (url.includes('loras/roots')) return { roots: ROOTS.loras };
                if (url.includes('checkpoints_roots')) return { roots: ROOTS.checkpoints };
                if (url.includes('unet_roots')) return { roots: ROOTS.unet };
                if (url.includes('embeddings/roots')) return { roots: [] };
                return {};
            },
        }));
        vi.stubGlobal('fetch', fetchMock);
        try {
            const manager = createManager();
            manager.downloadRootRuleRoots = null;

            await manager.loadDownloadRootRules();

            expect(manager.downloadRootRuleRoots).toEqual(ROOTS);
            expect(document.querySelectorAll('.download-root-rule-group')).toHaveLength(4);
            expect(document.getElementById('downloadRootRulesError').textContent).toBe('');
        } finally {
            vi.unstubAllGlobals();
        }
    });
});

describe('SettingsManager download root rules default-root cue', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_root_rules: { loras: [], checkpoints: [], unet: [], embeddings: [] },
        };
    });

    const defaultHintFor = (typeIndex) =>
        document.querySelectorAll('.download-root-rule-group')[typeIndex]
            .querySelector('.download-root-rule-default-hint');

    it('renders a default hint under the group header when a default root is set', () => {
        appendDownloadRootRulesUi();
        state.global.settings.default_lora_root = '/models/loras-main';
        const manager = createManager();

        manager.renderDownloadRootRules();

        expect(defaultHintFor(0).textContent)
            .toBe('Default: /models/loras-main — unmatched downloads go here');
    });

    it('omits the default hint when the type has no roots or no default root', () => {
        appendDownloadRootRulesUi();
        state.global.settings.default_lora_root = '';
        state.global.settings.default_embedding_root = '/models/embeddings';
        const manager = createManager();

        manager.renderDownloadRootRules();

        // loras: default root is empty -> no hint
        expect(defaultHintFor(0)).toBeNull();
        // embeddings: no roots configured -> noRoots hint only, no default hint
        expect(defaultHintFor(3)).toBeNull();
    });

    it('marks the default root option with a (default) suffix but keeps the plain value', () => {
        appendDownloadRootRulesUi();
        state.global.settings.default_lora_root = '/models/lora-archive';
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/loras-main' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();

        manager.renderDownloadRootRules();

        const options = groupRows('loras')[0].querySelectorAll('select.download-root-rule-root option');
        expect([...options].map((o) => o.value)).toEqual(['/models/loras-main', '/models/lora-archive']);
        expect([...options].map((o) => o.textContent)).toEqual([
            '/models/loras-main',
            '/models/lora-archive (default)',
        ]);
    });

    it('compares roots loosely: separators, trailing slashes and case are ignored', () => {
        const manager = createManager();

        expect(manager.isDownloadRootRuleDefaultRoot('C:\\Models\\Loras\\', 'c:/models/loras')).toBe(true);
        expect(manager.isDownloadRootRuleDefaultRoot('/a/b/', '/a/b')).toBe(true);
        expect(manager.isDownloadRootRuleDefaultRoot('/a/b', '/a/c')).toBe(false);
        expect(manager.isDownloadRootRuleDefaultRoot('/a/b', '')).toBe(false);
    });

    it('does not render groups before the roots have been fetched', () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.downloadRootRuleRoots = null;

        manager.renderDownloadRootRules();

        expect(document.querySelectorAll('.download-root-rule-group')).toHaveLength(0);
    });

    it('changing a default root select re-renders the rules editor with the new default', async () => {
        appendDownloadRootRulesUi();
        document.body.insertAdjacentHTML(
            'beforeend',
            '<select id="defaultLoraRoot"><option value="/models/loras-main">a</option><option value="/models/lora-archive" selected>b</option></select>'
        );
        state.global.settings.default_lora_root = '/models/loras-main';
        const manager = createManager();
        manager.applyFrontendSettings = vi.fn();
        // Mimic the real saveSetting, which writes the value into state.
        manager.saveSetting = vi.fn().mockImplementation(async (key, value) => {
            state.global.settings[key] = value;
        });

        manager.renderDownloadRootRules();
        expect(defaultHintFor(0).textContent)
            .toBe('Default: /models/loras-main — unmatched downloads go here');

        await manager.saveSelectSetting('defaultLoraRoot', 'default_lora_root');

        expect(manager.saveSetting).toHaveBeenCalledWith('default_lora_root', '/models/lora-archive');
        expect(defaultHintFor(0).textContent)
            .toBe('Default: /models/lora-archive — unmatched downloads go here');
    });
});


describe('SettingsManager download root rules tag matching', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_root_rules: { loras: [], checkpoints: [], unet: [], embeddings: [] },
        };
    });

    it('normalizes tag rules as free text with case-insensitive dedupe', () => {
        const manager = createManager();

        const normalized = manager.normalizeDownloadRootRules({
            loras: [
                { match_type: 'tag', match: [' character ', 'Style', 'CHARACTER'], root: '/models/lora-archive' },
                { match_type: 'tag', match: [], root: '/models/lora-archive' },
                { match_type: 'unknown', match: ['x'], root: '/models/lora-archive' },
                { match_type: 'tag', match: ['character'], root: '' },
            ],
        });

        expect(normalized.loras).toEqual([
            { match_type: 'tag', match: ['character', 'Style'], root: '/models/lora-archive' },
        ]);
    });

    it('renders a tag rule with a static type chip, summary and tag input', () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'tag', match: ['character', 'style'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();

        manager.renderDownloadRootRules();

        const row = groupRows('loras')[0];
        // The match type is fixed at creation: a chip, not a dropdown.
        const chip = row.querySelector('.download-root-rule-match-chip');
        expect(chip.textContent).toBe('Tag');
        expect(chip.title).toBe('Tag');
        expect(row.querySelector('.download-root-rule-match-type')).toBeNull();
        expect(row.querySelector('.download-root-rule-summary').textContent)
            .toBe('character, style');
        expect(row.querySelector('.download-root-rule-tag-input').value)
            .toBe('character, style');
        // No base model checkbox list for tag rules
        expect(row.querySelector('.base-model-skip-list')).toBeNull();
    });

    it('renders a base model rule chip with the full name as tooltip', () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();

        manager.renderDownloadRootRules();

        const chip = groupRows('loras')[0].querySelector('.download-root-rule-match-chip');
        expect(chip.textContent).toBe('BM');
        expect(chip.title).toBe('Base model');
    });

    it('a tag draft promotes on the first committed tag input', async () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.renderDownloadRootRules();

        manager.addDownloadRootRule('loras', 'tag');

        // Still a draft: nothing persisted yet
        expect(manager.saveSetting).not.toHaveBeenCalled();

        const tagInput = groupRows('loras')[0].querySelector('.download-root-rule-tag-input');
        tagInput.value = 'character, Style, CHARACTER';
        tagInput.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.downloadRootRuleDrafts.loras).toBeUndefined();
        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [{ match_type: 'tag', match: ['character', 'Style'], root: '/models/loras-main' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
    });

    it('committing an empty tag list on a persisted rule removes the rule', async () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'tag', match: ['character'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        const tagInput = groupRows('loras')[0].querySelector('.download-root-rule-tag-input');
        tagInput.value = '  , ';
        tagInput.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
        expect(groupRows('loras')).toHaveLength(0);
    });

    it('editing tags on a persisted rule parses, dedupes and persists', async () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'tag', match: ['character'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        const tagInput = groupRows('loras')[0].querySelector('.download-root-rule-tag-input');
        tagInput.value = 'realistic, style, REALISTIC';
        tagInput.dispatchEvent(new Event('blur'));
        await vi.waitFor(() => {
            expect(manager.saveSetting).toHaveBeenCalled();
        });

        expect(manager.saveSetting).toHaveBeenCalledWith('download_root_rules', {
            loras: [{ match_type: 'tag', match: ['realistic', 'style'], root: '/models/lora-archive' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        });
    });
});


describe('SettingsManager download root rules row layout', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        vi.clearAllMocks();
        state.global.settings = {
            download_root_rules: { loras: [], checkpoints: [], unet: [], embeddings: [] },
        };
    });

    it('offers separate add buttons for base model and tag rules', () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.renderDownloadRootRules();

        const buttons = document.querySelectorAll('.download-root-rule-group')[0]
            .querySelectorAll('.download-root-rule-add-row .add-mapping-btn');
        expect(buttons).toHaveLength(2);
        expect(buttons[0].textContent).toContain('Base model rule');
        expect(buttons[1].textContent).toContain('Tag rule');

        buttons[1].click();
        expect(manager.downloadRootRuleDrafts.loras.match_type).toBe('tag');

        // While a draft exists both buttons are disabled
        const disabledButtons = document.querySelectorAll('.download-root-rule-group')[0]
            .querySelectorAll('.download-root-rule-add-row .add-mapping-btn');
        expect([...disabledButtons].every((btn) => btn.disabled)).toBe(true);
    });

    it('base model add button creates a base_model draft', () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.renderDownloadRootRules();

        document.querySelectorAll('.download-root-rule-group')[0]
            .querySelectorAll('.download-root-rule-add-row .add-mapping-btn')[0]
            .click();

        expect(manager.downloadRootRuleDrafts.loras.match_type).toBe('base_model');
        expect(groupRows('loras')[0].querySelector('.download-root-rule-match-chip').textContent)
            .toBe('BM');
    });

    it('the summary toggle uses a chevron icon with accessible title and aria state', () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: '/models/loras-main' }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        const toggle = groupRows('loras')[0].querySelector('.download-root-rule-toggle');
        expect(toggle.querySelector('.download-root-rule-chevron')).not.toBeNull();
        expect(toggle.querySelector('.base-model-skip-toggle-label')).toBeNull();
        expect(toggle.getAttribute('aria-expanded')).toBe('false');
        expect(toggle.title).toBe('Edit');

        toggle.click();

        const reopened = groupRows('loras')[0].querySelector('.download-root-rule-toggle');
        expect(reopened.getAttribute('aria-expanded')).toBe('true');
        expect(reopened.title).toBe('Collapse');
    });

    it('truncateMiddlePath keeps short paths intact and ellipsizes long ones', () => {
        const manager = createManager();

        expect(manager.truncateMiddlePath('/models/loras')).toBe('/models/loras');

        const long = '/models/library/very/deeply/nested/folder/structure/loras';
        const truncated = manager.truncateMiddlePath(long);
        expect(truncated.startsWith(long.slice(0, 24))).toBe(true);
        expect(truncated.endsWith(long.slice(-16))).toBe(true);
        expect(truncated).toContain('…');
        expect(truncated.length).toBe(24 + 1 + 16);
    });

    it('truncates long root paths in the dropdown but keeps full values and titles', () => {
        appendDownloadRootRulesUi();
        const longRoot = '/models/library/very/deeply/nested/folder/structure/loras';
        const manager = createManager();
        manager.downloadRootRuleRoots = {
            loras: [longRoot],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: longRoot }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };

        manager.renderDownloadRootRules();

        const rootSelect = groupRows('loras')[0].querySelector('select.download-root-rule-root');
        expect(rootSelect.options[0].value).toBe(longRoot);
        expect(rootSelect.options[0].title).toBe(longRoot);
        expect(rootSelect.options[0].textContent).toBe(manager.truncateMiddlePath(longRoot));
        expect(rootSelect.title).toBe(longRoot);
    });

    it('keeps the (default) suffix after the truncated path', () => {
        appendDownloadRootRulesUi();
        const longRoot = '/models/library/very/deeply/nested/folder/structure/loras';
        const manager = createManager();
        manager.downloadRootRuleRoots = {
            loras: [longRoot],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        state.global.settings.default_lora_root = longRoot;
        state.global.settings.download_root_rules = {
            loras: [{ match_type: 'base_model', match: ['Flux.1 D'], root: longRoot }],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };

        manager.renderDownloadRootRules();

        const option = groupRows('loras')[0]
            .querySelector('select.download-root-rule-root').options[0];
        expect(option.textContent).toBe(`${manager.truncateMiddlePath(longRoot)} (default)`);
    });

    it('shows actionable placeholder summaries for empty drafts', () => {
        appendDownloadRootRulesUi();
        const manager = createManager();
        manager.renderDownloadRootRules();

        manager.addDownloadRootRule('loras', 'base_model');
        expect(groupRows('loras')[0].querySelector('.download-root-rule-summary').textContent)
            .toBe('Select base models...');

        manager.removeDownloadRootRule('loras', 0, true);
        manager.addDownloadRootRule('loras', 'tag');
        expect(groupRows('loras')[0].querySelector('.download-root-rule-summary').textContent)
            .toBe('Enter tags...');
    });

    it('summarizes more than two matches as first two plus a count', () => {
        appendDownloadRootRulesUi();
        state.global.settings.download_root_rules = {
            loras: [
                { match_type: 'base_model', match: ['Flux.1 D', 'Wan Video', 'Pony', 'SDXL 1.0'], root: '/models/loras-main' },
            ],
            checkpoints: [],
            unet: [],
            embeddings: [],
        };
        const manager = createManager();
        manager.renderDownloadRootRules();

        expect(groupRows('loras')[0].querySelector('.download-root-rule-summary').textContent)
            .toBe('Flux.1 D, Wan Video, +2 more');
    });
});
