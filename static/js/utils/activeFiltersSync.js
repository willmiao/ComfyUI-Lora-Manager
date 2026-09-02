/**
 * Mirrors the manager page's active filter state to the backend's in-memory
 * store, so the ComfyUI-side autocomplete can apply it even when the manager
 * page and ComfyUI run in different browsers/origins (localStorage is not
 * shared there).
 */

import { getStorageItem, setActiveFiltersListener } from './storageHelpers.js';
import { debounce } from './debounce.js';

const SYNC_DEBOUNCE_MS = 300;

const debouncedPushByPage = {};

function buildActiveFiltersPayload(pageType) {
    const activeFolder = getStorageItem(`${pageType}_activeFolder`);
    const recursiveSearch = getStorageItem(`${pageType}_recursiveSearch`, true);
    const filters = getStorageItem(`${pageType}_filters`);

    return {
        // null stays null; legacy "null" string is normalized to null
        activeFolder: activeFolder && activeFolder !== 'null' ? activeFolder : null,
        recursiveSearch: recursiveSearch !== false,
        filters: filters && typeof filters === 'object' ? filters : null,
    };
}

export async function pushActiveFilters(pageType) {
    try {
        const response = await fetch(`/api/lm/${pageType}/active-filters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(buildActiveFiltersPayload(pageType)),
        });
        if (!response.ok) {
            console.warn(`[Lora Manager] Failed to sync active filters for ${pageType}: HTTP ${response.status}`);
        }
    } catch (error) {
        console.warn(`[Lora Manager] Failed to sync active filters for ${pageType}:`, error);
    }
}

export function syncActiveFilters(pageType) {
    if (!debouncedPushByPage[pageType]) {
        debouncedPushByPage[pageType] = debounce(() => {
            pushActiveFilters(pageType);
        }, SYNC_DEBOUNCE_MS);
    }
    debouncedPushByPage[pageType]();
}

/**
 * Register the storage listener and push the current (restored) state once.
 * The initial push covers server restarts, where the backend store is empty
 * until the manager page re-publishes its localStorage-restored filters.
 * @param {string} pageType - 'loras' | 'checkpoints' | 'embeddings'
 */
export function initActiveFiltersSync(pageType) {
    setActiveFiltersListener((changedPageType) => syncActiveFilters(changedPageType));
    pushActiveFilters(pageType);
}
