import { DEFAULT_PRIORITY_TAG_CONFIG } from './constants.js';

const MODEL_TYPE_ALIAS_MAP = {
    loras: 'lora',
    lora: 'lora',
    checkpoints: 'checkpoint',
    checkpoint: 'checkpoint',
    embeddings: 'embedding',
    embedding: 'embedding',
};

function normalizeModelTypeKey(modelType) {
    if (typeof modelType !== 'string') {
        return '';
    }
    const lower = modelType.toLowerCase();
    if (MODEL_TYPE_ALIAS_MAP[lower]) {
        return MODEL_TYPE_ALIAS_MAP[lower];
    }
    if (lower.endsWith('s')) {
        return lower.slice(0, -1);
    }
    return lower;
}

function splitPriorityEntries(raw = '') {
    const segments = [];
    raw.split('\n').forEach(line => {
        line.split(',').forEach(part => {
            const trimmed = part.trim();
            if (trimmed) {
                segments.push(trimmed);
            }
        });
    });
    return segments;
}

export function parsePriorityTagString(raw = '') {
    const entries = [];
    const rawEntries = splitPriorityEntries(raw);

    rawEntries.forEach((entry) => {
        const { canonical, aliases } = parsePriorityEntry(entry);
        if (!canonical) {
            return;
        }

        entries.push({ canonical, aliases });
    });

    return entries;
}

function parsePriorityEntry(entry) {
    let canonical = entry;
    let aliasSection = '';

    const openIndex = entry.indexOf('(');
    if (openIndex !== -1) {
        if (!entry.endsWith(')')) {
            canonical = entry.replace('(', '').replace(')', '');
        } else {
            canonical = entry.slice(0, openIndex).trim();
            aliasSection = entry.slice(openIndex + 1, -1);
        }
    }

    canonical = canonical.trim();
    if (!canonical) {
        return { canonical: '', aliases: [] };
    }

    const aliasList = aliasSection ? aliasSection.split('|').map((alias) => alias.trim()).filter(Boolean) : [];
    const seen = new Set();
    const normalizedCanonical = canonical.toLowerCase();
    const uniqueAliases = [];

    aliasList.forEach((alias) => {
        const normalized = alias.toLowerCase();
        if (normalized === normalizedCanonical) {
            return;
        }
        if (!seen.has(normalized)) {
            seen.add(normalized);
            uniqueAliases.push(alias);
        }
    });

    return { canonical, aliases: uniqueAliases };
}

export function formatPriorityTagEntries(entries, useNewlines = false) {
    if (!entries.length) {
        return '';
    }

    const separator = useNewlines ? ',\n' : ', ';
    return entries.map(({ canonical, aliases }) => {
        if (aliases && aliases.length) {
            return `${canonical}(${aliases.join('|')})`;
        }
        return canonical;
    }).join(separator);
}

export function validatePriorityTagString(raw = '') {
    const trimmed = raw.trim();
    if (!trimmed) {
        return { valid: true, errors: [], entries: [], formatted: '' };
    }

    const errors = [];
    const entries = [];
    const rawEntries = splitPriorityEntries(raw);
    const seenCanonicals = new Set();

    rawEntries.forEach((entry, index) => {
        const hasOpening = entry.includes('(');
        const hasClosing = entry.endsWith(')');

        if (hasOpening && !hasClosing) {
            errors.push({ type: 'missingClosingParen', index: index + 1 });
        }

        const { canonical, aliases } = parsePriorityEntry(entry);
        if (!canonical) {
            errors.push({ type: 'missingCanonical', index: index + 1 });
            return;
        }

        const normalizedCanonical = canonical.toLowerCase();
        if (seenCanonicals.has(normalizedCanonical)) {
            errors.push({ type: 'duplicateCanonical', canonical });
        } else {
            seenCanonicals.add(normalizedCanonical);
        }

        entries.push({ canonical, aliases });
    });

    const formatted = errors.length === 0
        ? formatPriorityTagEntries(entries, raw.includes('\n'))
        : raw.trim();

    return {
        valid: errors.length === 0,
        errors,
        entries,
        formatted,
    };
}

let cachedPriorityTagMap = null;
let fetchPromise = null;

export async function getPriorityTagSuggestionsMap() {
    if (cachedPriorityTagMap) {
        return cachedPriorityTagMap;
    }

    if (!fetchPromise) {
        fetchPromise = fetch('/api/lm/priority-tags')
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                const data = await response.json();
                if (!data || data.success === false || typeof data.tags !== 'object') {
                    throw new Error(data?.error || 'Invalid response payload');
                }

                const normalized = {};
                Object.entries(data.tags).forEach(([modelType, tags]) => {
                    if (!Array.isArray(tags)) {
                        return;
                    }
                    const key = normalizeModelTypeKey(modelType) || (typeof modelType === 'string' ? modelType.toLowerCase() : '');
                    if (!key) {
                        return;
                    }
                    const filtered = tags
                        .filter((tag) => typeof tag === 'string')
                        .map((tag) => tag.trim())
                        .filter(Boolean);
                    if (!normalized[key]) {
                        normalized[key] = [];
                    }
                    normalized[key].push(...filtered);
                });

                const withDefaults = applyDefaultPriorityTagFallback(normalized);
                cachedPriorityTagMap = withDefaults;
                return withDefaults;
            })
            .catch(() => {
                const fallback = buildDefaultPriorityTagMap();
                cachedPriorityTagMap = fallback;
                return fallback;
            })
            .finally(() => {
                fetchPromise = null;
            });
    }

    return fetchPromise;
}

export async function getPriorityTagSuggestions(modelType = null) {
    const map = await getPriorityTagSuggestionsMap();

    if (modelType) {
        const lower = typeof modelType === 'string' ? modelType.toLowerCase() : '';
        const normalizedKey = normalizeModelTypeKey(modelType);
        const candidates = [];
        if (lower) {
            candidates.push(lower);
        }
        if (normalizedKey && !candidates.includes(normalizedKey)) {
            candidates.push(normalizedKey);
        }
        Object.entries(MODEL_TYPE_ALIAS_MAP).forEach(([alias, target]) => {
            if (alias === lower || target === normalizedKey) {
                if (!candidates.includes(target)) {
                    candidates.push(target);
                }
            }
        });

        for (const key of candidates) {
            if (Array.isArray(map[key])) {
                return [...map[key]];
            }
        }
        return [];
    }

    const unique = new Set();
    Object.values(map).forEach((tags) => {
        tags.forEach((tag) => {
            unique.add(tag);
        });
    });
    return Array.from(unique);
}

function applyDefaultPriorityTagFallback(map) {
    const result = { ...buildDefaultPriorityTagMap(), ...map };
    Object.entries(result).forEach(([key, tags]) => {
        result[key] = dedupeTags(Array.isArray(tags) ? tags : []);
    });
    return result;
}

function buildDefaultPriorityTagMap() {
    const map = {};
    Object.entries(DEFAULT_PRIORITY_TAG_CONFIG).forEach(([modelType, configString]) => {
        const entries = parsePriorityTagString(configString);
        const key = normalizeModelTypeKey(modelType) || modelType;
        map[key] = entries.map((entry) => entry.canonical);
    });
    return map;
}

function dedupeTags(tags) {
    const seen = new Set();
    const ordered = [];
    tags.forEach((tag) => {
        const normalized = tag.toLowerCase();
        if (!seen.has(normalized)) {
            seen.add(normalized);
            ordered.push(tag);
        }
    });
    return ordered;
}

export function getDefaultPriorityTagConfig() {
    return { ...DEFAULT_PRIORITY_TAG_CONFIG };
}

export function invalidatePriorityTagSuggestionsCache() {
    cachedPriorityTagMap = null;
    fetchPromise = null;
}
