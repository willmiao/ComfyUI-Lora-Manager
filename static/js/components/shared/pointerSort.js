/**
 * pointerSort.js
 * Shared pointer-based drag-and-drop sorting for wrapped item lists
 * (model tags, trigger words, ...).
 *
 * The engine lifts the dragged item into a fixed-position "ghost", leaves a
 * correctly sized placeholder behind, and moves that placeholder around based
 * on the pointer position. Because the dragged node is re-inserted where the
 * placeholder ended up, the resulting DOM order *is* the new sort order — the
 * save path simply reads the items in DOM order.
 */

const DEFAULT_OPTIONS = {
    // Selector of the sortable items inside the container.
    itemSelector: '.metadata-item',
    // When set, a drag can only start from inside this element (a handle).
    // When null the whole item is draggable.
    handleSelector: null,
    // Elements inside an item that must never start a drag.
    ignoreSelector: '.metadata-delete-btn',
    // Items matching this selector cannot be dragged (e.g. while being edited).
    blockedItemSelector: null,
    draggingClass: 'reorder-dragging',
    placeholderClass: 'reorder-placeholder',
    containerSortingClass: 'reorder-sorting',
    // Added to <body> while dragging to disable text selection globally.
    bodySortingClass: 'reorder-drag-active',
    // Pointer travel (px) required before a drag starts. 0 = start on pointerdown.
    dragThreshold: 0,
    // Called after a successful drop with (item, container).
    onSorted: null,
};

// Marks a container whose items are actually sortable, so styles can offer the
// grab affordance only where dragging really works.
const CONTAINER_ENABLED_CLASS = 'pointer-sort-enabled';

let activeDragState = null;
let pendingDragState = null;

function resolveConfig(options = {}) {
    return { ...DEFAULT_OPTIONS, ...options };
}

function itemInitKey(config) {
    // Any option that changes how a pointerdown is interpreted is part of the
    // key, so re-enabling a container with new options replaces the handler
    // instead of silently keeping the old one.
    return [
        config.itemSelector,
        config.handleSelector || '',
        config.ignoreSelector || '',
        config.blockedItemSelector || '',
        config.dragThreshold,
    ].join('|');
}

/**
 * Make the items of a container draggable within it.
 * Safe to call repeatedly (e.g. after adding an item): already-configured items
 * are skipped, and newly added items get wired up.
 * @param {HTMLElement} container - Element holding the sortable items
 * @param {Object} [options] - See DEFAULT_OPTIONS
 */
export function enablePointerSort(container, options = {}) {
    if (!container) return;

    const config = resolveConfig(options);
    const initKey = itemInitKey(config);
    container.__pointerSortConfig = config;
    container.classList.add(CONTAINER_ENABLED_CLASS);

    container.querySelectorAll(config.itemSelector).forEach((item) => {
        item.removeAttribute('draggable');
        if (item.classList.contains(config.placeholderClass)) return;
        if (item.__pointerSortKey === initKey) return;

        if (item.__pointerSortHandler) {
            item.removeEventListener('pointerdown', item.__pointerSortHandler);
        }

        const handler = (event) => handlePointerDown(event, item, container, config);
        item.addEventListener('pointerdown', handler);
        item.__pointerSortKey = initKey;
        item.__pointerSortHandler = handler;
    });
}

/**
 * Remove drag handlers previously installed by enablePointerSort().
 * @param {HTMLElement} container - Element holding the sortable items
 * @param {Object} [options] - Used when the container has no stored config
 */
export function disablePointerSort(container, options = {}) {
    if (!container) return;

    const config = resolveConfig(container.__pointerSortConfig || options);
    container.querySelectorAll(config.itemSelector).forEach((item) => {
        if (item.__pointerSortHandler) {
            item.removeEventListener('pointerdown', item.__pointerSortHandler);
        }
        delete item.__pointerSortHandler;
        delete item.__pointerSortKey;
    });

    delete container.__pointerSortConfig;
    container.classList.remove(CONTAINER_ENABLED_CLASS);
    cancelPendingDrag(container);

    if (activeDragState && activeDragState.container === container) {
        finishPointerDrag();
    }
}

/**
 * Move an item by `offset` positions inside its container.
 * Shared by the keyboard interaction so it matches drag ordering exactly.
 * @param {HTMLElement} item - Item to move
 * @param {number} offset - Negative moves earlier, positive moves later
 * @param {Object} [options] - Same options as enablePointerSort(); use
 *   `options.container` when the item is not attached to its list yet
 * @returns {{index: number, total: number}|null} New position, or null when out of range
 */
export function moveItemWithinContainer(item, offset, options = {}) {
    if (!item || !offset) return null;

    const config = resolveConfig(options);
    const container = options.container || item.parentElement;
    if (!container) return null;

    const items = Array.from(container.querySelectorAll(config.itemSelector)).filter(
        (element) => !element.classList.contains(config.placeholderClass),
    );
    const index = items.indexOf(item);
    if (index === -1) return null;

    const target = index + offset;
    if (target < 0 || target >= items.length) return null;

    const reference = offset < 0 ? items[target] : items[target].nextSibling;
    container.insertBefore(item, reference);

    return { index: target, total: items.length };
}

function handlePointerDown(event, item, container, config) {
    if (activeDragState || pendingDragState) return;
    if (typeof event.button === 'number' && event.button !== 0) return;
    if (config.ignoreSelector && event.target.closest(config.ignoreSelector)) return;
    if (config.handleSelector && !event.target.closest(config.handleSelector)) return;
    if (config.blockedItemSelector && item.matches(config.blockedItemSelector)) return;
    if (item.classList.contains(config.placeholderClass)) return;

    if (config.dragThreshold > 0) {
        startPendingDrag({ item, container, config, startEvent: event });
        return;
    }

    // Prevent the browser's native text selection / image drag from kicking in.
    event.preventDefault();
    startPointerDrag({ item, container, config, startEvent: event });
}

function startPendingDrag({ item, container, config, startEvent }) {
    const state = {
        item,
        container,
        config,
        startX: startEvent.clientX,
        startY: startEvent.clientY,
    };

    state.onMove = (event) => {
        const dx = event.clientX - state.startX;
        const dy = event.clientY - state.startY;
        if (Math.hypot(dx, dy) < config.dragThreshold) return;

        cleanupPendingDrag();
        event.preventDefault();
        clearTextSelection();
        startPointerDrag({ item, container, config, startEvent: event });
    };
    state.onUp = () => cleanupPendingDrag();

    pendingDragState = state;

    document.addEventListener('pointermove', state.onMove);
    document.addEventListener('pointerup', state.onUp);
    document.addEventListener('pointercancel', state.onUp);
}

function cleanupPendingDrag() {
    if (!pendingDragState) return;

    const { onMove, onUp } = pendingDragState;
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
    document.removeEventListener('pointercancel', onUp);
    pendingDragState = null;
}

function cancelPendingDrag(container) {
    if (pendingDragState && (!container || pendingDragState.container === container)) {
        cleanupPendingDrag();
    }
}

function clearTextSelection() {
    if (typeof window === 'undefined' || !window.getSelection) return;
    const selection = window.getSelection();
    if (selection && selection.removeAllRanges) selection.removeAllRanges();
}

function startPointerDrag({ item, container, config, startEvent }) {
    if (activeDragState) finishPointerDrag();

    const itemRect = item.getBoundingClientRect();
    const placeholder = document.createElement('div');
    const placeholderClasses = Array.from(item.classList).filter(
        (name) => name !== config.draggingClass && name !== config.placeholderClass,
    );
    placeholderClasses.push(config.placeholderClass);
    placeholder.className = placeholderClasses.join(' ');
    placeholder.style.width = `${itemRect.width}px`;
    placeholder.style.height = `${itemRect.height}px`;

    container.insertBefore(placeholder, item);

    item.classList.add(config.draggingClass);
    item.style.width = `${itemRect.width}px`;
    item.style.height = `${itemRect.height}px`;
    item.style.position = 'fixed';
    item.style.left = `${itemRect.left}px`;
    item.style.top = `${itemRect.top}px`;
    item.style.pointerEvents = 'none';
    item.style.zIndex = '1000';

    container.classList.add(config.containerSortingClass);
    if (config.bodySortingClass && document.body) {
        document.body.classList.add(config.bodySortingClass);
    }

    // Swallow the click generated by this pointer sequence so dropping an item
    // never triggers its own click handler (copy-to-clipboard, inline editing).
    // Scoped to the dragged container so unrelated clicks are never affected.
    const swallowClick = (event) => {
        if (event.target !== container && !container.contains(event.target)) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        document.removeEventListener('click', swallowClick, true);
    };
    document.addEventListener('click', swallowClick, true);

    activeDragState = {
        container,
        item,
        placeholder,
        config,
        offsetX: startEvent.clientX - itemRect.left,
        offsetY: startEvent.clientY - itemRect.top,
        lastKnownPointer: { x: startEvent.clientX, y: startEvent.clientY },
        rafId: null,
        swallowClick,
    };

    document.addEventListener('pointermove', handlePointerMove);
    document.addEventListener('pointerup', handlePointerUp);
    document.addEventListener('pointercancel', handlePointerUp);
}

function handlePointerMove(event) {
    if (!activeDragState) return;

    activeDragState.lastKnownPointer = { x: event.clientX, y: event.clientY };

    if (activeDragState.rafId !== null) return;

    activeDragState.rafId = requestAnimationFrame(() => {
        if (!activeDragState) return;
        activeDragState.rafId = null;
        updateDraggingItemPosition();
        updatePlaceholderPosition();
    });
}

function handlePointerUp() {
    finishPointerDrag();
}

function updateDraggingItemPosition() {
    if (!activeDragState) return;

    const { item, offsetX, offsetY, lastKnownPointer } = activeDragState;
    const left = lastKnownPointer.x - offsetX;
    const top = lastKnownPointer.y - offsetY;
    item.style.left = `${left}px`;
    item.style.top = `${top}px`;
}

function updatePlaceholderPosition() {
    if (!activeDragState) return;

    const { container, placeholder, item, config, lastKnownPointer } = activeDragState;
    const siblings = Array.from(
        container.querySelectorAll(
            `${config.itemSelector}:not(.${config.placeholderClass})`,
        ),
    ).filter((element) => element !== item);

    let insertAfter = null;

    for (const sibling of siblings) {
        const rect = sibling.getBoundingClientRect();

        if (lastKnownPointer.y < rect.top) {
            container.insertBefore(placeholder, sibling);
            return;
        }

        if (lastKnownPointer.y <= rect.bottom) {
            if (lastKnownPointer.x < rect.left + rect.width / 2) {
                container.insertBefore(placeholder, sibling);
                return;
            }
            insertAfter = sibling;
            continue;
        }

        insertAfter = sibling;
    }

    if (!insertAfter) {
        container.insertBefore(placeholder, container.firstElementChild);
        return;
    }

    container.insertBefore(placeholder, insertAfter.nextSibling);
}

function finishPointerDrag() {
    if (!activeDragState) return;

    const { container, item, placeholder, config, rafId, swallowClick } = activeDragState;

    document.removeEventListener('pointermove', handlePointerMove);
    document.removeEventListener('pointerup', handlePointerUp);
    document.removeEventListener('pointercancel', handlePointerUp);

    container.classList.remove(config.containerSortingClass);
    if (config.bodySortingClass && document.body) {
        document.body.classList.remove(config.bodySortingClass);
    }

    if (rafId !== null) {
        cancelAnimationFrame(rafId);
        activeDragState.rafId = null;
    }

    // Always settle the placeholder from the last known pointer: the drop must
    // reflect the final pointer position even when no animation frame ran
    // (fast drags, or drags that started from the threshold-crossing move).
    updateDraggingItemPosition();
    updatePlaceholderPosition();

    if (placeholder && placeholder.parentNode === container) {
        container.insertBefore(item, placeholder);
        container.removeChild(placeholder);
    }

    item.classList.remove(config.draggingClass);
    item.style.position = '';
    item.style.width = '';
    item.style.height = '';
    item.style.left = '';
    item.style.top = '';
    item.style.pointerEvents = '';
    item.style.zIndex = '';

    activeDragState = null;

    if (typeof config.onSorted === 'function') {
        config.onSorted(item, container);
    }

    cleanupSwallowClick(swallowClick);
}

/**
 * The click that follows a drop is dispatched right after pointerup, so the
 * guard has to survive until the next macrotask.
 * @param {Function} handler - Capture-phase click handler to remove
 */
function cleanupSwallowClick(handler) {
    if (!handler) return;
    setTimeout(() => document.removeEventListener('click', handler, true), 0);
}
