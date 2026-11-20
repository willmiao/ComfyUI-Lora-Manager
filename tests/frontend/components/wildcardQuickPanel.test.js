import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
        settingsDialog: null,
        settingsInFlight: false,
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

afterEach(() => {
    document.body.innerHTML = '';
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

    it('disables copying for keys that cannot be referenced', () => {
        const container = document.createElement('div');
        const panel = createPanel();
        const resource = activeResource();
        resource.entries = [
            { key: 'ok', effective_key: 'ok', values_count: 1 },
            {
                key: 'a__b',
                effective_key: 'a__b',
                values_count: 2,
                reference_problem: "contains '__', which closes the token early",
            },
        ];

        panel.renderKeyRows(container, resource);

        const rows = container.querySelectorAll('.lm-wildcard-key');
        expect(rows[0].disabled).toBe(false);
        expect(rows[1].disabled).toBe(true);
        expect(rows[1].classList.contains('is-unreferenceable')).toBe(true);
        expect(rows[1].title).toContain('closes the token early');
    });

    it('disables copying an unreferenceable manual key', () => {
        const panel = createPanel();
        panel.items = [activeResource()];
        panel.manual = [
            {
                ...manualEntry(),
                key: 'a__b',
                reference_problem: "contains '__', which closes the token early",
            },
        ];
        panel.render();

        panel.resultsElement.querySelector('[data-kind="manual"]').click();

        const copy = [...panel.detailElement.querySelectorAll('button')].find((button) =>
            button.textContent.startsWith('Copy'),
        );
        expect(copy.disabled).toBe(true);
        expect(panel.detailElement.textContent).toContain('Cannot be referenced');
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


describe('WildcardQuickPanel activation settings', () => {
    it('previews and saves a prefix and alias for a single-key resource', async () => {
        const panel = createPanel();
        const resource = inactiveResource();
        resource.activation_namespace = 'characters';
        resource.activation_aliases = { c: 'hero' };
        panel.items = [resource];
        panel.selected = { kind: 'resource', filePath: resource.file_path };
        panel.load = vi.fn().mockResolvedValue(undefined);
        setActiveMock.mockResolvedValue({ success: true });

        panel.render();
        const trigger = panel.detailElement.querySelector('.lm-wildcard-settings-trigger');
        expect(trigger.title).toBe('Activation settings');
        expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
        const footerButtons = [...panel.detailElement.querySelectorAll('.lm-quick__actions > button')];
        expect(footerButtons.map((button) => button.textContent)).toEqual(['Activate', 'Open in manager']);

        trigger.click();
        const dialog = document.querySelector('.lm-wildcard-settings');
        const inputs = dialog.querySelectorAll('.lm-wildcard-settings__field input');
        expect(inputs[0].value).toBe('characters');
        expect(inputs[1].value).toBe('hero');

        inputs[0].value = 'New/Namespace';
        inputs[1].value = 'akame';
        inputs[0].dispatchEvent(new Event('input'));
        inputs[1].dispatchEvent(new Event('input'));
        expect(dialog.querySelector('code').textContent).toBe('__new/namespace/akame__');

        inputs[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await vi.waitFor(() => {
            expect(setActiveMock).toHaveBeenCalledWith('/inactive.zip', true, {
                namespace: 'New/Namespace',
                aliases: { c: 'akame' },
            });
            expect(panel.load).toHaveBeenCalledOnce();
        });
        expect(document.querySelector('.lm-wildcard-settings')).toBeNull();
        expect(panel.statusElement.textContent).toBe('Activated Inactive Pack');
    });

    it('edits only the prefix for multi-key resources and preserves stored aliases', async () => {
        const panel = createPanel();
        const resource = activeResource();
        resource.activation_aliases = { a: 'alpha', b: 'beta' };
        panel.items = [resource];
        panel.selected = { kind: 'resource', filePath: resource.file_path };
        panel.load = vi.fn().mockResolvedValue(undefined);
        setActiveMock.mockResolvedValue({ success: true });

        panel.openActivationSettings(resource);
        const dialog = document.querySelector('.lm-wildcard-settings');
        const fields = dialog.querySelectorAll('.lm-wildcard-settings__field');
        expect(fields[1].hidden).toBe(true);
        expect(dialog.querySelector('.lm-quick__primary').textContent).toBe('Save settings');

        const namespace = fields[0].querySelector('input');
        namespace.value = 'updated';
        dialog.querySelector('.lm-quick__primary').click();

        await vi.waitFor(() => {
            expect(setActiveMock).toHaveBeenCalledWith('/active.zip', true, {
                namespace: 'updated',
                aliases: { a: 'alpha', b: 'beta' },
            });
            expect(panel.load).toHaveBeenCalledOnce();
        });
        expect(panel.statusElement.textContent).toBe('Saved activation settings for Active Pack');
    });

    it('keeps conflicts inside the settings dialog without reloading', async () => {
        const panel = createPanel();
        const resource = inactiveResource();
        panel.items = [resource];
        panel.selected = { kind: 'resource', filePath: resource.file_path };
        panel.load = vi.fn().mockResolvedValue(undefined);
        const conflict = new Error('Activation would replace an existing wildcard key');
        conflict.payload = {
            conflicts: [{ key: 'shared/color', owners: [{ resource_id: '/other.txt' }] }],
        };
        setActiveMock.mockRejectedValue(conflict);

        panel.openActivationSettings(resource);
        const dialog = document.querySelector('.lm-wildcard-settings');
        dialog.querySelector('.lm-quick__primary').click();

        await vi.waitFor(() => {
            expect(dialog.querySelector('.lm-wildcard-settings__error').hidden).toBe(false);
        });
        expect(dialog.textContent).toContain('shared/color');
        expect(dialog.textContent).toContain('/other.txt');
        expect(panel.load).not.toHaveBeenCalled();
        expect(document.querySelector('.lm-wildcard-settings')).not.toBeNull();
    });
});
