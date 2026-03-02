/**
 * SidebarManager - Manages hierarchical folder navigation sidebar
 */
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';
import { translate } from '../utils/i18nHelpers.js';
import { state } from '../state/index.js';
import { bulkManager } from '../managers/BulkManager.js';
import { showToast } from '../utils/uiHelpers.js';

export class SidebarManager {
    constructor() {
        this.pageControls = null;
        this.pageType = null;
        this.treeData = {};
        this.selectedPath = '';
        this.expandedNodes = new Set();
        this.isVisible = true;
        this.isPinned = false;
        this.apiClient = null;
        this.openDropdown = null;
        this.hoverTimeout = null;
        this.isHovering = false;
        this.isInitialized = false;
        this.displayMode = 'tree'; // 'tree' or 'list'
        this.foldersList = [];
        this.recursiveSearchEnabled = true;
        this.draggedFilePaths = null;
        this.draggedRootPath = null;
        this.draggedFromBulk = false;
        this.dragHandlersInitialized = false;
        this.sidebarDragHandlersInitialized = false;
        this.folderTreeElement = null;
        this.currentDropTarget = null;
        this.lastPageControls = null;
        this.isDisabledBySetting = false;
        this.initializationPromise = null;
        this.isCreatingFolder = false;
        this._pendingDragState = null; // 用于保存拖拽创建文件夹时的状态

        // Bind methods
        this.handleTreeClick = this.handleTreeClick.bind(this);
        this.handleBreadcrumbClick = this.handleBreadcrumbClick.bind(this);
        this.handleDocumentClick = this.handleDocumentClick.bind(this);
        this.handleSidebarHeaderClick = this.handleSidebarHeaderClick.bind(this);
        this.handlePinToggle = this.handlePinToggle.bind(this);
        this.handleCollapseAll = this.handleCollapseAll.bind(this);
        this.handleMouseEnter = this.handleMouseEnter.bind(this);
        this.handleMouseLeave = this.handleMouseLeave.bind(this);
        this.handleHoverAreaEnter = this.handleHoverAreaEnter.bind(this);
        this.handleHoverAreaLeave = this.handleHoverAreaLeave.bind(this);
        this.updateContainerMargin = this.updateContainerMargin.bind(this);
        this.handleDisplayModeToggle = this.handleDisplayModeToggle.bind(this);
        this.handleFolderListClick = this.handleFolderListClick.bind(this);
        this.handleRecursiveToggle = this.handleRecursiveToggle.bind(this);
        this.handleCardDragStart = this.handleCardDragStart.bind(this);
        this.handleCardDragEnd = this.handleCardDragEnd.bind(this);
        this.handleFolderDragEnter = this.handleFolderDragEnter.bind(this);
        this.handleFolderDragOver = this.handleFolderDragOver.bind(this);
        this.handleFolderDragLeave = this.handleFolderDragLeave.bind(this);
        this.handleFolderDrop = this.handleFolderDrop.bind(this);
        this.handleSidebarDragEnter = this.handleSidebarDragEnter.bind(this);
        this.handleSidebarDragOver = this.handleSidebarDragOver.bind(this);
        this.handleSidebarDragLeave = this.handleSidebarDragLeave.bind(this);
        this.handleSidebarDrop = this.handleSidebarDrop.bind(this);
        this.handleCreateFolderSubmit = this.handleCreateFolderSubmit.bind(this);
        this.handleCreateFolderCancel = this.handleCreateFolderCancel.bind(this);
    }

    setHostPageControls(pageControls) {
        this.lastPageControls = pageControls;
    }

    async initialize(pageControls, options = {}) {
        const { forceInitialize = false } = options;

        if (this.isDisabledBySetting && !forceInitialize) {
            return;
        }

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

        // Set initial sidebar state immediately (hidden by default)
        this.setInitialSidebarState();

        this.setupEventHandlers();
        this.initializeDragAndDrop();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        await this.loadFolderTree();
        if (this.isDisabledBySetting && !forceInitialize) {
            this.cleanup();
            return;
        }
        this.restoreSelectedFolder();

        // Apply final state with animation after everything is loaded
        this.applyFinalSidebarState();

        // Update container margin based on initial sidebar state
        this.updateContainerMargin();

        this.isInitialized = true;
        console.log(`SidebarManager initialized for ${this.pageType} page`);
    }

    cleanup() {
        if (!this.isInitialized) return;

        // Clear any pending timeouts
        if (this.hoverTimeout) {
            clearTimeout(this.hoverTimeout);
            this.hoverTimeout = null;
        }

        // Clean up event handlers
        this.removeEventHandlers();

        this.clearAllDropHighlights();
        this.resetDragState();
        this.hideCreateFolderInput();

        // Cleanup sidebar drag handlers
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar && this.sidebarDragHandlersInitialized) {
            sidebar.removeEventListener('dragenter', this.handleSidebarDragEnter);
            sidebar.removeEventListener('dragover', this.handleSidebarDragOver);
            sidebar.removeEventListener('dragleave', this.handleSidebarDragLeave);
            sidebar.removeEventListener('drop', this.handleSidebarDrop);
            this.sidebarDragHandlersInitialized = false;
        }

        // Reset state
        this.pageControls = null;
        this.pageType = null;
        this.treeData = {};
        this.selectedPath = '';
        this.expandedNodes = new Set();
        this.openDropdown = null;
        this.isHovering = false;
        this.apiClient = null;
        this.isInitialized = false;
        this.recursiveSearchEnabled = true;

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
        const pinToggleBtn = document.getElementById('sidebarPinToggle');
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        const folderTree = document.getElementById('sidebarFolderTree');
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        const sidebarHeader = document.getElementById('sidebarHeader');
        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');
        const displayModeToggleBtn = document.getElementById('sidebarDisplayModeToggle');
        const recursiveToggleBtn = document.getElementById('sidebarRecursiveToggle');

        if (pinToggleBtn) {
            pinToggleBtn.removeEventListener('click', this.handlePinToggle);
        }
        if (collapseAllBtn) {
            collapseAllBtn.removeEventListener('click', this.handleCollapseAll);
        }
        if (folderTree) {
            folderTree.removeEventListener('click', this.handleTreeClick);
        }
        if (sidebarBreadcrumbNav) {
            sidebarBreadcrumbNav.removeEventListener('click', this.handleBreadcrumbClick);
        }
        if (sidebarHeader) {
            sidebarHeader.removeEventListener('click', this.handleSidebarHeaderClick);
        }
        if (sidebar) {
            sidebar.removeEventListener('mouseenter', this.handleMouseEnter);
            sidebar.removeEventListener('mouseleave', this.handleMouseLeave);
        }
        if (hoverArea) {
            hoverArea.removeEventListener('mouseenter', this.handleHoverAreaEnter);
            hoverArea.removeEventListener('mouseleave', this.handleHoverAreaLeave);
        }

        // Remove document click handler
        document.removeEventListener('click', this.handleDocumentClick);

        // Remove resize event handler
        window.removeEventListener('resize', this.updateContainerMargin);

        if (displayModeToggleBtn) {
            displayModeToggleBtn.removeEventListener('click', this.handleDisplayModeToggle);
        }
        if (recursiveToggleBtn) {
            recursiveToggleBtn.removeEventListener('click', this.handleRecursiveToggle);
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

        // Add sidebar-level drag handlers for creating new folders
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar && !this.sidebarDragHandlersInitialized) {
            sidebar.addEventListener('dragenter', this.handleSidebarDragEnter);
            sidebar.addEventListener('dragover', this.handleSidebarDragOver);
            sidebar.addEventListener('dragleave', this.handleSidebarDragLeave);
            sidebar.addEventListener('drop', this.handleSidebarDrop);
            this.sidebarDragHandlersInitialized = true;
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
            if (useBulkMove) {
                await this.apiClient.moveBulkModels(this.draggedFilePaths, destination);
            } else {
                await this.apiClient.moveSingleModel(this.draggedFilePaths[0], destination);
            }
            console.log('[SidebarManager] apiClient.move successful');

            if (this.pageControls && typeof this.pageControls.resetAndReload === 'function') {
                console.log('[SidebarManager] calling resetAndReload');
                await this.pageControls.resetAndReload(true);
            } else {
                console.log('[SidebarManager] calling refresh');
                await this.refresh();
            }

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

    // Version of performDragMove that accepts state as parameters (for create folder submit)
    async performDragMoveWithState(targetRelativePath, draggedFilePaths, draggedRootPath, draggedFromBulk) {
        console.log('[SidebarManager] performDragMoveWithState called with:', { targetRelativePath, draggedFilePaths, draggedRootPath, draggedFromBulk });

        if (!draggedFilePaths || draggedFilePaths.length === 0) {
            console.log('[SidebarManager] performDragMoveWithState returning false - no draggedFilePaths');
            return false;
        }

        if (!this.apiClient) {
            this.apiClient = this.pageControls?.getSidebarApiClient?.()
                || this.pageControls?.sidebarApiClient
                || getModelApiClient();
        }

        if (this.apiClient?.apiConfig?.config?.supportsMove === false) {
            console.log('[SidebarManager] performDragMoveWithState returning false - supportsMove is false');
            showToast('toast.models.moveFailed', { message: translate('sidebar.dragDrop.moveUnsupported', {}, 'Move not supported for this page') }, 'error');
            return false;
        }

        const rootPath = draggedRootPath ? draggedRootPath.replace(/\\/g, '/') : '';
        console.log('[SidebarManager] rootPath:', rootPath);
        if (!rootPath) {
            console.log('[SidebarManager] performDragMoveWithState returning false - no rootPath');
            showToast(
                'toast.models.moveFailed',
                { message: translate('sidebar.dragDrop.unableToResolveRoot', {}, 'Unable to determine destination path for move.') },
                'error'
            );
            return false;
        }

        const destination = this.combineRootAndRelativePath(rootPath, targetRelativePath);
        const useBulkMove = draggedFromBulk || draggedFilePaths.length > 1;

        try {
            console.log('[SidebarManager] calling apiClient.move, useBulkMove:', useBulkMove);
            if (useBulkMove) {
                await this.apiClient.moveBulkModels(draggedFilePaths, destination);
            } else {
                await this.apiClient.moveSingleModel(draggedFilePaths[0], destination);
            }
            console.log('[SidebarManager] apiClient.move successful');

            if (this.pageControls && typeof this.pageControls.resetAndReload === 'function') {
                console.log('[SidebarManager] calling resetAndReload');
                await this.pageControls.resetAndReload(true);
            } else {
                console.log('[SidebarManager] calling refresh');
                await this.refresh();
            }

            if (draggedFromBulk && state.bulkMode && typeof bulkManager?.toggleBulkMode === 'function') {
                bulkManager.toggleBulkMode();
            }

            console.log('[SidebarManager] performDragMoveWithState returning true');
            return true;
        } catch (error) {
            console.error('[SidebarManager] Error moving model(s) via drag-and-drop:', error);
            showToast('toast.models.moveFailed', { message: error.message || 'Unknown error' }, 'error');
            console.log('[SidebarManager] performDragMoveWithState returning false due to error');
            return false;
        }
    }

    // ===== Sidebar-level drag handlers for creating new folders =====

    handleSidebarDragEnter(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const sidebar = document.getElementById('folderSidebar');
        if (!sidebar) return;

        // Only show create folder zone if not hovering over an existing folder
        const folderElement = this.getFolderElementFromEvent(event);
        if (folderElement) {
            this.hideCreateFolderZone();
            return;
        }

        // Check if drag is within the sidebar tree container area
        const treeContainer = document.querySelector('.sidebar-tree-container');
        if (treeContainer && treeContainer.contains(event.target)) {
            event.preventDefault();
            this.showCreateFolderZone();
        }
    }

    handleSidebarDragOver(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (folderElement) {
            this.hideCreateFolderZone();
            return;
        }

        const treeContainer = document.querySelector('.sidebar-tree-container');
        if (treeContainer && treeContainer.contains(event.target)) {
            event.preventDefault();
            if (event.dataTransfer) {
                event.dataTransfer.dropEffect = 'move';
            }
        }
    }

    handleSidebarDragLeave(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const sidebar = document.getElementById('folderSidebar');
        if (!sidebar) return;

        const relatedTarget = event.relatedTarget instanceof Element ? event.relatedTarget : null;

        // Only hide if leaving the sidebar entirely
        if (!relatedTarget || !sidebar.contains(relatedTarget)) {
            this.hideCreateFolderZone();
        }
    }

    async handleSidebarDrop(event) {
        if (!this.draggedFilePaths || this.draggedFilePaths.length === 0) return;

        const folderElement = this.getFolderElementFromEvent(event);
        if (folderElement) {
            // Let the folder drop handler take over
            return;
        }

        const treeContainer = document.querySelector('.sidebar-tree-container');
        if (!treeContainer || !treeContainer.contains(event.target)) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();

        // Show create folder input
        this.showCreateFolderInput();
    }

    showCreateFolderZone() {
        if (this.isCreatingFolder) return;

        const treeContainer = document.querySelector('.sidebar-tree-container');
        if (!treeContainer) return;

        let zone = document.getElementById('sidebarCreateFolderZone');
        if (!zone) {
            zone = document.createElement('div');
            zone.id = 'sidebarCreateFolderZone';
            zone.className = 'sidebar-create-folder-zone';
            zone.innerHTML = `
                <div class="sidebar-create-folder-content">
                    <i class="fas fa-plus-circle"></i>
                    <span>${translate('sidebar.dragDrop.createFolderHint', {}, 'Release to create new folder')}</span>
                </div>
            `;
            treeContainer.appendChild(zone);
        }

        zone.classList.add('active');
    }

    hideCreateFolderZone() {
        const zone = document.getElementById('sidebarCreateFolderZone');
        if (zone) {
            zone.classList.remove('active');
        }
    }

    showCreateFolderInput() {
        console.log('[SidebarManager] showCreateFolderInput called');
        this.isCreatingFolder = true;
        
        // 立即保存拖拽状态，防止后续事件（如blur）清空状态
        this._pendingDragState = {
            filePaths: this.draggedFilePaths ? [...this.draggedFilePaths] : null,
            rootPath: this.draggedRootPath,
            fromBulk: this.draggedFromBulk
        };
        console.log('[SidebarManager] saved pending drag state:', this._pendingDragState);
        
        this.hideCreateFolderZone();

        const treeContainer = document.querySelector('.sidebar-tree-container');
        if (!treeContainer) return;

        // Remove existing input if any
        this.hideCreateFolderInput();

        const inputContainer = document.createElement('div');
        inputContainer.id = 'sidebarCreateFolderInput';
        inputContainer.className = 'sidebar-create-folder-input-container';
        inputContainer.innerHTML = `
            <div class="sidebar-create-folder-input-wrapper">
                <i class="fas fa-folder-plus"></i>
                <input type="text" 
                       class="sidebar-create-folder-input" 
                       placeholder="${translate('sidebar.dragDrop.newFolderName', {}, 'New folder name')}" 
                       autofocus />
                <button class="sidebar-create-folder-btn sidebar-create-folder-confirm" title="${translate('common.confirm', {}, 'Confirm')}">
                    <i class="fas fa-check"></i>
                </button>
                <button class="sidebar-create-folder-btn sidebar-create-folder-cancel" title="${translate('common.cancel', {}, 'Cancel')}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="sidebar-create-folder-hint">
                ${translate('sidebar.dragDrop.folderNameHint', {}, 'Press Enter to confirm, Escape to cancel')}
            </div>
        `;

        treeContainer.appendChild(inputContainer);

        // Focus input
        const input = inputContainer.querySelector('.sidebar-create-folder-input');
        if (input) {
            input.focus();
        }

        // Bind events
        const confirmBtn = inputContainer.querySelector('.sidebar-create-folder-confirm');
        const cancelBtn = inputContainer.querySelector('.sidebar-create-folder-cancel');

        // Flag to prevent blur from canceling when clicking buttons
        let isButtonClick = false;

        confirmBtn?.addEventListener('mousedown', () => { 
            isButtonClick = true; 
            console.log('[SidebarManager] confirmBtn mousedown - isButtonClick set to true');
        });
        cancelBtn?.addEventListener('mousedown', () => { 
            isButtonClick = true; 
            console.log('[SidebarManager] cancelBtn mousedown - isButtonClick set to true');
        });

        confirmBtn?.addEventListener('click', (e) => {
            console.log('[SidebarManager] confirmBtn click event triggered');
            this.handleCreateFolderSubmit();
        });
        cancelBtn?.addEventListener('click', () => {
            console.log('[SidebarManager] cancelBtn click event triggered');
            this.handleCreateFolderCancel();
        });
        input?.addEventListener('keydown', (e) => {
            console.log('[SidebarManager] input keydown:', e.key);
            if (e.key === 'Enter') {
                console.log('[SidebarManager] Enter pressed, calling handleCreateFolderSubmit');
                this.handleCreateFolderSubmit();
            } else if (e.key === 'Escape') {
                console.log('[SidebarManager] Escape pressed, calling handleCreateFolderCancel');
                this.handleCreateFolderCancel();
            }
        });
        input?.addEventListener('blur', () => {
            console.log('[SidebarManager] input blur event - isButtonClick:', isButtonClick);
            // Delay to allow button clicks to process first
            setTimeout(() => {
                console.log('[SidebarManager] blur timeout - isButtonClick:', isButtonClick, 'activeElement:', document.activeElement?.className);
                if (!isButtonClick && document.activeElement !== confirmBtn && document.activeElement !== cancelBtn) {
                    console.log('[SidebarManager] blur timeout - calling handleCreateFolderCancel');
                    this.handleCreateFolderCancel();
                } else {
                    console.log('[SidebarManager] blur timeout - NOT canceling (button click detected)');
                }
                isButtonClick = false;
            }, 200);
        });
    }

    hideCreateFolderInput() {
        console.log('[SidebarManager] hideCreateFolderInput called');
        const inputContainer = document.getElementById('sidebarCreateFolderInput');
        console.log('[SidebarManager] inputContainer:', inputContainer);
        if (inputContainer) {
            inputContainer.remove();
            console.log('[SidebarManager] inputContainer removed');
        }
        this.isCreatingFolder = false;
        console.log('[SidebarManager] isCreatingFolder set to false');
    }

    async handleCreateFolderSubmit() {
        console.log('[SidebarManager] handleCreateFolderSubmit called');
        const input = document.querySelector('#sidebarCreateFolderInput .sidebar-create-folder-input');
        console.log('[SidebarManager] input element:', input);
        if (!input) {
            console.log('[SidebarManager] input not found, returning');
            return;
        }

        const folderName = input.value.trim();
        console.log('[SidebarManager] folderName:', folderName);
        if (!folderName) {
            showToast('sidebar.dragDrop.emptyFolderName', {}, 'warning');
            return;
        }

        // Validate folder name (no slashes, no special chars)
        if (/[\\/:*?"<>|]/.test(folderName)) {
            showToast('sidebar.dragDrop.invalidFolderName', {}, 'error');
            return;
        }

        // Build target path - use selected path as parent, or root if none selected
        const parentPath = this.selectedPath || '';
        const targetRelativePath = parentPath ? `${parentPath}/${folderName}` : folderName;
        console.log('[SidebarManager] targetRelativePath:', targetRelativePath);

        // 使用 showCreateFolderInput 时保存的拖拽状态
        const pendingState = this._pendingDragState;
        console.log('[SidebarManager] using pending drag state:', pendingState);
        
        if (!pendingState || !pendingState.filePaths || pendingState.filePaths.length === 0) {
            console.log('[SidebarManager] no pending drag state found, cannot proceed');
            showToast('sidebar.dragDrop.noDragState', {}, 'error');
            this.hideCreateFolderInput();
            return;
        }

        this.hideCreateFolderInput();

        // Perform the move with saved state
        console.log('[SidebarManager] calling performDragMove with pending state');
        const success = await this.performDragMoveWithState(targetRelativePath, pendingState.filePaths, pendingState.rootPath, pendingState.fromBulk);
        console.log('[SidebarManager] performDragMove result:', success);

        if (success) {
            // Expand the parent folder to show the new folder
            if (parentPath) {
                this.expandedNodes.add(parentPath);
                this.saveExpandedState();
            }
            // Refresh the tree to show the newly created folder
            // restoreSelectedFolder() inside refresh() will maintain the current active folder
            await this.refresh();
        }

        // 清理待处理的拖拽状态
        this._pendingDragState = null;
        this.resetDragState();
        this.clearAllDropHighlights();
    }

    handleCreateFolderCancel() {
        this.hideCreateFolderInput();
        // 清理待处理的拖拽状态
        this._pendingDragState = null;
        this.resetDragState();
        this.clearAllDropHighlights();
    }

    saveSelectedFolder() {
        setStorageItem(`${this.pageType}_activeFolder`, this.selectedPath);
    }

    clearAllDropHighlights() {
        const highlighted = document.querySelectorAll('.sidebar-tree-node-content.drop-target, .sidebar-node-content.drop-target');
        highlighted.forEach((element) => element.classList.remove('drop-target'));
        this.currentDropTarget = null;
    }

    async init() {
        this.apiClient = this.pageControls?.getSidebarApiClient?.()
            || this.pageControls?.sidebarApiClient
            || getModelApiClient();

        // Set initial sidebar state immediately (hidden by default)
        this.setInitialSidebarState();

        this.setupEventHandlers();
        this.initializeDragAndDrop();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        await this.loadFolderTree();
        this.restoreSelectedFolder();

        // Apply final state with animation after everything is loaded
        this.applyFinalSidebarState();

        // Update container margin based on initial sidebar state
        this.updateContainerMargin();
    }

    setInitialSidebarState() {
        if (this.isDisabledBySetting) return;

        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');

        if (!sidebar || !hoverArea) return;

        // Get stored pin state
        const isPinned = getStorageItem(`${this.pageType}_sidebarPinned`, true);
        this.isPinned = isPinned;

        // Sidebar starts hidden by default (CSS handles this)
        // Just set up the hover area state
        if (window.innerWidth <= 1024) {
            hoverArea.classList.add('disabled');
        } else if (this.isPinned) {
            hoverArea.classList.add('disabled');
        } else {
            hoverArea.classList.remove('disabled');
        }
    }

    applyFinalSidebarState() {
        if (this.isDisabledBySetting) return;

        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
            this.updateAutoHideState();
        });
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

        // Pin toggle button
        const pinToggleBtn = document.getElementById('sidebarPinToggle');
        if (pinToggleBtn) {
            pinToggleBtn.addEventListener('click', this.handlePinToggle);
        }

        // Collapse all button
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        if (collapseAllBtn) {
            collapseAllBtn.addEventListener('click', this.handleCollapseAll);
        }

        // Recursive toggle button
        const recursiveToggleBtn = document.getElementById('sidebarRecursiveToggle');
        if (recursiveToggleBtn) {
            recursiveToggleBtn.addEventListener('click', this.handleRecursiveToggle);
        }

        // Tree click handler
        const folderTree = document.getElementById('sidebarFolderTree');
        if (folderTree) {
            folderTree.addEventListener('click', this.handleTreeClick);
        }

        // Breadcrumb click handler
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        if (sidebarBreadcrumbNav) {
            sidebarBreadcrumbNav.addEventListener('click', this.handleBreadcrumbClick);
        }

        // Hover detection for auto-hide
        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');

        if (sidebar) {
            sidebar.addEventListener('mouseenter', this.handleMouseEnter);
            sidebar.addEventListener('mouseleave', this.handleMouseLeave);
        }

        if (hoverArea) {
            hoverArea.addEventListener('mouseenter', this.handleHoverAreaEnter);
            hoverArea.addEventListener('mouseleave', this.handleHoverAreaLeave);
        }

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024 && this.isVisible) {
                const sidebar = document.getElementById('folderSidebar');

                if (sidebar && !sidebar.contains(e.target)) {
                    this.hideSidebar();
                }
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            this.updateAutoHideState();
            this.updateContainerMargin();
        });

        // Add document click handler for closing dropdowns
        document.addEventListener('click', this.handleDocumentClick);

        // Add dedicated resize listener for container margin updates
        window.addEventListener('resize', this.updateContainerMargin);

        // Display mode toggle button
        const displayModeToggleBtn = document.getElementById('sidebarDisplayModeToggle');
        if (displayModeToggleBtn) {
            displayModeToggleBtn.addEventListener('click', this.handleDisplayModeToggle);
        }
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

    handlePinToggle(event) {
        event.stopPropagation();
        this.isPinned = !this.isPinned;
        this.updateAutoHideState();
        this.updatePinButton();
        this.saveSidebarState();
        this.updateContainerMargin();
    }

    handleCollapseAll(event) {
        event.stopPropagation();
        this.expandedNodes.clear();
        this.renderFolderDisplay();
        this.saveExpandedState();
    }

    handleMouseEnter() {
        this.isHovering = true;
        if (this.hoverTimeout) {
            clearTimeout(this.hoverTimeout);
            this.hoverTimeout = null;
        }

        if (!this.isPinned) {
            this.showSidebar();
        }
    }

    handleMouseLeave() {
        this.isHovering = false;
        if (!this.isPinned) {
            this.hoverTimeout = setTimeout(() => {
                if (!this.isHovering) {
                    this.hideSidebar();
                }
            }, 300);
        }
    }

    handleHoverAreaEnter() {
        if (!this.isPinned) {
            this.showSidebar();
        }
    }

    handleHoverAreaLeave() {
        // Let the sidebar's mouse leave handler deal with hiding
    }

    showSidebar() {
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar && !this.isPinned) {
            sidebar.classList.add('hover-active');
            this.isVisible = true;
            this.updateContainerMargin();
        }
    }

    hideSidebar() {
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar && !this.isPinned) {
            sidebar.classList.remove('hover-active');
            this.isVisible = false;
            this.updateContainerMargin();
        }
    }

    updateAutoHideState() {
        if (this.isDisabledBySetting) return;

        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');

        if (!sidebar || !hoverArea) return;

        if (window.innerWidth <= 1024) {
            // Mobile: always use collapsed state
            sidebar.classList.remove('auto-hide', 'hover-active', 'visible');
            sidebar.classList.add('collapsed');
            hoverArea.classList.add('disabled');
            this.isVisible = false;
        } else if (this.isPinned) {
            // Desktop pinned: always visible
            sidebar.classList.remove('auto-hide', 'collapsed', 'hover-active');
            sidebar.classList.add('visible');
            hoverArea.classList.add('disabled');
            this.isVisible = true;
        } else {
            // Desktop auto-hide: use hover detection
            sidebar.classList.remove('collapsed', 'visible');
            sidebar.classList.add('auto-hide');
            hoverArea.classList.remove('disabled');

            if (this.isHovering) {
                sidebar.classList.add('hover-active');
                this.isVisible = true;
            } else {
                sidebar.classList.remove('hover-active');
                this.isVisible = false;
            }
        }

        // Update container margin when sidebar state changes
        this.updateContainerMargin();
    }

    // New method to update container margin based on sidebar state
    updateContainerMargin() {
        const container = document.querySelector('.container');
        const sidebar = document.getElementById('folderSidebar');

        if (!container || !sidebar || this.isDisabledBySetting) return;

        // Reset margin to default
        container.style.marginLeft = '';

        // Only adjust margin if sidebar is visible and pinned
        if ((this.isPinned || this.isHovering) && this.isVisible) {
            const sidebarWidth = sidebar.offsetWidth;
            const viewportWidth = window.innerWidth;
            const containerWidth = container.offsetWidth;

            // Check if there's enough space for both sidebar and container
            // We need: sidebar width + container width + some padding < viewport width
            if (sidebarWidth + containerWidth + sidebarWidth > viewportWidth) {
                // Not enough space, push container to the right
                container.style.marginLeft = `${sidebarWidth + 10}px`;
            }
        }
    }

    updateDomVisibility(enabled) {
        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');

        if (sidebar) {
            sidebar.classList.toggle('hidden-by-setting', !enabled);
            sidebar.setAttribute('aria-hidden', (!enabled).toString());
        }

        if (hoverArea) {
            hoverArea.classList.toggle('hidden-by-setting', !enabled);
            if (!enabled) {
                hoverArea.classList.add('disabled');
            }
        }
    }

    async setSidebarEnabled(enabled) {
        this.isDisabledBySetting = !enabled;
        this.updateDomVisibility(enabled);

        const shouldForceInitialization = !enabled && !this.isInitialized;
        const needsInitialization = !this.isInitialized || shouldForceInitialization;

        if (this.lastPageControls && needsInitialization) {
            if (!this.initializationPromise) {
                this.initializationPromise = this.initialize(this.lastPageControls, {
                    forceInitialize: shouldForceInitialization,
                })
                    .catch((error) => {
                        console.error('Sidebar initialization failed:', error);
                    })
                    .finally(() => {
                        this.initializationPromise = null;
                    });
            }

            await this.initializationPromise;
        } else if (this.initializationPromise) {
            await this.initializationPromise;
        }

        if (!enabled) {
            this.isHovering = false;
            this.isVisible = false;

            const container = document.querySelector('.container');
            if (container) {
                container.style.marginLeft = '';
            }

            if (this.isInitialized) {
                this.updateBreadcrumbs();
                this.updateSidebarHeader();
            }

            return;
        }

        if (this.isInitialized) {
            this.updateAutoHideState();
        }
    }

    updatePinButton() {
        const pinBtn = document.getElementById('sidebarPinToggle');
        if (pinBtn) {
            pinBtn.classList.toggle('active', this.isPinned);
            pinBtn.title = this.isPinned
                ? translate('sidebar.unpinSidebar')
                : translate('sidebar.pinSidebar');
        }
    }

    async loadFolderTree() {
        try {
            if (this.displayMode === 'tree') {
                const response = await this.apiClient.fetchUnifiedFolderTree();
                this.treeData = response.tree || {};
            } else {
                const response = await this.apiClient.fetchModelFolders();
                this.foldersList = response.folders || [];
            }
            this.renderFolderDisplay();
        } catch (error) {
            console.error('Failed to load folder data:', error);
            this.renderEmptyState();
        }
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

            return `
                <div class="sidebar-tree-node" data-path="${currentPath}">
                    <div class="sidebar-tree-node-content ${isSelected ? 'selected' : ''}" data-path="${currentPath}">
                        <div class="sidebar-tree-expand-icon ${isExpanded ? 'expanded' : ''}" 
                             style="${hasChildren ? '' : 'opacity: 0; pointer-events: none;'}">
                            <i class="fas fa-chevron-right"></i>
                        </div>
                        <i class="fas fa-folder sidebar-tree-folder-icon"></i>
                        <div class="sidebar-tree-folder-name" title="${folderName}">${folderName}</div>
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

        folderTree.innerHTML = `
            <div class="sidebar-tree-placeholder">
                <i class="fas fa-folder-open"></i>
                <div>${translate('sidebar.empty.noFolders', {}, 'No folders found')}</div>
                <div class="sidebar-empty-hint">
                    <i class="fas fa-hand-pointer"></i>
                    ${translate('sidebar.empty.dragHint', {}, 'Drag items here to create folders')}
                </div>
            </div>
        `;
    }

    renderFolderList() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;

        if (!this.foldersList || this.foldersList.length === 0) {
            this.renderEmptyState();
            return;
        }

        const foldersHtml = this.foldersList.map(folder => {
            const displayName = folder === '' ? '/' : folder;
            const isSelected = this.selectedPath === folder;

            return `
                <div class="sidebar-folder-item ${isSelected ? 'selected' : ''}" data-path="${folder}">
                    <div class="sidebar-node-content" data-path="${folder}">
                        <i class="fas fa-folder sidebar-folder-icon"></i>
                        <div class="sidebar-folder-name" title="${displayName}">${displayName}</div>
                    </div>
                </div>
            `;
        }).join('');

        folderTree.innerHTML = foldersHtml;
    }

    handleTreeClick(event) {
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

        // Reload models with new filter
        await this.pageControls.resetAndReload();

        // Auto-hide sidebar on mobile after selection
        if (window.innerWidth <= 1024) {
            this.hideSidebar();
        }
    }

    handleFolderListClick(event) {
        const folderItem = event.target.closest('.sidebar-folder-item');

        if (folderItem) {
            const path = folderItem.dataset.path;
            this.selectFolder(path);
        }
    }

    handleDisplayModeToggle(event) {
        event.stopPropagation();
        this.displayMode = this.displayMode === 'tree' ? 'list' : 'tree';
        this.updateDisplayModeButton();
        this.updateCollapseAllButton();
        this.updateRecursiveToggleButton();
        this.updateSearchRecursiveOption();
        this.saveDisplayMode();
        this.loadFolderTree(); // Reload with new display mode
    }

    async handleRecursiveToggle(event) {
        event.stopPropagation();

        if (this.displayMode !== 'tree') {
            return;
        }

        this.recursiveSearchEnabled = !this.recursiveSearchEnabled;
        setStorageItem(`${this.pageType}_recursiveSearch`, this.recursiveSearchEnabled);
        this.updateSearchRecursiveOption();
        this.updateRecursiveToggleButton();

        if (this.pageControls && typeof this.pageControls.resetAndReload === 'function') {
            try {
                await this.pageControls.resetAndReload(true);
            } catch (error) {
                console.error('Failed to reload models after toggling recursive search:', error);
            }
        }
    }

    updateDisplayModeButton() {
        const displayModeBtn = document.getElementById('sidebarDisplayModeToggle');
        if (displayModeBtn) {
            const icon = displayModeBtn.querySelector('i');
            if (this.displayMode === 'tree') {
                icon.className = 'fas fa-sitemap';
                displayModeBtn.title = translate('sidebar.switchToListView');
            } else {
                icon.className = 'fas fa-list';
                displayModeBtn.title = translate('sidebar.switchToTreeView');
            }
        }
    }

    updateCollapseAllButton() {
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        if (collapseAllBtn) {
            if (this.displayMode === 'list') {
                collapseAllBtn.disabled = true;
                collapseAllBtn.classList.add('disabled');
                collapseAllBtn.title = translate('sidebar.collapseAllDisabled');
            } else {
                collapseAllBtn.disabled = false;
                collapseAllBtn.classList.remove('disabled');
                collapseAllBtn.title = translate('sidebar.collapseAll');
            }
        }
    }

    updateRecursiveToggleButton() {
        const recursiveToggleBtn = document.getElementById('sidebarRecursiveToggle');
        if (!recursiveToggleBtn) return;

        const icon = recursiveToggleBtn.querySelector('i');
        const isTreeMode = this.displayMode === 'tree';
        const isActive = isTreeMode && this.recursiveSearchEnabled;

        recursiveToggleBtn.classList.toggle('active', isActive);
        recursiveToggleBtn.classList.toggle('disabled', !isTreeMode);
        recursiveToggleBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        recursiveToggleBtn.setAttribute('aria-disabled', isTreeMode ? 'false' : 'true');

        if (icon) {
            icon.className = 'fas fa-code-branch';
        }

        if (!isTreeMode) {
            recursiveToggleBtn.title = translate('sidebar.recursiveUnavailable');
        } else if (this.recursiveSearchEnabled) {
            recursiveToggleBtn.title = translate('sidebar.recursiveOn');
        } else {
            recursiveToggleBtn.title = translate('sidebar.recursiveOff');
        }
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
                const selectedItem = folderTree.querySelector(`[data-path="${this.selectedPath}"]`);
                if (selectedItem) {
                    selectedItem.classList.add('selected');
                }
            }
        } else {
            folderTree.querySelectorAll('.sidebar-tree-node-content').forEach(node => {
                node.classList.remove('selected');
            });

            if (this.selectedPath !== null && this.selectedPath !== undefined) {
                const selectedNode = folderTree.querySelector(`[data-path="${this.selectedPath}"] .sidebar-tree-node-content`);
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
                    <i class="fas fa-home"></i> ${this.apiClient.apiConfig.config.displayName} root
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
                                <div class="breadcrumb-dropdown-item" data-path="${folder}">
                                    ${folder}
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

            breadcrumbs.push(`<span class="sidebar-breadcrumb-separator">/</span>`);
            breadcrumbs.push(`
                <div class="breadcrumb-dropdown">
                    <span class="sidebar-breadcrumb-item ${isLast ? 'active' : ''}" data-path="${currentPath}">
                        ${part}
                        ${siblings.length > 1 ? `
                            <span class="breadcrumb-dropdown-indicator">
                                <i class="fas fa-caret-down"></i>
                            </span>
                        ` : ''}
                    </span>
                    ${siblings.length > 1 ? `
                        <div class="breadcrumb-dropdown-menu">
                            ${siblings.map(folder => `
                                <div class="breadcrumb-dropdown-item ${folder === part ? 'active' : ''}" 
                                     data-path="${currentPath.replace(part, folder)}">
                                    ${folder}
                                </div>`).join('')
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
                                    <div class="breadcrumb-dropdown-item" data-path="${currentPath}/${folder}">
                                        ${folder}
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

    toggleSidebar() {
        const sidebar = document.getElementById('folderSidebar');
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');

        if (!sidebar) return;

        this.isVisible = !this.isVisible;

        if (this.isVisible) {
            sidebar.classList.remove('collapsed');
            sidebar.classList.add('visible');
        } else {
            sidebar.classList.remove('visible');
            sidebar.classList.add('collapsed');
        }

        if (toggleBtn) {
            toggleBtn.classList.toggle('active', this.isVisible);
        }

        this.saveSidebarState();
    }

    closeSidebar() {
        const sidebar = document.getElementById('folderSidebar');
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');

        if (!sidebar) return;

        this.isVisible = false;
        sidebar.classList.remove('visible');
        sidebar.classList.add('collapsed');

        if (toggleBtn) {
            toggleBtn.classList.remove('active');
        }

        this.saveSidebarState();
    }

    restoreSidebarState() {
        const isPinned = getStorageItem(`${this.pageType}_sidebarPinned`, true);
        const expandedPaths = getStorageItem(`${this.pageType}_expandedNodes`, []);
        const displayMode = getStorageItem(`${this.pageType}_displayMode`, 'tree'); // 'tree' or 'list', default to 'tree'
        const recursiveSearchEnabled = getStorageItem(`${this.pageType}_recursiveSearch`, true);

        this.isPinned = isPinned;
        this.expandedNodes = new Set(expandedPaths);
        this.displayMode = displayMode;
        this.recursiveSearchEnabled = recursiveSearchEnabled;

        this.updatePinButton();
        this.updateDisplayModeButton();
        this.updateCollapseAllButton();
        this.updateSearchRecursiveOption();
        this.updateRecursiveToggleButton();
    }

    restoreSelectedFolder() {
        const activeFolder = getStorageItem(`${this.pageType}_activeFolder`);
        if (activeFolder && typeof activeFolder === 'string') {
            this.selectedPath = activeFolder;
            this.updateTreeSelection();
            this.updateBreadcrumbs();
            this.updateSidebarHeader();
        } else {
            this.selectedPath = '';
            this.updateSidebarHeader();
            this.updateBreadcrumbs(); // Always update breadcrumbs
        }
        // Removed hidden class toggle since breadcrumbs are always visible now
    }

    saveSidebarState() {
        setStorageItem(`${this.pageType}_sidebarPinned`, this.isPinned);
    }

    saveExpandedState() {
        setStorageItem(`${this.pageType}_expandedNodes`, Array.from(this.expandedNodes));
    }

    saveDisplayMode() {
        setStorageItem(`${this.pageType}_displayMode`, this.displayMode);
    }

    async refresh() {
        if (this.isDisabledBySetting || !this.isInitialized) {
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
