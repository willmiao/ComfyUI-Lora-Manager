/**
 * reorderSupport.js
 * Shared drag affordance for chip lists sorted with pointerSort.
 *
 * The drag gesture itself lives in pointerSort.js; this module owns the parts
 * every sortable list needs on top of it:
 *  - the `⠿` grip markup,
 *  - the "sortable" flag that reveals the grip only when reordering is possible.
 *
 * Convention used by both callers: a list always shows the grip while it is
 * sortable. Whether the item *body* is draggable as well depends on the item:
 *  - body has no click action (model/recipe tags) -> whole item is draggable,
 *  - body is click-to-edit (trigger words) -> only the grip starts a drag.
 *
 * Reordering is deliberately pointer-only: a keyboard shortcut would have to
 * fight the browser's own Alt + Arrow handling and the modal's arrow-key
 * navigation, so the grip is a plain decorative affordance rather than a
 * focusable control.
 */

import { escapeAttribute, escapeHtml } from './utils.js';

const SORTABLE_CLASS = 'has-sortable-words';

/**
 * Render the shared reorder grip
 * @param {string} label - Tooltip text
 * @returns {string} Handle markup
 */
export function renderReorderHandle(label) {
    const safeLabel = escapeAttribute(label || '');
    return `<span class="reorder-handle" aria-hidden="true" title="${safeLabel}"><i class="fas fa-grip-vertical"></i></span>`;
}

/**
 * Render the shared reorder hint shown in an edit controls row
 * @param {string} label - Hint text
 * @returns {string} Hint markup
 */
export function renderReorderHint(label) {
    return `<span class="reorder-hint"><i class="fas fa-grip-vertical"></i> ${escapeHtml(label || '')}</span>`;
}

/**
 * Show or hide the grip and hint of a list.
 * They are only offered while the list is editable and holds more than one
 * item, so the UI never shows an affordance that cannot do anything.
 * @param {Object} options - Options
 * @param {HTMLElement} options.container - Element holding the sortable items
 * @param {HTMLElement} [options.scope] - Element that receives the sortable flag
 * @param {string} options.itemSelector - Selector of the sortable items
 * @param {Function} [options.isActive] - Whether reordering is currently allowed
 */
export function refreshReorderState({
    container,
    scope = container,
    itemSelector,
    isActive = () => true,
}) {
    if (!container) return;

    const items = container.querySelectorAll(itemSelector);
    scope.classList.toggle(SORTABLE_CLASS, isActive() && items.length > 1);
}
