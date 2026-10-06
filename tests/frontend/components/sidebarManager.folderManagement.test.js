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
  MODAL_MANAGER_MODULE,
} = vi.hoisted(() => ({
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
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
const { state } = await import(STATE_MODULE);
const { setStorageItem, getStorageItem } = await import(STORAGE_HELPERS_MODULE);
const { showToast, showActionToast } = await import(UI_HELPERS_MODULE);
const { modalManager } = await import(MODAL_MANAGER_MODULE);

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
    // Mirrors the backend resolver: a single-root library answers with the one
    // directory the relative folder maps to.
    resolveFolder: vi.fn((folder) => Promise.resolve({
      success: true,
      folder,
      candidates: [{
        folder_path: `/models/loras/${folder}`,
        root: '/models/loras',
        is_symlink: false,
      }],
    })),
    createFolder: vi.fn().mockResolvedValue({ success: true, folder: 'new-folder', created: true }),
    deleteFolder: vi.fn().mockResolvedValue({
      success: true,
      folder: 'empty',
      model_count: 0,
      file_count: 0,
      dir_count: 0,
      restorable: true,
    }),
    renameFolder: vi.fn().mockResolvedValue({
      success: true,
      renamed: true,
      folder: 'renamed',
      previous_folder: 'empty',
    }),
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

  it('loads the full and models-only folder lists and counts the empty folders', async () => {
    const apiClient = createApiClient();
    apiClient.fetchUnifiedFolderTree.mockResolvedValue({ tree: { full: {}, empty: {} } });
    apiClient.fetchModelFolders.mockResolvedValue({ folders: ['', 'full'] });
    const manager = createManager(apiClient);

    await manager.loadFolderTree();

    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith({ includeEmpty: true });
    expect(apiClient.fetchModelFolders).toHaveBeenCalledWith();
    expect(manager.nonEmptyFolders).toEqual(new Set(['', 'full']));
    expect(manager.treeData).toEqual({ full: {}, empty: {} });
    expect(manager.emptyFolderCount).toBe(1);
  });

  it('keeps the folder data loaded while empty folders are hidden', async () => {
    const apiClient = createApiClient();
    apiClient.fetchUnifiedFolderTree.mockResolvedValue({ tree: { full: {}, empty: {} } });
    const manager = createManager(apiClient);
    manager.showEmptyFolders = false;

    await manager.loadFolderTree();

    // The data is still fetched so the menu can report the count; only the
    // rendering is gated by the preference.
    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith({ includeEmpty: true });
    expect(manager.emptyFolderCount).toBe(1);
  });

  it('passes includeEmpty to the folder list in list display mode', async () => {
    const apiClient = createApiClient();
    apiClient.fetchModelFolders
      .mockResolvedValueOnce({ folders: ['', 'full', 'empty'] })
      .mockResolvedValueOnce({ folders: ['', 'full'] });
    const manager = createManager(apiClient, { displayMode: 'list' });

    await manager.loadFolderTree();

    expect(apiClient.fetchModelFolders).toHaveBeenNthCalledWith(1, { includeEmpty: true });
    expect(apiClient.fetchModelFolders).toHaveBeenNthCalledWith(2);
    expect(manager.foldersList).toEqual(['', 'full', 'empty']);
    expect(manager.nonEmptyFolders).toEqual(new Set(['', 'full']));
    expect(manager.emptyFolderCount).toBe(1);
  });

  it('does not request empty folders when the page does not support folder management', async () => {
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);

    await manager.loadFolderTree();

    expect(apiClient.fetchUnifiedFolderTree).toHaveBeenCalledWith();
    expect(apiClient.fetchModelFolders).not.toHaveBeenCalled();
    expect(manager.nonEmptyFolders).toBeNull();
    expect(manager.emptyFolderCount).toBeNull();
  });

  it('persists the toggle and re-renders without refetching', () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.showEmptyFolders = false;
    manager.loadFolderTree = vi.fn();

    manager.handleEmptyFoldersToggle({ stopPropagation: vi.fn() });

    expect(manager.showEmptyFolders).toBe(true);
    expect(getStorageItem('loras_showEmptyFolders')).toBe(true);
    expect(manager.loadFolderTree).not.toHaveBeenCalled();
    expect(manager.renderFolderDisplay).toHaveBeenCalledTimes(1);
  });

  it('dims folders that contain no models', () => {
    const manager = createManager(createApiClient());
    manager.showEmptyFolders = true;
    manager.treeData = { full: {}, empty: {} };
    manager.nonEmptyFolders = new Set(['', 'full']);

    const html = manager.renderTreeNode(manager.treeData, '');

    expect(html).toContain('sidebar-tree-node-content  empty');
    expect(html.match(/empty/g).length).toBeGreaterThan(0);
    expect(html).not.toContain('sidebar-tree-node-content  empty" data-path="full"');
  });

  it('does not dim folders whose subtree contains models', () => {
    const manager = createManager(createApiClient());
    manager.showEmptyFolders = true;
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

  it('does not dim folders while the preference is off', () => {
    const manager = createManager(createApiClient());
    manager.showEmptyFolders = false;
    manager.treeData = { full: {}, empty: {} };
    manager.nonEmptyFolders = new Set(['', 'full']);

    const html = manager.renderTreeNode(manager.treeData, '');

    expect(html).not.toContain('sidebar-tree-node-content  empty');
  });

  describe('list view', () => {
    beforeEach(() => {
      document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    });

    it('hides empty folders from the flat list while the preference is off', () => {
      const manager = createManager(createApiClient(), { displayMode: 'list' });
      manager.showEmptyFolders = false;
      manager.foldersList = ['', 'full', 'empty'];
      manager.nonEmptyFolders = manager._buildNonEmptyFolderSet(['full']);

      manager.renderFolderList();

      const html = document.getElementById('sidebarFolderTree').innerHTML;
      expect(html).toContain('data-path="full"');
      expect(html).not.toContain('data-path="empty"');
    });

    it('shows empty folders dimmed in the flat list when the preference is on', () => {
      const manager = createManager(createApiClient(), { displayMode: 'list' });
      manager.showEmptyFolders = true;
      manager.foldersList = ['', 'full', 'empty'];
      manager.nonEmptyFolders = manager._buildNonEmptyFolderSet(['full']);

      manager.renderFolderList();

      const html = document.getElementById('sidebarFolderTree').innerHTML;
      expect(html).toContain('sidebar-node-content empty" data-path="empty"');
    });
  });
});

describe('SidebarManager view options menu', () => {
  const MENU_HTML = `
    <div id="sidebarViewOptionsMenu" class="context-menu">
      <div class="context-menu-item" data-action="view-mode-tree"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="view-mode-list"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="toggle-recursive"><i class="check-indicator" style="display:none"></i></div>
      <div class="context-menu-item" data-action="toggle-empty-folders"><span id="sidebarEmptyFoldersCount"></span><i class="check-indicator" style="display:none"></i></div>
    </div>`;

  function getCheck(action) {
    return document.querySelector(`#sidebarViewOptionsMenu [data-action="${action}"] .check-indicator`);
  }

  function getEmptyFoldersItem() {
    return document.querySelector('[data-action="toggle-empty-folders"]');
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

    expect(getEmptyFoldersItem().style.display).toBe('none');
  });

  it('hides the empty-folders item when the library has no empty folders', () => {
    const manager = createManager(createApiClient());
    manager.emptyFolderCount = 0;

    manager.updateViewOptionsMenu();

    expect(getEmptyFoldersItem().style.display).toBe('none');
  });

  it('keeps the empty-folders item visible while the count is unknown', () => {
    const manager = createManager(createApiClient());
    manager.emptyFolderCount = null;

    manager.updateViewOptionsMenu();

    expect(getEmptyFoldersItem().style.display).not.toBe('none');
  });

  it('shows the empty-folder count next to the label', () => {
    const manager = createManager(createApiClient());
    manager.emptyFolderCount = 12;

    manager.updateViewOptionsMenu();

    expect(getEmptyFoldersItem().style.display).not.toBe('none');
    expect(document.getElementById('sidebarEmptyFoldersCount').textContent).toBe('(12)');
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
    manager.showEmptyFolders = false;
    const menu = document.getElementById('sidebarViewOptionsMenu');
    menu.style.display = 'block';

    manager.handleViewOptionsAction('toggle-empty-folders');

    expect(manager.showEmptyFolders).toBe(true);
    expect(getCheck('toggle-empty-folders').style.display).toBe('block');
    expect(menu.style.display).toBe('block');
    expect(manager.renderFolderDisplay).toHaveBeenCalled();
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

  it('shows empty folders on a fresh library (default preference)', () => {
    const manager = createManager(createApiClient());
    manager.updateSearchRecursiveOption = vi.fn();
    manager.updateFolderManagementButtons = vi.fn();
    manager.updateCollapseAllButton = vi.fn();

    manager.restoreSidebarState();

    expect(manager.showEmptyFolders).toBe(true);
  });

  it('honours a stored preference to hide empty folders', () => {
    setStorageItem('loras_showEmptyFolders', false);
    const manager = createManager(createApiClient());
    manager.updateSearchRecursiveOption = vi.fn();
    manager.updateFolderManagementButtons = vi.fn();
    manager.updateCollapseAllButton = vi.fn();

    manager.restoreSidebarState();

    expect(manager.showEmptyFolders).toBe(false);
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
    manager.showEmptyFolders = false;
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._createFolder('characters/anime', 'characters');

    expect(success).toBe(true);
    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/characters/anime');
    // The new folder is empty, so creating it turns empty-folder display back
    // on to keep the folder visible in the tree.
    expect(manager.showEmptyFolders).toBe(true);
    expect(getStorageItem('loras_showEmptyFolders')).toBe(true);
    expect(manager.expandedNodes.has('characters')).toBe(true);
    expect(manager.refresh).toHaveBeenCalledTimes(1);
  });

  it('creates inside the parent root even when it is not the default root', async () => {
    const apiClient = createApiClient({
      fetchModelRoots: vi.fn().mockResolvedValue({
        roots: ['/models/loras', '/models/extra'],
      }),
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'recipes',
        candidates: [{
          folder_path: '/models/loras/recipes',
          root: '/models/loras',
          is_symlink: false,
        }],
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    state.global.settings = { default_lora_root: '/models/extra' };

    const success = await manager._createFolder('recipes/presets', 'recipes');

    // A new folder belongs next to the node it was created from; only a
    // root-level creation falls back to the configured default root.
    expect(success).toBe(true);
    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/recipes/presets');
  });

  it('re-enables empty folders when creating while the preference is off', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.showEmptyFolders = false;
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._createFolder('new-folder', '');

    expect(success).toBe(true);
    expect(manager.showEmptyFolders).toBe(true);
    expect(getStorageItem('loras_showEmptyFolders')).toBe(true);
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

  it('opens the create-folder input as an inline row under the context-menu folder', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.treeData = { characters: {} };
    manager.renderTree();

    manager._performFolderAction('create-subfolder', 'characters');

    const row = document.getElementById('sidebarCreateFolderInput');
    expect(row).not.toBeNull();
    expect(row.classList.contains('sidebar-create-folder-node')).toBe(true);
    expect(manager._createFolderBasePath).toBe('characters');
    // The leaf parent is expanded and the row sits inside its children container
    expect(manager.expandedNodes.has('characters')).toBe(true);
    const parentNode = document.querySelector('.sidebar-tree-node[data-path="characters"]');
    expect(parentNode.querySelector(':scope > .sidebar-tree-children').contains(row)).toBe(true);
  });

  it('inserts the row as the first child of an already-expanded parent', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.treeData = { characters: { anime: {} } };
    manager.expandedNodes = new Set(['characters']);
    manager.renderTree();

    manager.showCreateFolderInput('characters');

    const children = document.querySelector('.sidebar-tree-node[data-path="characters"] > .sidebar-tree-children');
    expect(children.firstElementChild.id).toBe('sidebarCreateFolderInput');
    // Existing children container is reused, no temporary one is tracked
    expect(manager._createFolderTempChildren).toBeNull();
  });

  it('appends the row at the top level for root creation', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.treeData = { characters: {} };
    manager.renderTree();

    manager.showCreateFolderInput('');

    const folderTree = document.getElementById('sidebarFolderTree');
    const row = document.getElementById('sidebarCreateFolderInput');
    expect(row.parentElement).toBe(folderTree);
    expect(folderTree.lastElementChild).toBe(row);
  });

  it('inserts the row after the parent item in list mode', () => {
    const manager = createManager(createApiClient(), { displayMode: 'list' });
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.foldersList = ['characters', 'characters/anime'];
    manager.renderFolderList();

    manager.showCreateFolderInput('characters');

    const items = [...document.querySelectorAll('#sidebarFolderTree > div')];
    const parentIndex = items.findIndex(el => el.dataset.path === 'characters');
    expect(items[parentIndex + 1].id).toBe('sidebarCreateFolderInput');
    // List-mode rows use the list content styling, not the tree one
    expect(items[parentIndex + 1].querySelector('.sidebar-node-content')).not.toBeNull();
  });

  it('removes the temporary children container when creation is canceled', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.treeData = { characters: {} };
    manager.renderTree();

    manager.showCreateFolderInput('characters');
    manager.handleCreateFolderCancel();

    expect(document.getElementById('sidebarCreateFolderInput')).toBeNull();
    expect(manager.isCreatingFolder).toBe(false);
    const parentNode = document.querySelector('.sidebar-tree-node[data-path="characters"]');
    expect(parentNode.querySelector(':scope > .sidebar-tree-children')).toBeNull();
  });

  it('cancels creation when the input loses focus', () => {
    vi.useFakeTimers();
    try {
      const manager = createManager(createApiClient());
      document.body.innerHTML = '<div id="sidebarFolderTree"></div>';

      manager.showCreateFolderInput('');
      const input = document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input');
      input.dispatchEvent(new Event('blur'));
      vi.advanceTimersByTime(150);

      expect(document.getElementById('sidebarCreateFolderInput')).toBeNull();
      expect(manager.isCreatingFolder).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('ignores tree clicks and context menus on the create row', () => {
    const manager = createManager(createApiClient());
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    manager.treeData = { characters: {} };
    manager.renderTree();
    manager.selectFolder = vi.fn();
    const showMenu = vi.spyOn(manager, '_showFolderContextMenu').mockImplementation(() => {});

    manager.showCreateFolderInput('characters');
    const input = document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input');

    manager.handleTreeClick({ target: input });
    expect(manager.selectFolder).not.toHaveBeenCalled();

    manager.handleTreeContextMenu({ target: input, preventDefault: vi.fn(), stopPropagation: vi.fn() });
    expect(showMenu).not.toHaveBeenCalled();
  });

  it('submits a standalone folder creation when no drag is pending', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';

    manager.showCreateFolderInput('characters');
    document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input').value = 'anime';

    await manager.handleCreateFolderSubmit();

    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/characters/anime');
    expect(document.getElementById('sidebarCreateFolderInput')).toBeNull();
  });
});

describe('SidebarManager folder deletion', () => {
  const MODAL_HTML = `
    <div id="deleteFolderModal" class="modal delete-modal">
      <div class="modal-content delete-modal-content">
        <h2 data-role="title"></h2>
        <p class="delete-message" data-role="message"></p>
        <div class="delete-model-info" data-role="info"></div>
        <div class="delete-folder-roots" data-role="roots"></div>
        <div class="modal-actions">
          <button class="cancel-btn" data-action="cancel-delete-folder">Cancel</button>
          <button class="delete-btn" data-action="confirm-delete-folder">Delete folder</button>
        </div>
      </div>
    </div>`;

  function confirmBtn() {
    return document.querySelector('#deleteFolderModal [data-action="confirm-delete-folder"]');
  }

  function rootChoices() {
    return [...document.querySelectorAll('#deleteFolderModal input[name="deleteFolderRoot"]')];
  }

  function keptNote() {
    return document.querySelector('#deleteFolderModal .folder-root-kept-note');
  }

  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = MODAL_HTML;
    state.global.settings = {};
    vi.clearAllMocks();
  });

  it('opens the confirm state for a folder whose subtree holds no models', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('empty');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('confirm');
    expect(confirmBtn().style.display).toBe('');
    expect(confirmBtn().disabled).toBe(false);
    // The pending target is the resolved directory, never the bare tree path:
    // the tree path is relative to a root this node may not even live under.
    expect(manager._pendingDeleteFolderRelative).toBe('empty');
    expect(manager._pendingDeleteFolderPath).toBe('/models/loras/empty');
    expect(modalManager.showModal).toHaveBeenCalledWith('deleteFolderModal');
    // The prediction is confirmed against the real guard before the user can
    // act on it.
    expect(apiClient.resolveFolder).toHaveBeenCalledWith('empty');
    expect(apiClient.deleteFolder).toHaveBeenCalledWith(
      '/models/loras/empty', { dryRun: true }
    );
  });

  it('explains the refusal when the subtree still holds models', async () => {
    const conflict = Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 2, excluded_model_count: 0 },
    });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('full');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('blocked');
    expect(confirmBtn().style.display).toBe('none');
    expect(manager._pendingDeleteFolderPath).toBeNull();
  });

  it('treats an unknown folder as model-free when the models-only set is missing', async () => {
    // nonEmptyFolders is null outside the include-empty tree; the dry run is
    // what actually decides, so the prediction is only a starting point.
    const manager = createManager(createApiClient());
    manager.nonEmptyFolders = null;

    await manager.showDeleteFolderModal('empty');

    expect(document.getElementById('deleteFolderModal').dataset.state).toBe('confirm');
  });

  it('blocks a folder the tree shows as empty when only excluded models live there', async () => {
    // The reported mismatch: excluded models are absent from the models-only
    // set (so the node dims as empty), yet they are real weight files on disk
    // and the delete guard refuses to cascade over them.
    const conflict = Object.assign(
      new Error('Folder still contains 3 model file(s), all excluded from the library'),
      { code: 'not_empty', manifest: { model_count: 3, excluded_model_count: 3 } }
    );
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('Flux.1 D/test');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('blocked');
    expect(confirmBtn().style.display).toBe('none');
    expect(manager._pendingDeleteFolderPath).toBeNull();
    // The message names the excluded models instead of contradicting the tree.
    expect(modal.querySelector('[data-role="message"]').textContent)
      .toContain('excluded from the library');
    expect(apiClient.deleteFolder).toHaveBeenCalledWith(
      '/models/loras/Flux.1 D/test', { dryRun: true }
    );
  });

  it('reports how many model files block the delete when some are excluded', async () => {
    const conflict = Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 4, excluded_model_count: 1 },
    });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('mixed');

    expect(
      document.getElementById('deleteFolderModal')
        .querySelector('[data-role="message"]').textContent
    ).toContain('4 model file(s)');
  });

  it('blocks the delete while a staged delete is still pending', async () => {
    const busy = Object.assign(new Error('staged delete pending'), { code: 'busy' });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(busy),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('empty');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('busy');
    expect(confirmBtn().style.display).toBe('none');
  });

  it('keeps the confirm button disabled until the check settles', async () => {
    let release;
    const apiClient = createApiClient({
      resolveFolder: vi.fn(() => new Promise((resolve) => { release = resolve; })),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    const pending = manager.showDeleteFolderModal('empty');
    expect(confirmBtn().disabled).toBe(true);

    release({
      success: true,
      folder: 'empty',
      candidates: [{
        folder_path: '/models/loras/empty',
        root: '/models/loras',
        is_symlink: false,
      }],
    });
    await pending;

    expect(confirmBtn().disabled).toBe(false);
    expect(document.getElementById('deleteFolderModal').dataset.state).toBe('confirm');
  });

  it('ignores a dry-run answer that lands after the modal was dismissed', async () => {
    let rejectProbe;
    const apiClient = createApiClient({
      deleteFolder: vi.fn(() => new Promise((_resolve, reject) => { rejectProbe = reject; })),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    const pending = manager.showDeleteFolderModal('empty');
    expect(document.getElementById('deleteFolderModal').dataset.state).toBe('confirm');

    await vi.waitFor(() => expect(rejectProbe).toBeTypeOf('function'));

    manager.hideDeleteFolderModal();
    rejectProbe(Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 1, excluded_model_count: 0 },
    }));
    await pending;

    expect(document.getElementById('deleteFolderModal').dataset.state).toBe('confirm');
  });

  it('falls back to the tree prediction when the check fails for another reason', async () => {
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(new Error('network down')),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('empty');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('confirm');
    expect(confirmBtn().disabled).toBe(false);
  });

  it('deletes the folder and offers the undo affordance for an empty one', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('empty');

    expect(success).toBe(true);
    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/loras/empty');
    expect(manager.refresh).toHaveBeenCalledTimes(1);
    expect(showActionToast).toHaveBeenCalledTimes(1);
    expect(showToast).not.toHaveBeenCalled();
  });

  it('restores a deleted empty folder through the create-folder API', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager._deleteFolder('empty');
    const undo = showActionToast.mock.calls[0][3].onAction;
    await undo();

    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/empty');
    expect(showToast).toHaveBeenCalledWith('sidebar.deleteFolderResult.restored', {}, 'success');
  });

  it('skips the undo affordance when non-model leftovers were removed', async () => {
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'empty',
        file_count: 2,
        dir_count: 1,
        restorable: false,
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager._deleteFolder('empty');

    expect(showActionToast).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.successWithFiles',
      { name: 'empty', count: 3 },
      'success'
    );
  });

  it('surfaces the not_empty conflict when the tree was stale', async () => {
    const conflict = Object.assign(new Error('still contains models'), { code: 'not_empty' });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('full');

    expect(success).toBe(false);
    expect(showToast).toHaveBeenCalledWith('sidebar.deleteFolderResult.notEmpty', {}, 'warning');
    expect(manager.refresh).not.toHaveBeenCalled();
  });

  it('includes the model count in the stale-tree toast when the manifest has one', async () => {
    const conflict = Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 3, excluded_model_count: 3 },
    });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('full');

    expect(success).toBe(false);
    expect(showToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.notEmptyWithCount', { count: 3 }, 'warning'
    );
  });

  it('surfaces a busy folder with a staged delete', async () => {
    const busy = Object.assign(new Error('staged delete pending'), { code: 'busy' });
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(busy),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager._deleteFolder('full');

    expect(showToast).toHaveBeenCalledWith('sidebar.deleteFolderResult.busy', {}, 'warning');
  });

  it('drops the removed subtree from the persisted expand state', () => {
    const manager = createManager(createApiClient());
    manager.expandedNodes = new Set(['empty', 'empty/deep', 'other']);
    manager.saveExpandedState = vi.fn();

    manager._forgetRemovedFolder('empty');

    expect([...manager.expandedNodes]).toEqual(['other']);
    expect(manager.saveExpandedState).toHaveBeenCalledTimes(1);
  });

  it('leaves the expand state untouched when nothing matched', () => {
    const manager = createManager(createApiClient());
    manager.expandedNodes = new Set(['other']);
    manager.saveExpandedState = vi.fn();

    manager._forgetRemovedFolder('empty');

    expect([...manager.expandedNodes]).toEqual(['other']);
    expect(manager.saveExpandedState).not.toHaveBeenCalled();
  });

  it('routes the modal buttons to cancel and confirm', () => {
    const manager = createManager(createApiClient());
    manager._deleteFolder = vi.fn().mockResolvedValue(true);
    manager._pendingDeleteFolderRelative = 'empty';
    manager._pendingDeleteFolderPath = '/models/loras/empty';
    manager._wireDeleteFolderModal();

    confirmBtn().dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(modalManager.closeModal).toHaveBeenCalledWith('deleteFolderModal');
    expect(manager._deleteFolder).toHaveBeenCalledWith('empty', '/models/loras/empty');
  });

  it('deletes the directory the node actually lives in, not the default root one', async () => {
    // The reported bug: the node exists under the primary root while
    // default_lora_root points at the extra root, so prefixing the default root
    // produced a path that did not exist and the delete always failed.
    const apiClient = createApiClient({
      fetchModelRoots: vi.fn().mockResolvedValue({
        roots: ['/models/loras', '/models/extra'],
      }),
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'recipes',
        candidates: [{
          folder_path: '/models/loras/recipes',
          root: '/models/loras',
          is_symlink: false,
        }],
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    state.global.settings = { default_lora_root: '/models/extra' };

    await manager.showDeleteFolderModal('recipes');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('confirm');
    expect(apiClient.deleteFolder).toHaveBeenCalledWith(
      '/models/loras/recipes', { dryRun: true }
    );
    // The absolute path is shown, so the modal names the directory it targets.
    expect(modal.querySelector('[data-role="info"]').textContent)
      .toContain('/models/loras/recipes');

    await manager.handleDeleteFolderConfirm();

    expect(apiClient.deleteFolder).toHaveBeenLastCalledWith('/models/loras/recipes');
  });

  it('lists every root holding the folder as a checked row, and deletes only the ticked ones', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'Pony',
        candidates: [
          { folder_path: '/models/extra/Pony', root: '/models/extra', is_symlink: false },
          { folder_path: '/models/loras/Pony', root: '/models/loras', is_symlink: false },
        ],
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    state.global.settings = { default_lora_root: '/models/extra' };

    await manager.showDeleteFolderModal('Pony');

    const modal = document.getElementById('deleteFolderModal');
    const choices = rootChoices();
    expect(choices.map((input) => input.value)).toEqual([
      '/models/extra/Pony',
      '/models/loras/Pony',
    ]);
    // Both copies are selected up front: the node stands for all of them, and
    // deleting it one root at a time was the complaint.
    expect(choices.map((input) => input.checked)).toEqual([true, true]);
    expect(choices.every((input) => input.type === 'checkbox')).toBe(true);
    expect(choices.every((input) => input.disabled === false)).toBe(true);
    expect(confirmBtn().textContent).toContain('2');
    // Each copy carries its own verdict instead of one shared claim.
    expect(modal.querySelectorAll('.folder-root-status')).toHaveLength(2);
    expect([...modal.querySelectorAll('.folder-root-status')].map((el) => el.textContent))
      .toEqual(['no models', 'no models']);
    // The absolute paths live on the rows, so the header does not single one out.
    expect(modal.querySelector('[data-role="info"]').textContent).not.toContain('/models/');
    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/extra/Pony', { dryRun: true });
    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/loras/Pony', { dryRun: true });

    // Unticking one copy keeps the other, and does not rebuild the list.
    const firstRow = choices[0];
    const secondRow = choices[1];
    expect(keptNote().textContent).toBe('');
    choices[1].checked = false;
    choices[1].dispatchEvent(new Event('change', { bubbles: true }));

    expect(rootChoices()[0]).toBe(firstRow);
    expect(rootChoices()[1]).toBe(secondRow);
    expect(rootChoices().map((input) => input.checked)).toEqual([true, false]);
    expect(confirmBtn().textContent).not.toContain('2');
    // The node stays in the sidebar while another root holds the folder, so the
    // modal says so before the user commits.
    expect(keptNote().textContent).toBe('Unchecked copies keep this folder in the sidebar.');

    // Unticking everything just disables the button: the user emptied the
    // selection, the folders are not "blocked".
    choices[0].checked = false;
    choices[0].dispatchEvent(new Event('change', { bubbles: true }));

    expect(confirmBtn().disabled).toBe(true);
    expect(confirmBtn().style.display).toBe('');
    expect(modal.querySelector('[data-role="title"]').textContent).toBe('Delete folder?');

    choices[0].checked = true;
    choices[0].dispatchEvent(new Event('change', { bubbles: true }));
    expect(confirmBtn().disabled).toBe(false);
    // Re-ticking the copy clears the warning again...
    choices[1].checked = true;
    choices[1].dispatchEvent(new Event('change', { bubbles: true }));
    expect(keptNote().textContent).toBe('');
    // ... and the copy is left alone for the rest of the test.
    choices[1].checked = false;
    choices[1].dispatchEvent(new Event('change', { bubbles: true }));

    await manager.handleDeleteFolderConfirm();

    // Real deletes: only the ticked copy, and both dry runs are distinct calls.
    expect(apiClient.deleteFolder).toHaveBeenLastCalledWith('/models/extra/Pony');
    expect(apiClient.deleteFolder).not.toHaveBeenCalledWith('/models/loras/Pony');
    expect(manager.refresh).toHaveBeenCalledTimes(1);
    // A single removed copy keeps the singular wording (no "from 1 roots"), but
    // the toast stays a plain success: the sidebar node's fate is disk truth.
    expect(showActionToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.success',
      { name: 'Pony' },
      'success',
      expect.any(Object)
    );
  });

  it('restores only the deleted copy when a kept copy survives the undo', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'test',
        candidates: [
          { folder_path: '/models/loras/test', root: '/models/loras', is_symlink: false },
          { folder_path: '/models/extra/test', root: '/models/extra', is_symlink: false },
        ],
      }),
      deleteFolder: vi.fn().mockResolvedValue({ success: true, folder: 'test', restorable: true }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager.showDeleteFolderModal('test');
    const choices = rootChoices();
    choices[1].checked = false;
    choices[1].dispatchEvent(new Event('change', { bubbles: true }));

    await manager.handleDeleteFolderConfirm();

    const undo = showActionToast.mock.calls[0][3].onAction;
    await undo();

    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/test');
    expect(apiClient.createFolder).not.toHaveBeenCalledWith('/models/extra/test');
  });

  it('unchecks and explains a copy that still holds models', async () => {
    const conflict = Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 2, excluded_model_count: 0 },
    });
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'Pony',
        candidates: [
          { folder_path: '/models/extra/Pony', root: '/models/extra', is_symlink: false },
          { folder_path: '/models/loras/Pony', root: '/models/loras', is_symlink: false },
        ],
      }),
      deleteFolder: vi.fn((path, options) => (
        path === '/models/loras/Pony' && options?.dryRun
          ? Promise.reject(conflict)
          : Promise.resolve({ success: true, folder: 'Pony', restorable: true })
      )),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager.showDeleteFolderModal('Pony');

    const choices = rootChoices();
    expect(choices.map((input) => input.checked)).toEqual([true, false]);
    expect(choices[1].disabled).toBe(true);
    const statuses = [...document.querySelectorAll('#deleteFolderModal .folder-root-status')];
    expect(statuses[0].textContent).toBe('no models');
    expect(statuses[1].textContent).toContain('2 model file(s)');
    expect(statuses[1].classList.contains('blocked')).toBe(true);
    expect(confirmBtn().disabled).toBe(false);

    await manager.handleDeleteFolderConfirm();

    // The clean copy is deleted; the blocked one is never asked for a real delete.
    expect(apiClient.deleteFolder).toHaveBeenLastCalledWith('/models/extra/Pony');
    expect(apiClient.deleteFolder).not.toHaveBeenCalledWith('/models/loras/Pony');
  });

  it('blocks the whole modal when no copy can be deleted', async () => {
    const conflict = Object.assign(new Error('still contains models'), {
      code: 'not_empty',
      manifest: { model_count: 1, excluded_model_count: 0 },
    });
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'Pony',
        candidates: [
          { folder_path: '/models/extra/Pony', root: '/models/extra', is_symlink: false },
          { folder_path: '/models/loras/Pony', root: '/models/loras', is_symlink: false },
        ],
      }),
      deleteFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);

    await manager.showDeleteFolderModal('Pony');

    const modal = document.getElementById('deleteFolderModal');
    expect(confirmBtn().style.display).toBe('none');
    expect(modal.querySelector('[data-role="title"]').textContent).toBe('Folder is not empty');
    expect(rootChoices().every((input) => input.disabled)).toBe(true);
  });

  it('deletes every ticked copy in one action and restores them all on undo', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'test',
        candidates: [
          { folder_path: '/models/loras/test', root: '/models/loras', is_symlink: false },
          { folder_path: '/models/extra/test', root: '/models/extra', is_symlink: false },
        ],
      }),
      deleteFolder: vi.fn().mockResolvedValue({ success: true, folder: 'test', restorable: true }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager.showDeleteFolderModal('test');
    await manager.handleDeleteFolderConfirm();

    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/loras/test');
    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/extra/test');
    expect(showActionToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.successMulti',
      { name: 'test', count: 2 },
      'success',
      expect.any(Object)
    );

    const undo = showActionToast.mock.calls[0][3].onAction;
    await undo();

    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/loras/test');
    expect(apiClient.createFolder).toHaveBeenCalledWith('/models/extra/test');
  });

  it('reports the copies it managed to delete when one of them fails', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'test',
        candidates: [
          { folder_path: '/models/loras/test', root: '/models/loras', is_symlink: false },
          { folder_path: '/models/extra/test', root: '/models/extra', is_symlink: false },
        ],
      }),
      deleteFolder: vi.fn((path, options) => {
        if (options?.dryRun) return Promise.resolve({ success: true });
        if (path === '/models/extra/test') {
          return Promise.reject(Object.assign(new Error('gone'), { code: 'missing' }));
        }
        return Promise.resolve({ success: true, folder: 'test', restorable: true });
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    await manager.showDeleteFolderModal('test');
    const success = await manager.handleDeleteFolderConfirm();

    expect(success).toBe(true);
    expect(showToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.partial',
      { count: 1, total: 2, failed: 1 },
      'warning'
    );
    expect(manager.refresh).toHaveBeenCalledTimes(1);
  });

  it('reports a stale tree node as missing instead of fabricating a path', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true, folder: 'removed', candidates: [],
      }),
    });
    const manager = createManager(apiClient);
    manager.nonEmptyFolders = new Set(['', 'full']);

    await manager.showDeleteFolderModal('removed');

    const modal = document.getElementById('deleteFolderModal');
    expect(modal.dataset.state).toBe('missing');
    expect(confirmBtn().style.display).toBe('none');
    expect(manager._pendingDeleteFolderPath).toBeNull();
    expect(apiClient.deleteFolder).not.toHaveBeenCalled();
  });

  it('refuses a node whose every copy is a symbolic link', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'linked',
        candidates: [
          { folder_path: '/models/loras/linked', root: '/models/loras', is_symlink: true },
        ],
      }),
    });
    const manager = createManager(apiClient);

    await manager.showDeleteFolderModal('linked');

    expect(document.getElementById('deleteFolderModal').dataset.state).toBe('symlink');
    expect(confirmBtn().style.display).toBe('none');
    expect(apiClient.deleteFolder).not.toHaveBeenCalled();
  });

  it('does not guess a root when the resolver fails on a multi-root library', async () => {
    const apiClient = createApiClient({
      fetchModelRoots: vi.fn().mockResolvedValue({
        roots: ['/models/loras', '/models/extra'],
      }),
      resolveFolder: vi.fn().mockRejectedValue(new Error('boom')),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('Pony');

    expect(success).toBe(false);
    expect(apiClient.deleteFolder).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('sidebar.folderResult.unresolved', {}, 'error');
  });

  it('keeps the single-root fallback for clients without the resolver', async () => {
    const apiClient = createApiClient({ resolveFolder: undefined });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('empty');

    expect(success).toBe(true);
    expect(apiClient.deleteFolder).toHaveBeenCalledWith('/models/loras/empty');
  });

  it('reports a folder that vanished between the check and the confirm', async () => {
    const apiClient = createApiClient({
      deleteFolder: vi.fn().mockRejectedValue(
        Object.assign(new Error('Folder no longer exists'), { code: 'missing' })
      ),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._deleteFolder('empty');

    expect(success).toBe(false);
    expect(showToast).toHaveBeenCalledWith(
      'sidebar.deleteFolderResult.missing', {}, 'warning'
    );
  });

  it('routes the context-menu action to the delete modal', () => {
    const manager = createManager(createApiClient());
    manager.showDeleteFolderModal = vi.fn();

    manager._performFolderAction('delete-folder', 'empty');

    expect(manager.showDeleteFolderModal).toHaveBeenCalledWith('empty');
  });

  it('hides the delete entry when folder management is unsupported', () => {
    document.body.insertAdjacentHTML('beforeend', `
      <div id="sidebarFolderContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="create-subfolder"></div>
        <div class="context-menu-item delete-item" data-action="delete-folder"></div>
      </div>`);
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);

    manager._showFolderContextMenu(10, 10, 'empty');

    const item = document.querySelector('#sidebarFolderContextMenu [data-action="delete-folder"]');
    expect(item.style.display).toBe('none');

    manager._closeFolderContextMenu();
  });
});

describe('SidebarManager folder rename', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = '<div id="sidebarFolderTree"></div>';
    state.global.settings = {};
    vi.clearAllMocks();
  });

  function renameInput() {
    return document.querySelector('#sidebarRenameFolderInput .sidebar-rename-folder-input');
  }

  it('turns the node into a prefilled inline row in tree mode', async () => {
    const manager = createManager(createApiClient());
    manager.treeData = { characters: { anime: {} } };
    manager.renderTree();

    await manager.showRenameFolderInput('characters/anime');

    const row = document.getElementById('sidebarRenameFolderInput');
    expect(row).not.toBeNull();
    expect(renameInput().value).toBe('anime');
    // The node is hidden in place, not removed: the row sits right before it
    const node = document.querySelector('.sidebar-tree-node[data-path="characters/anime"]');
    expect(node.style.display).toBe('none');
    expect(row.nextElementSibling).toBe(node);
    expect(manager._renameFolderPath).toBe('characters/anime');
  });

  it('inserts the row in place in list mode', async () => {
    const manager = createManager(createApiClient(), { displayMode: 'list' });
    manager.foldersList = ['characters', 'characters/anime'];
    manager.renderFolderList();

    await manager.showRenameFolderInput('characters/anime');

    const row = document.getElementById('sidebarRenameFolderInput');
    expect(row.querySelector('.sidebar-node-content')).not.toBeNull();
    const item = document.querySelector('.sidebar-folder-item[data-path="characters/anime"]');
    expect(row.nextElementSibling).toBe(item);
  });

  it('restores the node when the edit is canceled', async () => {
    const manager = createManager(createApiClient());
    manager.treeData = { characters: { anime: {} } };
    manager.renderTree();

    await manager.showRenameFolderInput('characters/anime');
    manager.handleRenameFolderCancel();

    expect(document.getElementById('sidebarRenameFolderInput')).toBeNull();
    expect(manager._renameFolderPath).toBeNull();
    const node = document.querySelector('.sidebar-tree-node[data-path="characters/anime"]');
    expect(node.style.display).toBe('');
  });

  it('renames through the API and re-keys the persisted selection', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    manager.selectedPath = 'characters/anime';
    manager.expandedNodes = new Set(['characters', 'characters/anime']);
    manager.pageControls = { pageState: { activeFolder: 'characters/anime' } };

    const success = await manager._renameFolder('characters/anime', 'animation');

    expect(success).toBe(true);
    expect(apiClient.renameFolder).toHaveBeenCalledWith('/models/loras/characters/anime', 'animation');
    expect(manager.selectedPath).toBe('renamed');
    expect(manager.pageControls.pageState.activeFolder).toBe('renamed');
    expect(getStorageItem('loras_activeFolder')).toBe('renamed');
    expect(manager.refresh).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(
      'sidebar.renameFolderResult.success', { name: 'animation' }, 'success'
    );
  });

  it('re-keys the expanded subtree and the selection', () => {
    const manager = createManager(createApiClient());
    manager.expandedNodes = new Set(['a', 'a/b', 'a/b/c', 'x']);
    manager.selectedPath = 'a/b/c';
    manager.saveExpandedState = vi.fn();

    manager._rekeyFolderPath('a/b', 'a/z');

    expect([...manager.expandedNodes]).toEqual(['a', 'a/z', 'a/z/c', 'x']);
    expect(manager.selectedPath).toBe('a/z/c');
    expect(manager.saveExpandedState).toHaveBeenCalledTimes(1);
  });

  it('submits the inline edit and skips the API for an unchanged name', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    manager.treeData = { characters: { anime: {} } };
    manager.renderTree();

    await manager.showRenameFolderInput('characters/anime');
    renameInput().value = 'anime';
    await manager.handleRenameFolderSubmit();

    expect(apiClient.renameFolder).not.toHaveBeenCalled();
    expect(document.getElementById('sidebarRenameFolderInput')).toBeNull();
  });

  it('rejects invalid names before calling the API', async () => {
    const apiClient = createApiClient();
    const manager = createManager(apiClient);
    manager.treeData = { characters: { anime: {} } };
    manager.renderTree();

    await manager.showRenameFolderInput('characters/anime');
    renameInput().value = 'bad/name';
    await manager.handleRenameFolderSubmit();

    expect(apiClient.renameFolder).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('sidebar.dragDrop.invalidFolderName', {}, 'error');
    // The row stays open so the name can be corrected
    expect(document.getElementById('sidebarRenameFolderInput')).not.toBeNull();
  });

  it('surfaces a name collision', async () => {
    const conflict = Object.assign(new Error('already exists'), { code: 'target_exists' });
    const apiClient = createApiClient({
      renameFolder: vi.fn().mockRejectedValue(conflict),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._renameFolder('characters/anime', 'animation');

    expect(success).toBe(false);
    expect(showToast).toHaveBeenCalledWith('sidebar.renameFolderResult.targetExists', {}, 'warning');
    expect(manager.refresh).not.toHaveBeenCalled();
  });

  it('routes the context-menu action to the inline rename row', () => {
    const manager = createManager(createApiClient());
    manager.showRenameFolderInput = vi.fn();

    manager._performFolderAction('rename-folder', 'characters/anime');

    expect(manager.showRenameFolderInput).toHaveBeenCalledWith('characters/anime');
  });

  it('renames the directory the node actually lives in', async () => {
    // Same trap as the delete flow: the node is under the primary root while
    // the configured default root is another one.
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'recipes',
        candidates: [{
          folder_path: '/models/loras/recipes',
          root: '/models/loras',
          is_symlink: false,
        }],
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    state.global.settings = { default_lora_root: '/models/extra' };

    const success = await manager._renameFolder('recipes', 'presets');

    expect(success).toBe(true);
    expect(apiClient.renameFolder).toHaveBeenCalledWith('/models/loras/recipes', 'presets');
  });

  it('lets the user pick the copy to rename when several roots hold the folder', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true,
        folder: 'Pony',
        candidates: [
          { folder_path: '/models/extra/Pony', root: '/models/extra', is_symlink: false },
          { folder_path: '/models/loras/Pony', root: '/models/loras', is_symlink: false },
        ],
      }),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);
    state.global.settings = { default_lora_root: '/models/extra' };
    manager.treeData = { Pony: {} };
    manager.renderTree();

    await manager.showRenameFolderInput('Pony');

    const picker = document.querySelector('#sidebarRenameFolderInput .sidebar-folder-root-select');
    expect([...picker.options].map((option) => option.value)).toEqual([
      '/models/extra/Pony',
      '/models/loras/Pony',
    ]);
    // The default root's copy is preselected, the other one stays reachable.
    expect(picker.value).toBe('/models/extra/Pony');

    picker.value = '/models/loras/Pony';
    renameInput().value = 'PonyV6';
    await manager.handleRenameFolderSubmit();

    expect(apiClient.renameFolder).toHaveBeenCalledWith('/models/loras/Pony', 'PonyV6');
  });

  it('reports a stale node instead of opening the rename row', async () => {
    const apiClient = createApiClient({
      resolveFolder: vi.fn().mockResolvedValue({
        success: true, folder: 'gone', candidates: [],
      }),
    });
    const manager = createManager(apiClient);
    manager.treeData = { gone: {} };
    manager.renderTree();

    await manager.showRenameFolderInput('gone');

    expect(document.getElementById('sidebarRenameFolderInput')).toBeNull();
    expect(showToast).toHaveBeenCalledWith('sidebar.renameFolderResult.missing', {}, 'warning');
  });

  it('does not guess a root when the resolver fails on a multi-root library', async () => {
    const apiClient = createApiClient({
      fetchModelRoots: vi.fn().mockResolvedValue({
        roots: ['/models/loras', '/models/extra'],
      }),
      resolveFolder: vi.fn().mockRejectedValue(new Error('boom')),
    });
    const manager = createManager(apiClient);
    manager.refresh = vi.fn().mockResolvedValue(undefined);

    const success = await manager._renameFolder('Pony', 'PonyV6');

    expect(success).toBe(false);
    expect(apiClient.renameFolder).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith('sidebar.folderResult.unresolved', {}, 'error');
  });

  it('hides the rename entry when folder management is unsupported', () => {
    document.body.insertAdjacentHTML('beforeend', `
      <div id="sidebarFolderContextMenu" class="context-menu">
        <div class="context-menu-item" data-action="rename-folder"></div>
      </div>`);
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);

    manager._showFolderContextMenu(10, 10, 'empty');

    const item = document.querySelector('#sidebarFolderContextMenu [data-action="rename-folder"]');
    expect(item.style.display).toBe('none');

    manager._closeFolderContextMenu();
  });
});

describe('SidebarManager folder context menu layout', () => {
  // Mirrors templates/components/context_menu.html: the update check on top,
  // the folder operations as one group, delete last behind its own divider.
  const MENU_HTML = `
    <div id="sidebarFolderContextMenu" class="context-menu">
      <div class="context-menu-item" data-action="check-folder-updates"></div>
      <div class="context-menu-separator"></div>
      <div class="context-menu-item" data-action="create-subfolder"></div>
      <div class="context-menu-item" data-action="rename-folder"></div>
      <div class="context-menu-separator"></div>
      <div class="context-menu-item delete-item" data-action="delete-folder"></div>
    </div>`;

  const separators = () => [...document.querySelectorAll('#sidebarFolderContextMenu .context-menu-separator')];
  const item = (action) => document.querySelector(`#sidebarFolderContextMenu [data-action="${action}"]`);
  const visible = (el) => el.style.display !== 'none';

  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = MENU_HTML;
    state.global.settings = {};
    vi.clearAllMocks();
  });

  it('keeps both dividers on a library page', () => {
    const manager = createManager(createApiClient());

    manager._showFolderContextMenu(10, 10, 'empty');

    expect(separators().map(visible)).toEqual([true, true]);
    expect(visible(item('create-subfolder'))).toBe(true);
    expect(visible(item('rename-folder'))).toBe(true);
    expect(visible(item('delete-folder'))).toBe(true);

    manager._closeFolderContextMenu();
  });

  it('collapses both dividers when the page has no folder management', () => {
    const apiClient = createApiClient();
    apiClient.apiConfig.config.supportsFolderManagement = false;
    const manager = createManager(apiClient);

    manager._showFolderContextMenu(10, 10, 'empty');

    expect(visible(item('check-folder-updates'))).toBe(true);
    expect(visible(item('create-subfolder'))).toBe(false);
    expect(visible(item('rename-folder'))).toBe(false);
    expect(visible(item('delete-folder'))).toBe(false);
    // Nothing left to divide: the update check stands alone
    expect(separators().map(visible)).toEqual([false, false]);

    manager._closeFolderContextMenu();
  });

  it('drops leading, trailing and doubled separators', () => {
    document.body.innerHTML = `
      <div id="sidebarFolderContextMenu" class="context-menu">
        <div class="context-menu-separator"></div>
        <div class="context-menu-item" data-action="a"></div>
        <div class="context-menu-separator"></div>
        <div class="context-menu-separator"></div>
        <div class="context-menu-item" data-action="b"></div>
        <div class="context-menu-separator"></div>
      </div>`;
    const manager = createManager(createApiClient());

    manager._updateContextMenuSeparators(document.getElementById('sidebarFolderContextMenu'));

    expect(separators().map(visible)).toEqual([false, true, false, false]);
  });
});

