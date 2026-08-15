import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MasonryScroller } from '../../../static/js/utils/MasonryScroller.js';
import { VirtualScroller } from '../../../static/js/utils/VirtualScroller.js';
import { getCurrentPageState, setCurrentPageType } from '../../../static/js/state/index.js';

// jsdom does not always provide requestAnimationFrame; polyfill when missing
if (typeof window !== 'undefined' && typeof window.requestAnimationFrame !== 'function') {
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  window.cancelAnimationFrame = (id) => clearTimeout(id);
}

const CONTAINER_WIDTH = 768; // yields 3 columns at default density: floor((768+12)/(240+12)) = 3
const COLUMN_GAP = 12;
const ROW_GAP = 20;
const PAD_TOP = 4;
const PAD_BOTTOM = 4;
const ITEM_WIDTH = (CONTAINER_WIDTH - 2 * COLUMN_GAP) / 3; // 248
const FALLBACK_HEIGHT = ITEM_WIDTH / (896 / 1152);

function createItemFn() {
  const el = document.createElement('div');
  const card = document.createElement('div');
  card.className = 'model-card';
  const preview = document.createElement('div');
  preview.className = 'card-preview';
  card.appendChild(preview);
  el.appendChild(card);
  return el;
}

function makeItems(dimensions) {
  return dimensions.map((dims, i) => ({
    file_path: `/recipes/item-${i}.png`,
    ...dims,
  }));
}

/**
 * Build a scroller attached to a stubbed container. clientWidth/clientHeight
 * are 0 in jsdom, so they are defined explicitly for deterministic layout.
 */
function createScroller({ items = [], fetchItemsFn, overscan, viewportHeight = 600, createItemFn: customCreateItemFn } = {}) {
  const wrapper = document.createElement('div');
  Object.defineProperty(wrapper, 'clientWidth', { value: CONTAINER_WIDTH, configurable: true });
  Object.defineProperty(wrapper, 'clientHeight', { value: viewportHeight, configurable: true });

  const grid = document.createElement('div');
  wrapper.appendChild(grid);
  document.body.appendChild(wrapper);

  const fetchMock = fetchItemsFn || vi.fn(async () => ({ items, totalItems: items.length, hasMore: false }));

  const scroller = new MasonryScroller({
    gridElement: grid,
    containerElement: wrapper,
    scrollContainer: wrapper,
    createItemFn: customCreateItemFn || createItemFn,
    fetchItemsFn: fetchMock,
    overscan,
  });

  return { scroller, wrapper, grid, fetchMock };
}

describe('MasonryScroller', () => {
  const liveScrollers = [];

  beforeEach(() => {
    setCurrentPageType('recipes');
    getCurrentPageState().duplicatesMode = false;
  });

  afterEach(() => {
    while (liveScrollers.length > 0) {
      liveScrollers.pop().dispose();
    }
    getCurrentPageState().duplicatesMode = false;
  });

  function track(setup) {
    liveScrollers.push(setup.scroller);
    return setup;
  }

  it('adds virtual-scroll and masonry-layout classes and creates the spacer', () => {
    const { scroller, grid } = track(createScroller());

    expect(grid.classList.contains('virtual-scroll')).toBe(true);
    expect(grid.classList.contains('masonry-layout')).toBe(true);
    expect(scroller.spacerElement.className).toBe('virtual-scroll-spacer');
    expect(grid.style.position).toBe('relative');
    expect(grid.contains(scroller.spacerElement)).toBe(true);
  });

  it('computes density-based column count and item width', () => {
    const { scroller } = track(createScroller());

    expect(scroller.columnsCount).toBe(3);
    expect(scroller.itemWidth).toBeCloseTo(ITEM_WIDTH);
  });

  it('places each item into the shortest column', () => {
    // Heights at ITEM_WIDTH=248: 496, 248, 124, 248, 248, 248
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    const cols = scroller.positions.map((p) => p.col);
    expect(cols).toEqual([0, 1, 2, 2, 1, 2]);

    // Tops follow the accumulated shortest-column heights
    expect(scroller.positions[0].top).toBeCloseTo(PAD_TOP);
    expect(scroller.positions[1].top).toBeCloseTo(PAD_TOP);
    expect(scroller.positions[2].top).toBeCloseTo(PAD_TOP);
    expect(scroller.positions[3].top).toBeCloseTo(PAD_TOP + 124 + ROW_GAP); // 148
    expect(scroller.positions[4].top).toBeCloseTo(PAD_TOP + 248 + ROW_GAP); // 272
    expect(scroller.positions[5].top).toBeCloseTo(148 + 248 + ROW_GAP); // 416

    // Left offsets are column index * (itemWidth + columnGap)
    expect(scroller.positions[1].left).toBeCloseTo(ITEM_WIDTH + COLUMN_GAP);
    expect(scroller.positions[2].left).toBeCloseTo(2 * (ITEM_WIDTH + COLUMN_GAP));
  });

  it('sets spacer height to the tallest column minus trailing gap plus padding', () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    // Column heights after placement: [520, 540, 684] (each starts at padTop)
    const expected = 684 - ROW_GAP + PAD_TOP + PAD_BOTTOM; // 672
    expect(scroller.spacerElement.style.height).toBe(`${expected}px`);
  });

  it('falls back to the 896/1152 ratio for items without dimensions', () => {
    const items = makeItems([{}, { width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    expect(scroller.positions[0].height).toBeCloseTo(FALLBACK_HEIGHT);
    expect(scroller.positions[1].height).toBeCloseTo(ITEM_WIDTH);
  });

  it('visible range respects the overscan band', () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller, wrapper } = track(createScroller({ items, viewportHeight: 300 }));

    scroller.refreshWithData(items, items.length, false);
    wrapper.scrollTop = 0;

    // Without overscan, item 5 (top=416) is below the 300px viewport
    scroller.overscan = 0;
    let visible = scroller.getVisibleRange();
    expect([...visible].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4]);

    // overscan=1 extends the band by one itemWidth (248px), pulling item 5 in
    scroller.overscan = 1;
    visible = scroller.getVisibleRange();
    expect(visible.has(5)).toBe(true);
  });

  it('renders visible items with inline masonry styles and clears model-card max-width', () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
    ]);
    const { scroller, grid, wrapper } = track(createScroller({ items, viewportHeight: 3000 }));

    scroller.refreshWithData(items, items.length, false);
    wrapper.scrollTop = 0;
    scroller.overscan = 5;

    scroller.renderItems();

    const rendered = grid.querySelectorAll('.virtual-scroll-item');
    expect(rendered.length).toBe(3);
    rendered.forEach((el, i) => {
      expect(el.style.position).toBe('absolute');
      expect(el.style.width).toBe(`${scroller.positions[i].width}px`);
      expect(el.style.height).toBe(`${scroller.positions[i].height}px`);
      expect(el.style.left).toBe(`${scroller.positions[i].left}px`);
      expect(el.style.top).toBe(`${scroller.positions[i].top}px`);
      expect(el.querySelector('.model-card').style.maxWidth).toBe('none');
      expect(el.querySelector('.model-card').style.minWidth).toBe('0');
    });
  });

  it('clears model-card max-width/min-width when the item element is the card root', () => {
    // Production shape for recipe cards: RecipeCard returns the .model-card
    // element itself, so the scroller must clear constraints on the element
    // rather than a descendant (querySelector would find nothing).
    const items = makeItems([{ width: 100, height: 200 }]);
    const cardRoot = document.createElement('div');
    cardRoot.className = 'model-card';
    const { scroller, grid, wrapper } = track(createScroller({
      items,
      viewportHeight: 3000,
      createItemFn: () => cardRoot.cloneNode(true),
    }));

    scroller.refreshWithData(items, items.length, false);
    wrapper.scrollTop = 0;
    scroller.overscan = 5;

    scroller.renderItems();

    const rendered = grid.querySelectorAll('.virtual-scroll-item');
    expect(rendered.length).toBe(1);
    expect(rendered[0].style.maxWidth).toBe('none');
    expect(rendered[0].style.minWidth).toBe('0');
  });

  it('triggers loadMoreItems when scrolled to the bottom', async () => {
    const firstPage = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const fetchMock = vi.fn(async () => ({ items: makeItems([{ width: 100, height: 100 }]), totalItems: 7, hasMore: false }));
    const { scroller, wrapper } = track(createScroller({ fetchItemsFn: fetchMock, viewportHeight: 600 }));

    scroller.refreshWithData(firstPage, 100, true);
    const pageState = getCurrentPageState();
    const expectedPage = pageState.currentPage;

    // contentBottom = 664; scrollBottom = 100 + 600 = 700 >= 664 - threshold
    wrapper.scrollTop = 100;
    scroller.handleScroll();

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(expectedPage, scroller.pageSize);
    });
  });

  it('does not trigger loadMoreItems when far from the bottom', async () => {
    const fetchMock = vi.fn(async () => ({ items: [], totalItems: 0, hasMore: false }));
    const manyItems = makeItems(Array.from({ length: 30 }, () => ({ width: 100, height: 200 })));
    const { scroller, wrapper } = track(createScroller({ fetchItemsFn: fetchMock, viewportHeight: 600 }));

    scroller.refreshWithData(manyItems, 1000, true);
    wrapper.scrollTop = 0;
    scroller.handleScroll();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns false from calculateLayout in duplicates mode', () => {
    const { scroller } = track(createScroller());

    getCurrentPageState().duplicatesMode = true;
    expect(scroller.calculateLayout()).toBe(false);
  });

  it('computes placement and spacer synchronously during initialize (before rAF)', async () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller } = track(createScroller({ items }));

    await scroller.initialize();

    // Assert immediately after initialize resolves, without waiting for rAF
    expect(scroller.positions.length).toBe(items.length);
    const expected = 684 - ROW_GAP + PAD_TOP + PAD_BOTTOM; // 672
    expect(scroller.spacerElement.style.height).toBe(`${expected}px`);
    expect(getCurrentPageState().currentPage).toBe(2);
  });

  it('shows the error placeholder and resets isLoading when the initial fetch fails', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('network down');
    });
    const { scroller, grid } = track(createScroller({ fetchItemsFn: fetchMock }));

    await expect(scroller.initialize()).resolves.toBeUndefined();

    const placeholder = grid.querySelector('#virtualScrollPlaceholder');
    expect(placeholder).not.toBeNull();
    expect(placeholder.textContent).toContain('Failed to load items');
    expect(scroller.isLoading).toBe(false);
  });

  it('shows the recipes empty placeholder when no items are returned', async () => {
    const { scroller, grid } = track(createScroller({ items: [] }));

    await scroller.initialize();

    const placeholder = grid.querySelector('#virtualScrollPlaceholder');
    expect(placeholder).not.toBeNull();
    expect(placeholder.textContent).toContain('No recipes found');
  });

  it('shows the recently-opened empty placeholder under the opened sort', async () => {
    getCurrentPageState().sortBy = 'opened:desc';
    const { scroller, grid } = track(createScroller({ items: [] }));

    await scroller.initialize();

    const placeholder = grid.querySelector('#virtualScrollPlaceholder');
    expect(placeholder).not.toBeNull();
    expect(placeholder.textContent).toContain('No recently opened recipes');
    getCurrentPageState().sortBy = '';
  });

  it('dispose removes classes, spacer and event listeners', () => {
    const { scroller, grid } = track(createScroller());

    scroller.dispose();

    expect(grid.classList.contains('virtual-scroll')).toBe(false);
    expect(grid.classList.contains('masonry-layout')).toBe(false);
    expect(grid.querySelector('.virtual-scroll-spacer')).toBeNull();
  });

  it('exposes every VirtualScroller prototype method (API parity)', () => {
    const virtualMethods = Object.getOwnPropertyNames(VirtualScroller.prototype);
    const masonryMethods = new Set(Object.getOwnPropertyNames(MasonryScroller.prototype));

    const missing = virtualMethods.filter((name) => !masonryMethods.has(name));
    expect(missing).toEqual([]);
  });

  it('exposes the VirtualScroller property surface after construction', () => {
    const { scroller } = track(createScroller());

    const expectedProperties = [
      'items',
      'renderedItems',
      'totalItems',
      'hasMore',
      'isLoading',
      'gridElement',
      'containerElement',
      'scrollContainer',
      'columnsCount',
      'itemWidth',
      'disabled',
      'spacerElement',
      'pageSize',
    ];

    for (const prop of expectedProperties) {
      expect(scroller[prop]).not.toBeUndefined();
    }
  });

  it('updateSingleItem re-places items and shows the updated indicator on rendered cards', () => {
    // Heights at ITEM_WIDTH=248: 496, 248, 124, 248, 248, 248
    // Item 2 (height 124) sits in column 2 with items 3 and 5 stacked below it
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller, grid, wrapper } = track(createScroller({ items, viewportHeight: 3000 }));

    scroller.refreshWithData(items, items.length, false);
    wrapper.scrollTop = 0;
    scroller.overscan = 5;
    scroller.renderItems();

    const spacerBefore = scroller.spacerElement.style.height;
    const colsBefore = scroller.positions.map((p) => p.col);

    const result = scroller.updateSingleItem('/recipes/item-2.png', { width: 100, height: 150 });

    expect(result).toBe(true);

    // Item 2 height grew 124 -> 372, so the full synchronous re-placement
    // re-flows every later item (item 3 moves from column 2 to column 1)
    expect(scroller.positions[2].height).toBeCloseTo(ITEM_WIDTH * 1.5);
    expect(scroller.positions.map((p) => p.col)).not.toEqual(colsBefore);
    expect(scroller.spacerElement.style.height).not.toBe(spacerBefore);

    // The re-placement equals a fresh full layout of the same items
    const { scroller: reference } = track(createScroller({ items }));
    reference.refreshWithData(scroller.items.slice(), items.length, false);
    expect(scroller.positions.map((p) => p.col)).toEqual(reference.positions.map((p) => p.col));
    for (let i = 0; i < items.length; i++) {
      expect(scroller.positions[i].top).toBeCloseTo(reference.positions[i].top);
    }

    // The rendered card was recreated in place with the update indicator
    const updatedCard = grid.querySelector('.virtual-scroll-item.updated');
    expect(updatedCard).not.toBeNull();
    const indicator = updatedCard.querySelector('.update-indicator');
    expect(indicator).not.toBeNull();
    expect(indicator.textContent).toBe('Updated');
    expect(updatedCard.querySelector('.card-preview').contains(indicator)).toBe(true);
    expect(updatedCard.style.height).toBe(`${scroller.positions[2].height}px`);
    expect(updatedCard.style.top).toBe(`${scroller.positions[2].top}px`);
  });

  it('updateSingleItem returns false for an unknown file path without throwing', () => {
    const items = makeItems([{ width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    let result;
    expect(() => {
      result = scroller.updateSingleItem('/recipes/does-not-exist.png', { title: 'x' });
    }).not.toThrow();
    expect(result).toBe(false);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it('removeItemByFilePath re-places the remaining items and decrements the total', () => {
    // Heights at ITEM_WIDTH=248: 496, 248, 124, 248, 248, 248
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, 60, false);

    const result = scroller.removeItemByFilePath('/recipes/item-2.png');

    expect(result).toBe(true);
    expect(scroller.items.length).toBe(5);
    expect(scroller.totalItems).toBe(59);
    expect(scroller.positions.length).toBe(5);

    // Remaining heights: 496, 248, 248, 248, 248 -> shortest-column placement
    expect(scroller.positions.map((p) => p.col)).toEqual([0, 1, 2, 1, 2]);
    expect(scroller.positions[3].top).toBeCloseTo(PAD_TOP + 248 + ROW_GAP); // 272
    expect(scroller.positions[4].top).toBeCloseTo(PAD_TOP + 248 + ROW_GAP); // 272

    // Spacer reflects the tallest remaining column
    const maxColumnHeight = Math.max(...scroller.columnHeights);
    const expected = maxColumnHeight - ROW_GAP + PAD_TOP + PAD_BOTTOM;
    expect(scroller.spacerElement.style.height).toBe(`${expected}px`);
  });

  it('removeItemByFilePath returns false for an unknown file path', () => {
    const items = makeItems([{ width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(scroller.removeItemByFilePath('/recipes/missing.png')).toBe(false);
    warnSpy.mockRestore();
  });

  it('removeMultipleItemsByFilePath re-places items with no layout gaps', () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
      { width: 100, height: 100 },
    ]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, 60, false);

    const result = scroller.removeMultipleItemsByFilePath([
      '/recipes/item-1.png',
      '/recipes/item-3.png',
    ]);

    expect(result).toBe(true);
    expect(scroller.items.map((i) => i.file_path)).toEqual([
      '/recipes/item-0.png',
      '/recipes/item-2.png',
      '/recipes/item-4.png',
      '/recipes/item-5.png',
    ]);
    expect(scroller.totalItems).toBe(58);

    // The remaining items are laid out exactly as a fresh full placement:
    // compare against a second scroller fed the same remaining items
    const remaining = scroller.items.slice();
    const { scroller: reference } = track(createScroller({ items: remaining }));
    reference.refreshWithData(remaining, remaining.length, false);

    expect(scroller.positions.map((p) => p.col)).toEqual(reference.positions.map((p) => p.col));
    for (let i = 0; i < remaining.length; i++) {
      expect(scroller.positions[i].top).toBeCloseTo(reference.positions[i].top);
      expect(scroller.positions[i].left).toBeCloseTo(reference.positions[i].left);
    }
  });

  it('removeMultipleItemsByFilePath returns false when nothing matches', () => {
    const items = makeItems([{ width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    expect(scroller.removeMultipleItemsByFilePath(['/recipes/missing.png'])).toBe(false);
    expect(scroller.removeMultipleItemsByFilePath([])).toBe(false);
  });

  it('disable stops rendering and enable recreates the spacer after innerHTML is cleared', async () => {
    const items = makeItems([
      { width: 100, height: 200 },
      { width: 100, height: 100 },
      { width: 100, height: 50 },
    ]);
    const { scroller, grid, wrapper } = track(createScroller({ items, viewportHeight: 3000 }));

    scroller.refreshWithData(items, items.length, false);
    wrapper.scrollTop = 0;
    scroller.overscan = 5;
    scroller.renderItems();
    expect(grid.querySelectorAll('.virtual-scroll-item').length).toBe(3);

    scroller.disable();

    expect(scroller.disabled).toBe(true);
    expect(grid.querySelectorAll('.virtual-scroll-item').length).toBe(0);
    expect(scroller.spacerElement.style.display).toBe('none');

    // Duplicates mode wipes the grid contents, destroying the spacer
    grid.innerHTML = '';
    expect(grid.contains(scroller.spacerElement)).toBe(false);

    scroller.enable();

    expect(scroller.disabled).toBe(false);
    expect(grid.contains(scroller.spacerElement)).toBe(true);
    expect(scroller.spacerElement.className).toBe('virtual-scroll-spacer');

    // Full re-placement ran synchronously on re-enable
    expect(scroller.positions.length).toBe(items.length);

    // Rendering resumes after the scheduled rAF
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(grid.querySelectorAll('.virtual-scroll-item').length).toBe(3);
  });

  it('getAdjacentItemByFilePath loads more pages when the target is beyond loaded items', async () => {
    const page1 = [0, 1, 2].map((i) => ({
      file_path: `/recipes/page1-${i}.png`,
      width: 100,
      height: 100,
    }));
    const page2 = [0, 1].map((i) => ({
      file_path: `/recipes/page2-${i}.png`,
      width: 100,
      height: 100,
    }));
    const fetchMock = vi.fn(async () => ({ items: page2, totalItems: 5, hasMore: false }));
    const { scroller } = track(createScroller({ fetchItemsFn: fetchMock }));

    scroller.refreshWithData(page1, 5, true);
    const pageState = getCurrentPageState();
    const expectedPage = pageState.currentPage;

    const result = await scroller.getAdjacentItemByFilePath('/recipes/page1-2.png', 'next');

    expect(fetchMock).toHaveBeenCalledWith(expectedPage, scroller.pageSize);
    expect(result).not.toBeNull();
    expect(result.index).toBe(3);
    expect(result.item.file_path).toBe('/recipes/page2-0.png');
  });

  it('getAdjacentItemByFilePath returns null at boundaries and for unknown paths', async () => {
    const items = makeItems([{ width: 100, height: 100 }, { width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, items.length, false);

    await expect(scroller.getAdjacentItemByFilePath('/recipes/item-0.png', 'prev')).resolves.toBeNull();
    await expect(scroller.getAdjacentItemByFilePath('/recipes/item-1.png', 'next')).resolves.toBeNull();
    await expect(scroller.getAdjacentItemByFilePath('/recipes/missing.png', 'next')).resolves.toBeNull();
  });

  it('getNavigationState reports index, prev/next availability and totals', () => {
    const items = makeItems([{ width: 100, height: 100 }, { width: 100, height: 100 }]);
    const { scroller } = track(createScroller({ items }));

    scroller.refreshWithData(items, 10, true);

    expect(scroller.getNavigationState('/recipes/item-0.png')).toEqual({
      index: 0,
      hasPrev: false,
      hasNext: true,
      loadedItems: 2,
      totalItems: 10,
    });

    const last = scroller.getNavigationState('/recipes/item-1.png');
    expect(last.index).toBe(1);
    expect(last.hasPrev).toBe(true);
    // hasMore keeps forward navigation available past the loaded window
    expect(last.hasNext).toBe(true);

    expect(scroller.getNavigationState('/recipes/missing.png').index).toBe(-1);
    expect(scroller.findIndexByFilePath('/recipes/item-1.png')).toBe(1);
    expect(scroller.findIndexByFilePath('')).toBe(-1);
  });
});
