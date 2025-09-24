import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderTemplate, resetDom } from '../utils/domFixtures.js';

vi.mock('../../../static/js/managers/LoadingManager.js', () => ({
  LoadingManager: vi.fn(() => ({})),
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { initialize: vi.fn() },
}));

vi.mock('../../../static/js/managers/UpdateService.js', () => ({
  updateService: { initialize: vi.fn() },
}));

vi.mock('../../../static/js/components/Header.js', () => ({
  HeaderManager: vi.fn(() => ({})),
}));

vi.mock('../../../static/js/managers/SettingsManager.js', () => ({
  settingsManager: {
    waitForInitialization: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { initialize: vi.fn() },
}));

vi.mock('../../../static/js/managers/BulkManager.js', () => ({
  bulkManager: {
    initialize: vi.fn(),
    setBulkContextMenu: vi.fn(),
  },
}));

vi.mock('../../../static/js/managers/ExampleImagesManager.js', () => ({
  ExampleImagesManager: vi.fn(() => ({
    initialize: vi.fn(),
  })),
}));

vi.mock('../../../static/js/managers/HelpManager.js', () => ({
  helpManager: {
    initialize: vi.fn(),
  },
}));

vi.mock('../../../static/js/managers/BannerService.js', () => ({
  bannerService: {
    initialize: vi.fn(),
    isBannerVisible: vi.fn().mockReturnValue(false),
  },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  initTheme: vi.fn(),
  initBackToTop: vi.fn(),
  showToast: vi.fn(),
}));

vi.mock('../../../static/js/i18n/index.js', () => ({
  i18n: {
    waitForReady: vi.fn().mockResolvedValue(undefined),
    getCurrentLocale: vi.fn().mockReturnValue('en'),
  },
}));

vi.mock('../../../static/js/managers/OnboardingManager.js', () => ({
  onboardingManager: {
    start: vi.fn(),
  },
}));

vi.mock('../../../static/js/components/ContextMenu/BulkContextMenu.js', () => ({
  BulkContextMenu: vi.fn(),
}));

vi.mock('../../../static/js/utils/eventManagementInit.js', () => ({
  initializeEventManagement: vi.fn(),
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  initializeInfiniteScroll: vi.fn(),
}));

vi.mock('../../../static/js/components/ContextMenu/index.js', () => ({
  createPageContextMenu: vi.fn((pageType) => ({ pageType })),
  createGlobalContextMenu: vi.fn(() => ({ type: 'global' })),
}));

import { appCore } from '../../../static/js/core.js';
import { initializeInfiniteScroll } from '../../../static/js/utils/infiniteScroll.js';
import { createPageContextMenu, createGlobalContextMenu } from '../../../static/js/components/ContextMenu/index.js';

const SUPPORTED_PAGES = ['loras', 'recipes', 'checkpoints', 'embeddings'];

describe('AppCore page orchestration', () => {
  beforeEach(() => {
    resetDom();
    delete window.pageContextMenu;
    delete window.globalContextMenuInstance;
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(SUPPORTED_PAGES)('initializes page features for %s pages', (pageType) => {
    renderTemplate('loras.html', { dataset: { page: pageType } });
    const contextSpy = vi.spyOn(appCore, 'initializeContextMenus');

    appCore.initializePageFeatures();

    expect(contextSpy).toHaveBeenCalledWith(pageType);
    expect(initializeInfiniteScroll).toHaveBeenCalledWith(pageType);
  });

  it('skips initialization when page type is unsupported', () => {
    renderTemplate('statistics.html', { dataset: { page: 'statistics' } });
    const contextSpy = vi.spyOn(appCore, 'initializeContextMenus');

    appCore.initializePageFeatures();

    expect(contextSpy).not.toHaveBeenCalled();
    expect(initializeInfiniteScroll).not.toHaveBeenCalled();
  });

  it('creates page and global context menus on first initialization', () => {
    const pageMenu = { menu: 'page' };
    const globalMenu = { menu: 'global' };
    createPageContextMenu.mockReturnValueOnce(pageMenu);
    createGlobalContextMenu.mockReturnValueOnce(globalMenu);

    appCore.initializeContextMenus('loras');

    expect(createPageContextMenu).toHaveBeenCalledWith('loras');
    expect(window.pageContextMenu).toBe(pageMenu);
    expect(createGlobalContextMenu).toHaveBeenCalledTimes(1);
    expect(window.globalContextMenuInstance).toBe(globalMenu);
  });

  it('reuses the existing global context menu instance on subsequent calls', () => {
    const existingGlobalMenu = { menu: 'existing' };
    window.globalContextMenuInstance = existingGlobalMenu;

    appCore.initializeContextMenus('loras');

    expect(createGlobalContextMenu).not.toHaveBeenCalled();
    expect(window.globalContextMenuInstance).toBe(existingGlobalMenu);
  });
});
