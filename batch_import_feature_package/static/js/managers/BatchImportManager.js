/**
 * Batch Import Manager - Handles bulk recipe import operations
 */

export class BatchImportManager {
    constructor(importManager) {
        this.importManager = importManager;
        this.batchResults = null;
        this.isProcessing = false;
        this.initializeEventHandlers();
    }

    initializeEventHandlers() {
        // Initialize event handlers when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.setupBatchImportModal();
            });
        } else {
            this.setupBatchImportModal();
        }
    }

    setupBatchImportModal() {
        // Setup batch import modal if it exists
        const batchModal = document.getElementById('batchImportModal');
        if (!batchModal) return;

        // Setup tab navigation
        const batchTabs = document.querySelectorAll('.batch-tab');
        batchTabs.forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target.closest('.batch-tab')));
        });

        // Add event listeners for batch operations
        const directoryInput = document.getElementById('batchDirectoryPath');
        if (directoryInput) {
            directoryInput.addEventListener('change', (e) => this.handleDirectorySelect(e));
        }
    }

    switchTab(tabElement) {
        if (!tabElement) return;

        // Get the tab name from data attribute
        const tabName = tabElement.getAttribute('data-tab');
        if (!tabName) return;

        // Remove active class from all tabs
        document.querySelectorAll('.batch-tab').forEach(t => {
            t.classList.remove('active');
        });

        // Remove active class from all tab contents
        document.querySelectorAll('.batch-tab-content').forEach(content => {
            content.classList.remove('active');
        });

        // Add active class to clicked tab
        tabElement.classList.add('active');

        // Add active class to corresponding tab content
        const tabContent = document.getElementById(`${tabName}Tab`);
        if (tabContent) {
            tabContent.classList.add('active');
            tabContent.style.display = 'block';
        }
    }

    /**
     * Open batch import modal
     */
    openBatchImportModal() {
        const modal = document.getElementById('batchImportModal');
        if (modal) {
            modal.style.display = 'flex';
            this.resetBatchForm();
        }
    }

    /**
     * Close batch import modal
     */
    closeBatchImportModal() {
        const modal = document.getElementById('batchImportModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    /**
     * Reset batch import form
     */
    resetBatchForm() {
        const directoryInput = document.getElementById('batchDirectoryPath');
        const urlsInput = document.getElementById('batchUrls');
        const messageEl = document.getElementById('batchMessage');
        const resultsEl = document.getElementById('batchResults');
        const exportBtn = document.getElementById('exportBtn');

        if (directoryInput) directoryInput.value = '';
        if (urlsInput) urlsInput.value = '';
        if (messageEl) {
            messageEl.textContent = '';
            messageEl.style.display = 'none';
        }
        if (resultsEl) {
            resultsEl.innerHTML = '';
            resultsEl.style.display = 'none';
        }
        if (exportBtn) exportBtn.style.display = 'none';
    }

    /**
     * Handle directory path input
     */
    handleDirectorySelect(event) {
        const path = event.target.value;
        const messageEl = document.getElementById('batchMessage');
        if (path && messageEl) {
            messageEl.textContent = `Ready to import from: ${path}`;
            messageEl.className = 'batch-message info';
            messageEl.style.display = 'block';
        }
    }

    /**
     * Import recipes from directory
     */
    async importFromDirectory() {
        const directoryInput = document.getElementById('batchDirectoryPath');
        const directoryPath = directoryInput ? directoryInput.value : '';
        
        if (!directoryPath) {
            this.showBatchMessage('Please enter a directory path', 'error');
            return;
        }

        await this.startBatchImport(
            '/api/lm/recipes/batch/import-directory',
            { directory_path: directoryPath }
        );
    }

    /**
     * Import recipes from URLs
     */
    async importFromUrls() {
        const urlsInput = document.getElementById('batchUrls');
        const urlsText = urlsInput ? urlsInput.value : '';
        
        if (!urlsText.trim()) {
            this.showBatchMessage('Please enter image URLs (one per line)', 'error');
            return;
        }

        const urls = urlsText
            .split('\n')
            .map(url => url.trim())
            .filter(url => url.length > 0);

        if (urls.length === 0) {
            this.showBatchMessage('Please enter valid URLs', 'error');
            return;
        }

        await this.startBatchImport(
            '/api/lm/recipes/batch/import-urls',
            { urls: urls }
        );
    }

    /**
     * Start batch import operation
     */
    async startBatchImport(endpoint, payload) {
        if (this.isProcessing) {
            this.showBatchMessage('A batch import is already in progress', 'warning');
            return;
        }

        this.isProcessing = true;
        this.showBatchMessage('Processing batch import...', 'info');
        
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            this.displayBatchResults(result);
            this.batchResults = result;

        } catch (error) {
            this.showBatchMessage(`Error: ${error.message}`, 'error');
            console.error('Batch import error:', error);
        } finally {
            this.isProcessing = false;
        }
    }

    /**
     * Display batch import results
     */
    displayBatchResults(result) {
        const resultsContainer = document.getElementById('batchResults');
        const exportBtn = document.getElementById('exportBtn');
        
        if (!resultsContainer) return;

        if (!result.success) {
            this.showBatchMessage(
                `Batch import completed with issues. Processed: ${result.processed}, Failed: ${result.failed}`,
                result.failed > 0 ? 'warning' : 'success'
            );
        } else {
            this.showBatchMessage(`Successfully imported ${result.processed} recipes!`, 'success');
        }

        // Build results summary
        let html = `
            <div class="batch-results-summary">
                <div class="result-stat">
                    <span class="label">Total Files:</span>
                    <span class="value">${result.total_files || result.total_urls || 0}</span>
                </div>
                <div class="result-stat success">
                    <span class="label">✓ Processed:</span>
                    <span class="value">${result.processed}</span>
                </div>
                <div class="result-stat error">
                    <span class="label">✗ Failed:</span>
                    <span class="value">${result.failed}</span>
                </div>
                <div class="result-stat warning">
                    <span class="label">⊘ Skipped:</span>
                    <span class="value">${result.skipped || 0}</span>
                </div>
            </div>
        `;

        // Show detailed results if available
        if (result.results && result.results.length > 0) {
            html += '<div class="batch-detailed-results"><h4>Imported Recipes:</h4><ul>';
            
            result.results.forEach(r => {
                const fileName = r.file_name || r.url || 'Unknown';
                html += `<li class="success-item">✓ ${fileName}</li>`;
            });
            
            html += '</ul></div>';
        }

        // Show errors if any
        if (result.errors && result.errors.length > 0) {
            html += '<div class="batch-errors"><h4>Errors:</h4><ul>';
            
            result.errors.forEach(err => {
                html += `<li class="error-item">✗ ${err}</li>`;
            });
            
            html += '</ul></div>';
        }

        resultsContainer.innerHTML = html;
        resultsContainer.style.display = 'block';

        // Show export button
        if (exportBtn && result.results && result.results.length > 0) {
            exportBtn.style.display = 'inline-block';
        }
    }

    /**
     * Show batch import message
     */
    showBatchMessage(message, type = 'info') {
        const messageEl = document.getElementById('batchMessage');
        if (messageEl) {
            messageEl.textContent = message;
            messageEl.className = `batch-message ${type}`;
            messageEl.style.display = 'block';
        }
    }

    /**
     * Export batch results as JSON
     */
    exportBatchResults() {
        if (!this.batchResults) {
            alert('No results to export');
            return;
        }

        const dataStr = JSON.stringify(this.batchResults, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `batch-import-results-${Date.now()}.json`;
        link.click();
        URL.revokeObjectURL(url);
    }
}

// Export for use in other modules
export default BatchImportManager;
