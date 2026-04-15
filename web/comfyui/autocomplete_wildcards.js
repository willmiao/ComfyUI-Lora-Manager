export const WILDCARD_COMMANDS = {
    '/wildcard': { type: 'wildcard', label: 'Wildcards' },
};

export const WILDCARD_INFO_ITEM_TYPES = {
    EMPTY_STATE: 'wildcard_empty_state',
    NO_MATCHES: 'wildcard_no_matches',
};

export function isWildcardCommand(command) {
    return command?.type === 'wildcard';
}

export function getWildcardSearchEndpoint() {
    return '/lm/wildcards/search';
}

export function getWildcardInsertText(relativePath = '') {
    const trimmed = typeof relativePath === 'string' ? relativePath.trim() : '';
    if (!trimmed) {
        return '';
    }
    return `__${trimmed}__`;
}

export function isWildcardInfoItem(item) {
    return Boolean(
        item &&
        typeof item === 'object' &&
        Object.values(WILDCARD_INFO_ITEM_TYPES).includes(item.type)
    );
}

export function createWildcardEmptyStateItem(meta = {}) {
    return {
        type: WILDCARD_INFO_ITEM_TYPES.EMPTY_STATE,
        title: 'No wildcards found yet',
        description: 'Create wildcard files in your wildcards folder, then use /wildcard to search and insert keys.',
        wildcardsDir: meta.wildcards_dir || '',
        supportedFormats: Array.isArray(meta.supported_formats) ? meta.supported_formats : [],
    };
}

export function createWildcardNoMatchesItem(searchTerm = '', meta = {}) {
    return {
        type: WILDCARD_INFO_ITEM_TYPES.NO_MATCHES,
        title: 'No wildcard matches',
        description: searchTerm
            ? `No wildcard keys matched "${searchTerm}".`
            : 'No wildcard keys matched your search.',
        wildcardsDir: meta.wildcards_dir || '',
        supportedFormats: Array.isArray(meta.supported_formats) ? meta.supported_formats : [],
    };
}
