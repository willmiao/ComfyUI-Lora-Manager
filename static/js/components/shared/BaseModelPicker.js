/**
 * BaseModelPicker.js
 * Shared searchable base model picker used by the single-model metadata modal
 * (commit mode) and the bulk base model modal (change mode).
 */

import { BASE_MODEL_CATEGORIES, getMergedBaseModels, BASE_MODELS_UPDATED_EVENT } from '../../utils/constants.js';
import { translate } from '../../utils/i18nHelpers.js';

// ── Filename-based base model inference ──────────────────────────────────────
// Rules are ordered by specificity — first match wins for dedup.
// Each rule checks the filename (lowercased) for a regex pattern and suggests
// the associated base model values.

export const BASE_MODEL_FILENAME_RULES = [
    { pattern: /flux\.?\s*2\s*klein/i, models: ['Flux.2 Klein 9B', 'Flux.2 Klein 9B-base', 'Flux.2 Klein 4B', 'Flux.2 Klein 4B-base'] },
    { pattern: /flux\.?\s*2/i, models: ['Flux.2 D', 'Flux.2 Klein 9B', 'Flux.2 Klein 4B'] },
    { pattern: /flux\.?\s*1\s*(dev|d)\b/i, models: ['Flux.1 D'] },
    { pattern: /flux\.?\s*1\s*(schnell|s)\b/i, models: ['Flux.1 S'] },
    { pattern: /flux/i, models: ['Flux.1 D', 'Flux.1 S', 'Flux.2 D'] },
    { pattern: /sdxl/i, models: ['SDXL 1.0', 'SDXL Lightning', 'SDXL Hyper'] },
    { pattern: /sd\s*1[._-\s]?5/i, models: ['SD 1.5'] },
    { pattern: /sd\s*1[._-\s]?4/i, models: ['SD 1.4'] },
    { pattern: /sd\s*1/i, models: ['SD 1.5', 'SD 1.4', 'SD 1.5 LCM', 'SD 1.5 Hyper'] },
    { pattern: /sd\s*3[._-\s]?5/i, models: ['SD 3.5', 'SD 3.5 Medium', 'SD 3.5 Large', 'SD 3.5 Large Turbo'] },
    { pattern: /sd\s*3/i, models: ['SD 3', 'SD 3.5'] },
    { pattern: /wan\s*\.?\s*video/i, models: ['Wan Video', 'Wan Video 1.3B t2v', 'Wan Video 14B t2v', 'Wan Video 14B i2v 480p', 'Wan Video 14B i2v 720p'] },
    { pattern: /hunyuan\s*\.?\s*video/i, models: ['Hunyuan Video'] },
    { pattern: /ltxv/i, models: ['LTXV', 'LTXV2', 'LTXV 2.3'] },
    { pattern: /cogvideo/i, models: ['CogVideoX'] },
    { pattern: /pony/i, models: ['Pony', 'Pony V7'] },
    { pattern: /illustrious/i, models: ['Illustrious'] },
    { pattern: /noobai/i, models: ['NoobAI'] },
    { pattern: /pixart/i, models: ['PixArt a', 'PixArt E'] },
    { pattern: /aura\s*\.?\s*flow/i, models: ['AuraFlow'] },
    { pattern: /kolors/i, models: ['Kolors'] },
    { pattern: /hunyuan\s*1/i, models: ['Hunyuan 1'] },
    { pattern: /lumina/i, models: ['Lumina'] },
    { pattern: /hidream/i, models: ['HiDream'] },
    { pattern: /qwen/i, models: ['Qwen'] },
    { pattern: /chroma/i, models: ['Chroma'] },
    { pattern: /anima/i, models: ['Anima'] },
    { pattern: /sd\s*2[._-\s]?[01]/i, models: ['SD 2.0', 'SD 2.1'] },
    { pattern: /mochi/i, models: ['Mochi'] },
    { pattern: /svd/i, models: ['SVD'] },
    { pattern: /zimage/i, models: ['ZImageTurbo', 'ZImageBase'] },
    { pattern: /nucleus/i, models: ['Nucleus'] },
    { pattern: /krea/i, models: ['Flux.1 Krea', 'Krea 2'] },
    { pattern: /ernie/i, models: ['Ernie', 'Ernie Turbo'] },
];

/**
 * Infer likely base model(s) from a filename + model name string.
 * Returns a deduplicated array in match-priority order.
 * @param {string} filename
 * @returns {string[]}
 */
export function inferBaseModelsFromFilename(filename) {
    if (!filename || typeof filename !== 'string') return [];
    const seen = new Set();
    const results = [];
    for (const rule of BASE_MODEL_FILENAME_RULES) {
        if (rule.pattern.test(filename)) {
            for (const model of rule.models) {
                if (!seen.has(model)) {
                    seen.add(model);
                    results.push(model);
                }
            }
        }
    }
    return results;
}

/**
 * Infer likely base model(s) from a set of file paths (bulk selection).
 * Each path contributes its basename to the inference; models are deduplicated
 * and sorted by how many selected paths matched them (most matches first).
 * Returns an empty array when nothing matches.
 * @param {string[]} filePaths
 * @returns {string[]}
 */
export function inferBaseModelsFromFilepaths(filePaths) {
    if (!Array.isArray(filePaths) || filePaths.length === 0) return [];
    const hitCounts = new Map(); // model -> number of paths that matched it
    for (const filePath of filePaths) {
        if (!filePath || typeof filePath !== 'string') continue;
        const basename = filePath.split(/[\\/]/).pop();
        for (const model of inferBaseModelsFromFilename(basename)) {
            hitCounts.set(model, (hitCounts.get(model) || 0) + 1);
        }
    }
    return Array.from(hitCounts.keys())
        .sort((a, b) => hitCounts.get(b) - hitCounts.get(a));
}

/**
 * Build the full categorized option list. Reads BASE_MODEL_CATEGORIES and
 * getMergedBaseModels() fresh on every call so late-arriving dynamic models
 * are picked up; uncategorized dynamic entries land in "Other (API)".
 * @returns {Array<{value: string, label: string, category: string}>}
 */
function buildCategorizedOptions() {
    const allModels = [];
    const categorizedModels = new Set();

    Object.entries(BASE_MODEL_CATEGORIES).forEach(([category, models]) => {
        models.forEach(model => {
            allModels.push({ value: model, label: model, category });
            categorizedModels.add(model);
        });
    });

    const uncategorizedModels = getMergedBaseModels().filter(model => !categorizedModels.has(model));
    uncategorizedModels.forEach(model => {
        allModels.push({ value: model, label: model, category: 'Other (API)' });
    });

    return allModels;
}

/**
 * Create a searchable base model picker.
 *
 * Two commit semantics are supported:
 * - 'commit' (default): selecting an item immediately calls onCommit(value).
 *   Escape or an outside click calls onDismiss().
 * - 'change': selecting an item updates the internal value and calls
 *   onChange(value); the caller owns when the selected value is persisted.
 * Typed text doubles as a custom value unless allowCustomValue is false,
 * in which case it is search-only.
 *
 * @param {Object} options
 * @param {string[]} [options.suggestions] - Models shown in the Suggested section
 * @param {string} [options.initialValue] - Initially selected value
 * @param {'commit'|'change'} [options.mode] - Commit semantics
 * @param {boolean} [options.allowCustomValue=true] - Accept typed text as a custom value
 * @param {(value: string) => void} [options.onCommit] - Commit-mode commit callback
 * @param {(value: string) => void} [options.onChange] - Called whenever the value changes
 * @param {() => void} [options.onDismiss] - Commit-mode dismiss callback (Escape/outside click)
 * @returns {{ element: HTMLElement, getValue: Function, setValue: Function, refreshOptions: Function, destroy: Function }}
 */
export function createBaseModelPicker(options = {}) {
    const {
        suggestions = [],
        initialValue = '',
        mode = 'commit',
        allowCustomValue = true,
        onCommit = null,
        onChange = null,
        onDismiss = null,
    } = options;

    const isCommitMode = mode !== 'change';
    let currentValue = initialValue || '';
    let currentFilter = '';
    let destroyed = false;

    // ── Build widget DOM ────────────────────────────────────────────────────
    const wrapper = document.createElement('div');
    wrapper.className = 'base-model-search-wrapper';

    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'base-model-search-input-wrapper';
    const searchIcon = document.createElement('i');
    searchIcon.className = 'fas fa-search search-icon';
    searchIcon.setAttribute('aria-hidden', 'true');
    inputWrapper.appendChild(searchIcon);
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'base-model-search-input';
    searchInput.placeholder = translate('modals.model.metadata.baseModelSearchPlaceholder', {}, 'Search base model…');
    searchInput.autocomplete = 'off';
    searchInput.spellcheck = false;
    inputWrapper.appendChild(searchInput);
    wrapper.appendChild(inputWrapper);

    const dropdown = document.createElement('div');
    dropdown.className = 'base-model-dropdown';
    wrapper.appendChild(dropdown);

    // ── Render ──────────────────────────────────────────────────────────────
    function renderDropdown(filterText) {
        currentFilter = filterText || '';
        const lowerFilter = currentFilter.toLowerCase().trim();
        const allModels = buildCategorizedOptions();
        const suggestedSet = new Set(suggestions);
        dropdown.innerHTML = '';
        let hasVisibleItems = false;
        const fragment = document.createDocumentFragment();

        // 1. Suggested section (filtered by search)
        const suggestedToShow = lowerFilter
            ? suggestions.filter(m => m.toLowerCase().includes(lowerFilter))
            : suggestions;

        if (suggestedToShow.length > 0) {
            const section = document.createElement('div');
            section.className = 'base-model-dropdown-section';

            const header = document.createElement('div');
            header.className = 'base-model-dropdown-header suggested-header';
            header.innerHTML = '<i class="fas fa-star" aria-hidden="true"></i> ' +
                translate('modals.model.metadata.baseModelSuggested', {}, 'Suggested');
            section.appendChild(header);

            suggestedToShow.forEach(model => {
                const item = document.createElement('div');
                item.className = 'base-model-dropdown-item';
                if (model === currentValue) item.classList.add('selected');
                item.dataset.value = model;
                item.textContent = model;
                section.appendChild(item);
                hasVisibleItems = true;
            });

            fragment.appendChild(section);
        }

        // 2. Categorized options (deduplicated against suggestions)
        const categoryMap = {};
        allModels.forEach(m => {
            if (suggestedSet.has(m.value)) return; // already shown in Suggested
            if (lowerFilter && !m.label.toLowerCase().includes(lowerFilter)) return;
            if (!categoryMap[m.category]) categoryMap[m.category] = [];
            categoryMap[m.category].push(m);
        });

        Object.entries(categoryMap).forEach(([category, items]) => {
            if (items.length === 0) return;
            const section = document.createElement('div');
            section.className = 'base-model-dropdown-section';

            const header = document.createElement('div');
            header.className = 'base-model-dropdown-header';
            header.textContent = category;
            section.appendChild(header);

            items.forEach(m => {
                const item = document.createElement('div');
                item.className = 'base-model-dropdown-item';
                if (m.value === currentValue) item.classList.add('selected');
                item.dataset.value = m.value;
                item.textContent = m.label;
                section.appendChild(item);
                hasVisibleItems = true;
            });

            fragment.appendChild(section);
        });

        // 3. Empty state
        if (!hasVisibleItems) {
            const empty = document.createElement('div');
            empty.className = 'base-model-dropdown-empty';
            empty.textContent = translate('modals.model.metadata.baseModelNoMatch', {}, 'No matching base models');
            fragment.appendChild(empty);
        }

        dropdown.appendChild(fragment);

        // Scroll the selected item into view
        const selected = dropdown.querySelector('.base-model-dropdown-item.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }
    }

    // Initial render — show everything
    renderDropdown('');

    // ── Value handling ──────────────────────────────────────────────────────
    function applySelection(value) {
        currentValue = value;
        if (isCommitMode) {
            if (typeof onCommit === 'function') onCommit(value);
            return;
        }
        // Change mode: mirror the selection into the input and notify only.
        searchInput.value = value;
        // Filter the list down to the selected item instead of resetting to
        // the full list (which scroll-jumps to the selection). Custom values
        // that are not in the option list keep the full list visible.
        const isKnownValue = suggestions.includes(value) ||
            buildCategorizedOptions().some(m => m.value === value);
        renderDropdown(isKnownValue ? value : '');
        if (typeof onChange === 'function') onChange(value);
    }

    // ── Events ──────────────────────────────────────────────────────────────
    let filterTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(filterTimeout);
        filterTimeout = setTimeout(() => {
            renderDropdown(searchInput.value);
            // Change mode with custom values: typed text is the live value.
            if (!isCommitMode && allowCustomValue) {
                currentValue = searchInput.value;
                if (typeof onChange === 'function') onChange(currentValue);
            }
        }, 50);
    });

    // Click to select
    dropdown.addEventListener('click', (e) => {
        const item = e.target.closest('.base-model-dropdown-item');
        if (!item) return;
        applySelection(item.dataset.value);
    });

    // Keyboard navigation
    searchInput.addEventListener('keydown', (e) => {
        const items = Array.from(dropdown.querySelectorAll('.base-model-dropdown-item'));
        const activeIdx = items.findIndex(el => el.classList.contains('active'));

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            items.forEach(el => el.classList.remove('active'));
            const next = Math.min(activeIdx + 1, items.length - 1);
            if (items[next]) {
                items[next].classList.add('active');
                items[next].scrollIntoView({ block: 'nearest' });
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            items.forEach(el => el.classList.remove('active'));
            const prev = Math.max(activeIdx - 1, 0);
            if (items[prev]) {
                items[prev].classList.add('active');
                items[prev].scrollIntoView({ block: 'nearest' });
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const activeItem = items.find(el => el.classList.contains('active'));
            if (activeItem) {
                applySelection(activeItem.dataset.value);
            } else if (allowCustomValue && searchInput.value.trim()) {
                applySelection(searchInput.value.trim());
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            if (isCommitMode && typeof onDismiss === 'function') {
                onDismiss();
            }
        }
    });

    // Commit mode: outside click commits typed text (when custom values are
    // allowed) or dismisses. Deferred to avoid the opening click itself.
    const outsideClickHandler = (e) => {
        if (wrapper.contains(e.target)) return;
        const typedValue = searchInput.value.trim();
        if (allowCustomValue && typedValue) {
            applySelection(typedValue);
        } else if (typeof onDismiss === 'function') {
            onDismiss();
        }
    };
    let outsideClickTimer = null;
    if (isCommitMode) {
        outsideClickTimer = setTimeout(() => {
            outsideClickTimer = null;
            if (!destroyed) {
                document.addEventListener('click', outsideClickHandler);
            }
        }, 0);
    }

    // Refresh when dynamic base models arrive late; keeps the current search text.
    const handleBaseModelsUpdated = () => {
        if (destroyed) return;
        refreshOptions();
    };
    window.addEventListener(BASE_MODELS_UPDATED_EVENT, handleBaseModelsUpdated);

    // ── Public API ──────────────────────────────────────────────────────────
    function getValue() {
        return currentValue;
    }

    function setValue(value) {
        currentValue = value || '';
        searchInput.value = currentValue;
        renderDropdown('');
    }

    function refreshOptions() {
        renderDropdown(currentFilter);
    }

    function destroy() {
        if (destroyed) return;
        destroyed = true;
        clearTimeout(filterTimeout);
        if (outsideClickTimer) {
            clearTimeout(outsideClickTimer);
            outsideClickTimer = null;
        }
        document.removeEventListener('click', outsideClickHandler);
        window.removeEventListener(BASE_MODELS_UPDATED_EVENT, handleBaseModelsUpdated);
    }

    return { element: wrapper, getValue, setValue, refreshOptions, destroy };
}
