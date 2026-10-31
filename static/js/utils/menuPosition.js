/**
 * Viewport positioning for `position: fixed` popup menus.
 *
 * `.context-menu` is `position: fixed` (see menu.css), so a menu is placed with
 * viewport coordinates and can be clipped only by the browser window. The
 * previous placement used the cursor coordinates directly and merely "flipped"
 * the menu to the opposite side when it did not fit. A flipped menu could still
 * leave the viewport — a menu taller than the space around a click near the
 * bottom edge ends up above the top edge — and a menu taller than the viewport
 * could not be placed at all. Both cases hide entries with no way to reach them
 * (#1167).
 *
 * This helper picks the side with room, clamps the result inside the viewport
 * on both axes, and caps the height so an oversized menu scrolls internally
 * instead of being cut off.
 */

export const MENU_VIEWPORT_MARGIN = 8;

function viewportWidth() {
    return window.innerWidth || document.documentElement.clientWidth || 0;
}

function viewportHeight() {
    return window.innerHeight || document.documentElement.clientHeight || 0;
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Position a fixed popup menu relative to a viewport point.
 *
 * @param {HTMLElement} menu The menu element (must be `position: fixed`).
 * @param {number} x Cursor X, or the anchor's right edge when `alignX` is 'right'.
 * @param {number} y Desired top edge (cursor Y, or the anchor's bottom edge).
 * @param {{margin?: number, alignX?: 'left'|'right'}} [options] `margin` is the
 *        gap kept from the viewport edges; `alignX: 'right'` anchors the menu's
 *        right edge to `x` (dropdowns opened from a button) instead of its left.
 * @returns {{left: number, top: number, width: number, height: number}} The
 *          applied geometry, which is also handy for assertions.
 */
export function positionFixedMenu(menu, x, y, options = {}) {
    const margin = Number.isFinite(options.margin) ? options.margin : MENU_VIEWPORT_MARGIN;
    const alignRight = options.alignX === 'right';

    // Drop size caps left over from a previous open before measuring this one.
    menu.style.maxHeight = '';
    menu.style.overflowY = '';
    menu.style.display = 'block';

    let rect = menu.getBoundingClientRect();
    const viewportW = viewportWidth();
    const viewportH = viewportHeight();

    // A menu taller than the viewport cannot be placed anywhere in full: cap it
    // and let it scroll so every entry stays reachable.
    const maxHeight = Math.max(viewportH - margin * 2, 0);
    if (maxHeight > 0 && rect.height > maxHeight) {
        menu.style.maxHeight = `${maxHeight}px`;
        menu.style.overflowY = 'auto';
        rect = menu.getBoundingClientRect();
    }

    const width = rect.width;
    const height = rect.height;

    // Horizontal: keep the requested side, flip only when the other one has
    // room, then clamp so neither an anchored nor a flipped menu leaves the
    // viewport when the menu is wider than the space on either side.
    let left = alignRight ? x - width : x;
    if (!alignRight && left + width > viewportW - margin) {
        left = x - width;
    }
    left = clamp(left, margin, viewportW - width - margin);

    // Vertical: below the cursor when it fits, above when that fits, otherwise
    // clamp — an oversized menu ends up pinned to the edge that shows the most.
    let top = y;
    if (top + height > viewportH - margin && y - height >= margin) {
        top = y - height;
    }
    top = clamp(top, margin, viewportH - height - margin);

    menu.style.left = `${Math.round(left)}px`;
    menu.style.top = `${Math.round(top)}px`;

    return { left, top, width, height };
}

/**
 * Keep an open submenu inside the viewport.
 *
 * Submenus are absolutely positioned inside their trigger row (menu.css), so
 * they inherit the parent menu's placement. That works horizontally (flip to
 * the other side) but not vertically: when the trigger row sits near the bottom
 * edge, the submenu extends below the window. Shift it up, and cap its height
 * when it cannot fit even then.
 *
 * @param {HTMLElement} submenu The `.context-submenu` element, already visible.
 */
export function positionSubmenu(submenu, margin = MENU_VIEWPORT_MARGIN) {
    const viewportW = viewportWidth();
    const viewportH = viewportHeight();

    // Reset the vertical offset so the CSS placement (top: -1px) is the baseline.
    submenu.style.top = '';
    submenu.style.maxHeight = '';
    submenu.style.overflowY = '';

    if (submenu.getBoundingClientRect().right > viewportW - margin) {
        submenu.classList.add('flip-left');
    } else {
        submenu.classList.remove('flip-left');
    }

    let rect = submenu.getBoundingClientRect();
    const maxHeight = Math.max(viewportH - margin * 2, 0);
    if (maxHeight > 0 && rect.height > maxHeight) {
        submenu.style.maxHeight = `${maxHeight}px`;
        submenu.style.overflowY = 'auto';
        rect = submenu.getBoundingClientRect();
    }

    // `top` is relative to the trigger row, so shifting by the overflow amount
    // moves the submenu up the same number of pixels on screen.
    const baseTop = parseFloat(window.getComputedStyle(submenu).top) || 0;
    let offset = 0;
    if (rect.bottom > viewportH - margin) {
        offset -= rect.bottom - (viewportH - margin);
    }
    if (rect.top + offset < margin) {
        offset += margin - (rect.top + offset);
    }
    if (offset !== 0) {
        submenu.style.top = `${Math.round(baseTop + offset)}px`;
    }
}
