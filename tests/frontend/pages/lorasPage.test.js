import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderLorasPage } from '../utils/pageFixtures.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const updateCardsForBulkModeMock = vi.fn();
const createPageControlsMock = vi.fn();
const confirmDeleteMock = vi.fn();
const closeDeleteModalMock = vi.fn();
const confirmExcludeMock = vi.fn();
const closeExcludeModalMock = vi.fn();
const state = {};
const duplicatesManagerMock = vi.fn();

vi.mock('../../../static/js/core.js', () => ({
  appCore: {
    initialize: initializeAppMock,
    initializePageFeatures: initializePageFeaturesMock,
  },
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state,
}));

vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
  updateCardsForBulkMode: updateCardsForBulkModeMock,
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

vi.mock('../../../static/js/components/ModelDuplicatesManager.js', () => ({
  ModelDuplicatesManager: duplicatesManagerMock,
}));

describe('LoraPageManager', () => {
  let LoraPageManager;
  let initializeLoraPage;
  let duplicatesManagerInstance;

  beforeEach(async () => {
    vi.clearAllMocks();

    state.bulkMode = undefined;
    state.selectedLoras = undefined;

    duplicatesManagerInstance = {
      checkDuplicatesCount: vi.fn(),
    };

    duplicatesManagerMock.mockReturnValue(duplicatesManagerInstance);
    createPageControlsMock.mockReturnValue({ destroy: vi.fn() });
    initializeAppMock.mockResolvedValue(undefined);

    renderLorasPage();

    ({ LoraPageManager, initializeLoraPage } = await import('../../../static/js/loras.js'));
  });

  afterEach(() => {
    delete window.confirmDelete;
    delete window.closeDeleteModal;
    delete window.confirmExclude;
    delete window.closeExcludeModal;
    delete window.modelDuplicatesManager;
  });

  it('configures state and exposes globals during construction', () => {
    const manager = new LoraPageManager();

    expect(state.bulkMode).toBe(false);
    expect(state.selectedLoras).toBeInstanceOf(Set);
    expect(createPageControlsMock).toHaveBeenCalledWith('loras');
    expect(duplicatesManagerMock).toHaveBeenCalledWith(manager);

    expect(window.confirmDelete).toBe(confirmDeleteMock);
    expect(window.closeDeleteModal).toBe(closeDeleteModalMock);
    expect(window.confirmExclude).toBe(confirmExcludeMock);
    expect(window.closeExcludeModal).toBe(closeExcludeModalMock);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });

  it('initializes cards and page features', async () => {
    const manager = new LoraPageManager();

    await manager.initialize();

    expect(updateCardsForBulkModeMock).toHaveBeenCalledWith(false);
    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
  });

  it('boots the page when DOMContentLoaded handler runs', async () => {
    const manager = await initializeLoraPage();

    expect(initializeAppMock).toHaveBeenCalledTimes(1);
    expect(manager).toBeInstanceOf(LoraPageManager);
    expect(updateCardsForBulkModeMock).toHaveBeenCalledWith(false);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });
});
