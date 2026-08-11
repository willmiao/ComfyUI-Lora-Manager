import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderEmbeddingsPage } from '../utils/pageFixtures.js';

const initializeAppMock = vi.fn();
const initializePageFeaturesMock = vi.fn();
const createPageControlsMock = vi.fn();
const confirmDeleteMock = vi.fn();
const closeDeleteModalMock = vi.fn();
const confirmExcludeMock = vi.fn();
const closeExcludeModalMock = vi.fn();
const duplicatesManagerMock = vi.fn();

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
    EMBEDDING: 'embeddings',
  },
}));

vi.mock('../../../static/js/components/ModelDuplicatesManager.js', () => ({
  ModelDuplicatesManager: duplicatesManagerMock,
}));

describe('EmbeddingsPageManager', () => {
  let EmbeddingsPageManager;
  let initializeEmbeddingsPage;
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

    renderEmbeddingsPage();

    ({ EmbeddingsPageManager, initializeEmbeddingsPage } = await import('../../../static/js/embeddings.js'));
  });

  afterEach(() => {
    delete window.confirmDelete;
    delete window.closeDeleteModal;
    delete window.confirmExclude;
    delete window.closeExcludeModal;
    delete window.modelDuplicatesManager;
  });

  it('wires page controls and exposes modal helpers during construction', () => {
    const manager = new EmbeddingsPageManager();

    expect(createPageControlsMock).toHaveBeenCalledWith('embeddings');
    expect(duplicatesManagerMock).toHaveBeenCalledWith(manager, 'embeddings');

    expect(window.confirmDelete).toBe(confirmDeleteMock);
    expect(window.closeDeleteModal).toBe(closeDeleteModalMock);
    expect(window.confirmExclude).toBe(confirmExcludeMock);
    expect(window.closeExcludeModal).toBe(closeExcludeModalMock);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });

  it('initializes shared page features', async () => {
    const manager = new EmbeddingsPageManager();

    await manager.initialize();

    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
  });

  it('boots the embeddings page through the initializer', async () => {
    const manager = await initializeEmbeddingsPage();

    expect(initializeAppMock).toHaveBeenCalledTimes(1);
    expect(manager).toBeInstanceOf(EmbeddingsPageManager);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });
});
