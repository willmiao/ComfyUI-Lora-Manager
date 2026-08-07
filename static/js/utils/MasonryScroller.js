import { state, getCurrentPageState } from '../state/index.js';
import { showToast } from './uiHelpers.js';

/**
 * Column-based (masonry) virtual scroller.
 *
 * Mirrors the VirtualScroller constructor options and lifecycle, but places
 * items into the shortest column instead of a fixed row grid. Each item keeps
 * its natural aspect ratio (width/height provided by the backend); items
 * without dimensions fall back to the default 896:1152 card ratio.
 *
 * Synchronous layout contract: column placement (_layoutItems) and the spacer
 * height are computed synchronously inside loadInitialBatch/refreshWithData,
 * BEFORE scheduleRender's rAF callback. This guarantees the scroll container's
 * scrollHeight is correct within 2 rAFs so restoreScrollPosition
 * (infiniteScroll.js) can preserve the scroll position after refresh.
 */
export class MasonryScroller {
    constructor(options) {
        // Configuration
        this.gridElement = options.gridElement;
        this.createItemFn = options.createItemFn;
        this.fetchItemsFn = options.fetchItemsFn;
        this.overscan = options.overscan || 5; // Extra items to render above/below viewport
        this.containerElement = options.containerElement || this.gridElement.parentElement;
        this.scrollContainer = options.scrollContainer || this.containerElement;
        this.batchSize = options.batchSize || 50;
        this.pageSize = options.pageSize || 100;
        this.itemAspectRatio = 896 / 1152; // Fallback aspect ratio of cards
        this.rowGap = options.rowGap || 20; // Vertical gap between items (default 20px)
        this.columnGap = options.columnGap || 12; // Horizontal gap between columns

        // Container padding properties
        this.containerPaddingTop = options.containerPaddingTop || 4; // Default top padding from CSS
        this.containerPaddingBottom = options.containerPaddingBottom || 4; // Default bottom padding from CSS

        // Data windowing flag is accepted for API parity but never enabled here
        this.enableDataWindowing = false;

        // State
        this.items = []; // All items metadata
        this.renderedItems = new Map(); // Map of rendered DOM elements by index
        this.totalItems = 0;
        this.isLoading = false;
        this.hasMore = true;
        this.lastScrollTop = 0;
        this.scrollDirection = 'down';
        this.disabled = false;
        this.resizeObserver = null;

        // Masonry layout state
        this.columnsCount = 0;
        this.itemWidth = 0;
        this.positions = []; // Per-index placement: { col, top, left, width, height }
        this.columnHeights = []; // Accumulated height per column
        this.lastRenderRange = new Set(); // Indices rendered in the last pass

        // Loading timeout state
        this.loadingTimeout = null;
        this.loadingTimeoutDuration = options.loadingTimeoutDuration || 15000; // 15 seconds default

        // Initialize
        this.initializeContainer();
        this.setupEventListeners();
        this.calculateLayout();
    }

    initializeContainer() {
        // Add virtual scroll and masonry classes to grid
        this.gridElement.classList.add('virtual-scroll');
        this.gridElement.classList.add('masonry-layout');

        // Set the container to have relative positioning
        if (getComputedStyle(this.containerElement).position === 'static') {
            this.containerElement.style.position = 'relative';
        }

        // Create a spacer element with the total height
        this.spacerElement = document.createElement('div');
        this.spacerElement.className = 'virtual-scroll-spacer';
        this.spacerElement.style.width = '100%';
        this.spacerElement.style.height = '0px'; // Will be updated as items are loaded
        this.spacerElement.style.pointerEvents = 'none';

        // The grid will be used for the actual visible items
        this.gridElement.style.position = 'relative';
        this.gridElement.style.minHeight = '0';

        // Apply padding directly to ensure consistency
        this.gridElement.style.paddingTop = `${this.containerPaddingTop}px`;
        this.gridElement.style.paddingBottom = `${this.containerPaddingBottom}px`;

        // Place the spacer inside the grid container
        this.gridElement.appendChild(this.spacerElement);
    }

    calculateLayout() {
        const pageState = getCurrentPageState();
        if (pageState.duplicatesMode) {
            return false;
        }

        // Get container width and style information
        const containerWidth = this.containerElement.clientWidth;
        const containerStyle = getComputedStyle(this.containerElement);
        const paddingLeft = parseInt(containerStyle.paddingLeft, 10) || 0;
        const paddingRight = parseInt(containerStyle.paddingRight, 10) || 0;

        // Calculate available content width (excluding padding)
        const availableContentWidth = containerWidth - paddingLeft - paddingRight;

        // Get display density setting
        const displayDensity = state.global.settings?.display_density || 'default';

        // Base gap between cards
        const baseGap = 12;
        this.columnGap = baseGap;

        // Define minimum card width based on density setting to ensure usability
        // Cards smaller than this become hard to interact with and view
        const minCardWidths = {
            'default': 240,  // Default: comfortable minimum
            'medium': 200,   // Medium: slightly smaller
            'compact': 170   // Compact: smallest usable size
        };
        const minCardWidth = minCardWidths[displayDensity] || 240;

        // Calculate maximum possible columns that fit in available width
        // Formula: maxColumns = floor((availableWidth + gap) / (minCardWidth + gap))
        const maxPossibleColumns = Math.floor((availableContentWidth + this.columnGap) / (minCardWidth + this.columnGap));

        // Ensure at least 1 column
        const maxColumns = Math.max(1, maxPossibleColumns);

        // Define preferred maximum columns based on display density and screen size
        // These are upper limits to prevent too many columns on ultra-wide screens
        let preferredMaxColumns;
        if (window.innerWidth >= 3000) { // 4K
            if (displayDensity === 'default') {
                preferredMaxColumns = 8;
            } else if (displayDensity === 'medium') {
                preferredMaxColumns = 10;
            } else { // compact
                preferredMaxColumns = 12;
            }
        } else if (window.innerWidth >= 2150) { // 2K/1440p
            if (displayDensity === 'default') {
                preferredMaxColumns = 6;
            } else if (displayDensity === 'medium') {
                preferredMaxColumns = 8;
            } else { // compact
                preferredMaxColumns = 10;
            }
        } else { // 1080p and smaller
            if (displayDensity === 'default') {
                preferredMaxColumns = 5;
            } else if (displayDensity === 'medium') {
                preferredMaxColumns = 6;
            } else { // compact
                preferredMaxColumns = 8;
            }
        }

        // Use the smaller of: max columns that fit, or preferred max
        // This ensures cards are never smaller than minCardWidth
        this.columnsCount = Math.min(maxColumns, preferredMaxColumns);

        // Calculate card width to perfectly fill available space
        // Formula: (availableWidth - totalGap) / columns
        const totalGap = (this.columnsCount - 1) * this.columnGap;
        this.itemWidth = (availableContentWidth - totalGap) / this.columnsCount;

        // Edge-to-edge layout: no offset, grid fills container
        const actualGridWidth = this.itemWidth * this.columnsCount + totalGap;

        // Update grid element to fill available width
        this.gridElement.style.maxWidth = `${actualGridWidth}px`;
        this.gridElement.style.width = `${actualGridWidth}px`;

        // Add or remove density classes for style adjustments
        this.gridElement.classList.remove('default-density', 'medium-density', 'compact-density');
        this.gridElement.classList.add(`${displayDensity}-density`);

        // Recompute placement and spacer synchronously, then re-render
        this._layoutItems();
        this.updateSpacerHeight();
        this.clearRenderedItems();
        this.scheduleRender();

        return true;
    }

    /**
     * Compute the display height of an item at the current column width.
     * Falls back to the default 896:1152 card ratio when dimensions are
     * missing (videos, missing previews, legacy data).
     */
    _computeHeight(item) {
        if (item && item.width && item.height) {
            return this.itemWidth * item.height / item.width;
        }
        return this.itemWidth / this.itemAspectRatio;
    }

    /**
     * Place every loaded item into the shortest column.
     * Produces this.positions (per-index placement) and this.columnHeights.
     */
    _layoutItems() {
        this.positions = [];
        this.columnHeights = [];
        if (this.columnsCount === 0) return;

        // All columns start at the container's top padding
        for (let c = 0; c < this.columnsCount; c++) {
            this.columnHeights.push(this.containerPaddingTop);
        }

        for (let i = 0; i < this.items.length; i++) {
            const item = this.items[i];
            const height = this._computeHeight(item);

            // Find the shortest column (first wins on ties)
            let col = 0;
            for (let c = 1; c < this.columnsCount; c++) {
                if (this.columnHeights[c] < this.columnHeights[col]) {
                    col = c;
                }
            }

            const top = this.columnHeights[col];
            const left = col * (this.itemWidth + this.columnGap);

            this.positions.push({ col, top, left, width: this.itemWidth, height });

            this.columnHeights[col] += height + this.rowGap;
        }
    }

    updateSpacerHeight() {
        if (this.columnsCount === 0) return;

        // Total height = tallest column minus the trailing row gap, plus padding
        const maxColumnHeight = this.columnHeights.length > 0 ? Math.max(...this.columnHeights) : 0;
        const spacerHeight = Math.max(
            0,
            maxColumnHeight - this.rowGap + this.containerPaddingTop + this.containerPaddingBottom
        );

        // Update spacer height to represent all items
        this.spacerElement.style.height = `${spacerHeight}px`;
    }

    setupEventListeners() {
        // Debounced scroll handler
        this.scrollHandler = this.debounce(() => this.handleScroll(), 10);
        this.scrollContainer.addEventListener('scroll', this.scrollHandler);

        // Window resize handler for layout recalculation
        this.resizeHandler = this.debounce(() => {
            this.calculateLayout();
        }, 150);

        window.addEventListener('resize', this.resizeHandler);

        // Use ResizeObserver for more accurate container size detection
        if (typeof ResizeObserver !== 'undefined') {
            this.resizeObserver = new ResizeObserver(this.debounce(() => {
                this.calculateLayout();
            }, 150));

            this.resizeObserver.observe(this.containerElement);
        }
    }

    async initialize() {
        try {
            await this.loadInitialBatch();
            this.scheduleRender();
        } catch (err) {
            console.error('Failed to initialize masonry scroller:', err);
            showToast('toast.virtual.loadFailed', {}, 'error');
        }
    }

    async loadInitialBatch() {
        const pageState = getCurrentPageState();
        if (this.isLoading) return;

        this.isLoading = true;
        this.setLoadingTimeout(); // Add loading timeout safety

        try {
            const { items, totalItems, hasMore } = await this.fetchItemsFn(1, this.pageSize);

            this.items = items || [];
            this.totalItems = totalItems || 0;
            this.hasMore = hasMore;

            // Synchronous layout contract: placement and spacer height must be
            // computed here, before any rAF-driven render, so the scroll
            // container's scrollHeight is correct for restoreScrollPosition.
            this._layoutItems();
            this.updateSpacerHeight();

            // Check if there are no items and show placeholder if needed
            if (this.items.length === 0) {
                this.showNoItemsPlaceholder();
            } else {
                this.removeNoItemsPlaceholder();
            }

            // Reset page state to sync with our scroller
            pageState.currentPage = 2; // Next page to load would be 2
            pageState.hasMore = this.hasMore;
            pageState.isLoading = false;

            return { items, totalItems, hasMore };
        } catch (err) {
            console.error('Failed to load initial batch:', err);
            this.showNoItemsPlaceholder('Failed to load items. Please try refreshing the page.');
            throw err;
        } finally {
            this.isLoading = false;
            this.clearLoadingTimeout(); // Clear the timeout
        }
    }

    async loadMoreItems() {
        const pageState = getCurrentPageState();
        if (this.isLoading || !this.hasMore) return;

        this.isLoading = true;
        pageState.isLoading = true;
        this.setLoadingTimeout(); // Add loading timeout safety

        try {
            console.log('Loading more items, page:', pageState.currentPage);
            const { items, hasMore } = await this.fetchItemsFn(pageState.currentPage, this.pageSize);

            if (items && items.length > 0) {
                this.items = [...this.items, ...items];
                this.hasMore = hasMore;
                pageState.hasMore = hasMore;

                // Update page for next request
                pageState.currentPage++;

                // Recompute placement and spacer synchronously
                this._layoutItems();
                this.updateSpacerHeight();

                // Render the newly loaded items if they're in view
                this.scheduleRender();

                console.log(`Loaded ${items.length} more items, total now: ${this.items.length}`);
            } else {
                this.hasMore = false;
                pageState.hasMore = false;
                console.log('No more items to load');
            }

            return items;
        } catch (err) {
            console.error('Failed to load more items:', err);
            showToast('toast.virtual.loadMoreFailed', {}, 'error');
        } finally {
            this.isLoading = false;
            pageState.isLoading = false;
            this.clearLoadingTimeout(); // Clear the timeout
        }
    }

    // Loading timeout safety: never leave isLoading stuck on a hung fetch
    setLoadingTimeout() {
        // Clear any existing timeout first
        this.clearLoadingTimeout();

        // Set a new timeout to prevent loading state from getting stuck
        this.loadingTimeout = setTimeout(() => {
            if (this.isLoading) {
                console.warn('Loading timeout occurred. Resetting loading state.');
                this.isLoading = false;
                const pageState = getCurrentPageState();
                pageState.isLoading = false;
            }
        }, this.loadingTimeoutDuration);
    }

    clearLoadingTimeout() {
        if (this.loadingTimeout) {
            clearTimeout(this.loadingTimeout);
            this.loadingTimeout = null;
        }
    }

    /**
     * Return the Set of currently visible item indices.
     * An item is visible when its vertical span intersects the viewport
     * expanded by overscanH = overscan * itemWidth on both sides.
     */
    getVisibleRange() {
        const scrollTop = this.scrollContainer.scrollTop;
        const viewportHeight = this.scrollContainer.clientHeight;
        const overscanH = this.overscan * this.itemWidth;

        const visible = new Set();
        const minTop = scrollTop - overscanH;
        const maxTop = scrollTop + viewportHeight + overscanH;

        for (let i = 0; i < this.positions.length; i++) {
            const pos = this.positions[i];
            if (pos.top < maxTop && pos.top + pos.height > minTop) {
                visible.add(i);
            }
        }

        return visible;
    }

    scheduleRender() {
        if (this.disabled || this.renderScheduled) return;

        this.renderScheduled = true;
        requestAnimationFrame(() => {
            this.renderItems();
            this.renderScheduled = false;
        });
    }

    renderItems() {
        if (this.disabled || this.items.length === 0 || this.columnsCount === 0) return;

        const visible = this.getVisibleRange();

        // Skip re-render when the visible set has not changed
        if (visible.size === this.lastRenderRange.size) {
            let identical = visible.size > 0;
            if (identical) {
                for (const index of visible) {
                    if (!this.lastRenderRange.has(index)) {
                        identical = false;
                        break;
                    }
                }
            }
            if (identical) return;
        }

        this.lastRenderRange = new Set(visible);

        // Remove items that are no longer visible
        for (const [index, element] of this.renderedItems.entries()) {
            if (!visible.has(index)) {
                element.remove();
                this.renderedItems.delete(index);
            }
        }

        // Use DocumentFragment for batch DOM operations
        const fragment = document.createDocumentFragment();

        // Add new visible items to the fragment
        for (const index of visible) {
            if (index >= this.items.length) continue;
            if (!this.renderedItems.has(index)) {
                const item = this.items[index];
                const element = this.createItemElement(item, index);
                fragment.appendChild(element);
                this.renderedItems.set(index, element);
            }
        }

        // Add the fragment to the grid (single DOM operation)
        if (fragment.childNodes.length > 0) {
            this.gridElement.appendChild(fragment);
        }

        // If we're close to the end and have more items to load, fetch them
        let lastVisibleIndex = -1;
        for (const index of visible) {
            if (index > lastVisibleIndex) lastVisibleIndex = index;
        }
        if (lastVisibleIndex >= 0 &&
            lastVisibleIndex >= this.items.length - (this.columnsCount * 2) &&
            this.hasMore && !this.isLoading) {
            this.loadMoreItems();
        }
    }

    clearRenderedItems() {
        this.renderedItems.forEach(element => element.remove());
        this.renderedItems.clear();
        this.lastRenderRange = new Set();
    }

    refreshWithData(items, totalItems, hasMore) {
        this.items = items || [];
        this.totalItems = totalItems || 0;
        this.hasMore = hasMore;

        // Synchronous layout contract: placement and spacer height are
        // computed before the rAF-driven render so scroll restoration works.
        this._layoutItems();
        this.updateSpacerHeight();

        // Check if there are no items and show placeholder if needed
        if (this.items.length === 0) {
            this.showNoItemsPlaceholder();
        } else {
            this.removeNoItemsPlaceholder();
        }

        // Clear all rendered items and redraw
        this.clearRenderedItems();
        this.scheduleRender();
    }

    createItemElement(item, index) {
        // Create the DOM element
        const element = this.createItemFn(item);

        // Add virtual scroll item class
        element.classList.add('virtual-scroll-item');

        // Look up the precomputed masonry placement
        const pos = this.positions[index];

        // Position the element with absolute positioning
        element.style.position = 'absolute';
        element.style.left = `${pos.left}px`;
        element.style.top = `${pos.top}px`;
        element.style.width = `${pos.width}px`;
        element.style.height = `${pos.height}px`;

        // Remove max-width constraint from model-card to allow dynamic sizing
        const modelCard = element.querySelector('.model-card');
        if (modelCard) {
            modelCard.style.maxWidth = 'none';
        }

        return element;
    }

    handleScroll() {
        // Determine scroll direction
        const scrollTop = this.scrollContainer.scrollTop;
        this.scrollDirection = scrollTop > this.lastScrollTop ? 'down' : 'up';
        this.lastScrollTop = scrollTop;

        // Render visible items
        this.scheduleRender();

        // If we're near the bottom and have more items, load them
        const { clientHeight, scrollHeight } = this.scrollContainer;
        const scrollBottom = scrollTop + clientHeight;

        // Bottom of the tallest column's last item (columnHeights include the
        // trailing row gap after each item, so subtract it back out)
        const contentBottom = this.columnHeights.length > 0
            ? Math.max(...this.columnHeights) - this.rowGap
            : 0;

        // Trigger when within 20% of the scroll height, or within two item
        // widths of the bottom, whichever threshold is smaller
        const scrollThreshold = Math.min(
            scrollHeight * 0.2,
            this.itemWidth * 2
        );

        const shouldLoadMore = scrollBottom >= contentBottom - scrollThreshold;

        if (shouldLoadMore && this.hasMore && !this.isLoading) {
            this.loadMoreItems();
        }
    }

    reset() {
        // Remove all rendered items
        this.clearRenderedItems();

        // Reset state
        this.items = [];
        this.totalItems = 0;
        this.hasMore = true;
        this.positions = [];
        this.columnHeights = [];

        // Reset spacer height
        this.spacerElement.style.height = '0px';

        // Remove any placeholder
        this.removeNoItemsPlaceholder();

        // Schedule a re-render
        this.scheduleRender();
    }

    dispose() {
        // Remove event listeners
        this.scrollContainer.removeEventListener('scroll', this.scrollHandler);
        window.removeEventListener('resize', this.resizeHandler);

        // Clean up the resize observer if present
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
        }

        // Remove any active grid loading overlay
        this.hideGridLoading();

        // Remove rendered elements
        this.clearRenderedItems();

        // Remove spacer
        this.spacerElement.remove();

        // Remove virtual scroll and masonry classes
        this.gridElement.classList.remove('virtual-scroll');
        this.gridElement.classList.remove('masonry-layout');

        // Clear any pending timeout
        this.clearLoadingTimeout();
    }

    // Placeholder display helpers
    showNoItemsPlaceholder(message) {
        // Remove any existing placeholder first
        this.removeNoItemsPlaceholder();

        // Create placeholder message
        const placeholder = document.createElement('div');
        placeholder.className = 'placeholder-message';

        // Determine appropriate message based on page type
        let placeholderText = '';

        if (message) {
            placeholderText = message;
        } else {
            const pageType = state.currentPageType;

            if (pageType === 'recipes') {
                placeholderText = `
                    <p>No recipes found</p>
                    <p>Add recipe images to your recipes folder to see them here.</p>
                `;
            } else if (pageType === 'loras') {
                placeholderText = `
                    <p>No LoRAs found</p>
                    <p>Add LoRAs to your models folder to see them here.</p>
                `;
            } else if (pageType === 'checkpoints') {
                placeholderText = `
                    <p>No checkpoints found</p>
                    <p>Add checkpoints to your models folder to see them here.</p>
                `;
            } else {
                placeholderText = `
                    <p>No items found</p>
                    <p>Try adjusting your search filters or add more content.</p>
                `;
            }
        }

        placeholder.innerHTML = placeholderText;
        placeholder.id = 'virtualScrollPlaceholder';

        // Append placeholder to the grid
        this.gridElement.appendChild(placeholder);
    }

    removeNoItemsPlaceholder() {
        const placeholder = document.getElementById('virtualScrollPlaceholder');
        if (placeholder) {
            placeholder.remove();
        }
    }

    // Utility method for debouncing
    debounce(func, wait) {
        let timeout;
        return function (...args) {
            const context = this;
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(context, args), wait);
        };
    }

    /**
     * Show a grid-scoped loading indicator (replaces full-page overlay)
     * Only covers the card grid area, leaving header/sidebar unaffected.
     */
    showGridLoading() {
        // Remove any stale overlay from a prior deferred hide (e.g. from final rAF)
        this.hideGridLoading();
        const overlay = document.createElement('div');
        overlay.className = 'grid-loading-overlay';
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        overlay.appendChild(spinner);
        this.gridElement.appendChild(overlay);
        this.gridLoadingOverlay = overlay;
    }

    /**
     * Hide the grid-scoped loading indicator.
     */
    hideGridLoading() {
        if (this.gridLoadingOverlay) {
            this.gridLoadingOverlay.remove();
            this.gridLoadingOverlay = null;
        }
    }
}
