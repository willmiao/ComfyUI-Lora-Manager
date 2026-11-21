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
    const resourceCount = Math.max(0, Number(meta.library_resource_count) || 0);
    const activeResourceCount = Math.min(
        resourceCount,
        Math.max(0, Number(meta.active_resource_count) || 0),
    );
    const hasInactiveResources = resourceCount > activeResourceCount;
    const hasOnlyEmptyActiveResources = resourceCount > 0 && !hasInactiveResources;
    const resourceLabel = resourceCount === 1 ? 'collection' : 'collections';

    let title = 'No wildcards yet';
    let description = 'Download or import a wildcard collection, then activate it to make its keys available here.';
    let primaryAction = 'open-manager';
    if (hasInactiveResources) {
        title = 'No active wildcards';
        description = `You have ${resourceCount} wildcard ${resourceLabel} in your library. Activate one to make its keys available in ComfyUI.`;
        primaryAction = 'open-quick-panel';
    } else if (hasOnlyEmptyActiveResources) {
        title = 'No usable wildcard keys';
        description = 'Your active wildcard collections do not provide any usable keys. Check them in the Wildcards Manager.';
    }

    return {
        type: WILDCARD_INFO_ITEM_TYPES.EMPTY_STATE,
        title,
        description,
        primaryAction,
        showGlobalNote: hasInactiveResources,
        libraryResourceCount: resourceCount,
        activeResourceCount,
        wildcardsDir: meta.wildcards_dir || '',
        supportedFormats: Array.isArray(meta.supported_formats) ? meta.supported_formats : [],
    };
}

export function createWildcardNoMatchesItem(searchTerm = '', meta = {}) {
    return {
        type: WILDCARD_INFO_ITEM_TYPES.NO_MATCHES,
        title: 'No wildcard matches',
        description: searchTerm
            ? `No wildcard keys match "${searchTerm}". Try another search, or browse all wildcards.`
            : 'No wildcard keys match your search. Try another search, or browse all wildcards.',
        wildcardsDir: meta.wildcards_dir || '',
        supportedFormats: Array.isArray(meta.supported_formats) ? meta.supported_formats : [],
    };
}
