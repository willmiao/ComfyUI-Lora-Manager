/**
 * Floating tooltip for `[data-tooltip]` triggers.
 *
 * A CSS pseudo-element tooltip is a descendant of the element that owns it, so
 * any scrollable ancestor clips it: the settings modal scrolls
 * (`.settings-content` uses `overflow-y: auto`), which chopped the first lines
 * off help texts whose trigger sits near the top of the pane (the Active
 * Library deprecation notice was the visible symptom).
 *
 * The tooltip is therefore rendered once into `<body>` and positioned with
 * `position: fixed`: no ancestor can clip it. It prefers the space above the
 * trigger and flips below when it does not fit, and it is clamped to the
 * viewport so it never spills off screen.
 */

const TOOLTIP_ID = 'lm-tooltip';
const TRIGGER_SELECTOR = '[data-tooltip]';
const VISIBLE_CLASS = 'visible';

// Distance kept between the trigger and the tooltip.
const TRIGGER_GAP = 8;
// Distance kept between the tooltip and the viewport edges.
const VIEWPORT_MARGIN = 8;

let tooltipElement = null;
let activeTrigger = null;
let initialized = false;

function viewportWidth() {
    return window.innerWidth || document.documentElement.clientWidth || 0;
}

function viewportHeight() {
    return window.innerHeight || document.documentElement.clientHeight || 0;
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
}

function getTooltipElement() {
    // The element can be dropped by a DOM reset, so re-create it when detached.
    if (tooltipElement && tooltipElement.isConnected) {
        return tooltipElement;
    }

    tooltipElement = document.getElementById(TOOLTIP_ID);
    if (!tooltipElement) {
        tooltipElement = document.createElement('div');
        tooltipElement.id = TOOLTIP_ID;
        tooltipElement.className = 'lm-tooltip';
        tooltipElement.setAttribute('role', 'tooltip');
        document.body.appendChild(tooltipElement);
    }

    return tooltipElement;
}

function positionTooltip(trigger) {
    const element = getTooltipElement();
    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = element.getBoundingClientRect();

    // Prefer above the trigger, flip below when there is not enough room.
    const fitsAbove = triggerRect.top - TRIGGER_GAP - tooltipRect.height >= VIEWPORT_MARGIN;
    const preferredTop = fitsAbove
        ? triggerRect.top - tooltipRect.height - TRIGGER_GAP
        : triggerRect.bottom + TRIGGER_GAP;

    const maxTop = viewportHeight() - tooltipRect.height - VIEWPORT_MARGIN;
    const maxLeft = viewportWidth() - tooltipRect.width - VIEWPORT_MARGIN;

    element.style.top = `${Math.round(clamp(preferredTop, VIEWPORT_MARGIN, maxTop))}px`;
    // Center on the trigger, then keep the box inside the viewport.
    element.style.left = `${Math.round(
        clamp(triggerRect.left + (triggerRect.width - tooltipRect.width) / 2, VIEWPORT_MARGIN, maxLeft)
    )}px`;
}

function showTooltip(trigger) {
    const text = trigger.getAttribute('data-tooltip');
    if (!text) return;

    const element = getTooltipElement();
    activeTrigger = trigger;
    element.textContent = text;

    // Measured while hidden: `visibility: hidden` still lays the box out, which
    // keeps the tooltip from flashing at the previous trigger's position.
    element.classList.remove(VISIBLE_CLASS);
    positionTooltip(trigger);
    element.classList.add(VISIBLE_CLASS);

    trigger.setAttribute('aria-describedby', TOOLTIP_ID);
}

/**
 * Hide the tooltip if one is showing.
 */
export function hideTooltip() {
    if (activeTrigger) {
        activeTrigger.removeAttribute('aria-describedby');
        activeTrigger = null;
    }

    if (tooltipElement) {
        tooltipElement.classList.remove(VISIBLE_CLASS);
    }
}

function triggerFromEvent(event) {
    const target = event.target;
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest(TRIGGER_SELECTOR);
}

function handlePointerOver(event) {
    const trigger = triggerFromEvent(event);
    // Moving between children of the same trigger must not restart the tooltip.
    if (!trigger || trigger === activeTrigger) return;
    showTooltip(trigger);
}

function handlePointerOut(event) {
    if (!activeTrigger) return;

    const related = event.relatedTarget;
    if (related && activeTrigger.contains(related)) return;

    if (triggerFromEvent(event) === activeTrigger) {
        hideTooltip();
    }
}

function handleFocusIn(event) {
    const trigger = triggerFromEvent(event);
    if (trigger && trigger !== activeTrigger) {
        showTooltip(trigger);
    }
}

function handleFocusOut(event) {
    if (!activeTrigger) return;

    const related = event.relatedTarget;
    if (related && activeTrigger.contains(related)) return;

    if (triggerFromEvent(event) === activeTrigger) {
        hideTooltip();
    }
}

function handleKeyDown(event) {
    if (event.key === 'Escape') {
        hideTooltip();
    }
}

function handleViewportChange() {
    if (!activeTrigger) return;

    // The trigger can be removed while its tooltip is open (settings sections
    // are re-rendered on search).
    if (!activeTrigger.isConnected) {
        hideTooltip();
        return;
    }

    positionTooltip(activeTrigger);
}

/**
 * Start listening for tooltip triggers. Delegated, so triggers added later
 * (settings rows are re-rendered) work without extra wiring. Idempotent.
 */
export function initTooltips() {
    if (initialized) return;
    initialized = true;

    document.addEventListener('mouseover', handlePointerOver);
    document.addEventListener('mouseout', handlePointerOut);
    document.addEventListener('focusin', handleFocusIn);
    document.addEventListener('focusout', handleFocusOut);
    document.addEventListener('keydown', handleKeyDown);
    // Tapping a trigger on touch devices leaves no mouseout behind.
    document.addEventListener('touchstart', hideTooltip, { passive: true });

    // Capture phase so scrolling any container (the settings pane included)
    // keeps the tooltip attached to its trigger.
    window.addEventListener('scroll', handleViewportChange, true);
    window.addEventListener('resize', handleViewportChange);
}
