import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const { SIDEBAR_MANAGER_MODULE, MODAL_UTILS_MODULE } = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  MODAL_UTILS_MODULE: new URL('../../../static/js/utils/modalUtils.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();
const showActionToastMock = vi.fn();
const showConfirmationModalMock = vi.fn();

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (key, _args, fallback) => fallback || key,
}));

vi.mock('../../../static/js/managers/BulkManager.js', () => ({
  bulkManager: {},
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  showActionToast: showActionToastMock,
}));

vi.mock('../../../static/js/utils/updateCheckHelpers.js', () => ({
  performFolderUpdateCheck: vi.fn(),
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

vi.mock(MODAL_UTILS_MODULE, () => ({
  showConfirmationModal: showConfirmationModalMock,
}));

vi.mock('../../../static/js/utils/contextMenuCoordinator.js', () => ({
  closeContextMenus: vi.fn(),
  registerContextMenuCloser: vi.fn(),
}));

vi.mock('../../../static/js/utils/menuPosition.js', () => ({
  positionFixedMenu: vi.fn(),
}));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);

function createApiClient(overrides = {}) {
  return {
    apiConfig: {
      config: {
        displayName: 'LoRA',
        singularName: 'lora',
        supportsMove: true,
        supportsFolderManagement: true,
      },
    },
    resolveFolder: vi.fn().mockResolvedValue({
      success: true,
      candidates: [
        { folder_path: '/models/loras/random', root: '/models/loras', is_symlink: false },
        { folder_path: '/other/loras/random', root: '/other/loras', is_symlink: false },
      ],
    }),
    previewFilenameTemplate: vi.fn().mockResolvedValue({
      success: true,
      dry_run: true,
      summary: { total: 3, success: 3, skipped: 0, failures: 0 },
      planned_moves: [],
    }),
    applyFilenameTemplate: vi.fn().mockResolvedValue(undefined),
    loadMoreWithVirtualScroll: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function createManager(apiClient, pageType = 'loras') {
  const manager = new SidebarManager();
  manager.pageType = pageType;
  manager.apiClient = apiClient;
  return manager;
}

describe('SidebarManager scoped filename template apply', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '';
    showConfirmationModalMock.mockResolvedValue(true);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('dry-runs every candidate directory for the folder, then renames after confirmation', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);

    await manager.applyFilenameTemplateToFolder('random');

    expect(apiClient.resolveFolder).toHaveBeenCalledWith('random');
    expect(apiClient.previewFilenameTemplate).toHaveBeenCalledWith({
      folderPaths: ['/models/loras/random', '/other/loras/random'],
    });
    expect(showConfirmationModalMock).toHaveBeenCalledTimes(1);
    expect(apiClient.applyFilenameTemplate).toHaveBeenCalledWith(null, {
      folderPaths: ['/models/loras/random', '/other/loras/random'],
    });
    expect(apiClient.loadMoreWithVirtualScroll).toHaveBeenCalledWith(true);
  });

  it('does not rename when the confirmation is cancelled', async () => {
    showConfirmationModalMock.mockResolvedValue(false);
    const apiClient = createApiClient();
    const manager = createManager(apiClient);

    await manager.applyFilenameTemplateToFolder('random');

    expect(apiClient.applyFilenameTemplate).not.toHaveBeenCalled();
    expect(apiClient.loadMoreWithVirtualScroll).not.toHaveBeenCalled();
  });

  it('reports when every file in the folder already matches', async () => {
    const apiClient = createApiClient();
    apiClient.previewFilenameTemplate.mockResolvedValue({
      success: true,
      dry_run: true,
      summary: { total: 3, success: 0, skipped: 3, failures: 0 },
      planned_moves: [],
    });
    const manager = createManager(apiClient);

    await manager.applyFilenameTemplateToFolder('random');

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateNothingToRename',
      {},
      'info'
    );
    expect(showConfirmationModalMock).not.toHaveBeenCalled();
    expect(apiClient.applyFilenameTemplate).not.toHaveBeenCalled();
  });

  it('warns when the folder no longer resolves to a directory', async () => {
    const apiClient = createApiClient();
    apiClient.resolveFolder.mockResolvedValue({ success: true, candidates: [] });
    const manager = createManager(apiClient);

    await manager.applyFilenameTemplateToFolder('random');

    expect(showToastMock).toHaveBeenCalledWith(
      'sidebar.applyFilenameTemplateResult.missing',
      {},
      'warning'
    );
    expect(apiClient.previewFilenameTemplate).not.toHaveBeenCalled();
  });

  it('reports a dry-run failure without opening the confirmation', async () => {
    const apiClient = createApiClient();
    apiClient.previewFilenameTemplate.mockRejectedValue(
      new Error('Another library operation is already running.')
    );
    const manager = createManager(apiClient);

    await manager.applyFilenameTemplateToFolder('random');

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateFailed',
      { error: 'Another library operation is already running.' },
      'error'
    );
    expect(showConfirmationModalMock).not.toHaveBeenCalled();
    expect(apiClient.applyFilenameTemplate).not.toHaveBeenCalled();
  });

  it('shows the folder menu entry only on pages with a filename template', () => {
    document.body.innerHTML = `
      <div id="sidebarFolderContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="scan-folder"><span>scan</span></div>
        <div class="context-menu-item" data-action="apply-filename-template"><span>rename</span></div>
        <div class="context-menu-item" data-action="create-subfolder"><span>create</span></div>
        <div class="context-menu-item" data-action="rename-folder"><span>rename folder</span></div>
        <div class="context-menu-item" data-action="delete-folder"><span>delete</span></div>
      </div>
    `;

    const manager = createManager(createApiClient(), 'loras');
    manager._showFolderContextMenu(10, 10, 'random');
    expect(
      document.querySelector('[data-action="apply-filename-template"]').style.display
    ).toBe('');

    const workflowsManager = createManager(createApiClient(), 'workflows');
    workflowsManager._showFolderContextMenu(10, 10, 'random');
    expect(
      document.querySelector('[data-action="apply-filename-template"]').style.display
    ).toBe('none');
  });
});
