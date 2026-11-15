/**
 * CreatorPicker.js
 * Header-chip creator editing with a library-backed anchored picker.
 *
 * The creator stays a header chip: clicking it keeps opening the Civitai
 * profile (handled by the model modal's delegated click handler), while a
 * pencil inside the chip opens this module's popover. A missing creator is
 * represented by a dashed "+ Add creator" chip in the same action group.
 */

import { getModelApiClient } from '../../api/modelApiFactory.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
import { escapeAttribute, escapeHtml } from './utils.js';

export const CREATOR_PICKER_LIMIT = 8;
export const CREATOR_SEARCH_DEBOUNCE_MS = 200;
export const CREATOR_USERNAME_MAX_LENGTH = 64;

/**
 * Render the creator chip or the add chip.
 * @param {Object|null|undefined} creator - civitai.creator payload
 * @returns {string} chip markup
 */
export function renderCreatorChip(creator) {
    if (!creator || typeof creator !== 'object' || !creator.username) {
        const addLabel = translate('modals.model.metadata.creatorAdd', {}, 'Add creator');
        return `<button type="button" class="creator-info creator-info--add"
                        data-action="add-creator" aria-label="${escapeAttribute(addLabel)}"
                        aria-haspopup="dialog" aria-expanded="false">
                    <i class="fas fa-plus" aria-hidden="true"></i> ${escapeHtml(addLabel)}
                </button>`;
    }

    const username = String(creator.username || '');
    const displayName = escapeHtml(username);
    const usernameAttribute = escapeAttribute(username);
    const isManual = creator.source === 'manual';
    const profileTitle = translate(
        'modals.model.actions.viewCreatorProfile',
        {},
        'View Creator Profile'
    );
    const editLabel = translate('modals.model.metadata.creatorEdit', {}, 'Edit creator');
    const manualLabel = translate('modals.model.metadata.creatorManual', {}, 'Manual');
    const manualHint = translate(
        'modals.model.metadata.creatorManualHint',
        {},
        "Added manually. Metadata refresh won't overwrite it."
    );
    const avatar = creator.image
        ? `<div class="creator-avatar">
                <img src="${escapeAttribute(creator.image)}" alt="${usernameAttribute}"
                     onerror="this.onerror=null; this.src='/loras_static/icons/user-placeholder.png';">
            </div>`
        : `<div class="creator-avatar creator-placeholder">
                <i class="fas fa-user" aria-hidden="true"></i>
            </div>`;
    const manualBadge = isManual
        ? `<span class="creator-badge" title="${escapeAttribute(manualHint)}">${escapeHtml(manualLabel)}</span>`
        : '';

    return `<div class="creator-info creator-info--editable"
                 data-action="view-creator"
                 data-username="${usernameAttribute}"
                 data-source="${escapeAttribute(isManual ? 'manual' : 'civitai')}"
                 title="${escapeAttribute(profileTitle)}">
                <span class="creator-identity">
                    ${avatar}
                    <span class="creator-username">${displayName}</span>
                    ${manualBadge}
                </span>
                <button type="button" class="creator-edit-btn"
                        data-action="edit-creator" title="${escapeAttribute(editLabel)}"
                        aria-label="${escapeAttribute(editLabel)}"
                        aria-haspopup="dialog" aria-expanded="false">
                    <i class="fas fa-pencil-alt" aria-hidden="true"></i>
                </button>
            </div>`;
}

/**
 * Normalize a manually entered creator name.
 * @param {string} raw
 * @returns {string}
 */
export function normalizeCreatorName(raw) {
    let name = String(raw ?? '').trim();
    if (name.startsWith('@')) {
        name = name.replace(/^@+/, '');
    }
    return name.replace(/\s+/g, ' ').trim();
}

function initialOf(name) {
    const first = Array.from(String(name || '').trim())[0];
    return first ? first.toUpperCase() : '?';
}

function modelCountLabel(count) {
    return count === 1
        ? translate('modals.model.metadata.creatorModelCountOne', { count }, '{count} model')
        : translate('modals.model.metadata.creatorModelCount', { count }, '{count} models');
}

function matchCountLabel(count) {
    return count === 1
        ? translate('modals.model.metadata.creatorMatchCountOne', { count }, '{count} match')
        : translate('modals.model.metadata.creatorMatchCount', { count }, '{count} matches');
}

function isNarrowViewport() {
    return typeof window.matchMedia === 'function'
        && window.matchMedia('(max-width: 640px)').matches;
}

async function defaultFetchCreators(query) {
    const params = new URLSearchParams({
        query: query || '',
        limit: String(CREATOR_PICKER_LIMIT),
    });
    const response = await fetch(`/api/lm/creators?${params.toString()}`, {
        headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
        throw new Error('Failed to load creators');
    }
    const data = await response.json();
    return {
        creators: Array.isArray(data?.creators) ? data.creators : [],
        total: Number(data?.total) || 0,
        libraryTotal: Number(data?.library_total) || 0,
    };
}

/**
 * Controller for one creator chip + its anchored picker.
 *
 * The modal delegates `edit-creator` / `add-creator` clicks to
 * `modalElement._creatorPicker.open(trigger)`. The controller keeps the chip
 * visible, appends the popover to `.creator-chip-wrap`, and re-renders the chip
 * after a successful save/removal.
 */
export class CreatorPicker {
    constructor({
        filePath = '',
        modelType = '',
        creator = null,
        wrapper = null,
        fetchCreators = null,
        saveCreator = null,
    } = {}) {
        this.filePath = filePath;
        this.modelType = modelType;
        this.creator = creator && creator.username ? { ...creator } : null;
        this.wrapper = wrapper;
        this.fetchCreators = fetchCreators || defaultFetchCreators;
        this.saveCreator = saveCreator || ((nextCreator) => this.defaultSaveCreator(nextCreator));

        this.isOpen = false;
        this.saving = false;
        this.loading = false;
        this.loadError = false;
        this.query = '';
        this.creators = [];
        this.total = 0;
        this.libraryTotal = 0;
        this.options = [];
        this.activeIndex = -1;
        this.requestSeq = 0;
        this.debounceTimer = null;
        this.trigger = null;
        this.popover = null;
        this.caret = null;
        this.input = null;
        this.body = null;
        this.listbox = null;

        this.outsideHandler = (event) => this.onOutsideMouseDown(event);
        this.resizeHandler = () => this.positionPopover();
        this.modalContent = null;
    }

    /**
     * Open the picker from a chip trigger. Clicking the same trigger again
     * toggles it closed.
     * @param {HTMLElement} trigger
     */
    open(trigger) {
        if (this.saving) return;
        const wrapper = trigger?.closest?.('.creator-chip-wrap') || this.wrapper;
        if (!wrapper) return;

        if (this.isOpen) {
            this.close();
            return;
        }

        this.wrapper = wrapper;
        this.trigger = trigger || wrapper.querySelector('[data-action="edit-creator"], [data-action="add-creator"]');
        this.isOpen = true;
        this.query = '';
        this.creators = [];
        this.total = 0;
        this.libraryTotal = 0;
        this.options = [];
        this.activeIndex = -1;
        this.loading = false;
        this.loadError = false;
        this.requestSeq += 1;

        this.renderPopover();
        this.bindPopover();
        this.trigger?.setAttribute('aria-expanded', 'true');
        this.input?.focus();
        this.positionPopover();

        document.addEventListener('mousedown', this.outsideHandler, true);
        window.addEventListener('resize', this.resizeHandler);
        this.modalContent = wrapper.closest('.modal-content');
        this.modalContent?.addEventListener('scroll', this.resizeHandler, { passive: true });

        this.loadCreators('', { immediate: true });
    }

    /**
     * Close the picker and remove its listeners/popover.
     * @param {{restoreFocus?: boolean}} [options]
     */
    close({ restoreFocus = true } = {}) {
        if (!this.isOpen) return;
        this.isOpen = false;
        this.saving = false;
        this.clearDebounce();
        this.requestSeq += 1;

        document.removeEventListener('mousedown', this.outsideHandler, true);
        window.removeEventListener('resize', this.resizeHandler);
        this.modalContent?.removeEventListener('scroll', this.resizeHandler);
        this.modalContent = null;

        if (this.trigger?.isConnected) {
            this.trigger.setAttribute('aria-expanded', 'false');
        }
        this.popover?.remove();
        this.caret?.remove();
        this.popover = null;
        this.caret = null;
        this.input = null;
        this.body = null;
        this.listbox = null;
        this.options = [];
        this.activeIndex = -1;

        if (restoreFocus) {
            const nextTrigger = this.wrapper?.querySelector(
                '[data-action="edit-creator"], [data-action="add-creator"]'
            );
            nextTrigger?.focus({ preventScroll: true });
        }
        this.trigger = null;
    }

    destroy() {
        this.close({ restoreFocus: false });
        this.wrapper = null;
    }

    // ── Popover shell ──────────────────────────────────────────────────────

    renderPopover() {
        const dialogLabel = translate(
            this.creator
                ? 'modals.model.metadata.creatorEdit'
                : 'modals.model.metadata.creatorAdd',
            {},
            this.creator ? 'Edit creator' : 'Add creator'
        );
        const searchPlaceholder = translate(
            'modals.model.metadata.creatorSearchPlaceholder',
            {},
            'Search creators or type a new name...'
        );
        const creatorLabel = translate('modals.model.metadata.creator', {}, 'Creator');

        // Portal the panel to <body>: `.modal-content` is a scroll container
        // with `overflow-x: hidden`, which clips absolutely positioned
        // children when the chip sits near the left edge. A fixed panel with
        // viewport-clamped coordinates stays fully visible at every width.
        document.getElementById('creatorPickerPopover')?.remove();
        document.body.insertAdjacentHTML(
            'beforeend',
            `<div class="creator-popover" id="creatorPickerPopover" role="dialog" aria-label="${escapeAttribute(dialogLabel)}">
                <div class="creator-popover-search">
                    <div class="creator-input-wrap">
                        <i class="fas fa-search creator-search-icon" aria-hidden="true"></i>
                        <input class="creator-input" type="text" role="combobox"
                               aria-autocomplete="list" aria-expanded="true"
                               aria-controls="creatorPickerListbox" aria-label="${escapeAttribute(creatorLabel)}"
                               placeholder="${escapeAttribute(searchPlaceholder)}"
                               autocomplete="off" spellcheck="false" dir="auto">
                        <i class="fas fa-spinner fa-spin creator-spinner" aria-hidden="true"></i>
                    </div>
                </div>
                <div class="creator-popover-body"></div>
                <div class="sr-only creator-live" aria-live="polite"></div>
            </div>`
        );

        this.popover = document.getElementById('creatorPickerPopover');
        this.wrapper.querySelector('.creator-popover-caret')?.remove();
        this.caret = document.createElement('span');
        this.caret.className = 'creator-popover-caret';
        this.caret.setAttribute('aria-hidden', 'true');
        this.wrapper.appendChild(this.caret);
        this.input = this.popover?.querySelector('.creator-input');
        this.body = this.popover?.querySelector('.creator-popover-body');
    }

    bindPopover() {
        if (!this.popover || !this.input || !this.body) return;

        this.input.addEventListener('input', () => {
            this.query = this.input.value;
            this.activeIndex = this.query.trim() ? 0 : -1;
            this.requestSeq += 1;
            this.renderList();
            this.scheduleFetch(this.query);
        });

        this.input.addEventListener('keydown', (event) => this.onInputKeyDown(event));

        this.popover.addEventListener('click', (event) => {
            if (event.target.closest('.creator-remove-btn')) {
                event.preventDefault();
                event.stopPropagation();
                this.removeCreator();
                return;
            }
            const optionEl = event.target.closest('[data-index]');
            if (!optionEl) return;
            const option = this.options[Number(optionEl.dataset.index)];
            if (!option) return;
            if (option.type === 'create') {
                this.commitName(option.name);
            } else {
                this.commitCreator(option);
            }
        });

        this.popover.addEventListener('mouseover', (event) => {
            const optionEl = event.target.closest('[data-index]');
            if (!optionEl) return;
            const index = Number(optionEl.dataset.index);
            if (index !== this.activeIndex) this.setActive(index, { scroll: false });
        });
    }

    onInputKeyDown(event) {
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                this.moveActive(1);
                break;
            case 'ArrowUp':
                event.preventDefault();
                this.moveActive(-1);
                break;
            case 'Home':
                event.preventDefault();
                this.setActive(0);
                break;
            case 'End':
                event.preventDefault();
                this.setActive(this.options.length - 1);
                break;
            case 'Enter':
                event.preventDefault();
                this.commitActive();
                break;
            case 'Escape':
                event.preventDefault();
                // The ModalManager listens for Escape on document; closing the
                // picker must not also close the model modal.
                event.stopPropagation();
                this.close();
                break;
            case 'Tab':
                if (this.query.trim()) {
                    event.preventDefault();
                    this.commitTyped();
                } else {
                    this.close({ restoreFocus: false });
                }
                break;
            default:
                break;
        }
    }

    // ── List state ─────────────────────────────────────────────────────────

    scheduleFetch(query) {
        this.clearDebounce();
        this.debounceTimer = setTimeout(() => {
            this.debounceTimer = null;
            this.loadCreators(query);
        }, CREATOR_SEARCH_DEBOUNCE_MS);
    }

    clearDebounce() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = null;
        }
    }

    async loadCreators(query, { immediate = false } = {}) {
        if (!this.isOpen) return;
        if (!immediate) {
            this.clearDebounce();
        }

        const seq = ++this.requestSeq;
        this.loading = true;
        this.loadError = false;
        this.updateLoadingState();
        this.renderList();

        try {
            const result = await this.fetchCreators(query);
            if (!this.isOpen || seq !== this.requestSeq) return;
            this.creators = Array.isArray(result?.creators) ? result.creators : [];
            this.total = Number(result?.total) || this.creators.length;
            this.libraryTotal = Number(result?.libraryTotal) || this.libraryTotal || this.total;
            this.loading = false;
            this.loadError = false;
            this.renderList();
        } catch (error) {
            if (!this.isOpen || seq !== this.requestSeq) return;
            console.error('Failed to load creators:', error);
            this.loading = false;
            this.loadError = true;
            this.renderList();
        } finally {
            if (this.isOpen && seq === this.requestSeq) {
                this.loading = false;
                this.updateLoadingState();
            }
        }
    }

    updateLoadingState() {
        this.popover?.classList.toggle('is-loading', this.loading);
        this.popover?.classList.toggle('is-saving', this.saving);
        if (this.input) {
            this.input.disabled = this.saving;
        }
    }

    renderList() {
        if (!this.body) return;
        const query = this.query.trim();
        const queryLower = query.toLowerCase();
        const exact = query
            ? this.creators.find((creator) => String(creator.username).toLowerCase() === queryLower)
            : null;
        const showCreate = Boolean(query) && !exact;

        const options = [];
        if (showCreate) {
            options.push({ type: 'create', name: query });
        }
        this.creators.forEach((creator) => {
            options.push({ type: 'creator', ...creator });
        });
        this.options = options;

        if (this.activeIndex >= options.length) {
            this.activeIndex = options.length - 1;
        }
        if (!options.length) {
            this.activeIndex = -1;
        }

        const current = this.creator;
        let currentMarkup;
        if (current) {
            // Use a sentinel for the name so the <strong> lands on the name
            // regardless of where the translation places it.
            const [beforeName, afterName] = translate(
                'modals.model.metadata.creatorCurrent',
                { name: '\u0000' },
                'Current: \u0000'
            ).split('\u0000');
            currentMarkup = `<span class="creator-current">${escapeHtml(beforeName)}<strong title="${escapeAttribute(current.username)}" dir="auto">${escapeHtml(current.username)}</strong>${escapeHtml(afterName || '')}
                <button type="button" class="creator-remove-btn"
                        title="${escapeAttribute(translate('modals.model.metadata.creatorRemove', {}, 'Remove creator'))}"
                        aria-label="${escapeAttribute(translate('modals.model.metadata.creatorRemove', {}, 'Remove creator'))}">
                    <i class="fas fa-trash" aria-hidden="true"></i>
                </button>
            </span>`;
        } else {
            const libraryCount = this.libraryTotal || this.total;
            currentMarkup = `<span class="creator-current">${escapeHtml(translate(
                'modals.model.metadata.creatorLibraryCount',
                { count: libraryCount },
                `${libraryCount} in library`
            ))}</span>`;
        }

        const header = `<div class="creator-list-header">
            <span class="creator-list-title">${escapeHtml(query
                ? translate('modals.model.metadata.creatorMatchingHeader', {}, 'Matching creators')
                : translate('modals.model.metadata.creatorLibraryHeader', {}, 'Creators in your library'))}</span>
            ${currentMarkup}
        </div>`;

        let listHtml = `<div id="creatorPickerListbox" class="creator-listbox" role="listbox" aria-label="${escapeAttribute(
            translate('modals.model.metadata.creatorLibraryHeader', {}, 'Creators in your library')
        )}">`;

        if (showCreate) {
            listHtml += this.renderCreateRow(query, 0);
        }

        const offset = showCreate ? 1 : 0;
        listHtml += '<div class="creator-options">';
        if (this.loading && !this.creators.length) {
            listHtml += `<div class="creator-empty-state" role="presentation">
                <i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
                <span>${escapeHtml(translate('modals.model.metadata.creatorLoading', {}, 'Loading creators...'))}</span>
            </div>`;
        } else if (this.creators.length) {
            this.creators.forEach((creator, index) => {
                listHtml += this.renderOption(creator, offset + index);
            });
        } else if (this.loadError) {
            listHtml += `<div class="creator-empty-state" role="presentation">
                <i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
                <span>${escapeHtml(translate(
                    'modals.model.metadata.creatorLoadFailed',
                    {},
                    "Couldn't load creators. You can still type a new name."
                ))}</span>
            </div>`;
        } else if (query) {
            listHtml += `<div class="creator-empty-state" role="presentation">
                <i class="fas fa-user-plus" aria-hidden="true"></i>
                <span>${escapeHtml(translate(
                    'modals.model.metadata.creatorNoMatch',
                    { name: query },
                    `No existing creator matches “${query}”`
                ))}</span>
            </div>`;
        } else {
            listHtml += `<div class="creator-empty-state" role="presentation">
                <i class="fas fa-users" aria-hidden="true"></i>
                <span>${escapeHtml(translate(
                    'modals.model.metadata.creatorEmptyLibrary',
                    {},
                    'No creators in your library yet. Type a name to add the first one.'
                ))}</span>
            </div>`;
        }
        listHtml += '</div></div>';

        const footer = this.renderFooter(query);

        this.body.innerHTML = header + listHtml + footer;
        this.listbox = this.body.querySelector('#creatorPickerListbox');
        this.syncActiveAria();
        this.updateLiveRegion(query, showCreate);
    }

    renderCreateRow(query, index) {
        const [beforeName, afterName] = translate(
            'modals.model.metadata.creatorCreate',
            { name: '\u0000' },
            'Create “\u0000”'
        ).split('\u0000');
        const labelMarkup = `${escapeHtml(beforeName)}<strong>${escapeHtml(query)}</strong>${escapeHtml(afterName || '')}`;
        return `<div class="creator-create-row${this.activeIndex === index ? ' is-active' : ''}"
                     id="creatorPickerOption${index}" data-index="${index}" role="option"
                     aria-selected="${this.activeIndex === index}">
                    <span class="creator-create-icon"><i class="fas fa-plus" aria-hidden="true"></i></span>
                    <span class="creator-create-label">${labelMarkup}</span>
                    <span class="creator-new-badge">${escapeHtml(translate(
                        'modals.model.metadata.creatorNew',
                        {},
                        'New creator'
                    ))}</span>
                </div>`;
    }

    renderOption(creator, index) {
        const username = String(creator.username || '');
        const current = this.creator
            && String(this.creator.username).toLowerCase() === username.toLowerCase();
        const isActive = this.activeIndex === index;
        const query = this.query.trim();
        const label = query ? this.highlightMatch(username, query) : escapeHtml(username);
        const count = Number(creator.model_count) || 0;
        const avatarMarkup = creator.image
            ? `<span class="creator-option-avatar" aria-hidden="true"><img src="${escapeAttribute(creator.image)}" alt="" loading="lazy" onerror="this.onerror=null; this.src='/loras_static/icons/user-placeholder.png';"></span>`
            : `<span class="creator-option-avatar" aria-hidden="true">${escapeHtml(initialOf(username))}</span>`;
        return `<div class="creator-option${current ? ' is-current' : ''}${isActive ? ' is-active' : ''}"
                     id="creatorPickerOption${index}" data-index="${index}" role="option"
                     aria-selected="${isActive}"${current ? ' aria-current="true"' : ''}>
                    ${avatarMarkup}
                    <span class="creator-option-name" title="${escapeAttribute(username)}" dir="auto">${label}</span>
                    ${current ? '<i class="fas fa-check creator-check" aria-hidden="true"></i>' : ''}
                    <span class="creator-count">${escapeHtml(modelCountLabel(count))}</span>
                </div>`;
    }

    renderFooter(query) {
        const hint = translate(
            'modals.model.metadata.creatorKeyboardHint',
            {},
            '↑↓ navigate · ↵ select · esc cancel'
        );
        let countLabel = '';
        if (this.total > this.creators.length) {
            countLabel = translate(
                'modals.model.metadata.creatorShowing',
                { shown: this.creators.length, total: this.total },
                `Showing ${this.creators.length} of ${this.total} — keep typing`
            );
        } else if (query) {
            countLabel = matchCountLabel(this.total);
        } else {
            countLabel = translate(
                'modals.model.metadata.creatorLibraryCount',
                { count: this.total },
                `${this.total} in library`
            );
        }
        return `<div class="creator-dropdown-footer">
            <span class="creator-hint">${escapeHtml(hint)}</span>
            <span class="creator-result-count">${escapeHtml(countLabel)}</span>
        </div>`;
    }

    updateLiveRegion(query, showCreate) {
        const live = this.popover?.querySelector('.creator-live');
        if (!live) return;
        const createHint = showCreate && query
            ? ` ${translate(
                'modals.model.metadata.creatorCreateAnnounce',
                { name: query },
                `Press Enter to create ${query}.`
            )}`
            : '';
        live.textContent = `${matchCountLabel(this.total)}.${createHint}`;
    }

    highlightMatch(name, query) {
        const index = name.toLowerCase().indexOf(query.toLowerCase());
        if (index < 0) return escapeHtml(name);
        return [
            escapeHtml(name.slice(0, index)),
            `<mark>${escapeHtml(name.slice(index, index + query.length))}</mark>`,
            escapeHtml(name.slice(index + query.length)),
        ].join('');
    }

    syncActiveAria() {
        if (!this.input) return;
        const active = this.listbox && this.activeIndex >= 0
            ? this.listbox.querySelector(`[data-index="${this.activeIndex}"]`)
            : null;
        if (active) {
            this.input.setAttribute('aria-activedescendant', active.id);
        } else {
            this.input.removeAttribute('aria-activedescendant');
        }
    }

    setActive(index, { scroll = true } = {}) {
        if (!this.options.length) {
            this.activeIndex = -1;
        } else {
            this.activeIndex = Math.max(0, Math.min(index, this.options.length - 1));
        }
        if (this.listbox) {
            this.listbox.querySelectorAll('[data-index]').forEach((element) => {
                const active = Number(element.dataset.index) === this.activeIndex;
                element.classList.toggle('is-active', active);
                element.setAttribute('aria-selected', active ? 'true' : 'false');
                if (active && scroll && typeof element.scrollIntoView === 'function') {
                    element.scrollIntoView({ block: 'nearest' });
                }
            });
        }
        this.syncActiveAria();
    }

    moveActive(delta) {
        if (!this.options.length) return;
        if (this.activeIndex < 0) {
            this.setActive(delta > 0 ? 0 : this.options.length - 1);
            return;
        }
        this.setActive(this.activeIndex + delta);
    }

    // ── Commit / remove ────────────────────────────────────────────────────

    commitActive() {
        if (this.saving) return;
        const option = this.options[this.activeIndex];
        if (!option) {
            if (this.query.trim()) {
                this.commitTyped();
            }
            return;
        }
        if (option.type === 'create') {
            this.commitName(option.name);
        } else {
            this.commitCreator(option);
        }
    }

    commitTyped() {
        const name = normalizeCreatorName(this.query);
        if (!name) return;
        const known = this.creators.find(
            (creator) => String(creator.username).toLowerCase() === name.toLowerCase()
        );
        if (known) {
            this.commitCreator(known);
        } else {
            this.commitName(name);
        }
    }

    commitCreator(creator) {
        const username = String(creator.username || '').trim();
        if (!username) return;
        if (this.creator && this.creator.username.toLowerCase() === username.toLowerCase()) {
            this.close();
            return;
        }
        this.saveCreatorValue(username, creator.image || null);
    }

    commitName(raw) {
        const name = normalizeCreatorName(raw);
        if (!name) {
            this.close();
            return;
        }
        if (name.length > CREATOR_USERNAME_MAX_LENGTH) {
            showToast(
                translate(
                    'modals.model.metadata.creatorTooLong',
                    {},
                    'Creator name is too long (max 64 characters)'
                ),
                'error'
            );
            return;
        }
        const known = this.creators.find(
            (creator) => String(creator.username).toLowerCase() === name.toLowerCase()
        );
        if (known) {
            this.commitCreator(known);
            return;
        }
        this.saveCreatorValue(name, null);
    }

    async saveCreatorValue(username, image = null) {
        if (this.saving) return;
        this.saving = true;
        this.updateLoadingState();
        this.input?.focus();

        const avatar = typeof image === 'string' && image ? image : null;
        try {
            await this.saveCreatorImpl({
                username,
                image: avatar,
                source: 'manual',
            });
            this.creator = {
                username,
                image: avatar,
                source: 'manual',
            };
            this.close({ restoreFocus: false });
            this.renderChip();
            showToast(
                translate('modals.model.metadata.creatorSaved', {}, 'Creator updated'),
                'success'
            );
            this.focusChipTrigger();
        } catch (error) {
            console.error('Failed to save creator:', error);
            this.saving = false;
            this.updateLoadingState();
            this.close({ restoreFocus: false });
            showToast(
                translate(
                    'modals.model.metadata.creatorSaveFailed',
                    {},
                    "Couldn't update creator. Try again."
                ),
                'error'
            );
            this.focusChipTrigger();
        }
    }

    async removeCreator() {
        if (this.saving || !this.creator) return;
        this.saving = true;
        this.updateLoadingState();
        try {
            await this.saveCreatorImpl(null);
            this.creator = null;
            this.close({ restoreFocus: false });
            this.renderChip();
            showToast(
                translate('modals.model.metadata.creatorRemoved', {}, 'Creator removed'),
                'info'
            );
            this.focusChipTrigger();
        } catch (error) {
            console.error('Failed to remove creator:', error);
            this.saving = false;
            this.updateLoadingState();
            this.close({ restoreFocus: false });
            showToast(
                translate(
                    'modals.model.metadata.creatorSaveFailed',
                    {},
                    "Couldn't update creator. Try again."
                ),
                'error'
            );
            this.focusChipTrigger();
        }
    }

    async saveCreatorImpl(creator) {
        if (typeof this.saveCreator === 'function') {
            return this.saveCreator(creator);
        }
        return this.defaultSaveCreator(creator);
    }

    async defaultSaveCreator(creator) {
        const client = getModelApiClient(this.modelType);
        await client.saveModelMetadata(this.filePath, {
            civitai: {
                creator: creator
                    ? {
                        username: creator.username,
                        image: creator.image ?? null,
                        source: 'manual',
                    }
                    : null,
            },
        });
    }

    renderChip() {
        if (!this.wrapper) return;
        this.wrapper.innerHTML = renderCreatorChip(this.creator);
    }

    focusChipTrigger() {
        const target = this.wrapper?.querySelector(
            '[data-action="edit-creator"], [data-action="add-creator"]'
        );
        target?.focus({ preventScroll: true });
    }

    // ── Outside click / positioning ────────────────────────────────────────

    onOutsideMouseDown(event) {
        if (!this.isOpen) return;
        if (!this.wrapper?.isConnected) {
            // The modal was replaced/closed without a picker teardown.
            this.destroy();
            return;
        }
        const modal = this.wrapper.closest('.modal');
        if (modal && modal.style.display === 'none') {
            // The model modal was closed while the picker was open; do not
            // treat the next page click as an implicit commit.
            this.destroy();
            return;
        }
        if (this.wrapper?.contains(event.target)) return;
        if (this.popover?.contains(event.target)) return;
        if (event.target === modal || event.target.closest?.('.close')) {
            // Closing the model modal must not implicitly commit typed text.
            this.close({ restoreFocus: false });
            return;
        }
        if (this.query.trim()) {
            this.commitTyped();
        } else {
            this.close({ restoreFocus: false });
        }
    }

    positionPopover() {
        if (!this.isOpen || !this.popover || !this.wrapper) return;
        const rect = this.wrapper.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
        const viewportHeight = window.innerHeight;
        const top = Math.max(8, Math.min(rect.bottom + 10, viewportHeight - 120));
        this.popover.style.setProperty('--creator-popover-top', `${top}px`);

        if (isNarrowViewport()) {
            // The 640px breakpoint uses a full-width fixed panel (CSS).
            this.popover.style.removeProperty('--creator-popover-left');
            this.popover.style.removeProperty('--creator-popover-max-height');
            return;
        }

        const width = Math.min(360, viewportWidth - 24);
        const left = Math.max(
            8,
            Math.min(rect.right - width, viewportWidth - width - 8)
        );
        const maxHeight = Math.max(180, Math.min(480, viewportHeight - top - 12));
        this.popover.style.setProperty('--creator-popover-left', `${left}px`);
        this.popover.style.setProperty('--creator-popover-max-height', `${maxHeight}px`);
    }
}

/**
 * Create and attach a picker controller for the current model modal.
 * @param {Object} options
 * @returns {CreatorPicker|null}
 */
export function setupCreatorEditing({
    filePath = '',
    modelType = '',
    creator = null,
    modalElement = null,
} = {}) {
    const modal = modalElement || document.getElementById('modelModal');
    if (!modal) return null;
    modal._creatorPicker?.destroy?.();
    modal._creatorPicker = null;

    const wrapper = modal.querySelector('.creator-chip-wrap');
    if (!wrapper) return null;

    const picker = new CreatorPicker({
        filePath,
        modelType,
        creator,
        wrapper,
    });
    modal._creatorPicker = picker;
    return picker;
}
