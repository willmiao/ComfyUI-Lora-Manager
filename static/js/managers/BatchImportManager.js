import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { WS_ENDPOINTS } from '../api/apiConfig.js';

/**
 * Manager for batch importing recipes from multiple images
 */
export class BatchImportManager {
    constructor() {
        this.initialized = false;
        this.inputMode = 'urls'; // 'urls' or 'directory'
        this.operationId = null;
        this.wsConnection = null;
        this.pollingInterval = null;
        this.progress = null;
        this.results = null;
        this.isCancelled = false;
    }

    /**
     * Show the batch import modal
     */
    showModal() {
        if (!this.initialized) {
            this.initialize();
        }
        this.resetState();
        modalManager.showModal('batchImportModal');
    }

    /**
     * Initialize the manager
     */
    initialize() {
        this.initialized = true;
    }

    /**
     * Reset all state to initial values
     */
    resetState() {
        this.inputMode = 'urls';
        this.operationId = null;
        this.progress = null;
        this.results = null;
        this.isCancelled = false;

        // Reset UI
        this.showStep('batchInputStep');
        this.toggleInputMode('urls');
        
        // Clear inputs
        const urlInput = document.getElementById('batchUrlInput');
        if (urlInput) urlInput.value = '';
        
        const directoryInput = document.getElementById('batchDirectoryInput');
        if (directoryInput) directoryInput.value = '';
        
        const tagsInput = document.getElementById('batchTagsInput');
        if (tagsInput) tagsInput.value = '';
        
        const skipNoMetadata = document.getElementById('batchSkipNoMetadata');
        if (skipNoMetadata) skipNoMetadata.checked = true;
        
        const recursiveCheck = document.getElementById('batchRecursiveCheck');
        if (recursiveCheck) recursiveCheck.checked = true;

        // Reset progress UI
        this.updateProgressUI({
            total: 0,
            completed: 0,
            success: 0,
            failed: 0,
            skipped: 0,
            progress_percent: 0,
            current_item: '',
            status: 'pending'
        });

        // Reset results
        const detailsList = document.getElementById('batchDetailsList');
        if (detailsList) {
            detailsList.innerHTML = '';
            detailsList.style.display = 'none';
        }

        const toggleIcon = document.getElementById('resultsToggleIcon');
        if (toggleIcon) {
            toggleIcon.classList.remove('expanded');
        }

        // Clean up any existing connections
        this.cleanupConnections();
    }

    /**
     * Show a specific step in the modal
     */
    showStep(stepId) {
        document.querySelectorAll('.batch-import-step').forEach(step => {
            step.style.display = 'none';
        });
        
        const step = document.getElementById(stepId);
        if (step) {
            step.style.display = 'block';
        }
    }

    /**
     * Toggle between URL list and directory input modes
     */
    toggleInputMode(mode) {
        this.inputMode = mode;

        // Update toggle buttons
        document.querySelectorAll('.toggle-btn[data-mode]').forEach(btn => {
            btn.classList.remove('active');
        });
        
        const activeBtn = document.querySelector(`.toggle-btn[data-mode="${mode}"]`);
        if (activeBtn) {
            activeBtn.classList.add('active');
        }

        // Show/hide appropriate sections
        const urlSection = document.getElementById('urlListSection');
        const directorySection = document.getElementById('directorySection');

        if (urlSection && directorySection) {
            if (mode === 'urls') {
                urlSection.style.display = 'block';
                directorySection.style.display = 'none';
            } else {
                urlSection.style.display = 'none';
                directorySection.style.display = 'block';
            }
        }
    }

    /**
     * Start the batch import process
     */
    async startImport() {
        const data = this.collectInputData();
        
        if (!this.validateInput(data)) {
            return;
        }

        try {
            // Show progress step
            this.showStep('batchProgressStep');
            
            // Start the import
            const response = await this.sendStartRequest(data);
            
            if (response.success) {
                this.operationId = response.operation_id;
                this.isCancelled = false;
                
                // Connect to WebSocket for real-time updates
                this.connectWebSocket();
                
                // Start polling as fallback
                this.startPolling();
            } else {
                showToast('toast.recipes.batchImportFailed', { message: response.error }, 'error');
                this.showStep('batchInputStep');
            }
        } catch (error) {
            console.error('Error starting batch import:', error);
            showToast('toast.recipes.batchImportFailed', { message: error.message }, 'error');
            this.showStep('batchInputStep');
        }
    }

    /**
     * Collect input data from the form
     */
    collectInputData() {
        const data = {
            mode: this.inputMode,
            tags: [],
            skip_no_metadata: false
        };

        // Collect tags
        const tagsInput = document.getElementById('batchTagsInput');
        if (tagsInput && tagsInput.value.trim()) {
            data.tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t);
        }

        // Collect skip_no_metadata
        const skipNoMetadata = document.getElementById('batchSkipNoMetadata');
        if (skipNoMetadata) {
            data.skip_no_metadata = skipNoMetadata.checked;
        }

        if (this.inputMode === 'urls') {
            const urlInput = document.getElementById('batchUrlInput');
            if (urlInput) {
                const urls = urlInput.value.split('\n')
                    .map(line => line.trim())
                    .filter(line => line.length > 0);
                
                // Convert to items format
                data.items = urls.map(url => ({
                    source: url,
                    type: this.detectUrlType(url)
                }));
            }
        } else {
            const directoryInput = document.getElementById('batchDirectoryInput');
            if (directoryInput) {
                data.directory = directoryInput.value.trim();
            }
            
            const recursiveCheck = document.getElementById('batchRecursiveCheck');
            if (recursiveCheck) {
                data.recursive = recursiveCheck.checked;
            }
        }

        return data;
    }

    /**
     * Detect if a URL is http or local path
     */
    detectUrlType(url) {
        if (url.startsWith('http://') || url.startsWith('https://')) {
            return 'url';
        }
        return 'local_path';
    }

    /**
     * Validate the input data
     */
    validateInput(data) {
        if (data.mode === 'urls') {
            if (!data.items || data.items.length === 0) {
                showToast('toast.recipes.batchImportNoUrls', {}, 'error');
                return false;
            }
        } else {
            if (!data.directory) {
                showToast('toast.recipes.batchImportNoDirectory', {}, 'error');
                return false;
            }
        }
        return true;
    }

    /**
     * Send the start batch import request
     */
    async sendStartRequest(data) {
        const endpoint = data.mode === 'urls' 
            ? '/api/lm/recipes/batch-import/start'
            : '/api/lm/recipes/batch-import/directory';

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        return await response.json();
    }

    /**
     * Connect to WebSocket for real-time progress updates
     */
    connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/batch-import-progress?id=${this.operationId}`;
        
        this.wsConnection = new WebSocket(wsUrl);
        
        this.wsConnection.onopen = () => {
            console.log('Connected to batch import progress WebSocket');
        };
        
        this.wsConnection.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'batch_import_progress') {
                    this.handleProgressUpdate(data);
                }
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        this.wsConnection.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.wsConnection.onclose = () => {
            console.log('WebSocket connection closed');
        };
    }

    /**
     * Start polling for progress updates (fallback)
     */
    startPolling() {
        this.pollingInterval = setInterval(async () => {
            if (!this.operationId || this.isCancelled) {
                return;
            }
            
            try {
                const response = await fetch(`/api/lm/recipes/batch-import/progress?operation_id=${this.operationId}`);
                const data = await response.json();
                
                if (data.success && data.progress) {
                    this.handleProgressUpdate(data.progress);
                }
            } catch (error) {
                console.error('Error polling progress:', error);
            }
        }, 1000);
    }

    /**
     * Handle progress update from WebSocket or polling
     */
    handleProgressUpdate(progress) {
        this.progress = progress;
        this.updateProgressUI(progress);
        
        // Check if import is complete
        if (progress.status === 'completed' || progress.status === 'cancelled' || 
            (progress.total > 0 && progress.completed >= progress.total)) {
            this.importComplete(progress);
        }
    }

    /**
     * Update the progress UI
     */
    updateProgressUI(progress) {
        // Update progress bar
        const progressBar = document.getElementById('batchProgressBar');
        if (progressBar) {
            progressBar.style.width = `${progress.progress_percent || 0}%`;
        }
        
        // Update percentage
        const progressPercent = document.getElementById('batchProgressPercent');
        if (progressPercent) {
            progressPercent.textContent = `${Math.round(progress.progress_percent || 0)}%`;
        }
        
        // Update stats
        const totalCount = document.getElementById('batchTotalCount');
        if (totalCount) totalCount.textContent = progress.total || 0;
        
        const successCount = document.getElementById('batchSuccessCount');
        if (successCount) successCount.textContent = progress.success || 0;
        
        const failedCount = document.getElementById('batchFailedCount');
        if (failedCount) failedCount.textContent = progress.failed || 0;
        
        const skippedCount = document.getElementById('batchSkippedCount');
        if (skippedCount) skippedCount.textContent = progress.skipped || 0;
        
        // Update current item
        const currentItem = document.getElementById('batchCurrentItem');
        if (currentItem) {
            currentItem.textContent = progress.current_item || '-';
        }
        
        // Update status text
        const statusText = document.getElementById('batchStatusText');
        if (statusText) {
            if (progress.status === 'running') {
                statusText.textContent = translate('recipes.batchImport.importing', {}, 'Importing...');
            } else if (progress.status === 'completed') {
                statusText.textContent = translate('recipes.batchImport.completed', {}, 'Import completed');
            } else if (progress.status === 'cancelled') {
                statusText.textContent = translate('recipes.batchImport.cancelled', {}, 'Import cancelled');
            }
        }

        // Update container classes
        const progressContainer = document.querySelector('.batch-progress-container');
        if (progressContainer) {
            progressContainer.classList.remove('completed', 'cancelled', 'error');
            if (progress.status === 'completed') {
                progressContainer.classList.add('completed');
            } else if (progress.status === 'cancelled') {
                progressContainer.classList.add('cancelled');
            } else if (progress.failed > 0 && progress.failed === progress.total) {
                progressContainer.classList.add('error');
            }
        }
    }

    /**
     * Handle import completion
     */
    importComplete(progress) {
        this.cleanupConnections();
        this.results = progress;
        
        // Refresh recipes list to show newly imported recipes
        if (window.recipeManager && typeof window.recipeManager.loadRecipes === 'function') {
            window.recipeManager.loadRecipes();
        }
        
        // Show results step
        this.showStep('batchResultsStep');
        this.updateResultsUI(progress);
    }

    /**
     * Update the results UI
     */
    updateResultsUI(progress) {
        // Update summary cards
        const resultsTotal = document.getElementById('resultsTotal');
        if (resultsTotal) resultsTotal.textContent = progress.total || 0;
        
        const resultsSuccess = document.getElementById('resultsSuccess');
        if (resultsSuccess) resultsSuccess.textContent = progress.success || 0;
        
        const resultsFailed = document.getElementById('resultsFailed');
        if (resultsFailed) resultsFailed.textContent = progress.failed || 0;
        
        const resultsSkipped = document.getElementById('resultsSkipped');
        if (resultsSkipped) resultsSkipped.textContent = progress.skipped || 0;
        
        // Update header based on results
        const resultsHeader = document.getElementById('batchResultsHeader');
        if (resultsHeader) {
            const icon = resultsHeader.querySelector('.results-icon i');
            const title = resultsHeader.querySelector('.results-title');
            
                if (this.isCancelled) {
                if (icon) {
                    icon.className = 'fas fa-stop-circle';
                    icon.parentElement.classList.add('warning');
                }
                if (title) title.textContent = translate('recipes.batchImport.cancelled', {}, 'Import cancelled');
            } else if (progress.failed === 0 && progress.success > 0) {
                if (icon) {
                    icon.className = 'fas fa-check-circle';
                    icon.parentElement.classList.remove('warning', 'error');
                }
                if (title) title.textContent = translate('recipes.batchImport.completed', {}, 'Import completed');
            } else if (progress.failed > 0 && progress.success === 0) {
                if (icon) {
                    icon.className = 'fas fa-times-circle';
                    icon.parentElement.classList.add('error');
                }
                if (title) title.textContent = translate('recipes.batchImport.failed', {}, 'Import failed');
            } else {
                if (icon) {
                    icon.className = 'fas fa-exclamation-circle';
                    icon.parentElement.classList.add('warning');
                }
                if (title) title.textContent = translate('recipes.batchImport.completedWithErrors', {}, 'Completed with errors');
            }
        }
    }

    /**
     * Toggle the results details visibility
     */
    toggleResultsDetails() {
        const detailsList = document.getElementById('batchDetailsList');
        const toggleIcon = document.getElementById('resultsToggleIcon');
        const toggle = document.querySelector('.details-toggle');
        
        if (detailsList && toggleIcon) {
            if (detailsList.style.display === 'none') {
                detailsList.style.display = 'block';
                toggleIcon.classList.add('expanded');
                if (toggle) toggle.classList.add('expanded');
                
                // Load details if not loaded
                if (detailsList.children.length === 0 && this.results && this.results.items) {
                    this.loadResultsDetails(this.results.items);
                }
            } else {
                detailsList.style.display = 'none';
                toggleIcon.classList.remove('expanded');
                if (toggle) toggle.classList.remove('expanded');
            }
        }
    }

    /**
     * Load results details into the list
     */
    loadResultsDetails(items) {
        const detailsList = document.getElementById('batchDetailsList');
        if (!detailsList) return;
        
        detailsList.innerHTML = '';
        
        items.forEach(item => {
            const resultItem = document.createElement('div');
            resultItem.className = 'result-item';
            
            const statusClass = item.status === 'success' ? 'success' : 
                               item.status === 'failed' ? 'failed' : 'skipped';
            const statusIcon = item.status === 'success' ? 'check' : 
                              item.status === 'failed' ? 'times' : 'forward';
            
            resultItem.innerHTML = `
                <div class="result-item-status ${statusClass}">
                    <i class="fas fa-${statusIcon}"></i>
                </div>
                <div class="result-item-info">
                    <div class="result-item-name">${this.escapeHtml(item.source || item.current_item || 'Unknown')}</div>
                    ${item.error_message ? `<div class="result-item-error">${this.escapeHtml(item.error_message)}</div>` : ''}
                </div>
            `;
            
            detailsList.appendChild(resultItem);
        });
    }

    /**
     * Cancel the current import
     */
    async cancelImport() {
        if (!this.operationId) return;
        
        this.isCancelled = true;
        
        try {
            const response = await fetch('/api/lm/recipes/batch-import/cancel', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ operation_id: this.operationId })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showToast('toast.recipes.batchImportCancelling', {}, 'info');
            } else {
                showToast('toast.recipes.batchImportCancelFailed', { message: data.error }, 'error');
            }
        } catch (error) {
            console.error('Error cancelling import:', error);
            showToast('toast.recipes.batchImportCancelFailed', { message: error.message }, 'error');
        }
    }

    /**
     * Close modal and reset state
     */
    closeAndReset() {
        this.cleanupConnections();
        this.resetState();
        modalManager.closeModal('batchImportModal');
    }

    /**
     * Start a new import (from results step)
     */
    startNewImport() {
        this.resetState();
        this.showStep('batchInputStep');
    }

    /**
     * Toggle directory browser visibility
     */
    toggleDirectoryBrowser() {
        const browser = document.getElementById('batchDirectoryBrowser');
        if (browser) {
            const isVisible = browser.style.display !== 'none';
            browser.style.display = isVisible ? 'none' : 'block';
            
            if (!isVisible) {
                // Load initial directory when opening
                const currentPath = document.getElementById('batchDirectoryInput').value;
                this.loadDirectory(currentPath || '/');
            }
        }
    }

    /**
     * Load directory contents
     */
    async loadDirectory(path) {
        try {
            const response = await fetch('/api/lm/recipes/browse-directory', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ path })
            });

            const data = await response.json();

            if (data.success) {
                this.renderDirectoryBrowser(data);
            } else {
                showToast('toast.recipes.batchImportBrowseFailed', { message: data.error }, 'error');
            }
        } catch (error) {
            console.error('Error loading directory:', error);
            showToast('toast.recipes.batchImportBrowseFailed', { message: error.message }, 'error');
        }
    }

    /**
     * Render directory browser UI
     */
    renderDirectoryBrowser(data) {
        const currentPathEl = document.getElementById('batchCurrentPath');
        const folderList = document.getElementById('batchFolderList');
        const fileList = document.getElementById('batchFileList');
        const directoryCount = document.getElementById('batchDirectoryCount');
        const imageCount = document.getElementById('batchImageCount');

        if (currentPathEl) {
            currentPathEl.textContent = data.current_path;
        }

        // Render folders
        if (folderList) {
            folderList.innerHTML = '';
            
            // Add parent directory if available
            if (data.parent_path) {
                const parentItem = this.createFolderItem('..', data.parent_path, true);
                folderList.appendChild(parentItem);
            }

            data.directories.forEach(dir => {
                folderList.appendChild(this.createFolderItem(dir.name, dir.path));
            });
        }

        // Render files
        if (fileList) {
            fileList.innerHTML = '';
            data.image_files.forEach(file => {
                fileList.appendChild(this.createFileItem(file.name, file.path, file.size));
            });
        }

        // Update stats
        if (directoryCount) {
            directoryCount.textContent = data.directory_count;
        }
        if (imageCount) {
            imageCount.textContent = data.image_count;
        }
    }

    /**
     * Create folder item element
     */
    createFolderItem(name, path, isParent = false) {
        const item = document.createElement('div');
        item.className = 'folder-item';
        item.dataset.path = path;
        
        item.innerHTML = `
            <i class="fas fa-folder${isParent ? '' : ''}"></i>
            <span class="item-name">${this.escapeHtml(name)}</span>
        `;
        
        item.addEventListener('click', () => {
            if (isParent) {
                this.navigateToParentDirectory();
            } else {
                this.loadDirectory(path);
            }
        });
        
        return item;
    }

    /**
     * Create file item element
     */
    createFileItem(name, path, size) {
        const item = document.createElement('div');
        item.className = 'file-item';
        item.dataset.path = path;
        
        item.innerHTML = `
            <i class="fas fa-image"></i>
            <span class="item-name">${this.escapeHtml(name)}</span>
            <span class="item-size">${this.formatFileSize(size)}</span>
        `;
        
        return item;
    }

    /**
     * Navigate to parent directory
     */
    navigateToParentDirectory() {
        const currentPath = document.getElementById('batchCurrentPath')?.textContent;
        if (currentPath) {
            // Get parent path using path manipulation
            const lastSeparator = currentPath.lastIndexOf('/');
            const parentPath = lastSeparator > 0 ? currentPath.substring(0, lastSeparator) : currentPath;
            this.loadDirectory(parentPath);
        }
    }

    /**
     * Select current directory
     */
    selectCurrentDirectory() {
        const currentPath = document.getElementById('batchCurrentPath')?.textContent;
        const directoryInput = document.getElementById('batchDirectoryInput');
        
        if (currentPath && directoryInput) {
            directoryInput.value = currentPath;
            this.toggleDirectoryBrowser(); // Close browser
            showToast('toast.recipes.batchImportDirectorySelected', { path: currentPath }, 'success');
        }
    }

    /**
     * Format file size for display
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 10) / 10 + ' ' + sizes[i];
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Browse for directory using File System Access API (deprecated - kept for compatibility)
     */
    async browseDirectory() {
        // Now redirects to the new directory browser
        this.toggleDirectoryBrowser();
    }

    /**
     * Clean up WebSocket and polling connections
     */
    cleanupConnections() {
        if (this.wsConnection) {
            if (this.wsConnection.readyState === WebSocket.OPEN || 
                this.wsConnection.readyState === WebSocket.CONNECTING) {
                this.wsConnection.close();
            }
            this.wsConnection = null;
        }
        
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Create singleton instance
export const batchImportManager = new BatchImportManager();
