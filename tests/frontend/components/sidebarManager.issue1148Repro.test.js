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
vi.mock(BULK_MANAGER_MODULE, () => ({ bulkManager: {} }));
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn(), showActionToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));
vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { showToast } = await import(UI_HELPERS_MODULE);
const { state } = await import(STATE_MODULE);

const ROOT = '/models/loras';
const SOURCE_FILE = `${ROOT}/anima/character/x.safetensors`;
const TARGET = 'anima/series/test';

function createManager(moveSingleModel, { roots = [ROOT] } = {}) {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.displayMode = 'tree';
  manager.apiClient = {
    apiConfig: { config: { supportsMove: true } },
    moveSingleModel,
    fetchModelRoots: roots instanceof Error
      ? vi.fn().mockRejectedValue(roots)
      : vi.fn().mockResolvedValue({ roots }),
    fetchUnifiedFolderTree: vi.fn().mockResolvedValue({ success: true, tree: {} }),
    fetchModelFolders: vi.fn().mockResolvedValue({ folders: [] }),
  };
  manager.pageControls = { pageState: { searchOptions: {} } };
  return manager;
}

function buildDom() {
  document.body.innerHTML = `
    <div class="folder-sidebar" id="folderSidebar">
      <div class="sidebar-tree-container">
        <div class="sidebar-tree" id="sidebarFolderTree"></div>
      </div>
    </div>
    <div id="modelGrid">
      <div class="model-card"
           data-filepath="${SOURCE_FILE}"
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

function dragCard(manager, folderValue) {
  const card = document.querySelector('.model-card');
  if (folderValue !== undefined) {
    card.dataset.folder = folderValue;
  }
  manager.handleCardDragStart(createDragEvent(card));
}

describe('issue #1148: drag-drop move root resolution', () => {
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

  it('consistent card: destination is root + target', async () => {
    const moveSingleModel = vi.fn().mockResolvedValue({ success: true, new_file_path: `${ROOT}/${TARGET}/x.safetensors` });
    const manager = createManager(moveSingleModel);

    dragCard(manager, 'anima/character');
    await manager.performDragMove(TARGET);

    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });

  it('polluted card (folder=""): root still resolves from the library roots', async () => {
    const moveSingleModel = vi.fn().mockResolvedValue({ success: true, new_file_path: `${ROOT}/${TARGET}/x.safetensors` });
    const manager = createManager(moveSingleModel);

    dragCard(manager, '');
    await manager.performDragMove(TARGET);

    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });

  it('polluted card (folder case mismatch): root still resolves from the library roots', async () => {
    const moveSingleModel = vi.fn().mockResolvedValue({ success: true, new_file_path: `${ROOT}/${TARGET}/x.safetensors` });
    const manager = createManager(moveSingleModel);

    dragCard(manager, 'Anima/Character');
    await manager.performDragMove(TARGET);

    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });

  it('roots API down + mismatched folder: move aborts instead of nesting the target', async () => {
    const moveSingleModel = vi.fn();
    const manager = createManager(moveSingleModel, { roots: new Error('offline') });

    dragCard(manager, 'somewhere/else');
    const result = await manager.performDragMove(TARGET);

    expect(result).toBe(false);
    expect(moveSingleModel).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalled();
  });

  it('roots API down + consistent card: heuristic still resolves the root', async () => {
    const moveSingleModel = vi.fn().mockResolvedValue({ success: true, new_file_path: `${ROOT}/${TARGET}/x.safetensors` });
    const manager = createManager(moveSingleModel, { roots: new Error('offline') });

    dragCard(manager, 'anima/character');
    await manager.performDragMove(TARGET);

    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });

  it('roots API down + case-only mismatch: heuristic resolves case-insensitively', async () => {
    const moveSingleModel = vi.fn().mockResolvedValue({ success: true, new_file_path: `${ROOT}/${TARGET}/x.safetensors` });
    const manager = createManager(moveSingleModel, { roots: new Error('offline') });

    dragCard(manager, 'Anima/Character');
    await manager.performDragMove(TARGET);

    expect(moveSingleModel).toHaveBeenCalledWith(SOURCE_FILE, `${ROOT}/${TARGET}`);
  });
});
