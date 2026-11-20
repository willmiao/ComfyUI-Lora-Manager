import { beforeEach, describe, expect, it, vi } from 'vitest';

const { CANVAS_API_MODULE, setActiveMock, searchMock } = vi.hoisted(() => ({
    CANVAS_API_MODULE: new URL('../../../web/comfyui/wildcard_canvas_api.js', import.meta.url).pathname,
    setActiveMock: vi.fn(),
    searchMock: vi.fn(),
}));

vi.mock(CANVAS_API_MODULE, () => ({
    openWildcardManager: vi.fn(),
    openWildcardsFolder: vi.fn(),
    searchWildcardLibrary: searchMock,
    setWildcardActive: setActiveMock,
}));

function activeResource() {
    return {
        file_path: '/active.zip',
        model_name: 'Active Pack',
        file_name: 'active',
        active: true,
        entry_count: 2,
        value_count: 5,
        wildcard_format: 'zip',
        base_model: 'Illustrious',
        preview_url: '/preview.png',
        activation_namespace: '',
        activation_aliases: {},
        entries: [
            { key: 'a', effective_key: 'a', values_count: 2 },
            { key: 'b', effective_key: 'b', values_count: 3 },
        ],
        errors: [],
    };
}

function inactiveResource() {
    return {
        file_path: '/inactive.zip',
        model_name: 'Inactive Pack',
        file_name: 'inactive',
        active: false,
        entry_count: 1,
        value_count: 2,
        wildcard_format: 'zip',
        base_model: 'SDXL 1.0',
        preview_url: '',
        activation_namespace: '',
        activation_aliases: {},
        entries: [{ key: 'c', effective_key: 'c', values_count: 2 }],
        errors: [],
    };
}

function manualEntry() {
    return {
        key: 'example',
        values_count: 10,
        source_path: '/manual/example.txt',
        sample_values: ['one', 'two', 'three'],
    };
}

function createPanel() {
    const panel = Object.create(WildcardPanel.prototype);
    Object.assign(panel, {
        panel: { isOpen: () => true },
        items: [],
        manual: [],
        conflicts: [],
        selected: null,
        scope: 'all',
        searchQuery: '',
        manualCollapsed: false,
        keyFilter: '',
        loadError: '',
        activationError: null,
        activationInFlight: null,
        resultsElement: document.createElement('div'),
        detailElement: document.createElement('aside'),
        statusElement: document.createElement('span'),
        hintsElement: document.createElement('span'),
        scopeButtons: {},
        previewTooltip: null,
        previewTimer: null,
        previewRow: null,
    });
    return panel;
}

let WildcardPanel;

beforeEach(async () => {
    vi.clearAllMocks();
    ({ WildcardQuickPanel: WildcardPanel } = await import('../../../web/comfyui/wildcard_quick_panel.js'));
});

describe('WildcardQuickPanel', () => {
    it('lists active, library and manual entries with state badges', () => {
        const panel = createPanel();
        panel.items = [activeResource(), inactiveResource()];
        panel.manual = [manualEntry()];

        panel.render();

        const text = panel.resultsElement.textContent;
        expect(text).toContain('Active Pack');
        expect(text).toContain('Inactive Pack');
        expect(text).toContain('example');
        expect(text).toContain('Library');
        expect(panel.resultsElement.querySelectorAll('.lm-wildcard-state.is-active')).toHaveLength(1);
        expect(panel.resultsElement.querySelectorAll('.lm-wildcard-state.is-manual')).toHaveLength(1);
    });

    it('keeps manual entries visible when the Active scope hides the library', () => {
        const panel = createPanel();
        panel.items = [activeResource(), inactiveResource()];
        panel.manual = [manualEntry()];

        panel.scope = 'active';
        panel.render();

        const text = panel.resultsElement.textContent;
        expect(text).not.toContain('Library');
        expect(text).not.toContain('Inactive Pack');
        expect(text).toContain('Active Pack');
        expect(text).toContain('example');
        expect(panel.visibleResources()).toHaveLength(1);
    });

    it('renders the manual detail without activation controls', () => {
        const panel = createPanel();
        panel.items = [activeResource()];
        panel.manual = [manualEntry()];
        panel.render();

        panel.resultsElement.querySelector('[data-kind="manual"]').click();

        expect(panel.detailElement.textContent).toContain('Always active · not toggleable');
        expect(panel.detailElement.textContent).toContain('Value preview (10)');
        expect(panel.detailElement.textContent).toContain('one');
        expect(panel.detailElement.textContent).not.toContain('Deactivate');
        expect(panel.detailElement.textContent).toContain('Copy __example__');
    });

    it('keeps the clicked row focused so Escape reaches the panel', () => {
        const panel = createPanel();
        document.body.appendChild(panel.resultsElement);
        try {
            panel.items = [activeResource(), inactiveResource()];
            panel.manual = [];
            panel.render();

            const row = panel.resultsElement.querySelector('[data-file-path="/inactive.zip"]');
            row.focus();
            row.click();

            expect(document.activeElement).toBe(row);
            expect(panel.resultsElement.contains(document.activeElement)).toBe(true);
            expect(row.classList.contains('is-selected')).toBe(true);
        } finally {
            panel.resultsElement.remove();
        }
    });

    it('uses the shared activation API for managed resources', async () => {
        const panel = createPanel();
        const resource = inactiveResource();
        panel.items = [resource];
        panel.selected = { kind: 'resource', filePath: resource.file_path };
        panel.load = vi.fn().mockResolvedValue(undefined);
        setActiveMock.mockResolvedValue({ success: true });

        await panel.toggleActivation(resource);

        expect(setActiveMock).toHaveBeenCalledWith('/inactive.zip', true);
        expect(panel.load).toHaveBeenCalledOnce();
    });

    it('only resolves hover previews for resources with a real preview', () => {
        const panel = createPanel();
        panel.items = [activeResource(), inactiveResource()];

        expect(panel.resolveRowPreview('/active.zip')).toEqual({
            previewUrl: '/preview.png',
            displayName: 'Active Pack',
        });
        expect(panel.resolveRowPreview('/inactive.zip')).toBeNull();
    });
});
