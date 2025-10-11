import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { DEFAULT_PRIORITY_TAG_CONFIG } from '../../../static/js/utils/constants.js';

const MODULE_PATH = '../../../static/js/utils/priorityTagHelpers.js';

let originalFetch;
let invalidateCacheFn;

beforeEach(() => {
    originalFetch = global.fetch;
    invalidateCacheFn = null;
    vi.resetModules();
});

afterEach(() => {
    if (invalidateCacheFn) {
        invalidateCacheFn();
        invalidateCacheFn = null;
    }

    if (originalFetch === undefined) {
        delete global.fetch;
    } else {
        global.fetch = originalFetch;
    }

    vi.restoreAllMocks();
});

describe('priorityTagHelpers suggestion handling', () => {
    it('returns trimmed, deduplicated suggestions scoped to the requested model type', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                success: true,
                tags: {
                    loras: ['character', 'style ', 'style'],
                    checkpoints: ['Base ', 'Primary'],
                },
            }),
        });
        vi.stubGlobal('fetch', fetchMock);

        const module = await import(MODULE_PATH);
        invalidateCacheFn = module.invalidatePriorityTagSuggestionsCache;

        const loraTags = await module.getPriorityTagSuggestions('loras');
        expect(loraTags).toEqual(['character', 'style']);

        const checkpointTags = await module.getPriorityTagSuggestions('CHECKPOINT');
        expect(checkpointTags).toEqual(['Base', 'Primary']);

        const aliasTags = await module.getPriorityTagSuggestions('lora');
        expect(aliasTags).toEqual(['character', 'style']);

        const defaultEmbedding = module
            .parsePriorityTagString(DEFAULT_PRIORITY_TAG_CONFIG.embedding)
            .map((entry) => entry.canonical);
        const embeddingTags = await module.getPriorityTagSuggestions('embeddings');
        expect(embeddingTags).toEqual(defaultEmbedding);

        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('returns a unique union of suggestions when no model type is provided', async () => {
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({
                success: true,
                tags: {
                    lora: ['primary', 'support'],
                    checkpoint: ['guide', 'primary'],
                    embeddings: ['hint'],
                },
            }),
        });
        vi.stubGlobal('fetch', fetchMock);

        const module = await import(MODULE_PATH);
        invalidateCacheFn = module.invalidatePriorityTagSuggestionsCache;

        const suggestions = await module.getPriorityTagSuggestions();
        expect(suggestions).toEqual(['primary', 'support', 'guide', 'hint']);
    });

    it('falls back to default configuration when fetching suggestions fails', async () => {
        const fetchMock = vi.fn().mockRejectedValue(new Error('network error'));
        vi.stubGlobal('fetch', fetchMock);

        const module = await import(MODULE_PATH);
        invalidateCacheFn = module.invalidatePriorityTagSuggestionsCache;

        const expected = module
            .parsePriorityTagString(DEFAULT_PRIORITY_TAG_CONFIG.lora)
            .map((entry) => entry.canonical);

        const result = await module.getPriorityTagSuggestions('loras');
        expect(result).toEqual(expected);
    });
});
