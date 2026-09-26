/**
 * SidebarManager - Manages hierarchical folder navigation sidebar
 */
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { translate } from '../utils/i18nHelpers.js';
import { state, getCurrentPageState } from '../state/index.js';
import { bulkManager } from '../managers/BulkManager.js';
import { modalManager } from '../managers/ModalManager.js';
import { showToast, showActionToast } from '../utils/uiHelpers.js';
import { performFolderUpdateCheck } from '../utils/updateCheckHelpers.js';
import { escapeHtml, escapeAttribute } from './shared/utils.js';
import { MODEL_CARD_DRAG_MIME_TYPE } from '../utils/constants.js';

// Pages whose folder sidebar starts hidden. "other" downloads default to a flat
// layout (no subfolders are created), so on a fresh library the tree is empty
// there and the sidebar would only consume horizontal space. The preference is
// still persisted per page once the user toggles it, and the edge indicator
// makes the hidden sidebar discoverable/recoverable.
const SIDEBAR_DEFAULT_HIDDEN_PAGES = new Set(['other']);

export class SidebarManager {
    constructor() {
        this.pageControls = null;
        this.pageType = null;
        this.treeData = {};
        this.folderTreeLoaded = false;
        this.selectedPath = '';
        this.expandedNodes = new Set();
        this.apiClient = null;
        this.openDropdown = null;
        this.isInitialized = false;
        this.displayMode = 'tree'; // 'tree' or 'list'
        this.foldersList = [];
        this.recursiveSearchEnabled = true;
        this.draggedFilePaths = null;
        this.draggedRootPath = null;
        this.draggedFromBulk = false;
        this.dragHandlersInitialized = false;
        this.folderTreeElement = null;
        this.currentDropTarget = null;
        this.lastPageControls = null;
        this.isDisabledByPage = false;
        this.initializationPromise = null;
        this.isCreatingFolder = false;
        this.showEmptyFolders = true;
        this.nonEmptyFolders = null; // models-only folder set used to dim empty nodes
        this.emptyFolderCount = null; // null = not known yet (no models-only list)
        this._createFolderBasePath = null;
        this._createFolderTempChildren = null; // children container added for a leaf parent during inline creation
        this._renameFolderPath = null;
        this._renameFolderNode = null;
        this._pendingDeleteFolderPath = null;
        this._deleteFolderModalWired = false;
        // Bumped on every modal open/close so a late dry-run answer can never
        // repaint a modal the user has already dismissed or retargeted.
        this._deleteFolderProbeToken = 0;

        // Bind methods
        this.handleTreeClick = this.handleTreeClick.bind(this);
        this.handleTreeContextMenu = this.handleTreeContextMenu.bind(this);
        this.handleBreadcrumbClick = this.handleBreadcrumbClick.bind(this);
        this.handleDocumentClick = this.handleDocumentClick.bind(this);
        this.handleSidebarHeaderClick = this.handleSidebarHeaderClick.bind(this);
        this.handleCollapseAll = this.handleCollapseAll.bind(this);
        this.updateContainerMargin = this.updateContainerMargin.bind(this);
        this.handleDisplayModeToggle = this.handleDisplayModeToggle.bind(this);
        this.handleFolderListClick = this.handleFolderListClick.bind(this);
        this.handleRecursiveToggle = this.handleRecursiveToggle.bind(this);
        this.handleEmptyFoldersToggle = this.handleEmptyFoldersToggle.bind(this);
        this.handleCreateFolderButton = this.handleCreateFolderButton.bind(this);
        this.handleViewOptionsButton = this.handleViewOptionsButton.bind(this);
        this.handleCardDragStart = this.handleCardDragStart.bind(this);
        this.handleCardDragEnd = this.handleCardDragEnd.bind(this);
        this.handleFolderDragEnter = this.handleFolderDragEnter.bind(this);
        this.handleFolderDragOver = this.handleFolderDragOver.bind(this);
        this.handleFolderDragLeave = this.handleFolderDragLeave.bind(this);
        this.handleFolderDrop = this.handleFolderDrop.bind(this);
        this.handleCreateFolderSubmit = this.handleCreateFolderSubmit.bind(this);
        this.handleCreateFolderCancel = this.handleCreateFolderCancel.bind(this);
        this.handleHideToggle = this.handleHideToggle.bind(this);
        this.getPageDisplayName = this.getPageDisplayName.bind(this);
    }

    setHostPageControls(pageControls) {
        this.lastPageControls = pageControls;
    }

    async initialize(pageControls, options = {}) {
        // Clean up previous initialization if exists
        if (this.isInitialized) {
            this.cleanup();
        }

        this.pageControls = pageControls;
        this.pageType = pageControls.pageType;
        this.lastPageControls = pageControls;
        this.apiClient = pageControls?.getSidebarApiClient?.()
            || pageControls?.sidebarApiClient
            || getModelApiClient();

        this.setupEventHandlers();
        this.initializeDragAndDrop();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        // Apply DOM visibility based on per-page state
        this.updateDomVisibility();
        await this.loadFolderTree();
        this.restoreSelectedFolder();

        // Update container margin based on initial sidebar state
        this.updateContainerMargin();

        this.isInitialized = true;
        console.log(`SidebarManager initialized for ${this.pageType} page`);
    }

    cleanup() {
        if (!this.isInitialized) return;

        // Clean up event handlers
        this.removeEventHandlers();

        this.clearAllDropHighlights();
        this.resetDragState();
        this.hideCreateFolderInput();
        this.hideRenameFolderInput();

        this.hideSidebarHiddenIndicator();

        // Reset state
        this.pageControls = null;
        this.pageType = null;
        this.treeData = {};
        this.selectedPath = '';
        this.expandedNodes = new Set();
        this.openDropdown = null;
        this.isDisabledByPage = false;
        this.apiClient = null;
        this.isInitialized = false;
        this.recursiveSearchEnabled = true;
        this.showEmptyFolders = true;
        this.nonEmptyFolders = null;
        this.emptyFolderCount = null;
        this._createFolderBasePath = null;
        this._createFolderTempChildren = null;
        this._renameFolderPath = null;
        this._renameFolderNode = null;
        this._pendingDeleteFolderPath = null;

        // Reset container margin
        const container = document.querySelector('.container');
        if (container) {
            container.style.marginLeft = '';
        }

        // Remove resize event listener
        window.removeEventListener('resize', this.updateContainerMargin);

        console.log('SidebarManager cleaned up');
        this.initializationPromise = null;
    }

    removeEventHandlers() {
        const folderTree = document.getElementById('sidebarFolderTree');
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        const sidebarHeader = document.getElementById('sidebarHeader');

        if (folderTree) {
            folderTree.removeEventListener('click', this.handleTreeClick);
            folderTree.removeEventListener('contextmenu', this.handleTreeContextMenu);
            folderTree.removeEventListener('dragover', this.handleFolderDragOver);
        }
        if (sidebarBreadcrumbNav) {
            sidebarBreadcrumbNav.removeEventListener('click', this.handleBreadcrumbClick);
        }
        if (sidebarHeader) {
            sidebarHeader.removeEventListener('click', this.handleSidebarHeaderClick);
        }

        // Remove document click handler
        document.removeEventListener('click', this.handleDocumentClick);

        // Remove resize event handler
        window.removeEventListener('resize', this.updateContainerMargin);

        const viewOptionsBtn = document.getElementById('sidebarViewOptions');
        if (viewOptionsBtn) {
            viewOptionsBtn.removeEventListener('click', this.handleViewOptionsButton);
        }
        this._closeViewOptionsMenu();

        const createFolderBtn = document.getElementById('sidebarCreateFolder');
        if (createFolderBtn) {
            createFolderBtn.removeEventListener('click', this.handleCreateFolderButton);
        }

        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        if (collapseAllBtn) {
            collapseAllBtn.removeEventListener('click', this.handleCollapseAll);
        }

        const hideToggle = document.getElementById('sidebarHideToggle');
        if (hideToggle) {
            hideToggle.removeEventListener('click', this.handleHideToggle);
        }
    }

    initializeDragAndDrop() {
        if (this.apiClient?.apiConfig?.config?.supportsMove === false) {
            return;
        }

        if (!this.dragHandlersInitialized) {
            document.addEventListener('dragstart', this.handleCardDragStart);
            document.addEventListener('dragend', this.handleCardDragEnd);
            this.dragHandlersInitialized = true;
        }

        const folderTree = document.getElementById('sidebarFolderTree');
        if (folderTree && this.folderTreeElement !== folderTree) {
            if (this.folderTreeElement) {
                this.folderTreeElement.removeEventListener('dragenter', this.handleFolderDragEnter);
                this.folderTreeElement.removeEventListener('dragover', this.handleFolderDragOver);
                this.folderTreeElement.removeEventListener('dragleave', this.handleFolderDragLeave);
                this.folderTreeElement.removeEventListener('drop', this.handleFolderDrop);
            }

            folderTree.addEventListener('dragenter', this.handleFolderDragEnter);
            folderTree.addEventListener('dragover', this.handleFolderDragOver);
            folderTree.addEventListener('dragleave', this.handleFolderDragLeave);
            folderTree.addEventListener('drop', this.handleFolderDrop);

            this.folderTreeElement = folderTree;
        }
    }

    handleCardDragStart(event) {
        const card = event.target.closest('.model-card');
        if (!card) return;

        const filePath = card.dataset.filepath;
        if (!filePath) return;

        const selectedSet = state.selectedModels instanceof Set
            ? state.selectedModels
            : new Set(state.selectedModels || []);
        const cardIsSelected = card.classList.contains('selected');
        const usingBulkSelection = Boolean(state.bulkMode && cardIsSelected && selectedSet && selectedSet.size > 0);

        const paths = usingBulkSelection ? Array.from(selectedSet) : [filePath];
        const filePaths = Array.from(new Set(paths.filter(Boolean)));

        if (filePaths.length === 0) {
            return;
        }

        this.draggedFilePaths = filePaths;
        this.draggedRootPath = this.getRootPathFromCard(card);
        this.draggedFromBulk = usingBulkSelection;

        const dataTransfer = event.dataTransfer;
        if (dataTransfer) {
            dataTransfer.effectAllowed = 'move';
            dataTransfer.setData('text/plain', filePaths.join(','));
            // Tag the drag as an internal card drag so preview-drop handlers on
            // other cards ignore it (no highlight, no preview replacement).
            dataTransfer.setData(MODEL_CARD_DRAG_MIME_TYPE, filePaths.join(','));
            try {
                dataTransfer.setData('application/json', JSON.stringify({ filePaths }));
            } catch (error) {
                // Ignore serialization errors
            }
        }

        card.classList.add('dragging');

        // Add dragging state to sidebar for visual feedback
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar) {
            sidebar.classList.add('dragging-active');
        }
    }

    handleCardDragEnd(event) {
        const card = event.target.closest('.model-card');
        if (card) {
            card.classList.remove('dragging');
        }
        
        // Remove dragging state from sidebar
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar) {
            sidebar.classList.remove('dragging-active');
        }

        this.clearAllDropHighlights();
        this.resetDragState();
    }

    getRootPathFromCard(card) {
        if (!card) return null;

        const filePathRaw = card.dataset.filepath || '';
        const normalizedFilePath = filePathRaw.replace(/\\/g, '/');
        const lastSlashIndex = normalizedFilePath.lastIndexOf('/');
        if (lastSlashIndex === -1) {
            return null;
        }

        const directory = normalizedFilePath.substring(0, lastSlashIndex);
        let folderValue = card.dataset.folder;
        if (!folderValue || folderValue === 'undefined') {
            folderValue = '';
        }
        const normalizedFolder = folderValue.replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');

        if (!normalizedFolder) {
            return directory;
        }

        const suffix = `/${normalizedFolder}`;
        if (directory.endsWith(suffix)) {
            return directory.slice(0, -suffix.length);
        }

        return directory;
    }

    combineRootAndRelativePath(root, relative) {
        const normalizedRoot = (root || '').replace(/\\/g, '/').replace(/\/+$/g, '');
        const normalizedRelative = (relative || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');

        if (!normalizedRoot) {
            return normalizedRelative;
        }

        if (!normalizedRelative) {
            return normalizedRoot;
        }

        return `${normalizedRoot}/${normalizedRelative}`;
    }

    getFolderElementFromEvent(event) {
        const folderTree = this.folderTreeElement || document.getElementById('sidebarFolderTree');
        if (!folderTree) return null;

        const target = event.target instanceof Element ? event.target.closest('[data-path]') : null;
        if (!target || !folderTree.contains(target)) {
            return null;
        }

        return target;
    }

    setDropTargetHighlight(element, shouldAdd) {
        if (!element) return;

        let targetElement = element;
        if (!targetElement.classList.contains('sidebar-tree-node-content') &&
            !targetElement.classList.contains('sidebar-node-content')) {
            targetElement = element.querySelector('.sidebar-tree-node-content, .sidebar-node-content');
        }

        if (targetElement) {
            targetElement.classList.toggle('drop-target', shouldAdd);
        }
    }

    handleFolderDragEnter(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (!folderElement) return;

        event.preventDefault();

        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = 'move';
        }

        this.setDropTargetHighlight(folderElement, true);
        this.currentDropTarget = folderElement;
    }

    handleFolderDragOver(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (!folderElement) return;

        event.preventDefault();

        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = 'move';
        }
    }

    handleFolderDragLeave(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (!folderElement) return;

        const relatedTarget = event.relatedTarget instanceof Element ? event.relatedTarget : null;
        if (!relatedTarget || !folderElement.contains(relatedTarget)) {
            this.setDropTargetHighlight(folderElement, false);
            if (this.currentDropTarget === folderElement) {
                this.currentDropTarget = null;
            }
        }
    }

    async handleFolderDrop(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (!folderElement) return;

        event.preventDefault();
        event.stopPropagation();

        this.setDropTargetHighlight(folderElement, false);
        this.currentDropTarget = null;

        const targetPath = folderElement.dataset.path || '';

        await this.performDragMove(targetPath);

        this.resetDragState();
        this.clearAllDropHighlights();
    }

    async performDragMove(targetRelativePath) {
        console.log('[SidebarManager] performDragMove called with targetRelativePath:', targetRelativePath);
        console.log('[SidebarManager] draggedFilePaths:', this.draggedFilePaths);
        console.log('[SidebarManager] draggedRootPath:', this.draggedRootPath);
        
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) {
            console.log('[SidebarManager] performDragMove returning false - no draggedFilePaths');
            return false;
        }

        if (!this.apiClient) {
            this.apiClient = this.pageControls?.getSidebarApiClient?.()
                || this.pageControls?.sidebarApiClient
                || getModelApiClient();
        }

        if (this.apiClient?.apiConfig?.config?.supportsMove === false) {
            console.log('[SidebarManager] performDragMove returning false - supportsMove is false');
            showToast('toast.models.moveFailed', { message: translate('sidebar.dragDrop.moveUnsupported', {}, 'Move not supported for this page') }, 'error');
            return false;
        }

        const rootPath = this.draggedRootPath ? this.draggedRootPath.replace(/\\/g, '/') : '';
        console.log('[SidebarManager] rootPath:', rootPath);
        if (!rootPath) {
            console.log('[SidebarManager] performDragMove returning false - no rootPath');
            showToast(
                'toast.models.moveFailed',
                { message: translate('sidebar.dragDrop.unableToResolveRoot', {}, 'Unable to determine destination path for move.') },
                'error'
            );
            return false;
        }

        const destination = this.combineRootAndRelativePath(rootPath, targetRelativePath);
        const useBulkMove = this.draggedFromBulk || this.draggedFilePaths.length > 1;

        try {
            console.log('[SidebarManager] calling apiClient.move, useBulkMove:', useBulkMove);
            let movedFiles = []; // Array of { original_file_path, new_file_path }

            if (useBulkMove) {
                const results = await this.apiClient.moveBulkModels(this.draggedFilePaths, destination);
                movedFiles = (results || [])
                    .filter(r => r.success)
                    .map(r => ({ original_file_path: r.original_file_path, new_file_path: r.new_file_path }));
            } else {
                const result = await this.apiClient.moveSingleModel(this.draggedFilePaths[0], destination);
                if (result) {
                    movedFiles.push({
                        original_file_path: result.original_file_path || this.draggedFilePaths[0],
                        new_file_path: result.new_file_path
                    });
                }
            }
            console.log('[SidebarManager] apiClient.move successful');

            // Update VirtualScroller in-place instead of full reload
            if (movedFiles.length > 0 && state.virtualScroller) {
                const pageState = getCurrentPageState();
                const normalizedActive = (pageState.activeFolder || '').replace(/\\/g, '/').replace(/\/$/, '');
                const isRecursive = pageState.searchOptions?.recursive ?? true;
                const isFolderFiltered = pageState.activeFolder !== null;

                const normalizedTarget = targetRelativePath.replace(/\\/g, '/').replace(/\/$/, '');

                // Determine if items in the target folder are visible in the current view
                let itemsRemainVisible = true;
                if (isFolderFiltered) {
                    if (isRecursive) {
                        itemsRemainVisible = normalizedActive === '' ||
                            normalizedTarget === normalizedActive ||
                            normalizedTarget.startsWith(normalizedActive + '/');
                    } else {
                        itemsRemainVisible = normalizedTarget === normalizedActive;
                    }
                }

                if (itemsRemainVisible) {
                    // Items stay visible — update each item's file_path to reflect new location
                    for (const moved of movedFiles) {
                        if (moved.original_file_path && moved.new_file_path) {
                            state.virtualScroller.updateSingleItem(moved.original_file_path, {
                                file_path: moved.new_file_path,
                                folder: normalizedTarget
                            });
                        }
                    }
                } else {
                    // Items no longer visible in current folder — remove from VirtualScroller
                    const pathsToRemove = movedFiles
                        .map(m => m.original_file_path)
                        .filter(Boolean);
                    if (pathsToRemove.length > 0) {
                        state.virtualScroller.removeMultipleItemsByFilePath(pathsToRemove);
                    }
                }
            }

            // Refresh sidebar folder tree only (no model data reload)
            await this.refresh();

            if (this.draggedFromBulk && state.bulkMode && typeof bulkManager?.toggleBulkMode === 'function') {
                bulkManager.toggleBulkMode();
            }

            console.log('[SidebarManager] performDragMove returning true');
            return true;
        } catch (error) {
            console.error('[SidebarManager] Error moving model(s) via drag-and-drop:', error);
            showToast('toast.models.moveFailed', { message: error.message || 'Unknown error' }, 'error');
            console.log('[SidebarManager] performDragMove returning false due to error');
            return false;
        }
    }

    resetDragState() {
        this.draggedFilePaths = null;
        this.draggedRootPath = null;
        this.draggedFromBulk = false;
    }

    showCreateFolderInput(basePath = null) {
        // Remove any existing input first — hideCreateFolderInput() also
        // clears isCreatingFolder, so it must run before the flag is set.
        this.hideCreateFolderInput();
        this.isCreatingFolder = true;

        // The folder is created under the given base path; falls back to the
        // currently selected folder or the root.
        this._createFolderBasePath = basePath !== null ? basePath : (this.selectedPath || '');

        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) {
            this.isCreatingFolder = false;
            return;
        }

        // Inline row at the creation location, file-explorer style: the new
        // folder will appear exactly where the input row is shown.
        const row = this._buildCreateFolderRow();
        this._insertCreateFolderRow(folderTree, row);
        row.scrollIntoView?.({ block: 'nearest' });

        const input = row.querySelector('.sidebar-create-folder-input');
        if (!input) return;
        input.focus();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.handleCreateFolderSubmit();
            } else if (e.key === 'Escape') {
                this.handleCreateFolderCancel();
            }
        });
        // Clicking away cancels creation, mirroring file-explorer behavior
        input.addEventListener('blur', () => {
            setTimeout(() => {
                if (this.isCreatingFolder) {
                    this.handleCreateFolderCancel();
                }
            }, 100);
        });
    }

    _buildCreateFolderRow() {
        const isListMode = this.displayMode === 'list';
        const row = document.createElement('div');
        row.id = 'sidebarCreateFolderInput';
        row.className = 'sidebar-create-folder-node';
        row.innerHTML = `
            <div class="${isListMode ? 'sidebar-node-content' : 'sidebar-tree-node-content'} sidebar-create-folder-row">
                ${isListMode ? '' : `
                <div class="sidebar-tree-expand-icon sidebar-create-folder-spacer">
                    <i class="fas fa-chevron-right"></i>
                </div>`}
                <i class="fas fa-folder-plus sidebar-tree-folder-icon"></i>
                <input type="text"
                       class="sidebar-create-folder-input"
                       placeholder="${translate('sidebar.dragDrop.newFolderName', {}, 'New folder name')}" />
            </div>
        `;
        return row;
    }

    _insertCreateFolderRow(folderTree, row) {
        const parentPath = this._createFolderBasePath;

        if (this.displayMode === 'list') {
            if (parentPath) {
                const parentItem = [...folderTree.querySelectorAll('.sidebar-folder-item')]
                    .find(item => item.dataset.path === parentPath);
                if (parentItem) {
                    parentItem.after(row);
                    return;
                }
            }
            folderTree.appendChild(row);
            return;
        }

        if (parentPath) {
            // Expand the parent so the row is visible, then insert as its
            // first child.
            if (!this.expandedNodes.has(parentPath)) {
                this.expandedNodes.add(parentPath);
                this.saveExpandedState();
                this.renderTree();
            }
            const parentNode = [...folderTree.querySelectorAll('.sidebar-tree-node')]
                .find(node => node.dataset.path === parentPath);
            if (parentNode) {
                let children = parentNode.querySelector(':scope > .sidebar-tree-children');
                if (!children) {
                    // Leaf folder: renderTree() only creates a children
                    // container for nodes with subfolders, so add one.
                    children = document.createElement('div');
                    children.className = 'sidebar-tree-children expanded';
                    parentNode.appendChild(children);
                    this._createFolderTempChildren = children;
                }
                children.prepend(row);
                return;
            }
        }

        // Root creation (or parent not currently visible): append at top level
        folderTree.appendChild(row);
    }

    hideCreateFolderInput() {
        // Clear the flag first so the input's blur handler does not treat
        // removing the row as a cancel.
        this.isCreatingFolder = false;

        const row = document.getElementById('sidebarCreateFolderInput');
        if (row) {
            row.remove();
        }

        // Remove the temporary children container if it is still empty
        if (this._createFolderTempChildren) {
            const container = this._createFolderTempChildren;
            this._createFolderTempChildren = null;
            if (container.isConnected && container.children.length === 0) {
                container.remove();
            }
        }
    }

    async handleCreateFolderSubmit() {
        const input = document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input');
        if (!input) {
            return;
        }

        const folderName = input.value.trim();
        if (!folderName) {
            showToast('sidebar.dragDrop.emptyFolderName', {}, 'warning');
            return;
        }

        // Validate folder name (no slashes, no special chars)
        if (/[\\/:*?"<>|]/.test(folderName)) {
            showToast('sidebar.dragDrop.invalidFolderName', {}, 'error');
            return;
        }

        // Build target path - use the base path captured when the input was
        // opened (context-menu folder or current selection), or root
        const parentPath = this._createFolderBasePath || '';
        const targetRelativePath = parentPath ? `${parentPath}/${folderName}` : folderName;

        this.hideCreateFolderInput();

        await this._createFolder(targetRelativePath, parentPath);
    }

    async _createFolder(targetRelativePath, parentPath) {
        if (!this._supportsFolderManagement() || typeof this.apiClient.createFolder !== 'function') {
            showToast('sidebar.createFolderResult.unsupported', {}, 'error');
            return false;
        }

        try {
            const rootsData = await this.apiClient.fetchModelRoots();
            const roots = rootsData?.roots || [];
            const root = this._resolveDefaultRoot(roots);
            if (!root) {
                showToast('sidebar.createFolderResult.noRoot', {}, 'error');
                return false;
            }

            const absolutePath = this.combineRootAndRelativePath(root, targetRelativePath);
            const result = await this.apiClient.createFolder(absolutePath);

            // A newly created folder is empty by definition. If the user turned
            // empty-folder display off, switch it back on so the folder they
            // just asked for is actually visible in the tree.
            if (!this.showEmptyFolders) {
                this.showEmptyFolders = true;
                setStorageItem(`${this.pageType}_showEmptyFolders`, true);
                this.updateViewOptionsMenu();
            }

            // Expand the parent folder to reveal the new node
            if (parentPath) {
                this.expandedNodes.add(parentPath);
                this.saveExpandedState();
            }

            await this.refresh();

            showToast('sidebar.createFolderResult.success', { name: result.folder || targetRelativePath }, 'success');
            return true;
        } catch (error) {
            console.error('[SidebarManager] Error creating folder:', error);
            showToast('sidebar.createFolderResult.failed', { message: error.message || 'Unknown error' }, 'error');
            return false;
        }
    }

    _resolveDefaultRoot(roots) {
        if (!roots || roots.length === 0) {
            return '';
        }

        const singularName = this.apiClient?.apiConfig?.config?.singularName;
        const defaultRoot = singularName
            ? state.global?.settings?.[`default_${singularName}_root`]
            : '';
        if (defaultRoot && roots.includes(defaultRoot)) {
            return defaultRoot;
        }

        return roots[0];
    }

    handleCreateFolderCancel() {
        this.hideCreateFolderInput();
    }

    // ===== Folder rename (inline row, file-explorer style) =====

    /**
     * Turn the folder node at *path* into an editable row.
     *
     * Mirrors the create-folder inline row (Enter confirms, Escape/blur
     * cancels) but is inserted where the node sits and hides that node while
     * editing, so the tree does not jump.
     */
    showRenameFolderInput(path) {
        if (!path) return;

        this.hideRenameFolderInput();

        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        const node = this._findFolderNodeElement(folderTree, path);
        if (!node) return;

        const row = this._buildRenameFolderRow(this._folderLeafName(path));
        node.parentElement.insertBefore(row, node);
        node.style.display = 'none';

        this._renameFolderNode = node;
        this._renameFolderPath = path;

        const input = row.querySelector('.sidebar-rename-folder-input');
        if (!input) return;
        input.focus();
        input.select();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                this.handleRenameFolderSubmit();
            } else if (e.key === 'Escape') {
                this.handleRenameFolderCancel();
            }
        });
        // Clicking away cancels, mirroring the create-folder row
        input.addEventListener('blur', () => {
            setTimeout(() => {
                if (this._renameFolderPath) {
                    this.handleRenameFolderCancel();
                }
            }, 100);
        });
    }

    _buildRenameFolderRow(currentName) {
        const isListMode = this.displayMode === 'list';
        const row = document.createElement('div');
        row.id = 'sidebarRenameFolderInput';
        row.className = 'sidebar-create-folder-node sidebar-rename-folder-node';
        row.innerHTML = `
            <div class="${isListMode ? 'sidebar-node-content' : 'sidebar-tree-node-content'} sidebar-create-folder-row">
                ${isListMode ? '' : `
                <div class="sidebar-tree-expand-icon sidebar-create-folder-spacer">
                    <i class="fas fa-chevron-right"></i>
                </div>`}
                <i class="fas fa-i-cursor sidebar-tree-folder-icon"></i>
                <input type="text"
                       class="sidebar-create-folder-input sidebar-rename-folder-input"
                       aria-label="${escapeAttribute(translate('sidebar.renameFolder', {}, 'Rename folder'))}"
                       value="${escapeAttribute(currentName)}" />
            </div>
        `;
        return row;
    }

    _findFolderNodeElement(folderTree, path) {
        return [...folderTree.querySelectorAll('.sidebar-tree-node, .sidebar-folder-item')]
            .find(element => element.dataset.path === path) || null;
    }

    _folderLeafName(path) {
        if (!path) return '';
        const index = path.lastIndexOf('/');
        return index === -1 ? path : path.slice(index + 1);
    }

    hideRenameFolderInput() {
        // Clear the flag first so the input's blur handler does not treat
        // removing the row as a cancel.
        this._renameFolderPath = null;

        const row = document.getElementById('sidebarRenameFolderInput');
        if (row) {
            row.remove();
        }

        const node = this._renameFolderNode;
        this._renameFolderNode = null;
        if (node && node.isConnected) {
            node.style.display = '';
        }
    }

    handleRenameFolderCancel() {
        this.hideRenameFolderInput();
    }

    async handleRenameFolderSubmit() {
        const input = document.querySelector('#sidebarRenameFolderInput .sidebar-rename-folder-input');
        const path = this._renameFolderPath;
        if (!input || !path) {
            return;
        }

        const newName = input.value.trim();
        if (!newName) {
            showToast('sidebar.dragDrop.emptyFolderName', {}, 'warning');
            return;
        }

        if (/[\\/:*?"<>|]/.test(newName)) {
            showToast('sidebar.dragDrop.invalidFolderName', {}, 'error');
            return;
        }

        this.hideRenameFolderInput();

        if (newName === this._folderLeafName(path)) {
            return;
        }

        await this._renameFolder(path, newName);
    }

    async _renameFolder(relativePath, newName) {
        if (!this._supportsFolderManagement() || typeof this.apiClient.renameFolder !== 'function') {
            showToast('sidebar.renameFolderResult.unsupported', {}, 'error');
            return false;
        }

        try {
            const rootsData = await this.apiClient.fetchModelRoots();
            const roots = rootsData?.roots || [];
            const root = this._resolveDefaultRoot(roots);
            if (!root) {
                showToast('sidebar.renameFolderResult.noRoot', {}, 'error');
                return false;
            }

            const absolutePath = this.combineRootAndRelativePath(root, relativePath);
            const result = await this.apiClient.renameFolder(absolutePath, newName);

            // Carry the user's place across the rename: the persisted
            // selection and the expanded set would otherwise point at a folder
            // the refreshed tree no longer contains.
            const newPath = result.folder || this._siblingFolderPath(relativePath, newName);
            this._rekeyFolderPath(relativePath, newPath);

            await this.refresh();

            showToast('sidebar.renameFolderResult.success', { name: newName }, 'success');
            return true;
        } catch (error) {
            console.error('[SidebarManager] Error renaming folder:', error);
            if (error?.code === 'target_exists') {
                showToast('sidebar.renameFolderResult.targetExists', {}, 'warning');
            } else if (error?.code === 'busy') {
                showToast('sidebar.renameFolderResult.busy', {}, 'warning');
            } else {
                showToast(
                    'sidebar.renameFolderResult.failed',
                    { message: error?.message || 'Unknown error' },
                    'error'
                );
            }
            return false;
        }
    }

    _siblingFolderPath(relativePath, newName) {
        const index = relativePath.lastIndexOf('/');
        const parent = index === -1 ? '' : relativePath.slice(0, index);
        return parent ? `${parent}/${newName}` : newName;
    }

    _rekeyFolderPath(previousPath, newPath) {
        if (!previousPath || !newPath || previousPath === newPath) return;

        const prefix = `${previousPath}/`;
        const newPrefix = `${newPath}/`;
        const rekey = (value) => {
            if (value === previousPath) return newPath;
            if (value.startsWith(prefix)) return newPrefix + value.slice(prefix.length);
            return value;
        };

        if (this.expandedNodes.size > 0) {
            this.expandedNodes = new Set([...this.expandedNodes].map(rekey));
            this.saveExpandedState();
        }

        if (this.selectedPath) {
            const rekeyed = rekey(this.selectedPath);
            if (rekeyed !== this.selectedPath) {
                this.selectedPath = rekeyed;
                if (this.pageControls?.pageState) {
                    this.pageControls.pageState.activeFolder = rekeyed;
                }
                setStorageItem(`${this.pageType}_activeFolder`, rekeyed);
            }
        }
    }

    /**
     * Open the folder delete modal for *path*.
     *
     * The models-only set that dims empty nodes is only a prediction: it is
     * built from the scanned, non-excluded models, while the delete guard walks
     * the folder on disk and refuses on any weight file — excluded ones
     * included. So the modal opens on the prediction for an instant answer and
     * is then corrected by a dry run of the very delete the user is about to
     * confirm, which is the only way the button can never contradict the
     * backend (see `_verifyFolderContents`).
     */
    async showDeleteFolderModal(path) {
        const modal = document.getElementById('deleteFolderModal');
        if (!modal) return;

        // Defensive: the modal may have been absent when listeners were wired.
        this._wireDeleteFolderModal();

        // Opening the modal — or targeting another folder — retires any
        // in-flight check from a previous open.
        const token = ++this._deleteFolderProbeToken;

        const holdsModels = this.nonEmptyFolders ? this.nonEmptyFolders.has(path) : false;
        const prediction = holdsModels
            ? {
                state: 'blocked',
                messageKey: 'sidebar.deleteFolderModal.notEmptyMessage',
                messageFallback: 'This folder still contains models. Delete or move them first.',
            }
            : { state: 'confirm' };

        const probePending = this._supportsFolderManagement()
            && typeof this.apiClient.deleteFolder === 'function';

        this._renderDeleteFolderModal(path, prediction.state, {
            ...prediction,
            checking: probePending,
        });

        modalManager.showModal('deleteFolderModal');

        if (!probePending) return;

        await this._verifyFolderContents(path, token, prediction);
    }

    /**
     * Paint one state of the folder delete modal.
     *
     * `state` is 'confirm' (deletion may proceed), 'blocked' (models would be
     * cascaded over, which the backend refuses) or 'busy' (a staged delete is
     * still pending inside the folder). `checking` keeps the confirm button
     * disabled while the authoritative server-side check runs.
     */
    _renderDeleteFolderModal(path, state, options = {}) {
        const modal = document.getElementById('deleteFolderModal');
        if (!modal) return;

        const title = modal.querySelector('[data-role="title"]');
        const message = modal.querySelector('[data-role="message"]');
        const info = modal.querySelector('[data-role="info"]');
        const confirmBtn = modal.querySelector('[data-action="confirm-delete-folder"]');
        const checking = Boolean(options.checking);

        const pathLine = `<strong>${escapeHtml(translate('sidebar.deleteFolderModal.folderLabel', {}, 'Folder'))}:</strong> ${escapeHtml(path)}`;
        const extraLines = [];

        if (state === 'confirm') {
            this._pendingDeleteFolderPath = path;
            title.textContent = translate(
                'sidebar.deleteFolderModal.title', {}, 'Delete folder?'
            );
            message.textContent = translate(
                'sidebar.deleteFolderModal.message', {},
                'The folder and everything inside it will be permanently removed from disk.'
            );
            if (!checking) {
                // While the check runs the "no models" claim is still only the
                // sidebar's prediction, so it is not repeated as a fact.
                extraLines.push(escapeHtml(translate(
                    'sidebar.deleteFolderModal.emptyNote', {}, 'This folder contains no models.'
                )));
            }
            confirmBtn.style.display = '';
            confirmBtn.disabled = checking;
        } else {
            this._pendingDeleteFolderPath = null;
            if (state === 'busy') {
                title.textContent = translate(
                    'sidebar.deleteFolderModal.busyTitle', {}, 'A deletion is still pending'
                );
                message.textContent = translate(
                    'sidebar.deleteFolderResult.busy', {},
                    'A deletion is still pending inside this folder. Wait for the undo window to expire.'
                );
            } else {
                title.textContent = translate(
                    'sidebar.deleteFolderModal.notEmptyTitle', {}, 'Folder is not empty'
                );
                message.textContent = translate(
                    options.messageKey || 'sidebar.deleteFolderModal.notEmptyMessage',
                    options.messageParams || {},
                    options.messageFallback
                        || 'This folder still contains models. Delete or move them first.'
                );
            }
            confirmBtn.style.display = 'none';
            confirmBtn.disabled = true;
        }

        if (checking) {
            extraLines.push(escapeHtml(translate(
                'sidebar.deleteFolderModal.checking', {}, 'Checking the folder contents...'
            )));
        }

        info.innerHTML = [pathLine, ...extraLines].join('<br>');
        modal.dataset.state = state;
    }

    /**
     * Ask the backend what deleting *relativePath* would actually remove.
     *
     * The dry run is authoritative: it walks the folder on disk and applies the
     * same guard the real delete uses, so it catches everything the sidebar
     * prediction cannot know — excluded models, weight files no scanner indexes
     * (a lora folder holding only a `.gguf`, say) and files added after the
     * last scan. A check that fails for any other reason falls back to the
     * prediction, leaving the real delete to report its own error.
     */
    async _verifyFolderContents(relativePath, token, prediction) {
        let resolved = null;
        try {
            resolved = await this._resolveFolderAbsolutePath(relativePath);
        } catch (error) {
            console.error('[SidebarManager] Failed to resolve the folder path:', error);
        }

        if (token !== this._deleteFolderProbeToken) return;

        if (!resolved) {
            this._renderDeleteFolderModal(relativePath, prediction.state, prediction);
            return;
        }

        try {
            await this.apiClient.deleteFolder(resolved.absolutePath, { dryRun: true });
            if (token !== this._deleteFolderProbeToken) return;
            this._renderDeleteFolderModal(relativePath, 'confirm');
        } catch (error) {
            if (token !== this._deleteFolderProbeToken) return;
            if (error?.code === 'not_empty') {
                this._renderDeleteFolderModal(
                    relativePath, 'blocked', this._notEmptyBlocker(error?.manifest)
                );
            } else if (error?.code === 'busy') {
                this._renderDeleteFolderModal(relativePath, 'busy');
            } else {
                this._renderDeleteFolderModal(relativePath, prediction.state, prediction);
            }
        }
    }

    /**
     * Message for a refused delete, split by whether the blocking models are
     * excluded from the library — the case where the sidebar legitimately shows
     * the folder as empty, which is exactly what used to be unexplained.
     */
    _notEmptyBlocker(manifest) {
        const modelCount = Number(manifest?.model_count) || 0;
        const excludedCount = Number(manifest?.excluded_model_count) || 0;

        if (modelCount > 0 && excludedCount > 0) {
            return {
                messageKey: 'sidebar.deleteFolderModal.notEmptyMessageExcluded',
                messageParams: { count: modelCount, excluded: excludedCount },
                messageFallback: `This folder still contains ${modelCount} model file(s), `
                    + `${excludedCount} of them excluded from the library. Un-exclude and `
                    + 'delete them first — deleting a folder never cascades over model files.',
            };
        }
        if (modelCount > 0) {
            return {
                messageKey: 'sidebar.deleteFolderModal.notEmptyMessageCount',
                messageParams: { count: modelCount },
                messageFallback: `This folder still contains ${modelCount} model file(s). `
                    + 'Delete or move them first — deleting a folder never cascades over model files.',
            };
        }
        return {
            messageKey: 'sidebar.deleteFolderModal.notEmptyMessage',
            messageFallback: 'This folder still contains models. Delete or move them first.',
        };
    }

    /**
     * Resolve a tree-relative folder path to the absolute business path the
     * folder APIs expect, or null when no model root is configured.
     */
    async _resolveFolderAbsolutePath(relativePath) {
        const rootsData = await this.apiClient.fetchModelRoots();
        const roots = rootsData?.roots || [];
        const root = this._resolveDefaultRoot(roots);
        if (!root) return null;

        return {
            root,
            absolutePath: this.combineRootAndRelativePath(root, relativePath),
        };
    }

    hideDeleteFolderModal() {
        this._pendingDeleteFolderPath = null;
        // Retire any in-flight check so a late answer cannot repaint a modal
        // the user already dismissed.
        this._deleteFolderProbeToken += 1;
        modalManager.closeModal('deleteFolderModal');
    }

    async handleDeleteFolderConfirm() {
        const path = this._pendingDeleteFolderPath;
        this.hideDeleteFolderModal();

        if (!path) return false;

        return this._deleteFolder(path);
    }

    async _deleteFolder(relativePath) {
        if (!this._supportsFolderManagement() || typeof this.apiClient.deleteFolder !== 'function') {
            showToast('sidebar.deleteFolderResult.unsupported', {}, 'error');
            return false;
        }

        try {
            const resolved = await this._resolveFolderAbsolutePath(relativePath);
            if (!resolved) {
                showToast('sidebar.deleteFolderResult.noRoot', {}, 'error');
                return false;
            }

            const result = await this.apiClient.deleteFolder(resolved.absolutePath);

            // Drop the node (and its subtree) from the persisted expand state
            // before refreshing, otherwise stale keys accumulate forever. A
            // selection inside the removed subtree is left to
            // restoreSelectedFolder(), which falls back to the root and
            // reloads the grid when the folder is gone from the fresh tree.
            this._forgetRemovedFolder(relativePath);

            await this.refresh();

            const name = result.folder || relativePath;
            if (result.restorable) {
                // A truly empty folder is reproducible one-for-one, so offer
                // the same 20s undo affordance the model delete flow uses.
                showActionToast('sidebar.deleteFolderResult.success', { name }, 'success', {
                    actionText: translate('toast.undo.action', {}, 'Undo'),
                    onAction: () => this._restoreDeletedFolder(resolved.absolutePath, relativePath),
                });
            } else {
                showToast(
                    'sidebar.deleteFolderResult.successWithFiles',
                    { name, count: (result.file_count || 0) + (result.dir_count || 0) },
                    'success'
                );
            }

            return true;
        } catch (error) {
            console.error('[SidebarManager] Error deleting folder:', error);
            if (error?.code === 'not_empty') {
                // The dry run normally catches this before the user can
                // confirm; reaching here means the folder changed in between.
                const modelCount = Number(error?.manifest?.model_count) || 0;
                if (modelCount > 0) {
                    showToast(
                        'sidebar.deleteFolderResult.notEmptyWithCount',
                        { count: modelCount },
                        'warning'
                    );
                } else {
                    showToast('sidebar.deleteFolderResult.notEmpty', {}, 'warning');
                }
            } else if (error?.code === 'busy') {
                showToast('sidebar.deleteFolderResult.busy', {}, 'warning');
            } else {
                showToast(
                    'sidebar.deleteFolderResult.failed',
                    { message: error?.message || 'Unknown error' },
                    'error'
                );
            }
            return false;
        }
    }

    async _restoreDeletedFolder(absolutePath, relativePath) {
        try {
            await this.apiClient.createFolder(absolutePath);
            this._forgetRemovedFolder(relativePath);
            await this.refresh();
            showToast('sidebar.deleteFolderResult.restored', {}, 'success');
            return true;
        } catch (error) {
            console.error('[SidebarManager] Error restoring deleted folder:', error);
            showToast('toast.undo.failed', { error: error?.message || '' }, 'error');
            return false;
        }
    }

    _forgetRemovedFolder(folderPath) {
        if (!folderPath) return;

        const prefix = `${folderPath}/`;
        let changed = false;
        for (const node of Array.from(this.expandedNodes)) {
            if (node === folderPath || node.startsWith(prefix)) {
                this.expandedNodes.delete(node);
                changed = true;
            }
        }
        if (changed) {
            this.saveExpandedState();
        }
    }

    _wireDeleteFolderModal() {
        if (this._deleteFolderModalWired) return;

        const modal = document.getElementById('deleteFolderModal');
        if (!modal) return;

        modal.addEventListener('click', (event) => {
            const item = event.target.closest('[data-action]');
            if (!item) return;
            const action = item.dataset.action;
            if (action === 'cancel-delete-folder') {
                this.hideDeleteFolderModal();
            } else if (action === 'confirm-delete-folder') {
                this.handleDeleteFolderConfirm();
            }
        });

        this._deleteFolderModalWired = true;
    }

    saveSelectedFolder() {
        setStorageItem(`${this.pageType}_activeFolder`, this.selectedPath);
    }

    clearAllDropHighlights() {
        const highlighted = document.querySelectorAll('.sidebar-tree-node-content.drop-target, .sidebar-node-content.drop-target');
        highlighted.forEach((element) => element.classList.remove('drop-target'));
        this.currentDropTarget = null;
    }

    updateSidebarTitle() {
        const sidebarTitle = document.getElementById('sidebarTitle');
        if (sidebarTitle) {
            sidebarTitle.textContent = translate('sidebar.modelRoot');
        }
    }

    setupEventHandlers() {
        // Sidebar header (root selection) - only trigger on title area
        const sidebarHeader = document.getElementById('sidebarHeader');
        if (sidebarHeader) {
            sidebarHeader.addEventListener('click', this.handleSidebarHeaderClick);
        }

        // View options menu button
        const viewOptionsBtn = document.getElementById('sidebarViewOptions');
        if (viewOptionsBtn) {
            viewOptionsBtn.addEventListener('click', this.handleViewOptionsButton);
        }

        // View options menu items
        const viewOptionsMenu = document.getElementById('sidebarViewOptionsMenu');
        if (viewOptionsMenu) {
            viewOptionsMenu.addEventListener('click', (e) => {
                const item = e.target.closest('.context-menu-item');
                if (!item || item.classList.contains('disabled')) return;
                const action = item.dataset.action;
                if (action) {
                    this.handleViewOptionsAction(action);
                }
            });
        }

        // Create folder button
        const createFolderBtn = document.getElementById('sidebarCreateFolder');
        if (createFolderBtn) {
            createFolderBtn.addEventListener('click', this.handleCreateFolderButton);
        }

        // Collapse all button
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        if (collapseAllBtn) {
            collapseAllBtn.addEventListener('click', this.handleCollapseAll);
        }

        // Tree click handler
        const folderTree = document.getElementById('sidebarFolderTree');
        if (folderTree) {
            folderTree.addEventListener('click', this.handleTreeClick);
            folderTree.addEventListener('contextmenu', this.handleTreeContextMenu);
        }

        // Breadcrumb click handler
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        if (sidebarBreadcrumbNav) {
            sidebarBreadcrumbNav.addEventListener('click', this.handleBreadcrumbClick);
        }

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024) {
                const sidebar = document.getElementById('folderSidebar');
                if (sidebar && !sidebar.contains(e.target) && !this.isDisabledByPage) {
                    sidebar.classList.remove('visible');
                }
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            this.updateContainerMargin();
        });

        // Add document click handler for closing dropdowns
        document.addEventListener('click', this.handleDocumentClick);

        // Add dedicated resize listener for container margin updates
        window.addEventListener('resize', this.updateContainerMargin);

        // Sidebar folder context menu click handler
        const sidebarFolderMenu = document.getElementById('sidebarFolderContextMenu');
        if (sidebarFolderMenu) {
            sidebarFolderMenu.addEventListener('click', (e) => {
                const item = e.target.closest('.context-menu-item');
                if (!item) return;
                const action = item.dataset.action;
                if (action) {
                    this.handleFolderContextMenuAction(action);
                }
            });
        }

        // Dedicated hide sidebar button
        const hideToggle = document.getElementById('sidebarHideToggle');
        if (hideToggle) {
            hideToggle.addEventListener('click', this.handleHideToggle);
        }

        // Folder delete confirmation modal buttons
        this._wireDeleteFolderModal();
    }

    handleDocumentClick(event) {
        // Close open dropdown when clicking outside
        if (this.openDropdown && !event.target.closest('.breadcrumb-dropdown')) {
            this.closeDropdown();
        }
    }

    handleSidebarHeaderClick(event) {
        // Only trigger root selection if clicking on the title area, not the buttons
        if (!event.target.closest('.sidebar-header-actions')) {
            this.selectFolder(null);
        }
    }

    handleHideToggle(event) {
        event.stopPropagation();
        this.toggleHideOnThisPage();
    }

    handleCollapseAll(event) {
        event?.stopPropagation();
        this.expandedNodes.clear();
        this.renderFolderDisplay();
        this.saveExpandedState();
    }

    // ===== Sidebar visibility (per-page) and container margin =====

    updateContainerMargin() {
        const container = document.querySelector('.container');
        const sidebar = document.getElementById('folderSidebar');

        if (!container || !sidebar) return;

        // Always reset margin first — needed when transitioning from visible to hidden
        container.style.marginLeft = '';

        // When per-page disabled, skip adjustment but margin is already reset
        if (this.isDisabledByPage) return;

        // Sidebar is visible — adjust margin if we need room
        const sidebarWidth = sidebar.offsetWidth;
        const viewportWidth = window.innerWidth;
        const containerWidth = container.offsetWidth;

        if (sidebarWidth + containerWidth + sidebarWidth > viewportWidth) {
            container.style.marginLeft = `${sidebarWidth + 10}px`;
        }
    }

    updateDomVisibility() {
        const isHidden = this.isDisabledByPage;
        const sidebar = document.getElementById('folderSidebar');

        if (sidebar) {
            sidebar.classList.toggle('visible', !isHidden);
            sidebar.classList.toggle('hidden-by-setting', isHidden);
            sidebar.setAttribute('aria-hidden', isHidden.toString());
        }

        // Show or hide the "sidebar hidden" edge indicator
        if (isHidden) {
            this.showSidebarHiddenIndicator();
        } else {
            this.hideSidebarHiddenIndicator();
        }
    }


    toggleHideOnThisPage() {
        this.isDisabledByPage = !this.isDisabledByPage;
        setStorageItem(`${this.pageType}_sidebarDisabled`, this.isDisabledByPage);
        this.updateDomVisibility();
        this.updateContainerMargin();
    }

    getPageDisplayName() {
        const names = {
            loras: 'LoRAs',
            recipes: 'Recipes',
            checkpoints: 'Checkpoints',
            embeddings: 'Embeddings',
            other: 'Other Models',
        };
        return names[this.pageType] || this.pageType;
    }

    showSidebarHiddenIndicator() {
        if (document.getElementById('sidebarHiddenIndicator')) return;

        const indicator = document.createElement('div');
        indicator.id = 'sidebarHiddenIndicator';
        indicator.className = 'sidebar-hidden-indicator';
        indicator.innerHTML = `
            <i class="fas fa-chevron-right"></i>
            <span class="sidebar-hidden-indicator-tooltip">${translate('sidebar.showSidebar')}</span>
        `;

        // Subtle breathing animation on first sight to aid discoverability;
        // stops permanently after user clicks the restore button once
        const restoreKey = `${this.pageType}_restoreButtonUsed`;
        if (!getStorageItem(restoreKey, false)) {
            indicator.classList.add('breathing');
        }

        indicator.addEventListener('click', () => {
            setStorageItem(restoreKey, true);
            this.toggleHideOnThisPage();
        });

        document.body.appendChild(indicator);
    }

    hideSidebarHiddenIndicator() {
        const indicator = document.getElementById('sidebarHiddenIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    async loadFolderTree() {
        try {
            const supportsEmptyFolders = this._supportsFolderManagement();
            // The full folder list (including empty directories) and the
            // models-only list are both always fetched: the first is the
            // single source of truth for the tree and for the empty-folder
            // count, the second is what "empty" is measured against. The
            // `showEmptyFolders` preference only gates rendering, so the
            // view-options menu can report the count (and hide the toggle
            // when there are none) while empty folders stay hidden.
            if (this.displayMode === 'tree') {
                const [treeResponse, foldersResponse] = await Promise.all([
                    supportsEmptyFolders
                        ? this.apiClient.fetchUnifiedFolderTree({ includeEmpty: true })
                        : this.apiClient.fetchUnifiedFolderTree(),
                    supportsEmptyFolders ? this.apiClient.fetchModelFolders() : Promise.resolve(null),
                ]);
                this.treeData = treeResponse.tree || {};
                this.nonEmptyFolders = foldersResponse
                    ? this._buildNonEmptyFolderSet(foldersResponse.folders || [])
                    : null;
                this.emptyFolderCount = this._computeEmptyFolderCount();
            } else {
                const [allFoldersResponse, foldersResponse] = await Promise.all([
                    this.apiClient.fetchModelFolders(
                        supportsEmptyFolders ? { includeEmpty: true } : undefined
                    ),
                    supportsEmptyFolders ? this.apiClient.fetchModelFolders() : Promise.resolve(null),
                ]);
                this.foldersList = allFoldersResponse.folders || [];
                this.nonEmptyFolders = foldersResponse
                    ? this._buildNonEmptyFolderSet(foldersResponse.folders || [])
                    : null;
                this.emptyFolderCount = this._computeEmptyFolderCount();
            }
            this.folderTreeLoaded = true;
            this.renderFolderDisplay();
        } catch (error) {
            this.folderTreeLoaded = false;
            this.emptyFolderCount = null;
            console.error('Failed to load folder data:', error);
            this.renderEmptyState();
        }
    }

    _supportsFolderManagement() {
        return Boolean(this.apiClient?.apiConfig?.config?.supportsFolderManagement);
    }

    // The models-only folder list only contains directories that directly
    // hold model files. Expand it with every ancestor prefix so a folder
    // whose subtree contains models (e.g. "a" with models in "a/b") is not
    // dimmed as empty — the "empty" style means "no models anywhere below".
    _buildNonEmptyFolderSet(folders) {
        const set = new Set();
        for (const folder of folders) {
            set.add(folder);
            if (!folder) continue;
            const parts = folder.split('/');
            for (let i = 1; i < parts.length; i++) {
                set.add(parts.slice(0, i).join('/'));
            }
        }
        return set;
    }

    /**
     * Whether a folder should render in the dimmed "empty" style.
     *
     * The full folder list is always loaded so the empty-folder count is
     * available, but the dimmed styling (like the folders themselves) is only
     * shown while the show-empty-folders preference is on.
     */
    _isRenderedEmptyFolder(path) {
        if (!this.showEmptyFolders || !this.nonEmptyFolders) return false;
        return !this.nonEmptyFolders.has(path);
    }

    // Apply the show-empty-folders preference to the flat folder list. When
    // the models-only set is unknown the list is passed through unchanged, so
    // the filter can never hide everything.
    _filterVisibleFolders(folders) {
        const list = folders || [];
        if (this.showEmptyFolders || !this.nonEmptyFolders) return list;
        return list.filter((folder) => !folder || this.nonEmptyFolders.has(folder));
    }

    /**
     * How many directories in the current view hold no models anywhere in
     * their subtree, or null when the models-only list is unavailable
     * (unsupported page or a failed request). Null keeps the view-options
     * menu in its "not sure yet" state instead of claiming there are none.
     */
    _computeEmptyFolderCount() {
        if (!this.nonEmptyFolders) return null;
        const known = this.displayMode === 'tree'
            ? this._collectTreePaths()
            : this._collectListPaths();
        return known.filter((path) => path && !this.nonEmptyFolders.has(path)).length;
    }

    // Every folder path present in the current tree, including intermediate
    // nodes that only exist to nest other folders.
    _collectTreePaths() {
        const paths = [];
        const walk = (node, prefix) => {
            for (const [name, children] of Object.entries(node || {})) {
                const path = prefix ? `${prefix}/${name}` : name;
                paths.push(path);
                walk(children, path);
            }
        };
        walk(this.treeData, '');
        return paths;
    }

    // Every folder path in the flat list view. Unlike the tree, that list
    // already carries full paths, so no prefix expansion is needed.
    _collectListPaths() {
        return (this.foldersList || []).filter(Boolean);
    }

    folderExistsInTree(path) {
        if (!path) return true;

        if (this.displayMode === 'tree') {
            let node = this.treeData;
            for (const segment of path.split('/')) {
                if (!node || typeof node !== 'object' || !(segment in node)) {
                    return false;
                }
                node = node[segment];
            }
            return true;
        }

        return this.foldersList.includes(path);
    }

    renderFolderDisplay() {
        if (this.displayMode === 'tree') {
            this.renderTree();
        } else {
            this.renderFolderList();
        }
        this.initializeDragAndDrop();
    }

    renderTree() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        if (!this.treeData || Object.keys(this.treeData).length === 0) {
            this.renderEmptyState();
            return;
        }

        folderTree.innerHTML = this.renderTreeNode(this.treeData, '');
    }

    renderTreeNode(nodeData, basePath) {
        const entries = Object.entries(nodeData);
        if (entries.length === 0) return '';

        return entries.map(([folderName, children]) => {
            const currentPath = basePath ? `${basePath}/${folderName}` : folderName;
            const hasChildren = Object.keys(children).length > 0;
            const isExpanded = this.expandedNodes.has(currentPath);
            const isSelected = this.selectedPath === currentPath;
            const isEmpty = this._isRenderedEmptyFolder(currentPath);

            const escapedPath = escapeAttribute(currentPath);
            const escapedFolderName = escapeHtml(folderName);
            const escapedTitle = escapeAttribute(folderName);

            return `
                <div class="sidebar-tree-node" data-path="${escapedPath}">
                    <div class="sidebar-tree-node-content ${isSelected ? 'selected' : ''} ${isEmpty ? 'empty' : ''}" data-path="${escapedPath}">
                        <div class="sidebar-tree-expand-icon ${isExpanded ? 'expanded' : ''}" 
                             style="${hasChildren ? '' : 'opacity: 0; pointer-events: none;'}">
                            <i class="fas fa-chevron-right"></i>
                        </div>
                        <i class="fas fa-folder${isEmpty ? '-open' : ''} sidebar-tree-folder-icon"></i>
                        <div class="sidebar-tree-folder-name" title="${escapedTitle}">${escapedFolderName}</div>
                    </div>
                    ${hasChildren ? `
                        <div class="sidebar-tree-children ${isExpanded ? 'expanded' : ''}">
                            ${this.renderTreeNode(children, currentPath)}
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    renderEmptyState() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        // Only pages with folder management (model libraries) offer the
        // header create button; other pages just show the empty label.
        const hintHtml = this._supportsFolderManagement() ? `
                <div class="sidebar-empty-hint">
                    <i class="fas fa-hand-pointer"></i>
                    ${translate('sidebar.empty.createHint', {}, 'Click the New Folder button above to create folders')}
                </div>` : '';

        folderTree.innerHTML = `
            <div class="sidebar-tree-placeholder">
                <i class="fas fa-folder-open"></i>
                <div>${translate('sidebar.empty.noFolders', {}, 'No folders found')}</div>${hintHtml}
            </div>
        `;
    }

    renderFolderList() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        // Unlike the tree — where the backend simply omits empty directories
        // when the preference is off — the flat list is always loaded in full
        // (the empty-folder count and the delete guard need it), so empty
        // entries are filtered out here instead.
        const visibleFolders = this._filterVisibleFolders(this.foldersList);

        if (visibleFolders.length === 0) {
            this.renderEmptyState();
            return;
        }

        const foldersHtml = visibleFolders.map(folder => {
            const displayName = folder === '' ? '/' : folder;
            const isSelected = this.selectedPath === folder;
            const isEmpty = this._isRenderedEmptyFolder(folder);
            const escapedPath = escapeAttribute(folder);
            const escapedDisplayName = escapeHtml(displayName);
            const escapedTitle = escapeAttribute(displayName);

            return `
                <div class="sidebar-folder-item ${isSelected ? 'selected' : ''}" data-path="${escapedPath}">
                    <div class="sidebar-node-content ${isEmpty ? 'empty' : ''}" data-path="${escapedPath}">
                        <i class="fas fa-folder${isEmpty ? '-open' : ''} sidebar-folder-icon"></i>
                        <div class="sidebar-folder-name" title="${escapedTitle}">${escapedDisplayName}</div>
                    </div>
                </div>
            `;
        }).join('');

        folderTree.innerHTML = foldersHtml;
    }

    handleTreeClick(event) {
        // Clicks on the inline create-folder row must not select/toggle nodes
        if (event.target.closest('.sidebar-create-folder-node')) return;

        if (this.displayMode === 'list') {
            this.handleFolderListClick(event);
            return;
        }

        const expandIcon = event.target.closest('.sidebar-tree-expand-icon');
        const nodeContent = event.target.closest('.sidebar-tree-node-content');

        if (expandIcon) {
            // Toggle expand/collapse
            const treeNode = expandIcon.closest('.sidebar-tree-node');
            const path = treeNode.dataset.path;
            const children = treeNode.querySelector('.sidebar-tree-children');

            if (this.expandedNodes.has(path)) {
                this.expandedNodes.delete(path);
                expandIcon.classList.remove('expanded');
                if (children) children.classList.remove('expanded');
            } else {
                this.expandedNodes.add(path);
                expandIcon.classList.add('expanded');
                if (children) children.classList.add('expanded');
            }

            this.saveExpandedState();
        } else if (nodeContent) {
            // Select folder
            const treeNode = nodeContent.closest('.sidebar-tree-node');
            const path = treeNode.dataset.path;
            this.selectFolder(path);
        }
    }

    handleTreeContextMenu(event) {
        // No context menu on the inline create-folder row
        if (event.target.closest('.sidebar-create-folder-node')) return;

        const nodeContent = event.target.closest('.sidebar-tree-node, .sidebar-folder-item');
        if (!nodeContent) return;

        event.preventDefault();
        event.stopPropagation();

        const path = nodeContent.dataset.path;
        if (path === undefined || path === null || path === '') return;

        this._showFolderContextMenu(event.clientX, event.clientY, path);
    }

    _showFolderContextMenu(x, y, path) {
        this._closeFolderContextMenu();
        this._closeViewOptionsMenu();

        const menu = document.getElementById('sidebarFolderContextMenu');
        if (!menu) return;

        // The folder operations are only available on pages backed by model
        // library roots (recipes have virtual folders only). Their dividers are
        // collapsed afterwards so such a page shows the update check alone
        // instead of dangling separators.
        const supportsFolderManagement = this._supportsFolderManagement();
        for (const action of ['create-subfolder', 'rename-folder', 'delete-folder']) {
            const item = menu.querySelector(`[data-action="${action}"]`);
            if (item) {
                item.style.display = supportsFolderManagement ? '' : 'none';
            }
        }
        this._updateContextMenuSeparators(menu);

        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
        menu.style.display = 'block';
        menu.dataset.folderPath = path;

        this._folderContextOpen = true;

        // Close on next click outside
        this._folderContextCloseHandler = (e) => {
            if (!menu.contains(e.target)) {
                this._closeFolderContextMenu();
            }
        };
        setTimeout(() => {
            document.addEventListener('click', this._folderContextCloseHandler);
        }, 0);
    }

    /**
     * Hide separators that no longer divide anything.
     *
     * Context-menu entries are gated per page, so a divider can end up
     * leading, trailing or doubled once its group is hidden — the recipes page,
     * for example, keeps only "check for updates". A separator survives only
     * when a visible entry sits on both of its sides, and a run of consecutive
     * separators collapses to a single line.
     */
    _updateContextMenuSeparators(menu) {
        const children = [...menu.children];
        const isSeparator = (element) => element.classList.contains('context-menu-separator');
        const visibleIndexes = children
            .map((element, index) => (!isSeparator(element) && element.style.display !== 'none' ? index : -1))
            .filter((index) => index !== -1);

        const first = visibleIndexes[0];
        const last = visibleIndexes[visibleIndexes.length - 1];
        let inSeparatorRun = false;

        children.forEach((element, index) => {
            if (!isSeparator(element)) {
                inSeparatorRun = false;
                return;
            }
            const keep = visibleIndexes.length >= 2
                && index > first
                && index < last
                && !inSeparatorRun;
            element.style.display = keep ? '' : 'none';
            inSeparatorRun = true;
        });
    }

    _closeFolderContextMenu() {
        const menu = document.getElementById('sidebarFolderContextMenu');
        if (menu) {
            menu.style.display = 'none';
            delete menu.dataset.folderPath;
        }
        if (this._folderContextCloseHandler) {
            document.removeEventListener('click', this._folderContextCloseHandler);
            this._folderContextCloseHandler = null;
        }
        this._folderContextOpen = false;
    }

    handleFolderContextMenuAction(action) {
        const menu = document.getElementById('sidebarFolderContextMenu');
        if (!menu) return;

        const path = menu.dataset.folderPath;
        this._closeFolderContextMenu();

        if (!path) return;

        this._performFolderAction(action, path);
    }

    async _performFolderAction(action, path) {
        switch (action) {
            case 'create-subfolder':
                this.showCreateFolderInput(path);
                break;
            case 'rename-folder':
                this.showRenameFolderInput(path);
                break;
            case 'delete-folder':
                this.showDeleteFolderModal(path);
                break;
            case 'check-folder-updates':
                try {
                    await performFolderUpdateCheck(path);
                } catch (error) {
                    console.error('Folder update check failed:', error);
                }
                break;
            default:
                console.warn('Unknown folder action:', action);
        }
    }

    handleBreadcrumbClick(event) {
        const breadcrumbItem = event.target.closest('.sidebar-breadcrumb-item');
        const dropdownItem = event.target.closest('.breadcrumb-dropdown-item');

        if (dropdownItem) {
            // Handle dropdown item selection
            const path = dropdownItem.dataset.path || '';
            this.selectFolder(path);
            this.closeDropdown();
        } else if (breadcrumbItem) {
            // Handle breadcrumb item click
            const path = breadcrumbItem.dataset.path || null;   // null for showing all models
            const isPlaceholder = breadcrumbItem.classList.contains('placeholder');
            const isActive = breadcrumbItem.classList.contains('active');
            const dropdown = breadcrumbItem.closest('.breadcrumb-dropdown');

            if (isPlaceholder || (isActive && path === this.selectedPath)) {
                // Open dropdown for placeholders or active items
                // Close any open dropdown first
                if (this.openDropdown && this.openDropdown !== dropdown) {
                    this.openDropdown.classList.remove('open');
                }

                // Toggle current dropdown
                dropdown.classList.toggle('open');

                // Update open dropdown reference
                this.openDropdown = dropdown.classList.contains('open') ? dropdown : null;
            } else {
                // Navigate to the selected path
                this.selectFolder(path);
            }
        }
    }

    closeDropdown() {
        if (this.openDropdown) {
            this.openDropdown.classList.remove('open');
            this.openDropdown = null;
        }
    }

    async selectFolder(path) {
        // Normalize path: null or undefined means root
        const normalizedPath = (path === null || path === undefined) ? '' : path;

        // Update selected path
        this.selectedPath = normalizedPath;

        // Update UI
        this.updateTreeSelection();
        this.updateBreadcrumbs();
        this.updateSidebarHeader();

        // Update page state
        this.pageControls.pageState.activeFolder = normalizedPath;
        setStorageItem(`${this.pageType}_activeFolder`, normalizedPath);

        // Reload models with new filter (loadMoreWithVirtualScroll will scroll to top)
        await this.pageControls.resetAndReload();
    }

    handleFolderListClick(event) {
        const folderItem = event.target.closest('.sidebar-folder-item');

        if (folderItem) {
            const path = folderItem.dataset.path;
            this.selectFolder(path);
        }
    }

    handleDisplayModeToggle(event) {
        event?.stopPropagation();
        this.displayMode = this.displayMode === 'tree' ? 'list' : 'tree';
        this.updateViewOptionsMenu();
        this.updateCollapseAllButton();
        this.updateSearchRecursiveOption();
        this.saveDisplayMode();
        this.loadFolderTree(); // Reload with new display mode
    }

    async handleRecursiveToggle(event) {
        event?.stopPropagation();

        if (this.displayMode !== 'tree') {
            return;
        }

        this.recursiveSearchEnabled = !this.recursiveSearchEnabled;
        setStorageItem(`${this.pageType}_recursiveSearch`, this.recursiveSearchEnabled);
        this.updateSearchRecursiveOption();
        this.updateViewOptionsMenu();

        if (this.pageControls && typeof this.pageControls.resetAndReload === 'function') {
            try {
                await this.pageControls.resetAndReload(true);
            } catch (error) {
                console.error('Failed to reload models after toggling recursive search:', error);
            }
        }
    }

    handleEmptyFoldersToggle(event) {
        event?.stopPropagation();

        if (!this._supportsFolderManagement()) {
            return;
        }

        this.showEmptyFolders = !this.showEmptyFolders;
        setStorageItem(`${this.pageType}_showEmptyFolders`, this.showEmptyFolders);
        this.updateViewOptionsMenu();
        // Both folder lists are already loaded (the count needs them), so
        // showing/hiding empty folders is a pure re-render.
        this.renderFolderDisplay();
    }

    handleCreateFolderButton(event) {
        event.stopPropagation();

        if (!this._supportsFolderManagement()) {
            return;
        }

        this.showCreateFolderInput();
    }

    handleViewOptionsButton(event) {
        event.stopPropagation();

        const menu = document.getElementById('sidebarViewOptionsMenu');
        if (!menu) return;

        if (menu.style.display === 'block') {
            this._closeViewOptionsMenu();
            return;
        }

        this._closeFolderContextMenu();
        this.updateViewOptionsMenu();

        const anchor = event.currentTarget;
        const rect = anchor.getBoundingClientRect();
        menu.style.display = 'block';
        // Right-align the menu under the button so it stays within the sidebar
        menu.style.left = `${Math.max(8, rect.right - menu.offsetWidth)}px`;
        menu.style.top = `${rect.bottom + 4}px`;

        this._viewOptionsCloseHandler = (e) => {
            if (!menu.contains(e.target)) {
                this._closeViewOptionsMenu();
            }
        };
        setTimeout(() => {
            document.addEventListener('click', this._viewOptionsCloseHandler);
        }, 0);
    }

    _closeViewOptionsMenu() {
        const menu = document.getElementById('sidebarViewOptionsMenu');
        if (menu) {
            menu.style.display = 'none';
        }
        if (this._viewOptionsCloseHandler) {
            document.removeEventListener('click', this._viewOptionsCloseHandler);
            this._viewOptionsCloseHandler = null;
        }
    }

    handleViewOptionsAction(action) {
        switch (action) {
            case 'view-mode-tree':
                if (this.displayMode !== 'tree') {
                    this.handleDisplayModeToggle();
                }
                this._closeViewOptionsMenu();
                break;
            case 'view-mode-list':
                if (this.displayMode !== 'list') {
                    this.handleDisplayModeToggle();
                }
                this._closeViewOptionsMenu();
                break;
            case 'toggle-recursive':
                // Keep the menu open so view preferences can be combined
                this.handleRecursiveToggle();
                break;
            case 'toggle-empty-folders':
                this.handleEmptyFoldersToggle();
                break;
            default:
                console.warn('Unknown view options action:', action);
        }
    }

    updateFolderManagementButtons() {
        const supported = this._supportsFolderManagement();

        const createFolderBtn = document.getElementById('sidebarCreateFolder');
        if (createFolderBtn) {
            createFolderBtn.style.display = supported ? '' : 'none';
        }

        this.updateViewOptionsMenu();
    }

    updateViewOptionsMenu() {
        const menu = document.getElementById('sidebarViewOptionsMenu');
        if (!menu) return;

        const setCheck = (action, checked) => {
            const check = menu.querySelector(`[data-action="${action}"] .check-indicator`);
            if (check) {
                check.style.display = checked ? 'block' : 'none';
            }
        };
        const setDisabled = (action, disabled) => {
            const item = menu.querySelector(`[data-action="${action}"]`);
            if (item) {
                item.classList.toggle('disabled', disabled);
            }
        };

        const isTreeMode = this.displayMode === 'tree';
        setCheck('view-mode-tree', isTreeMode);
        setCheck('view-mode-list', !isTreeMode);
        setCheck('toggle-recursive', isTreeMode && this.recursiveSearchEnabled);
        setDisabled('toggle-recursive', !isTreeMode);

        // Empty-folder display requires a model library backend, and the
        // toggle is only worth showing when there actually are empty folders
        // to reveal/hide. `null` means the folder data has not loaded yet, in
        // which case the item is kept visible rather than guessed at.
        const supportsFolderManagement = this._supportsFolderManagement();
        const hasEmptyFolders = !supportsFolderManagement
            || this.emptyFolderCount === null
            || this.emptyFolderCount > 0;
        setCheck('toggle-empty-folders', this.showEmptyFolders && supportsFolderManagement);

        const emptyFoldersItem = menu.querySelector('[data-action="toggle-empty-folders"]');
        if (emptyFoldersItem) {
            emptyFoldersItem.style.display = supportsFolderManagement && hasEmptyFolders ? '' : 'none';
        }

        // Surface the count so the preference's effect is visible without
        // opening the menu against a large library.
        const emptyFoldersCount = document.getElementById('sidebarEmptyFoldersCount');
        if (emptyFoldersCount) {
            emptyFoldersCount.textContent = this.emptyFolderCount
                ? `(${this.emptyFolderCount})`
                : '';
        }
    }

    updateCollapseAllButton() {
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        if (!collapseAllBtn) return;

        const isTreeMode = this.displayMode === 'tree';
        collapseAllBtn.disabled = !isTreeMode;
        collapseAllBtn.classList.toggle('disabled', !isTreeMode);
        collapseAllBtn.title = isTreeMode
            ? translate('sidebar.collapseAll')
            : translate('sidebar.collapseAllDisabled', {}, 'Not available in list view');
    }

    updateSearchRecursiveOption() {
        const isRecursive = this.displayMode === 'tree' && this.recursiveSearchEnabled;
        this.pageControls.pageState.searchOptions.recursive = isRecursive;
    }

    updateTreeSelection() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        if (this.displayMode === 'list') {
            // Remove all selections in list mode
            folderTree.querySelectorAll('.sidebar-folder-item').forEach(item => {
                item.classList.remove('selected');
            });

            // Add selection to current path
            if (this.selectedPath !== null && this.selectedPath !== undefined) {
                const escapedPathSelector = CSS.escape(this.selectedPath);
                const selectedItem = folderTree.querySelector(`[data-path="${escapedPathSelector}"]`);
                if (selectedItem) {
                    selectedItem.classList.add('selected');
                }
            }
        } else {
            folderTree.querySelectorAll('.sidebar-tree-node-content').forEach(node => {
                node.classList.remove('selected');
            });

            if (this.selectedPath !== null && this.selectedPath !== undefined) {
                const escapedPathSelector = CSS.escape(this.selectedPath);
                const selectedNode = folderTree.querySelector(`[data-path="${escapedPathSelector}"] .sidebar-tree-node-content`);
                if (selectedNode) {
                    selectedNode.classList.add('selected');
                    this.expandPathParents(this.selectedPath);
                }
            }
        }
    }

    expandPathParents(path) {
        if (!path) return;

        const parts = path.split('/');
        let currentPath = '';

        for (let i = 0; i < parts.length - 1; i++) {
            currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
            this.expandedNodes.add(currentPath);
        }

        this.renderTree();
    }

    // Get sibling folders for a given path level
    getSiblingFolders(pathParts, level) {
        if (level === 0) {
            // Root level siblings are top-level folders
            return Object.keys(this.treeData);
        }

        // Navigate to the parent folder to get siblings
        let currentNode = this.treeData;
        for (let i = 0; i < level; i++) {
            if (!currentNode[pathParts[i]]) {
                return [];
            }
            currentNode = currentNode[pathParts[i]];
        }

        return Object.keys(currentNode);
    }

    // Get child folders for a given path
    getChildFolders(path) {
        if (!path) {
            return Object.keys(this.treeData);
        }

        const parts = path.split('/');
        let currentNode = this.treeData;

        for (const part of parts) {
            if (!currentNode[part]) {
                return [];
            }
            currentNode = currentNode[part];
        }

        return Object.keys(currentNode);
    }

    updateBreadcrumbs() {
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        if (!sidebarBreadcrumbNav) return;

        const parts = this.selectedPath ? this.selectedPath.split('/') : [];
        let currentPath = '';

        // Start with root breadcrumb
        const rootSiblings = Object.keys(this.treeData);
        const isRootSelected = !this.selectedPath;
        const breadcrumbs = [`
            <div class="breadcrumb-dropdown">
                <span class="sidebar-breadcrumb-item ${isRootSelected ? 'active' : ''}" data-path="">
                    <i class="fas fa-home"></i> ${escapeHtml(this.apiClient.apiConfig.config.displayName)} root
                </span>
            </div>
        `];

        // Add separator and placeholder for next level if we're at root
        if (!this.selectedPath) {
            const nextLevelFolders = rootSiblings;
            if (nextLevelFolders.length > 0) {
                breadcrumbs.push(`<span class="sidebar-breadcrumb-separator">/</span>`);
                breadcrumbs.push(`
                    <div class="breadcrumb-dropdown">
                        <span class="sidebar-breadcrumb-item placeholder">
                            --
                            <span class="breadcrumb-dropdown-indicator">
                                <i class="fas fa-caret-down"></i>
                            </span>
                        </span>
                        <div class="breadcrumb-dropdown-menu">
                            ${nextLevelFolders.map(folder => `
                                <div class="breadcrumb-dropdown-item" data-path="${escapeAttribute(folder)}">
                                    ${escapeHtml(folder)}
                                </div>`).join('')
                    }
                        </div>
                    </div>
                `);
            }
        }

        // Add breadcrumb items for each path segment
        parts.forEach((part, index) => {
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            const isLast = index === parts.length - 1;

            // Get siblings for this level
            const siblings = this.getSiblingFolders(parts, index);
            const escapedCurrentPath = escapeAttribute(currentPath);
            const escapedPart = escapeHtml(part);

            breadcrumbs.push(`<span class="sidebar-breadcrumb-separator">/</span>`);
            breadcrumbs.push(`
                <div class="breadcrumb-dropdown">
                    <span class="sidebar-breadcrumb-item ${isLast ? 'active' : ''}" data-path="${escapedCurrentPath}">
                        ${escapedPart}
                        ${siblings.length > 1 ? `
                            <span class="breadcrumb-dropdown-indicator">
                                <i class="fas fa-caret-down"></i>
                            </span>
                        ` : ''}
                    </span>
                    ${siblings.length > 1 ? `
                        <div class="breadcrumb-dropdown-menu">
                            ${siblings.map(folder => {
                                const siblingPath = parts.slice(0, index).concat(folder).join('/');
                                return `
                                    <div class="breadcrumb-dropdown-item ${folder === part ? 'active' : ''}" 
                                         data-path="${escapeAttribute(siblingPath)}">
                                        ${escapeHtml(folder)}
                                    </div>`;
                            }).join('')
                    }
                        </div>
                    ` : ''}
                </div>
            `);

            // Add separator and placeholder for next level if not the last item
            if (isLast) {
                const childFolders = this.getChildFolders(currentPath);
                if (childFolders.length > 0) {
                    breadcrumbs.push(`<span class="sidebar-breadcrumb-separator">/</span>`);
                    breadcrumbs.push(`
                        <div class="breadcrumb-dropdown">
                            <span class="sidebar-breadcrumb-item placeholder">
                                --
                                <span class="breadcrumb-dropdown-indicator">
                                    <i class="fas fa-caret-down"></i>
                                </span>
                            </span>
                            <div class="breadcrumb-dropdown-menu">
                                ${childFolders.map(folder => `
                                    <div class="breadcrumb-dropdown-item" data-path="${escapeAttribute(currentPath + '/' + folder)}">
                                        ${escapeHtml(folder)}
                                    </div>`).join('')
                        }
                            </div>
                        </div>
                    `);
                }
            }
        });

        sidebarBreadcrumbNav.innerHTML = breadcrumbs.join('');
    }

    updateSidebarHeader() {
        const sidebarHeader = document.getElementById('sidebarHeader');
        if (!sidebarHeader) return;

        if (!this.selectedPath) {
            sidebarHeader.classList.add('root-selected');
        } else {
            sidebarHeader.classList.remove('root-selected');
        }
    }

    restoreSidebarState() {
        // Migration: old pin/unpin and global hide → per-page hide
        this._migrateOldSettings();

        const expandedPaths = getStorageItem(`${this.pageType}_expandedNodes`, []);
        const displayMode = getStorageItem(`${this.pageType}_displayMode`, 'tree'); // 'tree' or 'list', default to 'tree'
        const recursiveSearchEnabled = getStorageItem(`${this.pageType}_recursiveSearch`, true);
        this.isDisabledByPage = getStorageItem(
            `${this.pageType}_sidebarDisabled`,
            SIDEBAR_DEFAULT_HIDDEN_PAGES.has(this.pageType)
        );

        this.expandedNodes = new Set(expandedPaths);
        this.displayMode = displayMode;
        this.recursiveSearchEnabled = recursiveSearchEnabled;
        // Empty folders are shown by default so the sidebar matches the
        // destination picker (which lists them too) instead of silently hiding
        // a folder that a download just landed in. New folders created from the
        // header stay visible for the same reason.
        this.showEmptyFolders = getStorageItem(`${this.pageType}_showEmptyFolders`, true);

        this.updateSearchRecursiveOption();
        this.updateFolderManagementButtons();
        this.updateCollapseAllButton();
    }

    /**
     * One-time migration: old pin/unpin and global show_folder_sidebar → per-page hide
     * - sidebarPinned=false (was auto-hide) → sidebarDisabled=true for that page
     * - show_folder_sidebar=false (global) → sidebarDisabled=true for ALL pages
     */
    _migrateOldSettings() {
        if (getStorageItem('_sidebar_migration_done')) return;

        const PAGES = ['loras', 'recipes', 'checkpoints', 'embeddings', 'other'];

        // 1. Migrate global hide setting to per-page
        if (state?.global?.settings?.show_folder_sidebar === false) {
            PAGES.forEach(p => setStorageItem(`${p}_sidebarDisabled`, true));
        }

        // 2. Migrate unpinned (auto-hide) to per-page hide
        PAGES.forEach(p => {
            const wasPinned = getStorageItem(`${p}_sidebarPinned`, true);
            const alreadyDisabled = getStorageItem(`${p}_sidebarDisabled`, false);
            if (wasPinned === false && !alreadyDisabled) {
                // Was auto-hide → user didn't want sidebar taking space
                setStorageItem(`${p}_sidebarDisabled`, true);
            }
            // Clean up old keys
            localStorage.removeItem(`${p}_sidebarPinned`);
        });

        setStorageItem('_sidebar_migration_done', true);
    }

    restoreSelectedFolder() {
        const activeFolder = getStorageItem(`${this.pageType}_activeFolder`);
        if (activeFolder && typeof activeFolder === 'string') {
            // Fall back to the root when the persisted folder no longer
            // exists in the freshly loaded tree (e.g. it was moved or
            // deleted); otherwise the grid stays empty with a phantom
            // breadcrumb. Skip validation when the tree failed to load so a
            // transient API error doesn't wipe the saved location.
            if (this.folderTreeLoaded && !this.folderExistsInTree(activeFolder)) {
                console.warn(`Persisted folder "${activeFolder}" not found in folder tree, falling back to root`);
                this.selectedPath = '';
                if (this.pageControls?.pageState) {
                    this.pageControls.pageState.activeFolder = '';
                }
                setStorageItem(`${this.pageType}_activeFolder`, '');
                // When the reset happens after initialization (e.g. via
                // refresh() after a drag move emptied the folder), reload the
                // listing so the grid shows the root contents instead of
                // staying empty. Skipped during initialize() — the first load
                // picks up the cleared filter on its own.
                if (this.isInitialized && typeof this.pageControls?.resetAndReload === 'function') {
                    this.pageControls.resetAndReload().catch((error) => {
                        console.error('Failed to reload after resetting folder selection:', error);
                    });
                }
            } else {
                this.selectedPath = activeFolder;
            }
            this.updateTreeSelection();
            this.updateBreadcrumbs();
            this.updateSidebarHeader();
        } else {
            this.selectedPath = '';
            this.updateSidebarHeader();
            this.updateBreadcrumbs(); // Always update breadcrumbs
        }
    }

    saveExpandedState() {
        setStorageItem(`${this.pageType}_expandedNodes`, Array.from(this.expandedNodes));
    }

    saveDisplayMode() {
        setStorageItem(`${this.pageType}_displayMode`, this.displayMode);
    }

    async refresh() {
        if (!this.isInitialized) {
            return;
        }

        await this.loadFolderTree();
        this.restoreSelectedFolder();
    }

    destroy() {
        this.cleanup();
    }
}

// Create and export global instance
export const sidebarManager = new SidebarManager();
