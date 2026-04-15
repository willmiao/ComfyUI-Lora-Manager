export const WILDCARD_COMMANDS = {
    '/wild': { type: 'wildcard', label: 'Wildcards' },
    '/wildcard': { type: 'wildcard', label: 'Wildcards' },
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
