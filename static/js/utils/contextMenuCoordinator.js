/**
 * Cross-menu coordination for the app's popup context menus.
 *
 * The page menus (model card, bulk selection, page-global) and the sidebar
 * menus (folder tree, view options) are separate components, and each one only
 * knew how to close itself. Right-clicking a folder while a card menu was open
 * therefore left both on screen, and right-clicking a card while the folder
 * menu was open left the sidebar menu behind.
 *
 * Every menu registers a closer here. Opening a menu first closes all the
 * others, which keeps at most one context menu visible no matter which region
 * of the window it was opened from.
 */

const closers = new Map();

/**
 * Register (or replace) the closer of a menu element.
 *
 * @param {string} id Unique id of the menu element.
 * @param {() => void} close Hides the menu; must be safe to call while hidden.
 */
export function registerContextMenuCloser(id, close) {
    if (!id || typeof close !== 'function') return;
    closers.set(id, close);
}

/**
 * Hide every registered menu except `exceptId`.
 *
 * @param {string|null} [exceptId] The menu that is about to open, if any.
 */
export function closeContextMenus(exceptId = null) {
    for (const [id, close] of closers) {
        if (id === exceptId) continue;
        try {
            close();
        } catch (error) {
            console.error(`Failed to close context menu "${id}":`, error);
        }
    }
}
