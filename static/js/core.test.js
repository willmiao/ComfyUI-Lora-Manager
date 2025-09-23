import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const migrateStorageItemsMock = vi.fn();
const initializeInfiniteScrollMock = vi.fn();
const initThemeMock = vi.fn();
const initBackToTopMock = vi.fn();
const initializeEventManagementMock = vi.fn();
const createPageContextMenuMock = vi.fn().mockReturnValue('page-menu');
const createGlobalContextMenuMock = vi.fn().mockReturnValue('global-menu');
const bulkManagerInitializeMock = vi.fn();
const setBulkContextMenuMock = vi.fn();
const helpManagerInitializeMock = vi.fn();
const updateServiceInitializeMock = vi.fn();
const bannerServiceInitializeMock = vi.fn();
const isBannerVisibleMock = vi.fn().mockReturnValue(false);
const onboardingStartMock = vi.fn();
const settingsWaitMock = vi.fn().mockResolvedValue();
const i18nWaitMock = vi.fn().mockResolvedValue();
const i18nLocaleMock = vi.fn().mockReturnValue('en');

const mockState = {
    currentPageType: 'loras',
    global: {
        settings: {
            card_info_display: 'hover'
        }
    }
};

const mockModalManager = { initialize: vi.fn() };
const mockBulkManager = {
    initialize: bulkManagerInitializeMock,
    setBulkContextMenu: setBulkContextMenuMock
};
const mockHelpManager = { initialize: helpManagerInitializeMock };
const mockUpdateService = { initialize: updateServiceInitializeMock };
const mockBannerService = {
    initialize: bannerServiceInitializeMock,
    isBannerVisible: isBannerVisibleMock
};
const mockOnboardingManager = { start: onboardingStartMock };
const mockSettingsManager = { waitForInitialization: settingsWaitMock };
const mockMoveManager = {};
const mockI18n = {
    waitForReady: i18nWaitMock,
    getCurrentLocale: i18nLocaleMock
};

const loadingManagerInstances = [];
const HeaderManagerInstances = [];
const bulkContextMenuInstances = [];
const exampleImagesManagerInitializeMock = vi.fn();

const LoadingManagerMock = vi.fn(() => {
    const instance = { id: Symbol('LoadingManager') };
    loadingManagerInstances.push(instance);
    return instance;
});

const HeaderManagerMock = vi.fn(() => {
    const instance = { id: Symbol('HeaderManager') };
    HeaderManagerInstances.push(instance);
    return instance;
});

const BulkContextMenuMock = vi.fn(() => {
    const instance = { id: Symbol('BulkContextMenu') };
    bulkContextMenuInstances.push(instance);
    return instance;
});

const ExampleImagesManagerMock = vi.fn(() => {
    const instance = { initialize: exampleImagesManagerInitializeMock };
    globalThis.exampleImagesManager = instance;
    return instance;
});

vi.stubGlobal('exampleImagesManager', null);

vi.mock('./utils/storageHelpers.js', () => ({
    migrateStorageItems: migrateStorageItemsMock
}));

vi.mock('./state/index.js', () => ({
    state: mockState
}));

vi.mock('./managers/LoadingManager.js', () => ({
    LoadingManager: LoadingManagerMock
}));

vi.mock('./managers/ModalManager.js', () => ({
    ModalManager: vi.fn(),
    modalManager: mockModalManager
}));

vi.mock('./managers/UpdateService.js', () => ({
    updateService: mockUpdateService
}));

vi.mock('./components/Header.js', () => ({
    HeaderManager: HeaderManagerMock
}));

vi.mock('./managers/SettingsManager.js', () => ({
    settingsManager: mockSettingsManager
}));

vi.mock('./managers/MoveManager.js', () => ({
    moveManager: mockMoveManager
}));

vi.mock('./managers/BulkManager.js', () => ({
    bulkManager: mockBulkManager
}));

vi.mock('./managers/ExampleImagesManager.js', () => ({
    ExampleImagesManager: ExampleImagesManagerMock
}));

vi.mock('./managers/HelpManager.js', () => ({
    helpManager: mockHelpManager
}));

vi.mock('./managers/BannerService.js', () => ({
    bannerService: mockBannerService
}));

vi.mock('./utils/uiHelpers.js', () => ({
    initTheme: initThemeMock,
    initBackToTop: initBackToTopMock
}));

vi.mock('./utils/infiniteScroll.js', () => ({
    initializeInfiniteScroll: initializeInfiniteScrollMock
}));

vi.mock('./i18n/index.js', () => ({
    i18n: mockI18n
}));

vi.mock('./managers/OnboardingManager.js', () => ({
    onboardingManager: mockOnboardingManager
}));

vi.mock('./components/ContextMenu/BulkContextMenu.js', () => ({
    BulkContextMenu: BulkContextMenuMock
}));

vi.mock('./components/ContextMenu/index.js', () => ({
    createPageContextMenu: createPageContextMenuMock,
    createGlobalContextMenu: createGlobalContextMenuMock
}));

vi.mock('./utils/eventManagementInit.js', () => ({
    initializeEventManagement: initializeEventManagementMock
}));

beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
    document.body.removeAttribute('data-page');
    mockState.currentPageType = 'loras';
    mockState.global.settings.card_info_display = 'hover';
    isBannerVisibleMock.mockReturnValue(false);
    loadingManagerInstances.length = 0;
    HeaderManagerInstances.length = 0;
    bulkContextMenuInstances.length = 0;
    delete window.pageContextMenu;
    delete window.globalContextMenuInstance;
});

afterEach(() => {
    vi.useRealTimers();
});

const loadCoreModule = async () => {
    vi.resetModules();
    return import('./core.js');
};

describe('AppCore module bootstrapping', () => {
    it('registers storage migration on DOMContentLoaded', async () => {
        const addEventListenerSpy = vi.spyOn(document, 'addEventListener');
        await loadCoreModule();

        expect(addEventListenerSpy).toHaveBeenCalledWith('DOMContentLoaded', expect.any(Function));
        const listener = addEventListenerSpy.mock.calls.find(([event]) => event === 'DOMContentLoaded')[1];
        listener();
        expect(migrateStorageItemsMock).toHaveBeenCalledTimes(1);
    });

    it('initializes managers, UI helpers, and onboarding sequence', async () => {
        vi.useFakeTimers();
        const { AppCore } = await loadCoreModule();
        const appCore = new AppCore();

        document.body.dataset.page = 'loras';

        const result = await appCore.initialize();

        expect(result).toBe(appCore);
        expect(i18nWaitMock).toHaveBeenCalled();
        expect(i18nLocaleMock).toHaveBeenCalled();
        expect(settingsWaitMock).toHaveBeenCalled();

        expect(LoadingManagerMock).toHaveBeenCalledTimes(1);
        const loadingInstance = LoadingManagerMock.mock.results[0].value;
        expect(mockState.loadingManager).toBe(loadingInstance);

        expect(mockModalManager.initialize).toHaveBeenCalled();
        expect(updateServiceInitializeMock).toHaveBeenCalled();
        expect(bannerServiceInitializeMock).toHaveBeenCalled();
        expect(window.modalManager).toBe(mockModalManager);
        expect(window.settingsManager).toBe(mockSettingsManager);
        expect(window.bulkManager).toBe(mockBulkManager);
        expect(window.helpManager).toBe(mockHelpManager);

        expect(HeaderManagerMock).toHaveBeenCalledTimes(1);
        expect(initThemeMock).toHaveBeenCalled();
        expect(initBackToTopMock).toHaveBeenCalled();

        expect(bulkManagerInitializeMock).toHaveBeenCalled();
        expect(BulkContextMenuMock).toHaveBeenCalledTimes(1);
        expect(setBulkContextMenuMock).toHaveBeenCalledWith(bulkContextMenuInstances[0]);

        expect(ExampleImagesManagerMock).toHaveBeenCalledTimes(1);
        expect(exampleImagesManagerInitializeMock).toHaveBeenCalled();
        expect(helpManagerInitializeMock).toHaveBeenCalled();

        expect(document.body.classList.contains('hover-reveal')).toBe(true);
        expect(initializeEventManagementMock).toHaveBeenCalled();

        vi.runAllTimers();
        expect(onboardingStartMock).toHaveBeenCalled();
    });

    it('skips bulk manager when recipes page is active', async () => {
        const { AppCore } = await loadCoreModule();
        const appCore = new AppCore();
        mockState.currentPageType = 'recipes';

        await appCore.initialize();

        expect(bulkManagerInitializeMock).not.toHaveBeenCalled();
        expect(BulkContextMenuMock).not.toHaveBeenCalled();
        expect(setBulkContextMenuMock).not.toHaveBeenCalled();
    });

    it('initializes page features with context menus and infinite scroll', async () => {
        const { AppCore } = await loadCoreModule();
        const appCore = new AppCore();
        document.body.dataset.page = 'loras';

        appCore.initializeContextMenus = vi.fn(appCore.initializeContextMenus.bind(appCore));

        appCore.initializePageFeatures();

        expect(appCore.initializeContextMenus).toHaveBeenCalledWith('loras');
        expect(initializeInfiniteScrollMock).toHaveBeenCalledWith('loras');
        expect(createPageContextMenuMock).toHaveBeenCalledWith('loras');
        expect(window.pageContextMenu).toBe('page-menu');
        expect(createGlobalContextMenuMock).toHaveBeenCalled();
        expect(window.globalContextMenuInstance).toBe('global-menu');
    });

    it('does not reinitialize once initialized', async () => {
        const { AppCore } = await loadCoreModule();
        const appCore = new AppCore();

        await appCore.initialize();
        await appCore.initialize();

        expect(i18nWaitMock).toHaveBeenCalledTimes(1);
        expect(settingsWaitMock).toHaveBeenCalledTimes(1);
    });
});
