const DUPLICATE_GROUP_BATCH_SIZE = 25;
const DUPLICATE_CARD_BATCH_SIZE = 12;
const SCROLLABLE_CARD_COUNT = 6;

export class DuplicatesViewManager {
    constructor() {
        this.duplicateGroups = [];
        this.inDuplicateMode = false;
        this.selectedForDeletion = new Set();
        this._isDeleting = false;
        this._libraryNeedsRefresh = false;
        this._renderedGroupCount = 0;
        this._groupGrid = null;
        this._renderGroup = null;
        this._groupObserver = null;
        this._groupSentinel = null;
    }

    toggleCardSelection(itemId, card, checkbox) {
        if (this._isDeleting) return;

        if (checkbox.checked) {
            this.selectedForDeletion.add(itemId);
            card.classList.add('duplicate-selected');
        } else {
            this.selectedForDeletion.delete(itemId);
            card.classList.remove('duplicate-selected');
        }

        this.updateSelectedCount();
    }

    updateSelectedCount() {
        const selectedCountEl = document.getElementById('duplicatesSelectedCount');
        if (selectedCountEl) {
            selectedCountEl.textContent = this.selectedForDeletion.size;
        }

        const deleteBtn = document.querySelector('.btn-delete-selected');
        if (deleteBtn) {
            const disabled = this._isDeleting || this.selectedForDeletion.size === 0;
            deleteBtn.disabled = disabled;
            deleteBtn.classList.toggle('disabled', disabled);
        }
    }

    _setDeletingState(isDeleting) {
        const banner = document.getElementById('duplicatesBanner');
        if (isDeleting) {
            banner?.setAttribute('aria-busy', 'true');
            const controls = document.querySelectorAll(
                '#duplicatesBanner button, #findDuplicatesBtn, .duplicate-group button, .duplicate-group .selector-checkbox'
            );
            controls.forEach(control => {
                if (control.disabled) return;
                control.dataset.duplicatesDeleteDisabled = 'true';
                control.disabled = true;
            });
            this.updateSelectedCount();
            return;
        }

        banner?.removeAttribute('aria-busy');
        document.querySelectorAll('[data-duplicates-delete-disabled="true"]').forEach(control => {
            control.disabled = false;
            delete control.dataset.duplicatesDeleteDisabled;
        });
        this.updateSelectedCount();
    }

    _removeSuccessfullyDeleted(itemIds) {
        const deletedIds = new Set(itemIds);
        this.duplicateGroups = this.duplicateGroups.map(group => {
            const itemsKey = Array.isArray(group.models) ? 'models' : 'recipes';
            const items = Array.isArray(group[itemsKey]) ? group[itemsKey] : [];
            return {
                ...group,
                [itemsKey]: items.filter(item => {
                    const itemId = itemsKey === 'models' ? item.file_path : item.id;
                    return !deletedIds.has(itemId);
                }),
            };
        }).filter(group => (group.models || group.recipes || []).length > 1);

        const visibleIds = new Set();
        this.duplicateGroups.forEach(group => {
            const itemsKey = Array.isArray(group.models) ? 'models' : 'recipes';
            (group[itemsKey] || []).forEach(item => {
                visibleIds.add(itemsKey === 'models' ? item.file_path : item.id);
            });
        });
        Array.from(this.selectedForDeletion).forEach(itemId => {
            if (!visibleIds.has(itemId)) {
                this.selectedForDeletion.delete(itemId);
            }
        });
    }

    _syncRenderedGroupSelection(groupDiv) {
        if (!groupDiv) return;

        groupDiv.querySelectorAll('.selector-checkbox').forEach(checkbox => {
            const itemId = checkbox.dataset.filePath || checkbox.dataset.recipeId;
            const selected = this.selectedForDeletion.has(itemId);
            checkbox.checked = selected;
            checkbox.closest('.model-card')?.classList.toggle('duplicate-selected', selected);
        });
    }

    _renderCardGroup(groupDiv, cardsDiv, items, renderCard) {
        let renderedCount = 0;
        const appendCards = end => {
            const fragment = document.createDocumentFragment();
            for (let index = renderedCount; index < end; index += 1) {
                fragment.appendChild(renderCard(items[index], index));
            }
            renderedCount = end;
            cardsDiv.appendChild(fragment);
        };

        appendCards(Math.min(DUPLICATE_CARD_BATCH_SIZE, items.length));

        if (items.length <= SCROLLABLE_CARD_COUNT) return;

        cardsDiv.classList.add('scrollable');
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'group-toggle-btn';
        toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
        toggleBtn.title = 'Expand/Collapse';
        toggleBtn.onclick = () => {
            if (renderedCount < items.length) {
                appendCards(items.length);
            }
            cardsDiv.classList.toggle('scrollable');
            toggleBtn.innerHTML = cardsDiv.classList.contains('scrollable')
                ? '<i class="fas fa-chevron-down"></i>'
                : '<i class="fas fa-chevron-up"></i>';
        };
        groupDiv.appendChild(toggleBtn);
    }

    _startProgressiveGroupRendering(grid, renderGroup) {
        this._stopProgressiveGroupRendering();
        this._groupGrid = grid;
        this._renderGroup = renderGroup;
        this._renderedGroupCount = 0;
        grid.style.removeProperty('width');
        grid.style.removeProperty('max-width');
        grid.innerHTML = '';

        if (typeof IntersectionObserver !== 'function') {
            while (this._renderedGroupCount < this.duplicateGroups.length) {
                this._renderNextGroupBatch();
            }
            return;
        }

        this._renderNextGroupBatch();
    }

    _renderNextGroupBatch() {
        if (!this._groupGrid || !this._renderGroup) return;

        this._stopGroupObserver();
        const fragment = document.createDocumentFragment();
        const end = Math.min(
            this._renderedGroupCount + DUPLICATE_GROUP_BATCH_SIZE,
            this.duplicateGroups.length
        );

        for (let index = this._renderedGroupCount; index < end; index += 1) {
            fragment.appendChild(this._renderGroup(this.duplicateGroups[index], index));
        }
        this._renderedGroupCount = end;
        this._groupGrid.appendChild(fragment);

        if (
            this._renderedGroupCount >= this.duplicateGroups.length
            || typeof IntersectionObserver !== 'function'
        ) return;

        this._groupSentinel = document.createElement('div');
        this._groupSentinel.className = 'duplicates-group-sentinel';
        this._groupSentinel.setAttribute('aria-hidden', 'true');
        this._groupGrid.appendChild(this._groupSentinel);

        this._groupObserver = new IntersectionObserver(entries => {
            if (entries.some(entry => entry.isIntersecting)) {
                this._renderNextGroupBatch();
            }
        }, { rootMargin: '600px 0px' });
        this._groupObserver.observe(this._groupSentinel);
    }

    _stopGroupObserver() {
        this._groupObserver?.disconnect();
        this._groupObserver = null;
        this._groupSentinel?.remove();
        this._groupSentinel = null;
    }

    _stopProgressiveGroupRendering() {
        this._stopGroupObserver();
        this._groupGrid = null;
        this._renderGroup = null;
        this._renderedGroupCount = 0;
    }
}
