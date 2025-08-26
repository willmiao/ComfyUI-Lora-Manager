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
        
        // Bind methods
        this.handleTreeClick = this.handleTreeClick.bind(this);
        this.handleBreadcrumbClick = this.handleBreadcrumbClick.bind(this);
        this.toggleSidebar = this.toggleSidebar.bind(this);
        this.closeSidebar = this.closeSidebar.bind(this);
        
        this.init();
    }

    async init() {
        this.apiClient = getModelApiClient();
        this.setupEventHandlers();
        this.restoreSidebarState();
        await this.loadFolderTree();
        this.restoreSelectedFolder();
    }

    setupEventHandlers() {
        // Sidebar toggle button
        const toggleBtn = document.querySelector('.sidebar-toggle-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', this.toggleSidebar);
        }

        // Sidebar close button
        const closeBtn = document.getElementById('sidebarCloseBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', this.closeSidebar);
        }

        // Tree click handler
        const folderTree = document.getElementById('sidebarFolderTree');
        if (folderTree) {
            folderTree.addEventListener('click', this.handleTreeClick);
        }

        // Breadcrumb click handler
        const breadcrumbNav = document.getElementById('breadcrumbNav');
        if (breadcrumbNav) {
            breadcrumbNav.addEventListener('click', this.handleBreadcrumbClick);
        }

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024) {
                const sidebar = document.getElementById('folderSidebar');
                const toggleBtn = document.querySelector('.sidebar-toggle-btn');
                
                if (sidebar && !sidebar.contains(e.target) && 
                    toggleBtn && !toggleBtn.contains(e.target) && 
                    !sidebar.classList.contains('collapsed')) {
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
                        <div class="sidebar-tree-folder-icon">
                            <i class="fas fa-folder"></i>
                        </div>
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
        const breadcrumbItem = event.target.closest('.breadcrumb-item');
        if (breadcrumbItem) {
            const path = breadcrumbItem.dataset.path || '';
            this.selectFolder(path);
        }
    }

    async selectFolder(path) {
        // Update selected path
        this.selectedPath = path;
        
        // Update UI
        this.updateTreeSelection();
        this.updateBreadcrumbs();
        
        // Update page state
        this.pageControls.pageState.activeFolder = path || null;
        setStorageItem(`${this.pageType}_activeFolder`, path || null);
        
        // Show/hide breadcrumb container
        const breadcrumbContainer = document.getElementById('breadcrumbContainer');
        if (breadcrumbContainer) {
            breadcrumbContainer.classList.toggle('hidden', !path);
        }
        
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

    updateBreadcrumbs() {
        const breadcrumbNav = document.getElementById('breadcrumbNav');
        if (!breadcrumbNav) return;
        
        const parts = this.selectedPath ? this.selectedPath.split('/') : [];
        let currentPath = '';
        
        const breadcrumbs = [`
            <span class="breadcrumb-item ${!this.selectedPath ? 'active' : ''}" data-path="">
                <i class="fas fa-home"></i> All Folders
            </span>
        `];
        
        parts.forEach((part, index) => {
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            const isLast = index === parts.length - 1;
            
            breadcrumbs.push(`<span class="breadcrumb-separator">/</span>`);
            breadcrumbs.push(`
                <span class="breadcrumb-item ${isLast ? 'active' : ''}" data-path="${currentPath}">
                    ${part}
                </span>
            `);
        });
        
        breadcrumbNav.innerHTML = breadcrumbs.join('');
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
            
            // Show breadcrumb container
            const breadcrumbContainer = document.getElementById('breadcrumbContainer');
            if (breadcrumbContainer) {
                breadcrumbContainer.classList.remove('hidden');
            }
        }
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
        const closeBtn = document.getElementById('sidebarCloseBtn');
        const folderTree = document.getElementById('sidebarFolderTree');
        const breadcrumbNav = document.getElementById('breadcrumbNav');

        if (toggleBtn) {
            toggleBtn.removeEventListener('click', this.toggleSidebar);
        }
        if (closeBtn) {
            closeBtn.removeEventListener('click', this.closeSidebar);
        }
        if (folderTree) {
            folderTree.removeEventListener('click', this.handleTreeClick);
        }
        if (breadcrumbNav) {
            breadcrumbNav.removeEventListener('click', this.handleBreadcrumbClick);
        }
    }
}
