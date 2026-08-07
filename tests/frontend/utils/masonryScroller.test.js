import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MasonryScroller } from '../../../static/js/utils/MasonryScroller.js';
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
function createScroller({ items = [], fetchItemsFn, overscan, viewportHeight = 600 } = {}) {
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
    createItemFn,
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
    });
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

  it('dispose removes classes, spacer and event listeners', () => {
    const { scroller, grid } = track(createScroller());

    scroller.dispose();

    expect(grid.classList.contains('virtual-scroll')).toBe(false);
    expect(grid.classList.contains('masonry-layout')).toBe(false);
    expect(grid.querySelector('.virtual-scroll-spacer')).toBeNull();
  });
});
