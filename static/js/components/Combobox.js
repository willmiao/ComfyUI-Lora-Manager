// Combobox.js — Reusable dropdown-suggestion + free-text input component.
//
// Enhances an existing <input> element with a dropdown panel that merges static
// `presets` with asynchronously fetched options (`fetchOptions`). The input
// remains a free-text field — selecting a dropdown option is optional, the
// user can always type an arbitrary value.
//
// Zero dependencies: pure DOM manipulation. Exported on `window.Combobox`
// so non-module callers can instantiate it, and as a named ES module export
// for callers that import it directly.
//
// Usage:
//   const box = new Combobox(inputEl, {
//     presets: ['masterpiece', 'best quality'],
//     fetchOptions: async (q) => await fetchSuggestions(q),
//     placeholder: 'Type a value…',
//     onSelect: (value) => console.log('chose', value),
//   });
//   box.updatePresets(['new', 'presets']);
//   box.setValue('masterpiece');

const DEBOUNCE_MS = 300;

export class Combobox {
    /**
     * @param {HTMLInputElement} inputElement Existing <input> to enhance.
     * @param {Object} options
     * @param {string[]} [options.presets=[]] Static preset values shown in dropdown.
     * @param {(inputValue: string) => Promise<string[]>} [options.fetchOptions]
     *        Async function returning dynamic suggestions for the current input.
     * @param {string} [options.placeholder] Placeholder text for the empty state.
     * @param {(value: string) => void} [options.onSelect] Callback when an option is chosen.
     */
    constructor(inputElement, options = {}) {
        if (!inputElement || inputElement.tagName !== 'INPUT') {
            console.error('Combobox: expected an <input> element');
            return;
        }

        this.input = inputElement;
        this.presets = Array.isArray(options.presets) ? [...options.presets] : [];
        this.fetchOptions = typeof options.fetchOptions === 'function' ? options.fetchOptions : null;
        this.placeholder = options.placeholder || '';
        this.onSelect = typeof options.onSelect === 'function' ? options.onSelect : null;

        // Internal state
        this._isOpen = false;
        this._activeIndex = -1;
        this._renderedOptions = []; // current visible option strings (de-duplicated, merged)
        this._fetchToken = 0; // guards against out-of-order async fetch results
        this._fetchTimer = null;
        this._suppressInputOpen = false; // guards setValue() from reopening the dropdown

        this._buildDropdown();
        this._bindEvents();
    }

    // ---- public API ----

    /**
     * Replace the preset list. Re-renders the dropdown if it is open.
     * @param {string[]} presets
     * @returns {void}
     */
    updatePresets(presets) {
        this.presets = Array.isArray(presets) ? [...presets] : [];
        if (this._isOpen) {
            this._refresh();
        }
    }

    /**
     * Set the input value programmatically without triggering the dropdown
     * or firing synthetic events.
     * @param {string} value
     * @returns {void}
     */
    setValue(value) {
        const prev = this._suppressInputOpen;
        this._suppressInputOpen = true;
        this.input.value = value ?? '';
        this._suppressInputOpen = prev;
        if (this._isOpen) {
            this._refresh();
        }
    }

    // ---- build ----

    _buildDropdown() {
        const panel = document.createElement('div');
        panel.className = 'lm-combobox-panel';
        panel.setAttribute('role', 'listbox');
        panel.style.display = 'none';
        // Append to <body> so the panel is never clipped by an overflow:hidden
        // ancestor; positioning is recomputed on each open.
        document.body.appendChild(panel);
        this.panel = panel;

        if (this.placeholder) {
            this.input.setAttribute('placeholder', this.placeholder);
        }
        this.input.setAttribute('autocomplete', 'off');
        this.input.setAttribute('role', 'combobox');
        this.input.setAttribute('aria-autocomplete', 'list');
        this.input.setAttribute('aria-expanded', 'false');
    }

    // ---- event wiring ----

    _bindEvents() {
        this.input.addEventListener('focus', () => {
            if (this._suppressInputOpen) return;
            this._open();
        });

        this.input.addEventListener('input', () => {
            if (this._suppressInputOpen) return;
            this._open();          // no-op if already open
            this._refresh();       // re-filter by current input value
            this._scheduleFetch();
        });

        this.input.addEventListener('keydown', (event) => this._onKeyDown(event));

        // Click an option (delegated)
        this.panel.addEventListener('click', (event) => {
            const item = event.target.closest('.lm-combobox-option');
            if (!item) return;
            const value = item.dataset.value;
            if (value !== undefined) {
                this._choose(value);
            }
        });

        // Hover updates the active highlight so keyboard + mouse stay in sync.
        this.panel.addEventListener('mouseover', (event) => {
            const item = event.target.closest('.lm-combobox-option');
            if (!item) return;
            const idx = Number(item.dataset.index);
            if (!Number.isNaN(idx)) {
                this._setActiveIndex(idx);
            }
        });

        // Click outside closes the dropdown.
        this._outsideClickHandler = (event) => {
            if (this._isOpen && !this.input.contains(event.target) && !this.panel.contains(event.target)) {
                this._close();
            }
        };
        document.addEventListener('mousedown', this._outsideClickHandler);

        // Reposition on viewport changes while open.
        this._resizeHandler = () => {
            if (this._isOpen) this._position();
        };
        window.addEventListener('resize', this._resizeHandler);
        window.addEventListener('scroll', this._resizeHandler, true);
    }

    // ---- keyboard ----

    _onKeyDown(event) {
        if (!this._isOpen) {
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                this._open();
                this._setActiveIndex(0);
            }
            return;
        }

        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                this._setActiveIndex(this._activeIndex + 1);
                break;

            case 'ArrowUp':
                event.preventDefault();
                this._setActiveIndex(this._activeIndex - 1);
                break;

            case 'Enter':
                // Only intercept Enter to pick an option when one is actively
                // highlighted; otherwise let the input's default behavior
                // (form submit / free-text commit) proceed.
                if (this._activeIndex >= 0 && this._activeIndex < this._renderedOptions.length) {
                    event.preventDefault();
                    this._choose(this._renderedOptions[this._activeIndex]);
                }
                break;

            case 'Escape':
                event.preventDefault();
                this._close();
                this.input.focus();
                break;

            case 'Tab':
                // Allow normal tab navigation; just close the panel.
                this._close();
                break;
        }
    }

    // ---- open / close ----

    _open() {
        if (this._isOpen) return;
        this._isOpen = true;
        this.panel.style.display = 'block';
        this.input.setAttribute('aria-expanded', 'true');
        // On open, render ALL presets — do not filter by the current input
        // value.  Filtering on the input event is handled separately.
        this._render(this.presets);
        this._position();
    }

    _close() {
        if (!this._isOpen) return;
        this._isOpen = false;
        this.panel.style.display = 'none';
        this.input.setAttribute('aria-expanded', 'false');
        this._activeIndex = -1;
        this._cancelFetch();
    }

    _position() {
        const rect = this.input.getBoundingClientRect();
        const panelHeight = this.panel.offsetHeight;
        const viewportHeight = window.innerHeight;
        const spaceBelow = viewportHeight - rect.bottom;
        const spaceAbove = rect.top;

        // Flip above the input when there is more room there.
        const placeAbove = spaceBelow < panelHeight && spaceAbove > spaceBelow;
        const top = placeAbove
            ? rect.top + window.scrollY - panelHeight
            : rect.bottom + window.scrollY;

        this.panel.style.top = `${Math.max(0, top)}px`;
        this.panel.style.left = `${rect.left + window.scrollX}px`;
        this.panel.style.minWidth = `${rect.width}px`;
    }

    // ---- rendering ----

    /** Render a list of strings into the panel. */
    _render(items) {
        this._renderedOptions = items;
        this.panel.innerHTML = '';
        if (items.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'lm-combobox-empty';
            empty.textContent = this.placeholder ? this.placeholder : 'No options';
            this.panel.appendChild(empty);
            this._activeIndex = -1;
            return;
        }

        const fragment = document.createDocumentFragment();
        items.forEach((opt, idx) => {
            const item = document.createElement('div');
            item.className = 'lm-combobox-option';
            item.setAttribute('role', 'option');
            item.dataset.value = opt;
            item.dataset.index = String(idx);
            item.textContent = opt;
            if (idx === this._activeIndex) {
                item.classList.add('is-active');
            }
            fragment.appendChild(item);
        });
        this.panel.appendChild(fragment);

        if (this._activeIndex >= items.length) {
            this._setActiveIndex(items.length - 1);
        }
    }

    /** Filter presets by current input value and re-render. */
    _refresh() {
        const value = this.input.value;
        const filtered = this._filterPresets(value);
        const merged = this._mergeUnique(filtered, this._fetchedOptions || []);
        this._render(merged);
    }

    _filterPresets(value) {
        const v = (value || '').toLowerCase();
        if (!v) return [...this.presets];
        return this.presets.filter((p) => String(p).toLowerCase().startsWith(v));
    }

    _mergeUnique(...lists) {
        const seen = new Set();
        const out = [];
        for (const list of lists) {
            for (const item of list) {
                const key = String(item);
                if (!seen.has(key)) {
                    seen.add(key);
                    out.push(key);
                }
            }
        }
        return out;
    }

    _setActiveIndex(idx) {
        const max = this._renderedOptions.length - 1;
        const clamped = Math.max(-1, Math.min(max, idx));
        this._activeIndex = clamped;
        // Update DOM classes without full re-render.
        const items = this.panel.querySelectorAll('.lm-combobox-option');
        items.forEach((el, i) => {
            el.classList.toggle('is-active', i === clamped);
        });
        // Scroll the active item into view inside the panel.
        if (clamped >= 0 && items[clamped]) {
            items[clamped].scrollIntoView({ block: 'nearest' });
        }
    }

    /**
     * Remove the panel from the DOM and detach event listeners.
     * Call this before discarding the Combobox instance.
     */
    destroy() {
        this._close();
        if (this.panel && this.panel.parentNode) {
            this.panel.parentNode.removeChild(this.panel);
        }
        document.removeEventListener('mousedown', this._outsideClickHandler);
        window.removeEventListener('resize', this._resizeHandler);
        window.removeEventListener('scroll', this._resizeHandler, true);
    }

    _choose(value) {
        this.input.value = value;
        this._close();
        if (typeof this.onSelect === 'function') {
            this.onSelect(value);
        }
        // Re-focus without reopening the dropdown.
        this._suppressInputOpen = true;
        this.input.focus();
        this._suppressInputOpen = false;
    }

    // ---- async fetch (debounced) ----

    _scheduleFetch() {
        if (!this.fetchOptions) return;
        this._cancelFetch();
        this._fetchTimer = setTimeout(() => {
            this._fetchTimer = null;
            this._runFetch();
        }, DEBOUNCE_MS);
    }

    _cancelFetch() {
        if (this._fetchTimer) {
            clearTimeout(this._fetchTimer);
            this._fetchTimer = null;
        }
        this._fetchToken++; // invalidate any in-flight result
    }

    async _runFetch() {
        if (!this.fetchOptions) return;
        const token = this._fetchToken;
        const value = this.input.value;
        let results;
        try {
            results = await this.fetchOptions(value);
        } catch (err) {
            console.error('Combobox fetchOptions error:', err);
            results = [];
        }
        // Stale guard: a newer fetch or close superseded this one.
        if (token !== this._fetchToken || !this._isOpen) return;
        this._fetchedOptions = Array.isArray(results) ? results : [];
        this._refresh();
    }
}

// Expose for non-module callers (templates load via <script type="module">,
// but some widget code reads globals off `window`).
if (typeof window !== 'undefined') {
    window.Combobox = Combobox;
}