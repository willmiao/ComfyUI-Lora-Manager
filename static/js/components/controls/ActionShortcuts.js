// ActionShortcuts.js - Shared R/F/D keyboard shortcuts for the actions toolbar
import { eventManager } from '../../utils/EventManager.js';
import { isTypingContext } from '../../utils/uiHelpers.js';

/**
 * Event manager source shared by every page controls implementation
 * (PageControls and the recipes page's RecipePageControls).
 */
export const ACTION_SHORTCUTS_SOURCE = 'pageControls-actions';

const ACTION_BY_KEY = Object.freeze({
    r: 'refresh',
    f: 'fetch',
    d: 'download'
});

/**
 * Handle a keydown event for the actions toolbar shortcuts
 * (R = refresh, F = fetch metadata, D = download).
 *
 * The shortcut reuses the button's own click handler, so it needs no
 * page-specific knowledge beyond the data-action attribute.
 *
 * @param {KeyboardEvent} e
 * @returns {boolean} True when the event was handled and propagation should stop
 */
export function handleActionShortcut(e) {
    // Plain letters only — leave modified combos (Ctrl/Cmd/Alt) alone
    if (e.ctrlKey || e.metaKey || e.altKey) {
        return false;
    }

    // Don't hijack keys while typing in a text entry context
    if (isTypingContext(e.target)) {
        return false;
    }

    const action = ACTION_BY_KEY[e.key.toLowerCase()];
    if (!action) {
        return false;
    }

    // The button may not exist on this page (e.g. recipes has no
    // fetch/download) — let other handlers run in that case
    const button = document.querySelector(`[data-action="${action}"]`);
    if (!button) {
        return false;
    }

    e.preventDefault();
    // Native disabled buttons ignore .click(), so an in-progress
    // refresh is safe
    button.click();
    return true;
}

/**
 * Register the shared action shortcuts with the centralized event manager.
 *
 * Re-registering the same source replaces the previous handler so a page that
 * rebuilds its controls (or a test creating several managers) does not fire
 * the action twice.
 *
 * @param {string} [source] - Event manager source identifier
 */
export function registerActionShortcuts(source = ACTION_SHORTCUTS_SOURCE) {
    eventManager.removeHandler('keydown', source);
    eventManager.addHandler('keydown', source, (e) => handleActionShortcut(e), {
        priority: 90,
        skipWhenModalOpen: true
    });
}
