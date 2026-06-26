// SortDropdown.js — Decoupled sort trigger.
//
// The native <select> sizes its trigger to the widest <option>, so long
// options (e.g. "Fewest versions first") or long i18n translations force the
// control to be far wider than the selected text needs. This module wraps the
// existing <select> with a custom trigger + menu that mirror its state, so the
// trigger sizes to the selected text while the menu sizes to its content.
//
// The native <select> stays in the DOM (visually hidden) so existing code that
// reads/writes `.value` / `.disabled` and dynamically adds/removes <option>s
// (e.g. the VLM temporary option) keeps working unchanged. The `value` and
// `disabled` setters are overridden on the instance to keep the trigger label
// and disabled styling in sync with programmatic changes.
//
// Keyboard navigation (arrows, Home/End, type-to-select) mirrors native
// <select> behavior so the control remains fully accessible.

const SORT_GROUP_SELECTOR = '.sort-dropdown-group';
const ACTIVE_GROUP_SELECTOR = '.sort-dropdown-group.active, .dropdown-group.active';

/**
 * Initialize a decoupled sort dropdown around a native <select>.
 * Idempotent: safe to call more than once on the same element.
 * @param {HTMLSelectElement|null} select
 * @returns {void}
 */
export function initSortDropdown(select) {
    if (!select) return;

    const group = select.closest(SORT_GROUP_SELECTOR);
    if (!group || group.dataset.sortReady === '1') return;

    const trigger = group.querySelector('.sort-trigger');
    const menu = group.querySelector('.sort-dropdown-menu');
    const label = group.querySelector('.sort-trigger__label');
    if (!trigger || !menu || !label) return;

    const getOptions = () => menu.querySelectorAll('.sort-option');

    const buildItem = (opt) => {
        const item = document.createElement('div');
        item.className = 'sort-option';
        item.setAttribute('role', 'option');
        item.tabIndex = -1;
        item.dataset.value = opt.value;
        item.textContent = opt.textContent;
        item.addEventListener('click', (event) => {
            event.stopPropagation();
            if (select.disabled) return;
            choose(opt.value);
            close();
        });
        return item;
    };

    const buildMenu = () => {
        menu.innerHTML = '';
        const fragment = document.createDocumentFragment();
        for (const child of Array.from(select.children)) {
            if (child.tagName === 'OPTGROUP') {
                const header = document.createElement('div');
                header.className = 'sort-optgroup-label';
                header.textContent = child.label || '';
                fragment.appendChild(header);
                for (const opt of Array.from(child.children)) {
                    fragment.appendChild(buildItem(opt));
                }
            } else if (child.tagName === 'OPTION') {
                fragment.appendChild(buildItem(child));
            }
        }
        menu.appendChild(fragment);
        syncSelected();
    };

    const syncSelected = () => {
        const value = select.value;
        let labelText = '';
        let matched = false;
        getOptions().forEach((el) => {
            const selected = el.dataset.value === value;
            el.classList.toggle('is-selected', selected);
            el.setAttribute('aria-selected', selected ? 'true' : 'false');
            if (selected) {
                labelText = el.textContent;
                matched = true;
            }
        });
        if (!matched) {
            const opt = select.querySelector(`option[value="${cssEscape(value)}"]`);
            labelText = opt
                ? opt.textContent
                : (select.options[select.selectedIndex]?.textContent ?? '');
        }
        label.textContent = labelText;
    };

    const choose = (value) => {
        if (select.value === value) return;
        select.value = value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
    };

    const open = () => {
        document.querySelectorAll(ACTIVE_GROUP_SELECTOR).forEach((g) => {
            if (g !== group) g.classList.remove('active');
        });
        group.classList.add('active');
        trigger.setAttribute('aria-expanded', 'true');
        // Focus the currently selected option (or the first option) so
        // keyboard navigation starts from a sensible position.
        requestAnimationFrame(() => {
            const selected = menu.querySelector('.sort-option.is-selected');
            (selected || getOptions()[0])?.focus();
        });
    };

    const close = () => {
        group.classList.remove('active');
        trigger.setAttribute('aria-expanded', 'false');
    };

    const toggle = () => {
        if (group.classList.contains('active')) close();
        else open();
    };

    // ---- keyboard navigation ----

    // Type-to-select buffer: accumulate characters and reset after a pause.
    // Shared between trigger and menu keydown handlers.
    let typeBuffer = '';
    let typeTimer = null;

    const focusOptionByText = (prefix) => {
        const options = getOptions();
        const lower = prefix.toLowerCase();
        for (let i = 0; i < options.length; i++) {
            if (options[i].textContent.toLowerCase().startsWith(lower)) {
                options[i].focus();
                return;
            }
        }
    };

    const moveFocus = (options, direction) => {
        const focused = menu.querySelector('.sort-option:focus');
        let idx = focused ? Array.from(options).indexOf(focused) : -1;
        idx = Math.max(0, Math.min(options.length - 1, idx + direction));
        options[idx]?.focus();
    };

    const handleTypeToSelect = (event) => {
        if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return false;
        event.preventDefault();
        clearTimeout(typeTimer);
        typeBuffer += event.key;
        focusOptionByText(typeBuffer);
        typeTimer = setTimeout(() => { typeBuffer = ''; }, 800);
        return true;
    };

    trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        if (select.disabled) return;
        toggle();
    });

    trigger.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            close();
        } else if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
            event.preventDefault();
            if (!select.disabled) toggle();
        } else if (!group.classList.contains('active')) {
            // Type-to-select on closed dropdown: open and highlight match
            if (handleTypeToSelect(event)) {
                open();
            }
        }
    });

    menu.addEventListener('keydown', (event) => {
        const options = getOptions();
        if (options.length === 0) return;

        switch (event.key) {
            case 'Escape':
                event.preventDefault();
                close();
                trigger.focus();
                return;

            case 'ArrowDown':
                event.preventDefault();
                moveFocus(options, 1);
                return;

            case 'ArrowUp':
                event.preventDefault();
                moveFocus(options, -1);
                return;

            case 'Home':
                event.preventDefault();
                options[0]?.focus();
                return;

            case 'End':
                event.preventDefault();
                options[options.length - 1]?.focus();
                return;

            case 'Enter':
            case ' ':
                event.preventDefault();
                if (select.disabled) return;
                const focused = menu.querySelector('.sort-option:focus');
                if (focused) {
                    choose(focused.dataset.value);
                    close();
                    trigger.focus();
                }
                return;
        }

        handleTypeToSelect(event);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (event) => {
        if (!group.contains(event.target)) {
            close();
            trigger.focus();
        }
    });

    // ---- property overrides ----

    // Override `value` and `disabled` on this instance so programmatic
    // changes (loadSortPreference, VLM toggle, excluded-view sync, ...) keep
    // the trigger label and disabled styling in sync without touching callers.
    const proto = Object.getPrototypeOf(select);
    const valueDescriptor =
        Object.getOwnPropertyDescriptor(proto, 'value') ||
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    const disabledDescriptor =
        Object.getOwnPropertyDescriptor(proto, 'disabled') ||
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'disabled');

    if (valueDescriptor) {
        Object.defineProperty(select, 'value', {
            get() { return valueDescriptor.get.call(this); },
            set(v) {
                valueDescriptor.set.call(this, v);
                syncSelected();
            },
            configurable: true,
        });
    }

    if (disabledDescriptor) {
        Object.defineProperty(select, 'disabled', {
            get() { return disabledDescriptor.get.call(this); },
            set(v) {
                disabledDescriptor.set.call(this, v);
                group.classList.toggle('is-disabled', Boolean(v));
                trigger.disabled = Boolean(v);
                if (v) close();
            },
            configurable: true,
        });
    }

    // Rebuild the menu when <option>s change (VLM adds/removes a temporary
    // option at runtime).
    const observer = new MutationObserver(() => buildMenu());
    observer.observe(select, { childList: true });

    buildMenu();
    group.dataset.sortReady = '1';
}

function cssEscape(value) {
    if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') {
        return CSS.escape(value);
    }
    // Fallback for environments without CSS.escape
    return String(value).replace(/[!"#$%&'()*+,./:;<=>?@[\]^`{|}~\\ -]/g, '\\$&');
}
