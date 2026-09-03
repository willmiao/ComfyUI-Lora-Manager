import { describe, it, expect, vi } from 'vitest';

const {
    API_MODULE,
    APP_MODULE,
    CARET_HELPER_MODULE,
    PREVIEW_COMPONENT_MODULE,
    AUTOCOMPLETE_MODULE,
} = vi.hoisted(() => ({
    API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
    APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
    CARET_HELPER_MODULE: new URL('../../../web/comfyui/textarea_caret_helper.js', import.meta.url).pathname,
    PREVIEW_COMPONENT_MODULE: new URL('../../../web/comfyui/preview_tooltip.js', import.meta.url).pathname,
    AUTOCOMPLETE_MODULE: new URL('../../../web/comfyui/autocomplete.js', import.meta.url).pathname,
}));

vi.mock(API_MODULE, () => ({
    api: { fetchApi: vi.fn() },
}));

vi.mock(APP_MODULE, () => ({
    app: {
        canvas: { ds: { scale: 1 } },
        extensionManager: {
            setting: { get: vi.fn(), set: vi.fn() },
        },
        registerExtension: vi.fn(),
    },
}));

vi.mock(CARET_HELPER_MODULE, () => ({
    TextAreaCaretHelper: vi.fn(() => ({
        getBeforeCursor: vi.fn(() => ''),
        getCursorOffset: vi.fn(() => ({ left: 0, top: 0 })),
    })),
}));

vi.mock(PREVIEW_COMPONENT_MODULE, () => ({
    PreviewTooltip: vi.fn(() => ({ show: vi.fn(), hide: vi.fn(), cleanup: vi.fn() })),
}));

const METADATA_NAME = '__lm_autocomplete_meta_text';

function makeMetadataValue() {
    return {
        version: 1,
        textWidgetName: 'text',
        lastAccepted: {
            start: 0,
            end: 6,
            insertedText: '1girl ',
            textSnapshot: 'old prompt text, 1girl ',
        },
    };
}

describe('stripAutocompleteLastAccepted', () => {
    let stripAutocompleteLastAccepted;

    beforeAll(async () => {
        const module = await import(AUTOCOMPLETE_MODULE);
        stripAutocompleteLastAccepted = module.stripAutocompleteLastAccepted;
    });

    it('removes lastAccepted while keeping the metadata base fields', () => {
        const value = makeMetadataValue();
        const stripped = stripAutocompleteLastAccepted(value);

        expect(stripped).toEqual({ version: 1, textWidgetName: 'text' });
        expect('lastAccepted' in stripped).toBe(false);
        // Original value must not be mutated
        expect(value.lastAccepted).toBeDefined();
    });

    it('returns values without lastAccepted as-is (same reference)', () => {
        const value = { version: 1, textWidgetName: 'text' };
        expect(stripAutocompleteLastAccepted(value)).toBe(value);
    });

    it('returns non-object values as-is', () => {
        expect(stripAutocompleteLastAccepted(null)).toBe(null);
        expect(stripAutocompleteLastAccepted(undefined)).toBe(undefined);
        expect(stripAutocompleteLastAccepted('text')).toBe('text');
        expect(stripAutocompleteLastAccepted([1, 2])).toEqual([1, 2]);
    });
});

describe('stripAutocompleteMetadataFromPromptResult', () => {
    let stripResult;

    beforeAll(async () => {
        const module = await import(AUTOCOMPLETE_MODULE);
        stripResult = module.stripAutocompleteMetadataFromPromptResult;
    });

    function makeWorkflowNode() {
        const metadataValue = makeMetadataValue();
        return {
            properties: { __lm_widget_ids: ['text', METADATA_NAME] },
            widgets_values: ['current text', metadataValue],
            widgets_values_named: {
                text: 'current text',
                [METADATA_NAME]: metadataValue,
            },
        };
    }

    it('strips lastAccepted from workflow widgets_values using __lm_widget_ids alignment', () => {
        const result = {
            workflow: { nodes: [makeWorkflowNode()] },
            output: {},
        };

        const returned = stripResult(result);

        expect(returned).toBe(result);
        expect(result.workflow.nodes[0].widgets_values[1])
            .toEqual({ version: 1, textWidgetName: 'text' });
    });

    it('strips lastAccepted from widgets_values_named and leaves other widgets untouched', () => {
        const result = {
            workflow: { nodes: [makeWorkflowNode()] },
            output: {},
        };

        stripResult(result);

        const node = result.workflow.nodes[0];
        expect(node.widgets_values_named[METADATA_NAME])
            .toEqual({ version: 1, textWidgetName: 'text' });
        expect(node.widgets_values_named.text).toBe('current text');
        expect(node.widgets_values[0]).toBe('current text');
    });

    it('handles null entries in widgets_values (bypass compatibility padding)', () => {
        const node = makeWorkflowNode();
        node.properties.__lm_widget_ids = ['text', 'seed', METADATA_NAME];
        node.widgets_values = ['current text', null, makeMetadataValue()];
        const result = { workflow: { nodes: [node] }, output: {} };

        stripResult(result);

        expect(result.workflow.nodes[0].widgets_values[1]).toBe(null);
        expect(result.workflow.nodes[0].widgets_values[2])
            .toEqual({ version: 1, textWidgetName: 'text' });
    });

    it('still strips widgets_values_named when __lm_widget_ids is missing (legacy files)', () => {
        const node = makeWorkflowNode();
        delete node.properties;
        const arrayValue = node.widgets_values[1];
        const result = { workflow: { nodes: [node] }, output: {} };

        stripResult(result);

        // Array entries cannot be located without widget ids — left untouched
        expect(result.workflow.nodes[0].widgets_values[1]).toBe(arrayValue);
        expect(result.workflow.nodes[0].widgets_values_named[METADATA_NAME])
            .toEqual({ version: 1, textWidgetName: 'text' });
    });

    it('strips lastAccepted from output (API prompt) inputs', () => {
        const result = {
            workflow: { nodes: [] },
            output: {
                '7': {
                    class_type: 'Prompt (LoraManager)',
                    inputs: {
                        text: 'current text',
                        [METADATA_NAME]: makeMetadataValue(),
                    },
                },
            },
        };

        stripResult(result);

        const inputs = result.output['7'].inputs;
        expect(inputs[METADATA_NAME]).toEqual({ version: 1, textWidgetName: 'text' });
        expect(inputs.text).toBe('current text');
    });

    it('strips lastAccepted inside subgraph definitions', () => {
        const result = {
            workflow: {
                nodes: [],
                definitions: {
                    subgraphs: [{ nodes: [makeWorkflowNode()] }],
                },
            },
            output: {},
        };

        stripResult(result);

        const subgraphNode = result.workflow.definitions.subgraphs[0].nodes[0];
        expect(subgraphNode.widgets_values_named[METADATA_NAME])
            .toEqual({ version: 1, textWidgetName: 'text' });
    });

    it('leaves results without lastAccepted unchanged', () => {
        const metadataValue = { version: 1, textWidgetName: 'text' };
        const result = {
            workflow: {
                nodes: [{
                    properties: { __lm_widget_ids: ['text', METADATA_NAME] },
                    widgets_values: ['abc', metadataValue],
                    widgets_values_named: { text: 'abc', [METADATA_NAME]: metadataValue },
                }],
            },
            output: {
                '1': { inputs: { text: 'abc', [METADATA_NAME]: metadataValue } },
            },
        };

        stripResult(result);

        expect(result.workflow.nodes[0].widgets_values[1]).toBe(metadataValue);
        expect(result.output['1'].inputs[METADATA_NAME]).toBe(metadataValue);
    });

    it('tolerates malformed results', () => {
        expect(stripResult(null)).toBe(null);
        expect(stripResult(undefined)).toBe(undefined);
        expect(stripResult({})).toEqual({});

        const result = {
            workflow: { nodes: [null, { widgets_values: null }] },
            output: { '1': { inputs: null }, '2': {} },
        };
        expect(() => stripResult(result)).not.toThrow();
    });
});
