import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { BaseContextMenu } from '../../../static/js/components/ContextMenu/BaseContextMenu.js';
import { positionFixedMenu, positionSubmenu, MENU_VIEWPORT_MARGIN } from '../../../static/js/utils/menuPosition.js';

// #1167: menus opened near the bottom (or right) edge of the window were placed
// at the raw cursor coordinates. They were only "flipped" when they did not
// fit, which pushed a tall menu above the top edge, and a menu taller than the
// viewport could not be placed at all — its entries became unreachable.
const VIEWPORT_WIDTH = 800;
const VIEWPORT_HEIGHT = 600;
const MARGIN = MENU_VIEWPORT_MARGIN;

const originalViewport = { width: window.innerWidth, height: window.innerHeight };

function setViewport(width, height) {
  for (const [target, name, value] of [
    [window, 'innerWidth', width],
    [window, 'innerHeight', height],
    [document.documentElement, 'clientWidth', width],
    [document.documentElement, 'clientHeight', height],
  ]) {
    Object.defineProperty(target, name, { configurable: true, value });
  }
}

function restoreViewport() {
  setViewport(originalViewport.width, originalViewport.height);
}

function rect({ width = 0, height = 0, top = 0, left = 0 } = {}) {
  return {
    width, height, top, left,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON() { return { ...this }; },
  };
}

// Mirrors what a browser reports for a menu whose height is capped by the
// inline `max-height` the helper applies.
function stubSize(element, size) {
  element.getBoundingClientRect = () => {
    const cap = parseFloat(element.style.maxHeight);
    const height = Number.isFinite(cap) ? Math.min(size.height, cap) : size.height;
    return rect({ width: size.width, height });
  };
}

function createMenuElement(id, size) {
  const menu = document.createElement('div');
  menu.id = id;
  menu.className = 'context-menu';
  menu.innerHTML = '<div class="context-menu-item" data-action="one">One</div>';
  document.body.appendChild(menu);
  if (size) {
    stubSize(menu, size);
  }
  return menu;
}

function createCard() {
  const card = document.createElement('div');
  card.className = 'model-card';
  return card;
}

describe('positionFixedMenu', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setViewport(VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    restoreViewport();
    document.body.innerHTML = '';
  });

  it('opens at the cursor when the menu fits', () => {
    const menu = createMenuElement('menu', { width: 220, height: 300 });

    const geometry = positionFixedMenu(menu, 120, 140);

    expect(menu.style.left).toBe('120px');
    expect(menu.style.top).toBe('140px');
    expect(geometry).toMatchObject({ left: 120, top: 140, width: 220, height: 300 });
  });

  it('flips above the cursor when the menu would overflow the bottom', () => {
    const menu = createMenuElement('menu', { width: 220, height: 300 });

    positionFixedMenu(menu, 120, 450);

    expect(menu.style.top).toBe('150px');
  });

  it('keeps a tall menu inside the viewport instead of pushing it off the top', () => {
    // 500px menu at y=400 fits neither below (900) nor above (-100).
    const menu = createMenuElement('menu', { width: 220, height: 500 });

    positionFixedMenu(menu, 120, 400);

    const top = parseFloat(menu.style.top);
    expect(top).toBeGreaterThanOrEqual(MARGIN);
    expect(top + 500).toBeLessThanOrEqual(VIEWPORT_HEIGHT - MARGIN);
  });

  it('caps a menu taller than the viewport and lets it scroll', () => {
    const menu = createMenuElement('menu', { width: 220, height: 700 });

    positionFixedMenu(menu, 120, 400);

    const maxHeight = VIEWPORT_HEIGHT - MARGIN * 2;
    expect(menu.style.maxHeight).toBe(`${maxHeight}px`);
    expect(menu.style.overflowY).toBe('auto');
    expect(menu.style.top).toBe(`${MARGIN}px`);
  });

  it('drops the height cap when the next menu is short enough', () => {
    const menu = createMenuElement('menu', { width: 220, height: 700 });
    positionFixedMenu(menu, 120, 400);

    stubSize(menu, { width: 220, height: 200 });
    positionFixedMenu(menu, 120, 100);

    expect(menu.style.maxHeight).toBe('');
    expect(menu.style.overflowY).toBe('');
    expect(menu.style.top).toBe('100px');
  });

  it('opens to the left of the cursor near the right edge', () => {
    const menu = createMenuElement('menu', { width: 300, height: 200 });

    positionFixedMenu(menu, 700, 100);

    expect(menu.style.left).toBe(`${700 - 300}px`);
  });

  it('clamps a flipped menu to the left edge when it cannot fit on either side', () => {
    // Wider than half the viewport: flipping left from x=600 lands at -100.
    const menu = createMenuElement('menu', { width: 700, height: 200 });

    positionFixedMenu(menu, 600, 100);

    expect(menu.style.left).toBe(`${MARGIN}px`);
  });

  it('clamps a right-anchored menu to the left edge', () => {
    const menu = createMenuElement('menu', { width: 300, height: 200 });

    positionFixedMenu(menu, 50, 100, { alignX: 'right' });

    expect(menu.style.left).toBe(`${MARGIN}px`);
  });

  it('right-aligns a dropdown to the anchor when there is room', () => {
    const menu = createMenuElement('menu', { width: 160, height: 200 });

    positionFixedMenu(menu, 700, 100, { alignX: 'right' });

    expect(menu.style.left).toBe(`${700 - 160}px`);
    expect(menu.style.top).toBe('100px');
  });
});

describe('BaseContextMenu placement', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setViewport(VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    restoreViewport();
    document.body.innerHTML = '';
  });

  it('keeps the card menu inside the viewport at the bottom edge', () => {
    const menuElement = createMenuElement('cardMenu', { width: 260, height: 500 });
    const menu = new BaseContextMenu('cardMenu', '.model-card');

    menu.showMenu(120, 480, createCard());

    const top = parseFloat(menuElement.style.top);
    expect(top).toBeGreaterThanOrEqual(MARGIN);
    expect(top + 500).toBeLessThanOrEqual(VIEWPORT_HEIGHT - MARGIN);
  });

  it('measures after prepareMenu so entries toggled there are counted', () => {
    let prepared = false;
    const menuElement = createMenuElement('lateMenu');
    // The menu grows to 500px once its per-card entries are prepared.
    menuElement.getBoundingClientRect = () => rect({ width: 220, height: prepared ? 500 : 120 });

    class LateMenu extends BaseContextMenu {
      prepareMenu() {
        prepared = true;
      }
    }
    const menu = new LateMenu('lateMenu', '.model-card');

    menu.showMenu(120, 400, createCard());

    // Measuring before prepareMenu would have used the stale 120px height and
    // opened at y=400, leaving the real 500px menu hanging off the bottom.
    expect(prepared).toBe(true);
    expect(menuElement.style.top).toBe(`${VIEWPORT_HEIGHT - 500 - MARGIN}px`);
  });

  it('passes the clicked card to prepareMenu after setting currentCard', () => {
    createMenuElement('probeMenu', { width: 220, height: 100 });
    const card = createCard();
    const calls = [];

    class ProbeMenu extends BaseContextMenu {
      prepareMenu(card) {
        calls.push({ card, current: this.currentCard });
      }
    }
    const menu = new ProbeMenu('probeMenu', '.model-card');

    menu.showMenu(50, 60, card);

    expect(calls).toHaveLength(1);
    expect(calls[0].card).toBe(card);
    expect(calls[0].current).toBe(card);
  });
});

describe('positionSubmenu', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    setViewport(VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    restoreViewport();
    document.body.innerHTML = '';
  });

  function createSubmenu(geometry) {
    const submenu = document.createElement('div');
    submenu.className = 'context-submenu';
    submenu.getBoundingClientRect = () => rect(geometry);
    document.body.appendChild(submenu);
    return submenu;
  }

  it('flips a submenu left when it would leave the right edge', () => {
    const submenu = createSubmenu({ width: 200, height: 80, top: 100, left: 700 });

    positionSubmenu(submenu);

    expect(submenu.classList.contains('flip-left')).toBe(true);
  });

  it('moves a submenu up when its row sits near the bottom edge', () => {
    // Row at 540..620 overflows the 592 bottom limit by 28px.
    const submenu = createSubmenu({ width: 200, height: 80, top: 540, left: 100 });
    vi.spyOn(window, 'getComputedStyle').mockReturnValue({ top: '-1px' });

    positionSubmenu(submenu);

    expect(submenu.style.top).toBe(`${-1 - 28}px`);
  });

  it('caps a submenu taller than the viewport', () => {
    const submenu = createSubmenu({ width: 200, height: 700, top: 0, left: 100 });

    positionSubmenu(submenu);

    expect(submenu.style.maxHeight).toBe(`${VIEWPORT_HEIGHT - MARGIN * 2}px`);
    expect(submenu.style.overflowY).toBe('auto');
  });

  it('positions the submenu of a hovered row', () => {
    const menuElement = createMenuElement('hoverMenu', { width: 260, height: 200 });
    menuElement.innerHTML = `
      <div class="context-menu-item has-submenu">
        <span>Link Model</span>
        <div class="context-submenu">
          <div class="context-menu-item">Link to source</div>
        </div>
      </div>`;
    const submenu = menuElement.querySelector('.context-submenu');
    submenu.getBoundingClientRect = () => rect({ width: 200, height: 80, top: 540, left: 100 });
    const menu = new BaseContextMenu('hoverMenu', '.model-card');
    menu.showMenu(50, 400, createCard());

    menuElement.querySelector('.has-submenu').dispatchEvent(
      new MouseEvent('mouseover', { bubbles: true })
    );

    expect(submenu.style.display).toBe('block');
    // Shifted above its anchor row so it stays inside the window.
    expect(parseFloat(submenu.style.top)).toBeLessThan(0);

    menu.hideMenu();
    expect(submenu.style.top).toBe('');
    expect(submenu.classList.contains('flip-left')).toBe(false);
  });
});
