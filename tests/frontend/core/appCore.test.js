import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderTemplate, resetDom } from '../utils/domFixtures.js';

const loadingManagerInstance = { showSimpleLoading: vi.fn(), hide: vi.fn() };
const exampleImagesManagerInitialize = vi.fn();
const exampleImagesManagerInstance = { initialize: exampleImagesManagerInitialize };
const bulkContextMenuInstance = { menu: 'bulk-context' };
const headerManagerInstance = { type: 'header-manager' };

vi.mock('../../../static/js/managers/LoadingManager.js', () => ({
  LoadingManager: vi.fn(() => loadingManagerInstance),
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { initialize: vi.fn() },
}));

vi.mock('../../../static/js/managers/UpdateService.js', () => ({
  updateService: { initialize: vi.fn() },
}));

vi.mock('../../../static/js/components/Header.js', () => ({
  HeaderManager: vi.fn(() => headerManagerInstance),
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
  ExampleImagesManager: vi.fn(() => exampleImagesManagerInstance),
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
  BulkContextMenu: vi.fn(() => bulkContextMenuInstance),
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
import { state } from '../../../static/js/state/index.js';
import { LoadingManager } from '../../../static/js/managers/LoadingManager.js';
import { modalManager } from '../../../static/js/managers/ModalManager.js';
import { updateService } from '../../../static/js/managers/UpdateService.js';
import { settingsManager } from '../../../static/js/managers/SettingsManager.js';
import { moveManager } from '../../../static/js/managers/MoveManager.js';
import { bulkManager } from '../../../static/js/managers/BulkManager.js';
import { ExampleImagesManager } from '../../../static/js/managers/ExampleImagesManager.js';
import { helpManager } from '../../../static/js/managers/HelpManager.js';
import { bannerService } from '../../../static/js/managers/BannerService.js';
import { initTheme, initBackToTop } from '../../../static/js/utils/uiHelpers.js';
import { onboardingManager } from '../../../static/js/managers/OnboardingManager.js';
import { BulkContextMenu } from '../../../static/js/components/ContextMenu/BulkContextMenu.js';
import { HeaderManager } from '../../../static/js/components/Header.js';
import { initializeEventManagement } from '../../../static/js/utils/eventManagementInit.js';
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

describe('AppCore initialization flow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    resetDom();
    document.body.className = '';
    appCore.initialized = false;
    state.loadingManager = undefined;
    state.currentPageType = 'loras';
    state.global.settings.card_info_display = 'always';
    delete window.modalManager;
    delete window.settingsManager;
    delete window.exampleImagesManager;
    delete window.helpManager;
    delete window.moveManager;
    delete window.bulkManager;
    delete window.headerManager;
    delete window.i18n;
    delete window.pageContextMenu;
    delete window.globalContextMenuInstance;
  });

  afterEach(async () => {
    await vi.runAllTimersAsync();
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('initializes core managers and global references', async () => {
    state.global.settings.card_info_display = 'hover';

    const result = await appCore.initialize();

    expect(result).toBe(appCore);
    expect(window.i18n).toBeDefined();
    expect(settingsManager.waitForInitialization).toHaveBeenCalledTimes(1);
    expect(LoadingManager).toHaveBeenCalledTimes(1);
    expect(state.loadingManager).toBe(loadingManagerInstance);
    expect(modalManager.initialize).toHaveBeenCalledTimes(1);
    expect(updateService.initialize).toHaveBeenCalledTimes(1);
    expect(bannerService.initialize).toHaveBeenCalledTimes(1);
    expect(window.modalManager).toBe(modalManager);
    expect(window.settingsManager).toBe(settingsManager);
    expect(window.moveManager).toBe(moveManager);
    expect(window.bulkManager).toBe(bulkManager);
    expect(HeaderManager).toHaveBeenCalledTimes(1);
    expect(window.headerManager).toBe(headerManagerInstance);
    expect(initTheme).toHaveBeenCalledTimes(1);
    expect(initBackToTop).toHaveBeenCalledTimes(1);
    expect(bulkManager.initialize).toHaveBeenCalledTimes(1);
    expect(BulkContextMenu).toHaveBeenCalledTimes(1);
    expect(bulkManager.setBulkContextMenu).toHaveBeenCalledWith(bulkContextMenuInstance);
    expect(ExampleImagesManager).toHaveBeenCalledTimes(1);
    expect(window.exampleImagesManager).toBe(exampleImagesManagerInstance);
    expect(exampleImagesManagerInitialize).toHaveBeenCalledTimes(1);
    expect(helpManager.initialize).toHaveBeenCalledTimes(1);
    expect(document.body.classList.contains('hover-reveal')).toBe(true);
    expect(initializeEventManagement).toHaveBeenCalledTimes(1);
    expect(onboardingManager.start).not.toHaveBeenCalled();

    await vi.runAllTimersAsync();

    expect(onboardingManager.start).toHaveBeenCalledTimes(1);
    expect(bannerService.isBannerVisible).toHaveBeenCalledWith('version-mismatch');
  });

  it('does not reinitialize once initialized', async () => {
    await appCore.initialize();
    await vi.runAllTimersAsync();

    vi.clearAllMocks();

    const result = await appCore.initialize();

    expect(result).toBeUndefined();
    expect(LoadingManager).not.toHaveBeenCalled();
    expect(modalManager.initialize).not.toHaveBeenCalled();
    expect(updateService.initialize).not.toHaveBeenCalled();
    expect(ExampleImagesManager).not.toHaveBeenCalled();
    expect(onboardingManager.start).not.toHaveBeenCalled();
  });

  it('skips bulk setup when viewing recipes', async () => {
    state.currentPageType = 'recipes';

    await appCore.initialize();

    expect(bulkManager.initialize).not.toHaveBeenCalled();
    expect(BulkContextMenu).not.toHaveBeenCalled();
    expect(bulkManager.setBulkContextMenu).not.toHaveBeenCalled();
  });

  it('suppresses onboarding when version mismatch banner is visible', async () => {
    bannerService.isBannerVisible.mockReturnValueOnce(true);

    await appCore.initialize();
    await vi.runAllTimersAsync();

    expect(onboardingManager.start).not.toHaveBeenCalled();
  });
});
