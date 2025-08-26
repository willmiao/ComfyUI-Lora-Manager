/**
 * SidebarManager - Manages hierarchical folder navigation sidebar
 */
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { getModelApiClient } from '../api/modelApiFactory.js';

export class SidebarManager {
    constructor(pageControls) {
        this.pageControls = pageControls;
        this.pageType = pageControls.pageType;
        this.treeData = {};
        this.selectedPath = '';
        this.expandedNodes = new Set();
        this.isVisible = true;
        this.apiClient = null;
        this.openDropdown = null;
        
        // Bind methods
        this.handleTreeClick = this.handleTreeClick.bind(this);
        this.handleBreadcrumbClick = this.handleBreadcrumbClick.bind(this);
        this.toggleSidebar = this.toggleSidebar.bind(this);
        this.closeSidebar = this.closeSidebar.bind(this);
        this.handleDocumentClick = this.handleDocumentClick.bind(this);
        
        this.init();
    }

    async init() {
        this.apiClient = getModelApiClient();
        this.setupEventHandlers();
        this.updateSidebarTitle();
        this.restoreSidebarState();
        await this.loadFolderTree();
        this.restoreSelectedFolder();
    }

    updateSidebarTitle() {
        const sidebarTitle = document.getElementById('sidebarTitle');
        if (sidebarTitle) {
            sidebarTitle.textContent = `${this.apiClient.apiConfig.config.displayName} Root`;
        }
    }

    setupEventHandlers() {
        // Sidebar toggle button
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', this.toggleSidebar);
        }

        // Sidebar header (root selection)
        const sidebarHeader = document.getElementById('sidebarHeader');
        if (sidebarHeader) {
            sidebarHeader.addEventListener('click', () => this.selectFolder(''));
        }

        // Sidebar close button
        const closeBtn = document.getElementById('sidebarToggleClose');
        if (closeBtn) {
            closeBtn.addEventListener('click', this.closeSidebar);
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

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024 && this.isVisible) {
                const sidebar = document.getElementById('folderSidebar');
                const toggleBtn = document.querySelector('.sidebar-toggle-btn');
                
                if (sidebar && !sidebar.contains(e.target) && 
                    toggleBtn && !toggleBtn.contains(e.target)) {
                    this.closeSidebar();
                }
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth > 1024 && this.isVisible) {
                const sidebar = document.getElementById('folderSidebar');
                if (sidebar) {
                    sidebar.classList.remove('collapsed');
                }
            }
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

    closeDropdown() {
        if (this.openDropdown) {
            this.openDropdown.classList.remove('open');
            this.openDropdown = null;
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
        
        // Always show breadcrumb container
        // Removed hiding breadcrumb container code
        
        // Reload models with new filter
        await this.pageControls.resetAndReload();
        
        // Auto-close sidebar on mobile after selection
        if (window.innerWidth <= 1024) {
            this.closeSidebar();
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
        sidebar.classList.toggle('collapsed', !this.isVisible);
        
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
        sidebar.classList.add('collapsed');
        
        if (toggleBtn) {
            toggleBtn.classList.remove('active');
        }
        
        this.saveSidebarState();
    }

    restoreSidebarState() {
        const isVisible = getStorageItem(`${this.pageType}_sidebarVisible`, true);
        const expandedPaths = getStorageItem(`${this.pageType}_expandedNodes`, []);
        
        this.isVisible = isVisible;
        this.expandedNodes = new Set(expandedPaths);
        
        const sidebar = document.getElementById('folderSidebar');
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');
        
        if (sidebar) {
            sidebar.classList.toggle('collapsed', !this.isVisible);
        }
        
        if (toggleBtn) {
            toggleBtn.classList.toggle('active', this.isVisible);
        }
    }

    restoreSelectedFolder() {
        const activeFolder = getStorageItem(`${this.pageType}_activeFolder`);
        if (activeFolder) {
            this.selectedPath = activeFolder;
            this.updateTreeSelection();
            this.updateBreadcrumbs();
            this.updateSidebarHeader();
        } else {
            this.updateSidebarHeader();
            this.updateBreadcrumbs(); // Always update breadcrumbs
        }
        // Removed hidden class toggle since breadcrumbs are always visible now
    }

    saveSidebarState() {
        setStorageItem(`${this.pageType}_sidebarVisible`, this.isVisible);
    }

    saveExpandedState() {
        setStorageItem(`${this.pageType}_expandedNodes`, Array.from(this.expandedNodes));
    }

    async refresh() {
        await this.loadFolderTree();
        this.restoreSelectedFolder();
    }

    destroy() {
        // Clean up event handlers
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');
        const closeBtn = document.getElementById('sidebarToggleClose');
        const folderTree = document.getElementById('sidebarFolderTree');
        const sidebarBreadcrumbNav = document.getElementById('sidebarBreadcrumbNav');
        const sidebarHeader = document.getElementById('sidebarHeader');

        if (toggleBtn) {
            toggleBtn.removeEventListener('click', this.toggleSidebar);
        }
        if (closeBtn) {
            closeBtn.removeEventListener('click', this.closeSidebar);
        }
        if (folderTree) {
            folderTree.removeEventListener('click', this.handleTreeClick);
        }
        if (sidebarBreadcrumbNav) {
            sidebarBreadcrumbNav.removeEventListener('click', this.handleBreadcrumbClick);
        }
        if (sidebarHeader) {
            sidebarHeader.removeEventListener('click', () => this.selectFolder(''));
        }
        
        // Remove document click handler
        document.removeEventListener('click', this.handleDocumentClick);
    }
}
