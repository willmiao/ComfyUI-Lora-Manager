import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderCheckpointsPage } from '../utils/pageFixtures.js';

const CHECKPOINT_TYPE = 'checkpoints';

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    CHECKPOINT: CHECKPOINT_TYPE,
  },
}));

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

vi.mock('../../../static/js/components/ModelDuplicatesManager.js', () => ({
  ModelDuplicatesManager: duplicatesManagerMock,
}));

describe('CheckpointsPageManager', () => {
  let CheckpointsPageManager;
  let initializeCheckpointsPage;
  let duplicatesManagerInstance;

  beforeEach(async () => {
    vi.clearAllMocks();

    duplicatesManagerInstance = {
      checkDuplicatesCount: vi.fn(),
    };

    duplicatesManagerMock.mockReturnValue(duplicatesManagerInstance);
    createPageControlsMock.mockReturnValue({ destroy: vi.fn() });
    initializeAppMock.mockResolvedValue(undefined);

    renderCheckpointsPage();

    ({ CheckpointsPageManager, initializeCheckpointsPage } = await import('../../../static/js/checkpoints.js'));
  });

  afterEach(() => {
    delete window.confirmDelete;
    delete window.closeDeleteModal;
    delete window.confirmExclude;
    delete window.closeExcludeModal;
    delete window.modelDuplicatesManager;
  });

  it('wires duplicates manager and exposes globals during construction', () => {
    const manager = new CheckpointsPageManager();

    expect(createPageControlsMock).toHaveBeenCalledWith(CHECKPOINT_TYPE);
    expect(duplicatesManagerMock).toHaveBeenCalledWith(manager, CHECKPOINT_TYPE);

    expect(window.confirmDelete).toBe(confirmDeleteMock);
    expect(window.closeDeleteModal).toBe(closeDeleteModalMock);
    expect(window.confirmExclude).toBe(confirmExcludeMock);
    expect(window.closeExcludeModal).toBe(closeExcludeModalMock);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });

  it('initializes shared page features', async () => {
    const manager = new CheckpointsPageManager();

    await manager.initialize();

    expect(initializePageFeaturesMock).toHaveBeenCalledTimes(1);
  });

  it('boots the page when DOMContentLoaded handler runs', async () => {
    const manager = await initializeCheckpointsPage();

    expect(initializeAppMock).toHaveBeenCalledTimes(1);
    expect(manager).toBeInstanceOf(CheckpointsPageManager);
    expect(window.modelDuplicatesManager).toBe(duplicatesManagerInstance);
  });
});
