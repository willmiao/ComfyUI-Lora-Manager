/**
 * reorderSupport.js
 * Shared keyboard + screen-reader layer for chip lists sorted with pointerSort.
 *
 * Drag gestures are handled by pointerSort.js; this module adds the parts every
 * sortable list needs on top of it:
 *  - the `⠿` grip affordance (markup + labels),
 *  - the "sortable" flag that reveals the grip only when reordering is possible,
 *  - Alt + Arrow keyboard reordering with aria-live announcements.
 *
 * Convention used by both callers: a list always shows the grip while it is
 * sortable. Whether the item *body* is draggable as well depends on the item:
 *  - body has no click action (model/recipe tags) -> whole item is draggable,
 *  - body is click-to-edit (trigger words) -> only the grip starts a drag.
 */

import { translate } from '../../utils/i18nHelpers.js';
import { escapeAttribute, escapeHtml } from './utils.js';
import { moveItemWithinContainer } from './pointerSort.js';

const SORTABLE_CLASS = 'has-sortable-words';
const LIVE_REGION_CLASS = 'reorder-live-region';
const SR_ONLY_CLASS = 'reorder-sr-only';
const DEFAULT_HANDLE_SELECTOR = '.reorder-handle';
const DEFAULT_ARIA_LABEL_KEY = 'common.reorder.ariaLabel';
const DEFAULT_ANNOUNCEMENT_KEY = 'common.reorder.announcement';

/**
 * Render the shared reorder grip button
 * @param {string} label - Tooltip / accessible label
 * @returns {string} Handle markup
 */
export function renderReorderHandle(label) {
    const safeLabel = escapeAttribute(label || '');
    return `<button type="button" class="reorder-handle" title="${safeLabel}" aria-label="${safeLabel}"><i class="fas fa-grip-vertical"></i></button>`;
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
 * Map a keydown event to a reorder offset
 * @param {KeyboardEvent} event - Keydown event
 * @returns {number} -1 (earlier), 1 (later) or 0 when it is not a reorder shortcut
 */
function getReorderOffset(event) {
    if (!event.altKey || event.ctrlKey || event.metaKey) return 0;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') return -1;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') return 1;
    return 0;
}

/**
 * Create the keyboard / label support of a sortable list
 * @param {Object} options - Options
 * @param {HTMLElement} options.container - Element holding the items
 * @param {HTMLElement} [options.scope] - Element that receives the sortable flag
 * @param {string} [options.handleSelector] - Grip selector inside an item
 * @param {Object} options.sortConfig - Same config passed to enablePointerSort()
 * @param {Function} [options.isActive] - Whether reordering is currently allowed
 * @param {Function} [options.getItemLabel] - (item) => label used in messages
 * @param {Object} [options.i18n] - { ariaLabel, announcement } translation keys
 * @returns {{refresh: Function, announce: Function, handleKeydown: Function}}
 */
export function createReorderSupport({
    container,
    scope = container,
    handleSelector = DEFAULT_HANDLE_SELECTOR,
    sortConfig,
    isActive = () => true,
    getItemLabel = (item) => item.dataset.word || item.dataset.tag || item.textContent.trim(),
    i18n = {},
}) {
    const itemSelector = sortConfig.itemSelector;
    const ariaLabelKey = i18n.ariaLabel || DEFAULT_ARIA_LABEL_KEY;
    const announcementKey = i18n.announcement || DEFAULT_ANNOUNCEMENT_KEY;

    const getItems = () => Array.from(container.querySelectorAll(itemSelector));

    function refresh() {
        const items = getItems();
        scope.classList.toggle(SORTABLE_CLASS, isActive() && items.length > 1);

        items.forEach((item, index) => {
            const handle = item.querySelector(handleSelector);
            if (!handle) return;

            const label = getItemLabel(item);
            handle.setAttribute('aria-label', translate(
                ariaLabelKey,
                { item: label, position: index + 1, total: items.length },
                `Reorder ${label}, position ${index + 1} of ${items.length}`,
            ));
        });
    }

    function ensureLiveRegion() {
        let liveRegion = scope.querySelector(`.${LIVE_REGION_CLASS}`);
        if (liveRegion) return liveRegion;

        liveRegion = document.createElement('div');
        liveRegion.className = `${LIVE_REGION_CLASS} ${SR_ONLY_CLASS}`;
        liveRegion.setAttribute('role', 'status');
        liveRegion.setAttribute('aria-live', 'polite');
        scope.appendChild(liveRegion);

        return liveRegion;
    }

    function announce(item) {
        const items = getItems();
        const index = items.indexOf(item);
        if (index === -1) return;

        ensureLiveRegion().textContent = translate(
            announcementKey,
            { position: index + 1, total: items.length },
            `Moved to position ${index + 1} of ${items.length}`,
        );
    }

    function handleKeydown(event) {
        const handle = event.target.closest(handleSelector);
        if (!handle || !isActive()) return;

        const offset = getReorderOffset(event);
        if (!offset) return;

        // Swallow the shortcut even at the ends of the list: Alt + Left/Right
        // would otherwise trigger the browser's back/forward navigation.
        event.preventDefault();
        event.stopPropagation();

        const item = handle.closest(itemSelector);
        if (!item) return;

        const result = moveItemWithinContainer(item, offset, sortConfig);
        if (!result) return;

        refresh();
        announce(item);

        const nextHandle = item.querySelector(handleSelector);
        if (nextHandle) nextHandle.focus();
    }

    if (!container.__reorderKeyboardAttached) {
        container.__reorderKeyboardAttached = true;
        container.addEventListener('keydown', handleKeydown);
    }

    return { refresh, announce, handleKeydown };
}
