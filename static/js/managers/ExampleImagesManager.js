import { showToast } from '../utils/uiHelpers.js';
import { state } from '../state/index.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { settingsManager } from './SettingsManager.js';

// ExampleImagesManager.js
export class ExampleImagesManager {
    constructor() {
        this.isDownloading = false;
        this.isPaused = false;
        this.progressUpdateInterval = null;
        this.startTime = null;
        this.progressPanel = null;
        this.isProgressPanelCollapsed = false;
        this.pauseButton = null; // Store reference to the pause button
        this.stopButton = null;
        this.isMigrating = false; // Track migration state separately from downloading
        this.hasShownCompletionToast = false; // Flag to track if completion toast has been shown
        this.isStopping = false;
        
        // Auto download properties
        this.autoDownloadInterval = null;
        this.lastAutoDownloadCheck = 0;
        this.autoDownloadCheckInterval = 10 * 60 * 1000; // 10 minutes in milliseconds
        this.pageInitTime = Date.now(); // Track when page was initialized
        
        // Initialize download path field and check download status
        this.initializePathOptions();
        this.checkDownloadStatus();
    }
    
    // Initialize the manager
    async initialize() {
        // Wait for settings to be initialized before proceeding
        if (window.settingsManager) {
            await window.settingsManager.waitForInitialization();
        }
        
        // Initialize event listeners
        this.initEventListeners();
        
        // Initialize progress panel reference
        this.progressPanel = document.getElementById('exampleImagesProgress');
        
        // Load collapse state from storage
        this.isProgressPanelCollapsed = getStorageItem('progress_panel_collapsed', false);
        if (this.progressPanel && this.isProgressPanelCollapsed) {
            this.progressPanel.classList.add('collapsed');
            const icon = document.querySelector('#collapseProgressBtn i');
            if (icon) {
                icon.className = 'fas fa-chevron-up';
            }
        }
        
        // Initialize progress panel button handlers
        this.pauseButton = document.getElementById('pauseExampleDownloadBtn');
        this.stopButton = document.getElementById('stopExampleDownloadBtn');
        const collapseBtn = document.getElementById('collapseProgressBtn');

        if (this.pauseButton) {
            this.pauseButton.onclick = () => this.pauseDownload();
        }

        if (this.stopButton) {
            this.stopButton.onclick = () => this.stopDownload();
        }
        
        if (collapseBtn) {
            collapseBtn.onclick = () => this.toggleProgressPanel();
        }

        // Setup auto download if enabled
        if (state.global.settings.auto_download_example_images) {
            this.setupAutoDownload();
        }

        // Make this instance globally accessible
        window.exampleImagesManager = this;
    }
    
    // Initialize event listeners for buttons
    initEventListeners() {
        const downloadBtn = document.getElementById('exampleImagesDownloadBtn');
        if (downloadBtn) {
            downloadBtn.onclick = () => this.handleDownloadButton();
        }
    }
    
    async initializePathOptions() {
        try {
            // Get custom path input element
            const pathInput = document.getElementById('exampleImagesPath');

            // Set path from backend settings
            const savedPath = state.global.settings.example_images_path || '';
            if (pathInput) {
                pathInput.value = savedPath;
                // Enable download button if path is set
                this.updateDownloadButtonState(!!savedPath);
            }
            
            // Add event listener to validate path input
            if (pathInput) {
                // Save path on Enter key or blur
                const savePath = async () => {
                    const hasPath = pathInput.value.trim() !== '';
                    this.updateDownloadButtonState(hasPath);
                    try {
                        await settingsManager.saveSetting('example_images_path', pathInput.value);
                            showToast('toast.exampleImages.pathUpdated', {}, 'success');
                    } catch (error) {
                        console.error('Failed to update example images path:', error);
                        showToast('toast.exampleImages.pathUpdateFailed', { message: error.message }, 'error');
                    }
                    // Setup or clear auto download based on path availability
                    if (state.global.settings.auto_download_example_images) {
                        if (hasPath) {
                            this.setupAutoDownload();
                        } else {
                            this.clearAutoDownload();
                        }
                    }
                };
                let ignoreNextBlur = false;
                pathInput.addEventListener('keydown', async (e) => {
                    if (e.key === 'Enter') {
                        ignoreNextBlur = true;
                        await savePath();
                        pathInput.blur(); // Remove focus from the input after saving
                    }
                });
                pathInput.addEventListener('blur', async () => {
                    if (ignoreNextBlur) {
                        ignoreNextBlur = false;
                        return;
                    }
                    await savePath();
                });
                // Still update button state on input, but don't save
                pathInput.addEventListener('input', () => {
                    const hasPath = pathInput.value.trim() !== '';
                    this.updateDownloadButtonState(hasPath);
                });
            }
        } catch (error) {
            console.error('Failed to initialize path options:', error);
        }
    }
    
    // Method to update download button state
    updateDownloadButtonState(enabled) {
        const downloadBtn = document.getElementById('exampleImagesDownloadBtn');
        if (downloadBtn) {
            if (enabled) {
                downloadBtn.classList.remove('disabled');
                downloadBtn.disabled = false;
            } else {
                downloadBtn.classList.add('disabled');
                downloadBtn.disabled = true;
            }
        }
    }
    
    // Method to handle download button click based on current state
    async handleDownloadButton() {
        if (this.isDownloading && this.isPaused) {
            // If download is paused, resume it
            this.resumeDownload();
        } else if (!this.isDownloading) {
            // If no download in progress, start a new one
            this.startDownload();
        } else {
            // If download is in progress, show info toast
            showToast('toast.exampleImages.downloadInProgress', {}, 'info');
        }
    }
    
    async checkDownloadStatus() {
        try {
            const response = await fetch('/api/lm/example-images-status');
            const data = await response.json();
            
            if (data.success) {
                this.isDownloading = data.is_downloading;
                this.isPaused = data.status.status === 'paused';
                
                // Update download button text based on status
                this.updateDownloadButtonText();
                
                if (this.isDownloading) {
                    // Ensure progress panel exists before updating UI
                    if (!this.progressPanel) {
                        this.progressPanel = document.getElementById('exampleImagesProgress');
                    }
                    
                    if (this.progressPanel) {
                        this.updateUI(data.status);
                        this.showProgressPanel();
                        
                        // Start the progress update interval if downloading
                        if (!this.progressUpdateInterval) {
                            this.startProgressUpdates();
                        }
                    } else {
                        console.warn('Progress panel not found, will retry on next update');
                        // Set a shorter timeout to try again
                        setTimeout(() => this.checkDownloadStatus(), 500);
                    }
                }
            }
        } catch (error) {
            console.error('Failed to check download status:', error);
        }
    }
    
    // Update download button text based on current state
    updateDownloadButtonText() {
        const btnTextElement = document.getElementById('exampleDownloadBtnText');
        if (btnTextElement) {
            if (this.isStopping) {
                btnTextElement.textContent = "Stopping...";
            } else if (this.isDownloading && this.isPaused) {
                btnTextElement.textContent = "Resume";
            } else if (!this.isDownloading) {
                btnTextElement.textContent = "Download";
            } else {
                btnTextElement.textContent = "Download";
            }
        }
    }
    
    async startDownload() {
        if (this.isDownloading) {
            showToast('toast.exampleImages.downloadInProgress', {}, 'warning');
            return;
        }
        
        try {
            const optimize = state.global.settings.optimize_example_images;
            
            const response = await fetch('/api/lm/download-example-images', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    optimize: optimize,
                    model_types: ['lora', 'checkpoint', 'embedding'] // Example types, adjust as needed
                })
            });
            
            const data = await response.json();

            if (data.success) {
                this.isDownloading = true;
                this.isPaused = false;
                this.isStopping = false;
                this.hasShownCompletionToast = false; // Reset toast flag when starting new download
                this.startTime = new Date();
                this.updateUI(data.status);
                this.showProgressPanel();
                this.startProgressUpdates();
                this.updateDownloadButtonText();
                if (this.stopButton) {
                    this.stopButton.disabled = false;
                }
                showToast('toast.exampleImages.downloadStarted', {}, 'success');

                // Close settings modal
                modalManager.closeModal('settingsModal');
            } else {
                showToast('toast.exampleImages.downloadStartFailed', { error: data.error }, 'error');
            }
        } catch (error) {
            console.error('Failed to start download:', error);
            showToast('toast.exampleImages.downloadStartFailed', {}, 'error');
        }
    }
    
    async pauseDownload() {
        if (!this.isDownloading || this.isPaused || this.isStopping) {
            return;
        }
        
        try {
            const response = await fetch('/api/lm/pause-example-images', {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.isPaused = true;
                document.getElementById('downloadStatusText').textContent = 'Paused';
                
                // Only update the icon element, not the entire innerHTML
                if (this.pauseButton) {
                    const iconElement = this.pauseButton.querySelector('i');
                    if (iconElement) {
                        iconElement.className = 'fas fa-play';
                    }
                    this.pauseButton.onclick = () => this.resumeDownload();
                }
                
                this.updateDownloadButtonText();
                showToast('toast.exampleImages.downloadPaused', {}, 'info');
            } else {
                showToast('toast.exampleImages.pauseFailed', { error: data.error }, 'error');
            }
        } catch (error) {
            console.error('Failed to pause download:', error);
            showToast('toast.exampleImages.pauseFailed', {}, 'error');
        }
    }
    
    async resumeDownload() {
        if (!this.isDownloading || !this.isPaused || this.isStopping) {
            return;
        }

        try {
            const response = await fetch('/api/lm/resume-example-images', {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                this.isPaused = false;
                document.getElementById('downloadStatusText').textContent = 'Downloading';

                // Only update the icon element, not the entire innerHTML
                if (this.pauseButton) {
                    const iconElement = this.pauseButton.querySelector('i');
                    if (iconElement) {
                        iconElement.className = 'fas fa-pause';
                    }
                    this.pauseButton.onclick = () => this.pauseDownload();
                }

                this.updateDownloadButtonText();
                showToast('toast.exampleImages.downloadResumed', {}, 'success');
            } else {
                showToast('toast.exampleImages.resumeFailed', { error: data.error }, 'error');
            }
        } catch (error) {
            console.error('Failed to resume download:', error);
            showToast('toast.exampleImages.resumeFailed', {}, 'error');
        }
    }

    async stopDownload() {
        if (this.isStopping) {
            return;
        }

        if (!this.isDownloading) {
            this.hideProgressPanel();
            return;
        }

        this.isStopping = true;
        this.isPaused = false;
        this.updateDownloadButtonText();

        if (this.stopButton) {
            this.stopButton.disabled = true;
        }

        try {
            const response = await fetch('/api/lm/stop-example-images', {
                method: 'POST'
            });

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                data = { success: false, error: 'Invalid server response' };
            }

            if (response.ok && data.success) {
                showToast('toast.exampleImages.downloadStopped', {}, 'info');
                this.hideProgressPanel();
            } else {
                this.isStopping = false;
                if (this.stopButton) {
                    this.stopButton.disabled = false;
                }
                const errorMessage = data && data.error ? data.error : 'Unknown error';
                showToast('toast.exampleImages.stopFailed', { error: errorMessage }, 'error');
            }
        } catch (error) {
            console.error('Failed to stop download:', error);
            this.isStopping = false;
            if (this.stopButton) {
                this.stopButton.disabled = false;
            }
            const errorMessage = error && error.message ? error.message : 'Unknown error';
            showToast('toast.exampleImages.stopFailed', { error: errorMessage }, 'error');
        } finally {
            this.updateDownloadButtonText();
        }
    }
    
    startProgressUpdates() {
        // Clear any existing interval
        if (this.progressUpdateInterval) {
            clearInterval(this.progressUpdateInterval);
        }
        
        // Set new interval to update progress every 2 seconds
        this.progressUpdateInterval = setInterval(async () => {
            await this.updateProgress();
        }, 2000);
    }
    
    async updateProgress() {
        try {
            const response = await fetch('/api/lm/example-images-status');
            const data = await response.json();
            
            if (data.success) {
                const currentStatus = data.status.status;
                this.isDownloading = data.is_downloading;
                this.isPaused = currentStatus === 'paused';
                this.isMigrating = data.is_migrating || false;

                if (currentStatus === 'stopping') {
                    this.isStopping = true;
                } else if (
                    !data.is_downloading ||
                    currentStatus === 'stopped' ||
                    currentStatus === 'completed' ||
                    currentStatus === 'error'
                ) {
                    this.isStopping = false;
                }

                // Update download button text
                this.updateDownloadButtonText();

                if (this.isDownloading) {
                    this.updateUI(data.status);
                } else {
                    // Download completed or failed
                    clearInterval(this.progressUpdateInterval);
                    this.progressUpdateInterval = null;
                    if (this.stopButton) {
                        this.stopButton.disabled = true;
                    }

                    if (currentStatus === 'completed' && !this.hasShownCompletionToast) {
                        const actionType = this.isMigrating ? 'migration' : 'download';
                        showToast('toast.downloads.imagesCompleted', { action: actionType }, 'success');
                        // Mark as shown to prevent duplicate toasts
                        this.hasShownCompletionToast = true;
                        // Reset migration flag
                        this.isMigrating = false;
                        // Hide the panel after a delay
                        setTimeout(() => this.hideProgressPanel(), 5000);
                    } else if (currentStatus === 'error') {
                        const actionType = this.isMigrating ? 'migration' : 'download';
                        showToast('toast.downloads.imagesFailed', { action: actionType }, 'error');
                        this.isMigrating = false;
                    } else if (currentStatus === 'stopped') {
                        this.hideProgressPanel();
                        this.isMigrating = false;
                    }
                }
            }
        } catch (error) {
            console.error('Failed to update progress:', error);
        }
    }
    
    updateUI(status) {
        // Ensure progress panel exists
        if (!this.progressPanel) {
            this.progressPanel = document.getElementById('exampleImagesProgress');
            if (!this.progressPanel) {
                console.error('Progress panel element not found in DOM');
                return;
            }
        }
        
        // Update status text
        const statusText = document.getElementById('downloadStatusText');
        if (statusText) {
            statusText.textContent = this.getStatusText(status.status);
        }
        
        // Update progress counts and bar
        const progressCounts = document.getElementById('downloadProgressCounts');
        if (progressCounts) {
            progressCounts.textContent = `${status.completed}/${status.total}`;
        }
        
        const progressBar = document.getElementById('downloadProgressBar');
        if (progressBar) {
            const progressPercent = status.total > 0 ? (status.completed / status.total) * 100 : 0;
            progressBar.style.width = `${progressPercent}%`;
            
            // Update mini progress circle
            this.updateMiniProgress(progressPercent);
        }
        
        // Update current model
        const currentModel = document.getElementById('currentModelName');
        if (currentModel) {
            currentModel.textContent = status.current_model || '-';
        }
        
        // Update time stats
        this.updateTimeStats(status);
        
        // Update errors
        this.updateErrors(status);
        
        // Update pause/resume button
        if (!this.pauseButton) {
            this.pauseButton = document.getElementById('pauseExampleDownloadBtn');
        }

        if (!this.stopButton) {
            this.stopButton = document.getElementById('stopExampleDownloadBtn');
        }

        if (this.pauseButton) {
            // Check if the button already has the SVG elements
            let hasProgressElements = !!this.pauseButton.querySelector('.mini-progress-circle');
            
            if (!hasProgressElements) {
                // If elements don't exist, add them
                this.pauseButton.innerHTML = `
                    <i class="${status.status === 'paused' ? 'fas fa-play' : 'fas fa-pause'}"></i>
                    <svg class="mini-progress-container" width="24" height="24" viewBox="0 0 24 24">
                        <circle class="mini-progress-background" cx="12" cy="12" r="10"></circle>
                        <circle class="mini-progress-circle" cx="12" cy="12" r="10" stroke-dasharray="62.8" stroke-dashoffset="62.8"></circle>
                    </svg>
                    <span class="progress-percent"></span>
                `;
            } else {
                // If elements exist, just update the icon
                const iconElement = this.pauseButton.querySelector('i');
                if (iconElement) {
                    iconElement.className = status.status === 'paused' ? 'fas fa-play' : 'fas fa-pause';
                }
            }

            // Update click handler
            this.pauseButton.onclick = status.status === 'paused'
                ? () => this.resumeDownload()
                : () => this.pauseDownload();

            this.pauseButton.disabled = ['completed', 'error', 'stopped'].includes(status.status) || status.status === 'stopping';

            // Update progress immediately
            const progressBar = document.getElementById('downloadProgressBar');
            if (progressBar) {
                const progressPercent = status.total > 0 ? (status.completed / status.total) * 100 : 0;
                this.updateMiniProgress(progressPercent);
            }
        }

        if (this.stopButton) {
            if (status.status === 'stopping' || this.isStopping) {
                this.stopButton.disabled = true;
            } else {
                const canStop = ['running', 'paused'].includes(status.status);
                this.stopButton.disabled = !canStop;
            }
        }
        
        // Update title text
        const titleElement = document.querySelector('.progress-panel-title');
        if (titleElement) {
            const titleIcon = titleElement.querySelector('i');
            if (titleIcon) {
                titleIcon.className = this.isMigrating ? 'fas fa-file-import' : 'fas fa-images';
            }
            
            titleElement.innerHTML = 
                `<i class="${this.isMigrating ? 'fas fa-file-import' : 'fas fa-images'}"></i> ` +
                `${this.isMigrating ? 'Example Images Migration' : 'Example Images Download'}`;
        }
    }
    
    // Update the mini progress circle in the pause button
    updateMiniProgress(percent) {
        // Ensure we have the pause button reference
        if (!this.pauseButton) {
            this.pauseButton = document.getElementById('pauseExampleDownloadBtn');
            if (!this.pauseButton) {
                console.error('Pause button not found');
                return;
            }
        }
        
        // Query elements within the context of the pause button
        const miniProgressCircle = this.pauseButton.querySelector('.mini-progress-circle');
        const percentText = this.pauseButton.querySelector('.progress-percent');
        
        if (miniProgressCircle && percentText) {
            // Circle circumference = 2πr = 2 * π * 10 = 62.8
            const circumference = 62.8;
            const offset = circumference - (percent / 100) * circumference;
            
            miniProgressCircle.style.strokeDashoffset = offset;
            percentText.textContent = `${Math.round(percent)}%`;
            
            // Only show percent text when panel is collapsed
            percentText.style.display = this.isProgressPanelCollapsed ? 'block' : 'none';
        } else {
            console.warn('Mini progress elements not found within pause button', 
                         this.pauseButton,
                         'mini-progress-circle:', !!miniProgressCircle, 
                         'progress-percent:', !!percentText);
        }
    }
    
    updateTimeStats(status) {
        const elapsedTime = document.getElementById('elapsedTime');
        const remainingTime = document.getElementById('remainingTime');
        
        if (!elapsedTime || !remainingTime) return;
        
        // Calculate elapsed time
        let elapsed;
        if (status.start_time) {
            const now = new Date();
            const startTime = new Date(status.start_time * 1000);
            elapsed = Math.floor((now - startTime) / 1000);
        } else {
            elapsed = 0;
        }
        
        elapsedTime.textContent = this.formatTime(elapsed);
        
        // Calculate remaining time
        if (status.total > 0 && status.completed > 0 && status.status === 'running') {
            const rate = status.completed / elapsed; // models per second
            const remaining = Math.floor((status.total - status.completed) / rate);
            remainingTime.textContent = this.formatTime(remaining);
        } else {
            remainingTime.textContent = '--:--:--';
        }
    }
    
    updateErrors(status) {
        const errorContainer = document.getElementById('downloadErrorContainer');
        const errorList = document.getElementById('downloadErrors');
        
        if (!errorContainer || !errorList) return;
        
        if (status.errors && status.errors.length > 0) {
            // Show only the last 3 errors
            const recentErrors = status.errors.slice(-3);
            errorList.innerHTML = recentErrors.map(error => 
                `<div class="error-item">${error}</div>`
            ).join('');
            
            errorContainer.classList.remove('hidden');
        } else {
            errorContainer.classList.add('hidden');
        }
    }
    
    formatTime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        return [
            hours.toString().padStart(2, '0'),
            minutes.toString().padStart(2, '0'),
            secs.toString().padStart(2, '0')
        ].join(':');
    }
    
    getStatusText(status) {
        const prefix = this.isMigrating ? 'Migrating' : 'Downloading';
        
        switch (status) {
            case 'running': return this.isMigrating ? 'Migrating' : 'Downloading';
            case 'paused': return 'Paused';
            case 'completed': return 'Completed';
            case 'error': return 'Error';
            case 'stopping': return 'Stopping';
            case 'stopped': return 'Stopped';
            default: return 'Initializing';
        }
    }
    
    showProgressPanel() {
        // Ensure progress panel exists
        if (!this.progressPanel) {
            this.progressPanel = document.getElementById('exampleImagesProgress');
            if (!this.progressPanel) {
                console.error('Progress panel element not found in DOM');
                return;
            }
        }
        this.progressPanel.classList.add('visible');
    }
    
    hideProgressPanel() {
        if (!this.progressPanel) {
            this.progressPanel = document.getElementById('exampleImagesProgress');
            if (!this.progressPanel) return;
        }
        this.progressPanel.classList.remove('visible');
    }
    
    toggleProgressPanel() {
        if (!this.progressPanel) {
            this.progressPanel = document.getElementById('exampleImagesProgress');
            if (!this.progressPanel) return;
        }
        
        this.isProgressPanelCollapsed = !this.isProgressPanelCollapsed;
        this.progressPanel.classList.toggle('collapsed');
        
        // Save collapsed state to storage
        setStorageItem('progress_panel_collapsed', this.isProgressPanelCollapsed);
        
        // Update icon
        const icon = document.querySelector('#collapseProgressBtn i');
        if (icon) {
            if (this.isProgressPanelCollapsed) {
                icon.className = 'fas fa-chevron-up';
            } else {
                icon.className = 'fas fa-chevron-down';
            }
        }
        
        // Force update mini progress if panel is collapsed
        if (this.isProgressPanelCollapsed) {
            const progressBar = document.getElementById('downloadProgressBar');
            if (progressBar) {
                const progressPercent = parseFloat(progressBar.style.width) || 0;
                this.updateMiniProgress(progressPercent);
            }
        }
    }

    setupAutoDownload() {
        // Only setup if conditions are met
        if (!this.canAutoDownload()) {
            return;
        }

        // Clear any existing interval
        this.clearAutoDownload();

        // Wait at least 30 seconds after page initialization before first check
        const timeSinceInit = Date.now() - this.pageInitTime;
        const initialDelay = Math.max(60000 - timeSinceInit, 5000); // At least 5 seconds, up to 60 seconds

        console.log(`Setting up auto download with initial delay of ${initialDelay}ms`);

        setTimeout(() => {
            // Do initial check
            this.performAutoDownloadCheck();

            // Set up recurring interval
            this.autoDownloadInterval = setInterval(() => {
                this.performAutoDownloadCheck();
            }, this.autoDownloadCheckInterval);

        }, initialDelay);
    }

    clearAutoDownload() {
        if (this.autoDownloadInterval) {
            clearInterval(this.autoDownloadInterval);
            this.autoDownloadInterval = null;
            console.log('Auto download interval cleared');
        }
    }

    canAutoDownload() {
        // Check if auto download is enabled
        if (!state.global.settings.auto_download_example_images) {
            return false;
        }

        // Check if download path is set in settings
        if (!state.global.settings.example_images_path) {
            return false;
        }

        // Check if already downloading
        if (this.isDownloading) {
            return false;
        }

        return true;
    }

    async performAutoDownloadCheck() {
        const now = Date.now();
        
        // Prevent too frequent checks (minimum 2 minutes between checks)
        if (now - this.lastAutoDownloadCheck < 2 * 60 * 1000) {
            console.log('Skipping auto download check - too soon since last check');
            return;
        }

        this.lastAutoDownloadCheck = now;

        if (!this.canAutoDownload()) {
            console.log('Auto download conditions not met, skipping check');
            return;
        }

        try {
            console.log('Performing auto download check...');
            
            const optimize = state.global.settings.optimize_example_images;
            
            const response = await fetch('/api/lm/download-example-images', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    optimize: optimize,
                    model_types: ['lora', 'checkpoint', 'embedding'],
                    auto_mode: true // Flag to indicate this is an automatic download
                })
            });
            
            const data = await response.json();
            
            if (!data.success) {
                console.warn('Auto download check failed:', data.error);
            }
        } catch (error) {
            console.error('Auto download check error:', error);
        }
    }
}
