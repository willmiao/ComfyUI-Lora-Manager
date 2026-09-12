import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderOtherPage } from '../utils/pageFixtures.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const createPageControlsMock = vi.fn();
const confirmDeleteMock = vi.fn();
const closeDeleteModalMock = vi.fn();
const confirmExcludeMock = vi.fn();
const closeExcludeModalMock = vi.fn();
const duplicatesManagerMock = vi.fn();
const initActiveFiltersSyncMock = vi.fn();

vi.mock('../../../static/js/core.js', () => ({
  appCore: {
    initialize: initializeAppMock,
    initializePageFeatures: initializePageFeaturesMock,
  },
}));

vi.mock('../../../static/js/components/controls/index.js', () => ({
  createPageControls: createPageControlsMock,
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  confirmDelete: confirmDeleteMock,
  closeDeleteModal: closeDeleteModalMock,
  confirmExclude: confirmExcludeMock,
  closeExcludeModal: closeExcludeModalMock,
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    OTHER: 'other',
  },
}));

vi.mock('../../../static/js/components/ModelDuplicatesManager.js', () => ({
  ModelDuplicatesManager: duplicatesManagerMock,
}));

vi.mock('../../../static/js/utils/activeFiltersSync.js', () => ({
  initActiveFiltersSync: initActiveFiltersSyncMock,
}));

describe('OtherPageManager', () => {
  let OtherPageManager;
  let initializeOtherPage;
  let duplicatesManagerInstance;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();

    duplicatesManagerInstance = {
      checkDuplicatesCount: vi.fn(),
    };

    duplicatesManagerMock.mockReturnValue(duplicatesManagerInstance);
    createPageControlsMock.mockReturnValue({ destroy: vi.fn() });
    initializeAppMock.mockResolvedValue(undefined);

    renderOtherPage();

    ({ OtherPageManager, initializeOtherPage } = await import('../../../static/js/other.js'));
  });

  afterEach(() => {
    delete window.confirmDelete;
    delete window.closeDeleteModal;
    delete window.confirmExclude;
    delete window.closeExcludeModal;
    delete window.modelDuplicatesManager;
  });

  it('wires page controls and exposes modal helpers during construction', () => {
    const manager = new OtherPageManager();

    expect(createPageControlsMock).toHaveBeenCalledWith('other');
    expect(duplicatesManagerMock).toHaveBeenCalledWith(manager, 'other');

    expect(window.confirmDelete).toBe(confirmDeleteMock);
    expect(window.closeDeleteModal).toBe(closeDeleteModalMock);
    expect(window.confirmExclude).toBe(confirmExcludeMock);
    expect(window.closeExcludeModal).toBe(closeExcludeModalMock);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });

  it('initializes shared page features and syncs active filters', async () => {
    const manager = new OtherPageManager();

    await manager.initialize();

    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
    expect(initActiveFiltersSyncMock).toHaveBeenCalledWith('other');
  });

  it('boots the other models page through the initializer', async () => {
    const manager = await initializeOtherPage();

    expect(initializeAppMock).toHaveBeenCalledTimes(1);
    expect(manager).toBeInstanceOf(OtherPageManager);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });
});
