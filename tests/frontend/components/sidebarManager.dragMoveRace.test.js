import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  SIDEBAR_MANAGER_MODULE,
  MODEL_API_FACTORY_MODULE,
  I18N_MODULE,
  BULK_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  UPDATE_CHECK_MODULE,
  STATE_MODULE,
  MODAL_MANAGER_MODULE,
} = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  MODEL_API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  UPDATE_CHECK_MODULE: new URL('../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
}));

vi.mock(MODEL_API_FACTORY_MODULE, () => ({ getModelApiClient: vi.fn() }));
vi.mock(I18N_MODULE, () => ({ translate: (key, _args, fallback) => fallback || key }));
vi.mock(BULK_MANAGER_MODULE, () => ({ bulkManager: { toggleBulkMode: vi.fn() } }));
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn(), showActionToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));
vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { bulkManager } = await import(BULK_MANAGER_MODULE);
const { showToast } = await import(UI_HELPERS_MODULE);
const { state } = await import(STATE_MODULE);

const ROOT = '/models/loras';
const SOURCE_FILE = `${ROOT}/anima/character/x.safetensors`;
const SECOND_FILE = `${ROOT}/anima/character/y.safetensors`;
const TARGET = 'anima/series/test';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createManager({ moveSingleModel = vi.fn(), moveBulkModels = vi.fn(), fetchModelRoots } = {}) {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.displayMode = 'tree';
  manager.apiClient = {
    apiConfig: { config: { supportsMove: true } },
    moveSingleModel,
    moveBulkModels,
    fetchModelRoots: fetchModelRoots || vi.fn().mockResolvedValue({ roots: [ROOT] }),
  };
  manager.pageControls = { pageState: { searchOptions: {} } };
  manager.refresh = vi.fn().mockResolvedValue();
  return manager;
}

function buildDom({ filePath = SOURCE_FILE, folder = 'anima/character' } = {}) {
  document.body.innerHTML = `
    <div class="folder-sidebar" id="folderSidebar">
      <div class="sidebar-tree-container">
        <div class="sidebar-tree" id="sidebarFolderTree"></div>
      </div>
    </div>
    <div id="modelGrid">
      <div class="model-card"
           data-filepath="${filePath}"
           data-folder="${folder}"
           data-name="X" data-file_name="x.safetensors">
      </div>
    </div>
  `;
}

function createDragEvent(target) {
  return {
    target,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
    dataTransfer: {
      effectAllowed: '',
      dropEffect: '',
      setData: vi.fn(),
      setDragImage: vi.fn(),
    },
  };
}

describe('SidebarManager drag-drop move vs dragend race', () => {
  beforeEach(() => {
    localStorage.clear();
    buildDom();
    state.bulkMode = false;
    state.selectedModels = new Set();
    state.virtualScroller = null;
    vi.clearAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('completes the move when dragend clears the drag state mid-flight', async () => {
    const roots = deferred();
    const moveSingleModel = vi.fn().mockResolvedValue({
      success: true,
      new_file_path: `${ROOT}/${TARGET}/x.safetensors`,
    });
    const manager = createManager({ moveSingleModel, fetchModelRoots: vi.fn(() => roots.promise) });

    const card = document.querySelector('.model-card');
    manager.handleCardDragStart(createDragEvent(card));

    const movePromise = manager.performDragMove(TARGET);
    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledTimes(1);

    // The browser dispatches dragend right after drop, while the move is
    // still awaiting the roots request. This used to null the drag state and
    // make performDragMove throw on `draggedFilePaths.length`.
    manager.handleCardDragEnd({ target: card });
    expect(manager.draggedFilePaths).toBeNull();

    roots.resolve({ roots: [ROOT] });

    await expect(movePromise).resolves.toBe(true);
    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
    expect(showToast).not.toHaveBeenCalled();
  });

  it('keeps the card-derived fallback root when the roots request fails mid-flight', async () => {
    const roots = deferred();
    const moveSingleModel = vi.fn().mockResolvedValue({
      success: true,
      new_file_path: `${ROOT}/${TARGET}/x.safetensors`,
    });
    const manager = createManager({ moveSingleModel, fetchModelRoots: vi.fn(() => roots.promise) });

    const card = document.querySelector('.model-card');
    manager.handleCardDragStart(createDragEvent(card));

    const movePromise = manager.performDragMove(TARGET);
    manager.handleCardDragEnd({ target: card });
    expect(manager.draggedRootPath).toBeNull();

    roots.reject(new Error('offline'));

    await expect(movePromise).resolves.toBe(true);
    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });

  it('still runs a bulk move and exits bulk mode after dragend cleared the state', async () => {
    state.bulkMode = true;
    state.selectedModels = new Set([SOURCE_FILE, SECOND_FILE]);
    const roots = deferred();
    const moveBulkModels = vi.fn().mockResolvedValue([
      { success: true, original_file_path: SOURCE_FILE, new_file_path: `${ROOT}/${TARGET}/x.safetensors` },
      { success: true, original_file_path: SECOND_FILE, new_file_path: `${ROOT}/${TARGET}/y.safetensors` },
    ]);
    const manager = createManager({ moveBulkModels, fetchModelRoots: vi.fn(() => roots.promise) });

    const card = document.querySelector('.model-card');
    card.classList.add('selected');
    manager.handleCardDragStart(createDragEvent(card));
    expect(manager.draggedFromBulk).toBe(true);

    const movePromise = manager.performDragMove(TARGET);
    manager.handleCardDragEnd({ target: card });
    expect(manager.draggedFromBulk).toBe(false);

    roots.resolve({ roots: [ROOT] });

    await expect(movePromise).resolves.toBe(true);
    expect(moveBulkModels).toHaveBeenCalledWith([SOURCE_FILE, SECOND_FILE], `${ROOT}/${TARGET}`);
    expect(bulkManager.toggleBulkMode).toHaveBeenCalledTimes(1);
  });
});
