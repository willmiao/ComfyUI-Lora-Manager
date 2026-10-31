import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { BaseContextMenu } from '../../../static/js/components/ContextMenu/BaseContextMenu.js';
import {
  closeContextMenus,
  registerContextMenuCloser,
} from '../../../static/js/utils/contextMenuCoordinator.js';

// Menus used to be independent: opening a page menu left a sidebar menu from a
// previous right-click open next to it (and vice versa). They now close each
// other through the coordinator.
let menuCounter = 0;

function nextId(prefix) {
  menuCounter += 1;
  return `${prefix}-${menuCounter}`;
}

function createMenuElement(id) {
  const element = document.createElement('div');
  element.id = id;
  element.className = 'context-menu';
  element.innerHTML = '<div class="context-menu-item" data-action="one">One</div>';
  document.body.appendChild(element);
  return element;
}

function createCard() {
  const card = document.createElement('div');
  card.className = 'model-card';
  return card;
}

describe('context menu coordination', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('closes the menu that was open when another one opens', () => {
    const firstElement = createMenuElement(nextId('firstMenu'));
    const secondElement = createMenuElement(nextId('secondMenu'));
    const first = new BaseContextMenu(firstElement.id, '.model-card');
    const second = new BaseContextMenu(secondElement.id, '.model-card');

    first.showMenu(10, 10, createCard());
    expect(firstElement.style.display).toBe('block');

    second.showMenu(20, 20, createCard());

    expect(firstElement.style.display).toBe('none');
    expect(secondElement.style.display).toBe('block');
  });

  it('closes menus registered by other components', () => {
    const pageElement = createMenuElement(nextId('pageMenu'));
    const pageMenu = new BaseContextMenu(pageElement.id, '.model-card');
    const sidebarHide = vi.fn();
    registerContextMenuCloser(nextId('sidebarMenu'), sidebarHide);

    pageMenu.showMenu(10, 10, createCard());

    expect(sidebarHide).toHaveBeenCalledTimes(1);
  });

  it('keeps the menu that is opening visible', () => {
    const element = createMenuElement(nextId('keptMenu'));
    const menu = new BaseContextMenu(element.id, '.model-card');
    menu.showMenu(10, 10, createCard());

    closeContextMenus(element.id);

    expect(element.style.display).toBe('block');
  });

  it('hides every menu when called without an exception', () => {
    const firstElement = createMenuElement(nextId('firstMenu'));
    const first = new BaseContextMenu(firstElement.id, '.model-card');
    const secondElement = createMenuElement(nextId('secondMenu'));
    const second = new BaseContextMenu(secondElement.id, '.model-card');
    const otherHide = vi.fn();
    registerContextMenuCloser(nextId('otherMenu'), otherHide);

    first.showMenu(10, 10, createCard());
    second.showMenu(20, 20, createCard());

    closeContextMenus();

    expect(firstElement.style.display).toBe('none');
    expect(secondElement.style.display).toBe('none');
    expect(otherHide).toHaveBeenCalled();
  });

  it('keeps working when one closer throws', () => {
    const element = createMenuElement(nextId('survivorMenu'));
    const menu = new BaseContextMenu(element.id, '.model-card');
    menu.showMenu(10, 10, createCard());
    const brokenHide = vi.fn().mockImplementationOnce(() => {
      throw new Error('boom');
    });
    registerContextMenuCloser(nextId('brokenMenu'), brokenHide);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => closeContextMenus(element.id)).not.toThrow();

    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
