// ModelTypeDropdown.js — Single-select model sub-type switcher for the
// controls bar (next to the sort dropdown).
//
// The filter panel's "Model Types" section is a multi-select filter buried
// behind the Filter button; switching the current view between sub-types
// (e.g. VAE vs Text Encoder on the Other page) through it takes several
// clicks and leaves no visible state. This dropdown is the quick,
// always-visible, single-select counterpart: picking a type sets
// filterManager.filters.modelTypes to exactly that type, "All Types" clears
// it. Multi-selections made in the filter panel are still honored — the
// trigger then shows "{count} types" until the user picks a single entry.
//
// Rendered on pages whose model-types endpoint can return more than one
// sub-type (loras / checkpoints / other); it hides itself otherwise.

import { MODEL_TYPE_DISPLAY_NAMES } from '../../utils/constants.js';
import { translate } from '../../utils/i18nHelpers.js';
import { formatCount, formatCountTitle } from '../../utils/formatters.js';

const GROUP_ID = 'modelTypeDropdown';
const ALL_TYPES_VALUE = '';
const ACTIVE_GROUP_SELECTOR = '.dropdown-group.active, .sort-dropdown-group.active';

function getLabelText() {
    return {
        all: translate('loras.controls.modelType.all', {}, 'All Types'),
        multiple: (count) => translate('loras.controls.modelType.multiple', { count }, `${count} types`),
    };
}

/**
 * Initialize the model type dropdown for the current page.
 * Idempotent: safe to call more than once.
 * @param {string} pageType - 'loras' | 'checkpoints' | 'other'
 */
export async function initModelTypeDropdown(pageType) {
    const group = document.getElementById(GROUP_ID);
    if (!group || group.dataset.modelTypeReady === '1') return;
    group.dataset.modelTypeReady = '1';

    const trigger = group.querySelector('.model-type-trigger');
    const menu = group.querySelector('.model-type-dropdown-menu');
    const label = group.querySelector('.model-type-trigger__label');
    if (!trigger || !menu || !label) return;

    let types = [];
    try {
        const response = await fetch(`/api/lm/${pageType}/model-types?limit=20`);
        if (!response.ok) throw new Error('Failed to fetch model types');
        const data = await response.json();
        if (!data.success || !Array.isArray(data.model_types)) throw new Error('Invalid response format');
        // Same normalization as FilterManager.createModelTypeTags: lowercase,
        // and only sub-types we have a display name for.
        types = data.model_types
            .map((entry) => {
                if (!entry || !entry.type) return null;
                const typeKey = entry.type.toString().trim().toLowerCase();
                if (!typeKey || !MODEL_TYPE_DISPLAY_NAMES[typeKey]) return null;
                return { type: typeKey, count: Number(entry.count) || 0 };
            })
            .filter(Boolean);
    } catch (error) {
        console.error('Error loading model types for dropdown:', error);
        return;
    }

    // Nothing to switch between — keep the control hidden.
    if (types.length <= 1) return;

    const filterManager = () => window.filterManager;

    const getSelectedTypes = () => filterManager()?.filters?.modelTypes ?? [];

    const buildMenu = () => {
        const labels = getLabelText();
        menu.innerHTML = '';
        const fragment = document.createDocumentFragment();

        const allItem = document.createElement('div');
        allItem.className = 'model-type-option';
        allItem.setAttribute('role', 'option');
        allItem.tabIndex = -1;
        allItem.dataset.value = ALL_TYPES_VALUE;
        allItem.textContent = labels.all;
        fragment.appendChild(allItem);

        types.forEach(({ type, count }) => {
            const item = document.createElement('div');
            item.className = 'model-type-option';
            item.setAttribute('role', 'option');
            item.tabIndex = -1;
            item.dataset.value = type;
            item.textContent = `${MODEL_TYPE_DISPLAY_NAMES[type]} (${formatCount(count)})`;
            // Same rule as the filter chips: the tooltip carries the exact count
            // at every magnitude, so hovering behaves the same whether or not
            // the menu had to abbreviate. It also replaces the tooltip this
            // option would otherwise inherit from the group, which describes the
            // control rather than this entry.
            item.title = formatCountTitle(MODEL_TYPE_DISPLAY_NAMES[type], count);
            fragment.appendChild(item);
        });

        menu.appendChild(fragment);
    };

    const getOptions = () => menu.querySelectorAll('.model-type-option');

    const syncFromFilters = () => {
        const labels = getLabelText();
        const selected = getSelectedTypes();
        let labelText;
        if (selected.length === 0) {
            labelText = labels.all;
        } else if (selected.length === 1 && MODEL_TYPE_DISPLAY_NAMES[selected[0]]) {
            labelText = MODEL_TYPE_DISPLAY_NAMES[selected[0]];
        } else {
            labelText = labels.multiple(selected.length);
        }
        label.textContent = labelText;

        const singleValue = selected.length === 1 ? selected[0] : null;
        getOptions().forEach((el) => {
            const isSelected = selected.length === 0
                ? el.dataset.value === ALL_TYPES_VALUE
                : el.dataset.value === singleValue;
            el.classList.toggle('is-selected', isSelected);
            el.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        });
    };

    const choose = async (value) => {
        const fm = filterManager();
        if (!fm) return;
        fm.filters.modelTypes = value === ALL_TYPES_VALUE ? [] : [value];
        fm.updateModelTypeSelections();
        fm.updateActiveFiltersCount();
        syncFromFilters();
        await fm.applyFilters(false);
    };

    const open = () => {
        document.querySelectorAll(ACTIVE_GROUP_SELECTOR).forEach((g) => {
            if (g !== group) g.classList.remove('active');
        });
        group.classList.add('active');
        trigger.setAttribute('aria-expanded', 'true');
        requestAnimationFrame(() => {
            const selected = menu.querySelector('.model-type-option.is-selected');
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

    // ---- keyboard navigation (mirrors SortDropdown.js) ----

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
        const focused = menu.querySelector('.model-type-option:focus');
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

    menu.addEventListener('click', (event) => {
        const item = event.target.closest('.model-type-option');
        if (!item) return;
        event.stopPropagation();
        choose(item.dataset.value);
        close();
        trigger.focus();
    });

    trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        toggle();
    });

    trigger.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            close();
        } else if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
            event.preventDefault();
            toggle();
        } else if (!group.classList.contains('active')) {
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
                const focused = menu.querySelector('.model-type-option:focus');
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
        }
    });

    buildMenu();
    syncFromFilters();
    // Record that the control is usable before revealing it: PageControls'
    // excluded-view sync must be able to tell "not initialized / single type"
    // (stay hidden) apart from "available, temporarily hidden by excluded
    // view" (restore on exit).
    group.dataset.modelTypeAvailable = '1';
    // The init fetch is async and PageControls.syncExcludedViewState() has
    // already run by now, so only reveal the control when the excluded view
    // is not the current mode.
    if (!document.body.classList.contains('excluded-view-active')) {
        group.classList.remove('hidden');
    }

    // Let FilterManager push external changes (panel chips, presets, clear)
    // back into the trigger label and menu selection.
    window.modelTypeDropdown = { syncFromFilters };
}
