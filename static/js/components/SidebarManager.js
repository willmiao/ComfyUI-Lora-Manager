/**
 * SidebarManager - Manages hierarchical folder navigation sidebar
 */
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';

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
    }

    async initialize(pageControls) {
        // Clean up previous initialization if exists
        if (this.isInitialized) {
            this.cleanup();
        }

        this.pageControls = pageControls;
        this.pageType = pageControls.pageType;
        this.apiClient = getModelApiClient();
        
        // Set initial sidebar state immediately (hidden by default)
        this.setInitialSidebarState();
        
        this.setupEventHandlers();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        await this.loadFolderTree();
        this.restoreSelectedFolder();
        
        // Apply final state with animation after everything is loaded
        this.applyFinalSidebarState();
        
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
        
        console.log('SidebarManager cleaned up');
    }

    removeEventHandlers() {
        const pinToggleBtn = document.getElementById('sidebarPinToggle');
        const collapseAllBtn = document.getElementById('sidebarCollapseAll');
        const folderTree = document.getElementById('sidebarFolderTree');
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        const sidebarHeader = document.getElementById('sidebarHeader');
        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');

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
    }

    async init() {
        this.apiClient = getModelApiClient();
        
        // Set initial sidebar state immediately (hidden by default)
        this.setInitialSidebarState();
        
        this.setupEventHandlers();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        await this.loadFolderTree();
        this.restoreSelectedFolder();
        
        // Apply final state with animation after everything is loaded
        this.applyFinalSidebarState();
    }

    setInitialSidebarState() {
        const sidebar = document.getElementById('folderSidebar');
        const hoverArea = document.getElementById('sidebarHoverArea');
        
        if (!sidebar || !hoverArea) return;
        
        // Get stored pin state
        const isPinned = getStorageItem(`${this.pageType}_sidebarPinned`, false);
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
        // Use requestAnimationFrame to ensure DOM is ready
        requestAnimationFrame(() => {
            this.updateAutoHideState();
        });
    }

    updateSidebarTitle() {
        const sidebarTitle = document.getElementById('sidebarTitle');
        if (sidebarTitle) {
            sidebarTitle.textContent = `${this.apiClient.apiConfig.config.displayName} Root`;
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
        });

        // Add document click handler for closing dropdowns
        document.addEventListener('click', this.handleDocumentClick);
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
            this.selectFolder('');
        }
    }

    handlePinToggle(event) {
        event.stopPropagation();
        this.isPinned = !this.isPinned;
        this.updateAutoHideState();
        this.updatePinButton();
        this.saveSidebarState();
    }

    handleCollapseAll(event) {
        event.stopPropagation();
        this.expandedNodes.clear();
        this.renderTree();
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
        }
    }

    hideSidebar() {
        const sidebar = document.getElementById('folderSidebar');
        if (sidebar && !this.isPinned) {
            sidebar.classList.remove('hover-active');
            this.isVisible = false;
        }
    }

    updateAutoHideState() {
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
    }

    updatePinButton() {
        const pinBtn = document.getElementById('sidebarPinToggle');
        if (pinBtn) {
            pinBtn.classList.toggle('active', this.isPinned);
            pinBtn.title = this.isPinned ? 'Unpin Sidebar' : 'Pin Sidebar';
        }
    }

    async loadFolderTree() {
        try {
            const response = await this.apiClient.fetchUnifiedFolderTree();
            this.treeData = response.tree || {};
            this.renderTree();
        } catch (error) {
            console.error('Failed to load folder tree:', error);
            this.renderEmptyState();
        }
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
                    <div class="sidebar-tree-node-content ${isSelected ? 'selected' : ''}">
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
                <div>No folders found</div>
            </div>
        `;
    }

    handleTreeClick(event) {
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
            const path = breadcrumbItem.dataset.path || '';
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
        // Update selected path
        this.selectedPath = path;
        
        // Update UI
        this.updateTreeSelection();
        this.updateBreadcrumbs();
        this.updateSidebarHeader();
        
        // Update page state
        this.pageControls.pageState.activeFolder = path || null;
        setStorageItem(`${this.pageType}_activeFolder`, path || null);
        
        // Reload models with new filter
        await this.pageControls.resetAndReload();
        
        // Auto-hide sidebar on mobile after selection
        if (window.innerWidth <= 1024) {
            this.hideSidebar();
        }
    }

    updateTreeSelection() {
        const folderTree = document.getElementById('sidebarFolderTree');
        if (!folderTree) return;
        
        // Remove all selections
        folderTree.querySelectorAll('.sidebar-tree-node-content').forEach(node => {
            node.classList.remove('selected');
        });
        
        // Add selection to current path
        if (this.selectedPath) {
            const selectedNode = folderTree.querySelector(`[data-path="${this.selectedPath}"] .sidebar-tree-node-content`);
            if (selectedNode) {
                selectedNode.classList.add('selected');
                
                // Expand parents to show selection
                this.expandPathParents(this.selectedPath);
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
        const breadcrumbs = [`
            <div class="breadcrumb-dropdown">
                <span class="sidebar-breadcrumb-item ${!this.selectedPath ? 'active' : ''}" data-path="">
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
        const isPinned = getStorageItem(`${this.pageType}_sidebarPinned`, false);
        const expandedPaths = getStorageItem(`${this.pageType}_expandedNodes`, []);
        
        this.isPinned = isPinned;
        this.expandedNodes = new Set(expandedPaths);
        
        this.updatePinButton();
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

    async refresh() {
        await this.loadFolderTree();
        this.restoreSelectedFolder();
    }

    destroy() {
        this.cleanup();
    }
}

// Create and export global instance
export const sidebarManager = new SidebarManager();