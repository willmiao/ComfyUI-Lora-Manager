import { describe, it, beforeEach, expect, vi } from 'vitest';

const {
  SIDEBAR_MANAGER_MODULE,
  STORAGE_HELPERS_MODULE,
  MODEL_API_FACTORY_MODULE,
  I18N_MODULE,
  BULK_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  UPDATE_CHECK_MODULE,
  STATE_MODULE,
} = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  MODEL_API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  UPDATE_CHECK_MODULE: new URL('../../../static/js/utils/updateCheckHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
}));

vi.mock(MODEL_API_FACTORY_MODULE, () => ({ getModelApiClient: vi.fn() }));
vi.mock(I18N_MODULE, () => ({ translate: (key, _args, fallback) => fallback || key }));
vi.mock(BULK_MANAGER_MODULE, () => ({ bulkManager: {} }));
vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn() }));
vi.mock(UPDATE_CHECK_MODULE, () => ({ performFolderUpdateCheck: vi.fn() }));

const { SidebarManager } = await import(SIDEBAR_MANAGER_MODULE);
const { state } = await import(STATE_MODULE);
const { setStorageItem, getStorageItem } = await import(STORAGE_HELPERS_MODULE);

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
    fetchUnifiedFolderTree: vi.fn().mockResolvedValue({ tree: { full: {}, empty: {} } }),
    fetchModelFolders: vi.fn().mockResolvedValue({ folders: ['', 'full'] }),
    fetchModelRoots: vi.fn().mockResolvedValue({ roots: ['/models/loras'] }),
    createFolder: vi.fn().mockResolvedValue({ success: true, folder: 'new-folder', created: true }),
    ...overrides,
  };
}

function createManager(apiClient, { displayMode = 'tree' } = {}) {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.displayMode = displayMode;
  manager.apiClient = apiClient;
  manager.pageControls = { pageState: { searchOptions: {} } };
  manager.renderFolderDisplay = vi.fn();
  manager.renderEmptyState = vi.fn();
  return manager;
}

describe('SidebarManager empty folders toggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
  });

  it('requests the models-only tree by default', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);

    await manager.loadFolderTree();

    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith();
    expect(apiClient.fetchModelFolders).not.toHaveBeenCalled();
    expect(manager.nonEmptyFolders).toBeNull();
    expect(manager.treeData).toEqual({ full: {}, empty: {} });
  });

  it('includes empty folders and tracks the models-only set when enabled', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.showEmptyFolders = true;

    await manager.loadFolderTree();

    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith({ includeEmpty: true });
    expect(apiClient.fetchModelFolders).toHaveBeenCalledWith();
    expect(manager.nonEmptyFolders).toEqual(new Set(['', 'full']));
  });

  it('passes includeEmpty to the folder list in list display mode', async () => {
    const apiClient = createApiClient();
    apiClient.fetchModelFolders
      .mockResolvedValueOnce({ folders: ['', 'full', 'empty'] })
      .mockResolvedValueOnce({ folders: ['', 'full'] });
    const manager = createManager(apiClient, { displayMode: 'list' });
    manager.showEmptyFolders = true;

    await manager.loadFolderTree();

    expect(apiClient.fetchModelFolders).toHaveBeenNthCalledWith(1, { includeEmpty: true });
    expect(manager.foldersList).toEqual(['', 'full', 'empty']);
    expect(manager.nonEmptyFolders).toEqual(new Set(['', 'full']));
  });

  it('ignores the preference when the page does not support folder management', async () => {
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);
    manager.showEmptyFolders = true;

    await manager.loadFolderTree();

    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith();
    expect(manager.nonEmptyFolders).toBeNull();
  });

  it('persists the toggle and reloads the tree', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.loadFolderTree = vi.fn();

    manager.handleEmptyFoldersToggle({ stopPropagation: vi.fn() });

    expect(manager.showEmptyFolders).toBe(true);
    expect(getStorageItem('loras_showEmptyFolders')).toBe(true);
    expect(manager.loadFolderTree).toHaveBeenCalledTimes(1);
  });

  it('dims folders that contain no models', () => {
    const manager = createManager(createApiClient());
    manager.treeData = { full: {}, empty: {} };
    manager.nonEmptyFolders = new Set(['', 'full']);

    const html = manager.renderTreeNode(manager.treeData, '');

    expect(html).toContain('sidebar-tree-node-content  empty');
    expect(html.match(/empty/g).length).toBeGreaterThan(0);
    expect(html).not.toContain('sidebar-tree-node-content  empty" data-path="full"');
  });

  it('does not dim folders whose subtree contains models', () => {
    const manager = createManager(createApiClient());
    // Models live in "characters/anime" only; "characters" itself holds no
    // direct models but must not be dimmed.
    manager.nonEmptyFolders = manager._buildNonEmptyFolderSet(['characters/anime']);
    manager.treeData = { characters: { anime: {} }, empty: {} };

    const html = manager.renderTreeNode(manager.treeData, '');

    const charactersNode = html.match(/<div class="sidebar-tree-node-content[^"]*" data-path="characters">/);
    const animeNode = html.match(/<div class="sidebar-tree-node-content[^"]*" data-path="characters\/anime">/);
    const emptyNode = html.match(/<div class="sidebar-tree-node-content[^"]*" data-path="empty">/);
    expect(charactersNode[0]).not.toContain('empty');
    expect(animeNode[0]).not.toContain('empty');
    expect(emptyNode[0]).toContain('empty');
  });
});

describe('SidebarManager view options menu', () => {
  const MENU_HTML = `
    <div id="sidebarViewOptionsMenu" class="context-menu">
      <div class="context-menu-item" data-action="view-mode-tree"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="view-mode-list"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="toggle-recursive"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="toggle-empty-folders"><i class="check-indicator" style="display:none"></i></div>
    </div>`;

  function getCheck(action) {
    return document.querySelector(`#sidebarViewOptionsMenu [data-action="${action}"] .check-indicator`);
  }

  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = MENU_HTML;
  });

  it('reflects the current view state with check indicators', () => {
    const manager = createManager(createApiClient());
    manager.displayMode = 'tree';
    manager.recursiveSearchEnabled = true;
    manager.showEmptyFolders = false;

    manager.updateViewOptionsMenu();

    expect(getCheck('view-mode-tree').style.display).toBe('block');
    expect(getCheck('view-mode-list').style.display).toBe('none');
    expect(getCheck('toggle-recursive').style.display).toBe('block');
    expect(getCheck('toggle-empty-folders').style.display).toBe('none');
  });

  it('disables the recursive toggle in list mode', () => {
    const manager = createManager(createApiClient());
    manager.displayMode = 'list';

    manager.updateViewOptionsMenu();

    expect(document.querySelector('[data-action="toggle-recursive"]').classList.contains('disabled')).toBe(true);
  });

  it('hides the empty-folders item when folder management is unsupported', () => {
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);

    manager.updateViewOptionsMenu();

    expect(document.querySelector('[data-action="toggle-empty-folders"]').style.display).toBe('none');
  });

  it('switches display mode from the menu and closes it', () => {
    const manager = createManager(createApiClient());
    manager.loadFolderTree = vi.fn();
    const menu = document.getElementById('sidebarViewOptionsMenu');
    menu.style.display = 'block';

    manager.handleViewOptionsAction('view-mode-list');

    expect(manager.displayMode).toBe('list');
    expect(manager.loadFolderTree).toHaveBeenCalledTimes(1);
    expect(menu.style.display).toBe('none');
  });

  it('toggles empty folders from the menu and keeps it open', () => {
    const manager = createManager(createApiClient());
    manager.loadFolderTree = vi.fn();
    const menu = document.getElementById('sidebarViewOptionsMenu');
    menu.style.display = 'block';

    manager.handleViewOptionsAction('toggle-empty-folders');

    expect(manager.showEmptyFolders).toBe(true);
    expect(getCheck('toggle-empty-folders').style.display).toBe('block');
    expect(menu.style.display).toBe('block');
  });

  it('collapses all folders from the header button', () => {
    document.body.insertAdjacentHTML('beforeend',
      '<button id="sidebarCollapseAll"><i class="fas fa-compress-alt"></i></button>');
    const manager = createManager(createApiClient());
    manager.expandedNodes = new Set(['a', 'a/b']);

    manager.handleCollapseAll();

    expect(manager.expandedNodes.size).toBe(0);
    expect(manager.renderFolderDisplay).toHaveBeenCalledTimes(1);
  });

  it('disables the collapse-all header button in list mode', () => {
    document.body.insertAdjacentHTML('beforeend',
      '<button id="sidebarCollapseAll"><i class="fas fa-compress-alt"></i></button>');
    const manager = createManager(createApiClient());
    manager.displayMode = 'list';

    manager.updateCollapseAllButton();

    const button = document.getElementById('sidebarCollapseAll');
    expect(button.disabled).toBe(true);
    expect(button.classList.contains('disabled')).toBe(true);

    manager.displayMode = 'tree';
    manager.updateCollapseAllButton();
    expect(button.disabled).toBe(false);
    expect(button.classList.contains('disabled')).toBe(false);
  });

  it('toggles the menu open and closed from the header button', () => {
    const manager = createManager(createApiClient());
    const button = document.createElement('button');
    document.body.appendChild(button);
    const menu = document.getElementById('sidebarViewOptionsMenu');

    manager.handleViewOptionsButton({ stopPropagation: vi.fn(), currentTarget: button });
    expect(menu.style.display).toBe('block');

    manager.handleViewOptionsButton({ stopPropagation: vi.fn(), currentTarget: button });
    expect(menu.style.display).toBe('none');
  });
});

describe('SidebarManager folder creation', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = '';
    state.global.settings = {};
  });

  it('resolves the configured default root when it is a known root', () => {
    const manager = createManager(createApiClient());
    state.global.settings = { default_lora_root: '/models/loras-main' };

    const root = manager._resolveDefaultRoot(['/models/loras', '/models/loras-main']);

    expect(root).toBe('/models/loras-main');
  });

  it('falls back to the first root when no default is configured', () => {
    const manager = createManager(createApiClient());

    expect(manager._resolveDefaultRoot(['/models/loras'])).toBe('/models/loras');
    expect(manager._resolveDefaultRoot([])).toBe('');
  });

  it('creates the folder under the selected path and reveals it', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.selectedPath = 'characters';
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._createFolder('characters/anime', 'characters');

    expect(success).toBe(true);
    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/characters/anime');
    // Empty-folder display is enabled so the new folder shows up immediately
    expect(manager.showEmptyFolders).toBe(true);
    expect(getStorageItem('loras_showEmptyFolders')).toBe(true);
    expect(manager.expandedNodes.has('characters')).toBe(true);
    expect(manager.refresh).toHaveBeenCalledTimes(1);
  });

  it('fails gracefully when no model root is configured', async () => {
    const apiClient = createApiClient();
    apiClient.fetchModelRoots.mockResolvedValue({ roots: [] });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn();

    const success = await manager._createFolder('new-folder', '');

    expect(success).toBe(false);
    expect(apiClient.createFolder).not.toHaveBeenCalled();
    expect(manager.refresh).not.toHaveBeenCalled();
  });

  it('opens the create-folder input for a context-menu folder', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div class="sidebar-tree-container"></div>';

    manager._performFolderAction('create-subfolder', 'characters');

    const input = document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input');
    expect(input).not.toBeNull();
    expect(manager._createFolderBasePath).toBe('characters');
  });

  it('submits a standalone folder creation when no drag is pending', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    document.body.innerHTML = '<div class="sidebar-tree-container"></div>';

    manager.showCreateFolderInput('characters');
    document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input').value = 'anime';

    await manager.handleCreateFolderSubmit();

    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/characters/anime');
    expect(document.getElementById('sidebarCreateFolderInput')).toBeNull();
  });
});
