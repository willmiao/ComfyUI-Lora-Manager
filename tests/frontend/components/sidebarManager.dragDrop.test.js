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
const { state } = await import(STATE_MODULE);

function createManager() {
  const manager = new SidebarManager();
  manager.pageType = 'loras';
  manager.displayMode = 'tree';
  manager.apiClient = { apiConfig: { config: { supportsMove: true } } };
  manager.pageControls = { pageState: { searchOptions: {} } };
  return manager;
}

function buildDom() {
  document.body.innerHTML = `
    <div class="folder-sidebar" id="folderSidebar">
      <div class="sidebar-tree-container">
        <div class="sidebar-tree" id="sidebarFolderTree">
          <div class="sidebar-tree-node" data-path="parent">
            <div class="sidebar-tree-node-content" data-path="parent">
              <div class="sidebar-tree-expand-icon"><i class="fas fa-chevron-right"></i></div>
              <i class="fas fa-folder sidebar-tree-folder-icon"></i>
              <div class="sidebar-tree-folder-name">parent</div>
            </div>
            <div class="sidebar-tree-children">
              <div class="sidebar-tree-node" data-path="parent/child">
                <div class="sidebar-tree-node-content" data-path="parent/child">
                  <div class="sidebar-tree-expand-icon" style="opacity: 0; pointer-events: none;"><i class="fas fa-chevron-right"></i></div>
                  <i class="fas fa-folder sidebar-tree-folder-icon"></i>
                  <div class="sidebar-tree-folder-name">child</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div id="modelGrid">
      <div class="model-card" data-filepath="/models/loras/a.safetensors" data-name="Model A" data-file_name="a.safetensors">
        <div class="card-preview"><img src="/preview/a.png" alt=""></div>
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

describe('SidebarManager drag-and-drop UX', () => {
  beforeEach(() => {
    localStorage.clear();
    buildDom();
    state.bulkMode = false;
    state.selectedModels = new Set();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('replaces the default drag image with a compact chip', () => {
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    const event = createDragEvent(card);

    manager.handleCardDragStart(event);

    expect(event.dataTransfer.setDragImage).toHaveBeenCalledTimes(1);
    const [chip, offsetX, offsetY] = event.dataTransfer.setDragImage.mock.calls[0];
    expect(chip.classList.contains('model-card-drag-chip')).toBe(true);
    // Anchored below-right of the cursor so the chip does not cover the
    // folder row the pointer is aiming at.
    expect(offsetX).toBeLessThan(0);
    expect(offsetY).toBeLessThan(0);
    expect(chip.querySelector('.model-card-drag-chip-thumb')?.src).toContain('/preview/a.png');
    expect(chip.querySelector('.model-card-drag-chip-name')?.textContent).toBe('Model A');
    expect(chip.querySelector('.model-card-drag-chip-count')).toBeNull();
    expect(chip.isConnected).toBe(true);

    manager.handleCardDragEnd({ target: card });
  });

  it('shows a count badge for bulk drags and removes the chip on dragend', () => {
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    card.classList.add('selected');
    state.bulkMode = true;
    state.selectedModels = new Set(['/models/loras/a.safetensors', '/models/loras/b.safetensors']);

    const event = createDragEvent(card);
    manager.handleCardDragStart(event);

    const [chip] = event.dataTransfer.setDragImage.mock.calls[0];
    expect(chip.querySelector('.model-card-drag-chip-count')?.textContent).toBe('×2');

    manager.handleCardDragEnd({ target: card });
    expect(chip.isConnected).toBe(false);
    expect(manager._dragPreviewElement).toBeNull();
  });

  it('uses an icon instead of the thumbnail for blurred previews', () => {
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    card.querySelector('.card-preview').classList.add('blurred');

    const event = createDragEvent(card);
    manager.handleCardDragStart(event);

    const [chip] = event.dataTransfer.setDragImage.mock.calls[0];
    expect(chip.querySelector('.model-card-drag-chip-thumb')).toBeNull();
    expect(chip.querySelector('.model-card-drag-chip-icon')).not.toBeNull();

    manager.handleCardDragEnd({ target: card });
  });

  it('auto-expands a collapsed folder after hovering during a drag', () => {
    vi.useFakeTimers();
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    manager.handleCardDragStart(createDragEvent(card));

    const nodeContent = document.querySelector('.sidebar-tree-node-content[data-path="parent"]');
    manager.handleFolderDragEnter({ ...createDragEvent(nodeContent), dataTransfer: { dropEffect: '' } });

    expect(manager.expandedNodes.has('parent')).toBe(false);

    vi.advanceTimersByTime(700);

    expect(manager.expandedNodes.has('parent')).toBe(true);
    const node = document.querySelector('.sidebar-tree-node[data-path="parent"]');
    expect(node.querySelector(':scope > .sidebar-tree-node-content > .sidebar-tree-expand-icon')
      .classList.contains('expanded')).toBe(true);
    expect(node.querySelector(':scope > .sidebar-tree-children').classList.contains('expanded')).toBe(true);

    manager.handleCardDragEnd({ target: card });
  });

  it('cancels the pending auto-expand when the pointer leaves the folder', () => {
    vi.useFakeTimers();
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    manager.handleCardDragStart(createDragEvent(card));

    const nodeContent = document.querySelector('.sidebar-tree-node-content[data-path="parent"]');
    manager.handleFolderDragEnter({ ...createDragEvent(nodeContent), dataTransfer: { dropEffect: '' } });
    manager.handleFolderDragLeave({
      target: nodeContent,
      relatedTarget: document.getElementById('modelGrid'),
      preventDefault: vi.fn(),
    });

    vi.advanceTimersByTime(700);

    expect(manager.expandedNodes.has('parent')).toBe(false);
    const node = document.querySelector('.sidebar-tree-node[data-path="parent"]');
    expect(node.querySelector(':scope > .sidebar-tree-children').classList.contains('expanded')).toBe(false);

    manager.handleCardDragEnd({ target: card });
  });

  it('does not schedule auto-expand for leaf folders', () => {
    vi.useFakeTimers();
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');
    const card = document.querySelector('.model-card');
    manager.handleCardDragStart(createDragEvent(card));

    const leafContent = document.querySelector('.sidebar-tree-node-content[data-path="parent/child"]');
    manager.handleFolderDragEnter({ ...createDragEvent(leafContent), dataTransfer: { dropEffect: '' } });

    expect(manager._dragExpandTimer).toBeNull();

    manager.handleCardDragEnd({ target: card });
  });

  it('points the auto-scroll direction at the hovered container edge', () => {
    const manager = createManager();
    manager.folderTreeElement = document.getElementById('sidebarFolderTree');

    // jsdom rects are all zeros: a small clientY is "near the top".
    manager._updateAutoScrollDirection(10);
    expect(manager._autoScrollDirection).toBe(-1);

    manager._updateAutoScrollDirection(-10);
    expect(manager._autoScrollDirection).toBe(-1);
  });
});
