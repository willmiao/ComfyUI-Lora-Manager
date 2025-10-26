import { translate } from '../utils/i18nHelpers.js';
import { formatFileSize } from '../utils/formatters.js';

// Loading management
export class LoadingManager {
    constructor() {
        this.overlay = document.getElementById('loading-overlay');

        if (!this.overlay) {
            this.overlay = document.createElement('div');
            this.overlay.id = 'loading-overlay';
            this.overlay.style.display = 'none';
            document.body.appendChild(this.overlay);
        }

        this.loadingContent = this.overlay.querySelector('.loading-content');
        if (!this.loadingContent) {
            this.loadingContent = document.createElement('div');
            this.loadingContent.className = 'loading-content';
            this.overlay.appendChild(this.loadingContent);
        }

        this.progressBar = this.loadingContent.querySelector('.progress-bar');
        if (!this.progressBar) {
            this.progressBar = document.createElement('div');
            this.progressBar.className = 'progress-bar';
            this.progressBar.setAttribute('role', 'progressbar');
            this.progressBar.setAttribute('aria-valuemin', '0');
            this.progressBar.setAttribute('aria-valuemax', '100');
            this.progressBar.setAttribute('aria-valuenow', '0');
            this.progressBar.style.width = '0%';
            this.loadingContent.appendChild(this.progressBar);
        }

        this.statusText = this.loadingContent.querySelector('.loading-status');
        if (!this.statusText) {
            this.statusText = document.createElement('div');
            this.statusText.className = 'loading-status';
            this.loadingContent.appendChild(this.statusText);
        }

        this.detailsContainer = null; // Will be created when needed
    }

    show(message = 'Loading...', progress = 0) {
        this.overlay.style.display = 'flex';
        this.setProgress(progress);
        this.setStatus(message);
        
        // Remove any existing details container
        this.removeDetailsContainer();
    }

    hide() {
        this.overlay.style.display = 'none';
        this.reset();
        this.removeDetailsContainer();
    }

    setProgress(percent) {
        this.progressBar.style.width = `${percent}%`;
        this.progressBar.setAttribute('aria-valuenow', percent);
    }

    setStatus(message) {
        this.statusText.textContent = message;
    }

    reset() {
        this.setProgress(0);
        this.setStatus('');
        this.removeDetailsContainer();
        this.progressBar.style.display = 'block';
    }

    // Create a details container for enhanced progress display
    createDetailsContainer() {
        // Remove existing container if any
        this.removeDetailsContainer();
        
        // Create new container
        this.detailsContainer = document.createElement('div');
        this.detailsContainer.className = 'progress-details-container';
        
        // Insert after the main progress bar
        if (this.loadingContent) {
            this.loadingContent.appendChild(this.detailsContainer);
        }
        
        return this.detailsContainer;
    }
    
    // Remove details container
    removeDetailsContainer() {
        if (this.detailsContainer) {
            this.detailsContainer.remove();
            this.detailsContainer = null;
        }
    }
    
    // Show enhanced progress for downloads
    showDownloadProgress(totalItems = 1) {
        this.show(translate('modals.download.status.preparing', {}, 'Preparing download...'), 0);
        this.progressBar.style.display = 'none';
        
        // Create details container
        const detailsContainer = this.createDetailsContainer();
        
        // Create current item progress
        const currentItemContainer = document.createElement('div');
        currentItemContainer.className = 'current-item-progress';
        
        const currentItemLabel = document.createElement('div');
        currentItemLabel.className = 'current-item-label';
        currentItemLabel.textContent = translate('modals.download.progress.currentFile', {}, 'Current file:');
        
        const currentItemBar = document.createElement('div');
        currentItemBar.className = 'current-item-bar-container';
        
        const currentItemProgress = document.createElement('div');
        currentItemProgress.className = 'current-item-bar';
        currentItemProgress.style.width = '0%';
        
        const currentItemPercent = document.createElement('span');
        currentItemPercent.className = 'current-item-percent';
        currentItemPercent.textContent = '0%';
        
        currentItemBar.appendChild(currentItemProgress);
        currentItemContainer.appendChild(currentItemLabel);
        currentItemContainer.appendChild(currentItemBar);
        currentItemContainer.appendChild(currentItemPercent);
        
        // Create overall progress elements if multiple items
        let overallLabel = null;
        if (totalItems > 1) {
            overallLabel = document.createElement('div');
            overallLabel.className = 'overall-progress-label';
            overallLabel.textContent = `Overall progress (0/${totalItems} complete):`;
            detailsContainer.appendChild(overallLabel);
        }
        
        // Add current item progress to container
        detailsContainer.appendChild(currentItemContainer);

        // Create transfer stats container
        const transferStats = document.createElement('div');
        transferStats.className = 'download-transfer-stats';

        const bytesDetail = document.createElement('div');
        bytesDetail.className = 'download-transfer-bytes';
        bytesDetail.textContent = translate(
            'modals.download.progress.transferredUnknown',
            {},
            'Transferred: --'
        );

        const speedDetail = document.createElement('div');
        speedDetail.className = 'download-transfer-speed';
        speedDetail.textContent = translate(
            'modals.download.progress.speed',
            { speed: '--' },
            'Speed: --'
        );

        transferStats.appendChild(bytesDetail);
        transferStats.appendChild(speedDetail);
        detailsContainer.appendChild(transferStats);

        const formatMetricSize = (value) => {
            if (value === undefined || value === null || isNaN(value)) {
                return '--';
            }
            if (value < 1) {
                return '0 B';
            }
            return formatFileSize(value);
        };

        const updateTransferStats = (metrics = {}) => {
            const { bytesDownloaded, totalBytes, bytesPerSecond } = metrics;

            if (bytesDetail) {
                const formattedDownloaded = formatMetricSize(bytesDownloaded);
                const formattedTotal = formatMetricSize(totalBytes);

                if (formattedDownloaded === '--' && formattedTotal === '--') {
                    bytesDetail.textContent = translate(
                        'modals.download.progress.transferredUnknown',
                        {},
                        'Transferred: --'
                    );
                } else if (formattedTotal === '--') {
                    bytesDetail.textContent = translate(
                        'modals.download.progress.transferredSimple',
                        { downloaded: formattedDownloaded },
                        `Transferred: ${formattedDownloaded}`
                    );
                } else {
                    bytesDetail.textContent = translate(
                        'modals.download.progress.transferred',
                        { downloaded: formattedDownloaded, total: formattedTotal },
                        `Transferred: ${formattedDownloaded} / ${formattedTotal}`
                    );
                }
            }

            if (speedDetail) {
                const formattedSpeed = formatMetricSize(bytesPerSecond);
                const displaySpeed = formattedSpeed === '--' ? '--' : `${formattedSpeed}/s`;
                speedDetail.textContent = translate(
                    'modals.download.progress.speed',
                    { speed: displaySpeed },
                    `Speed: ${displaySpeed}`
                );
            }
        };

        // Initialize transfer stats with empty data
        updateTransferStats();
        
        // Return update function
        return (currentProgress, currentIndex = 0, currentName = '', metrics = {}) => {
            // Update current item progress
            currentItemProgress.style.width = `${currentProgress}%`;
            currentItemPercent.textContent = `${Math.floor(currentProgress)}%`;
            
            // Update current item label if name provided
            if (currentName) {
                currentItemLabel.textContent = translate(
                    'modals.download.progress.downloading',
                    { name: currentName },
                    `Downloading: ${currentName}`
                );
            }
            
            // Update overall label if multiple items
            if (totalItems > 1 && overallLabel) {
                overallLabel.textContent = `Overall progress (${currentIndex}/${totalItems} complete):`;
                
                // Calculate and update overall progress
                const overallProgress = Math.floor((currentIndex + currentProgress/100) / totalItems * 100);
                this.setProgress(overallProgress);
            } else {
                // Single item, just update main progress
                this.setProgress(currentProgress);
            }

            updateTransferStats(metrics);
        };
    }

    async showWithProgress(callback, options = {}) {
        const { initialMessage = 'Processing...', completionMessage = 'Complete' } = options;
        
        try {
            this.show(initialMessage);
            await callback(this);
            this.setProgress(100);
            this.setStatus(completionMessage);
            await new Promise(resolve => setTimeout(resolve, 500));
        } finally {
            this.hide();
        }
    }

    // Enhanced progress display without callback pattern
    showEnhancedProgress(message = 'Processing...') {
        this.show(message, 0);
        
        // Return update functions
        return {
            updateProgress: (percent, currentItem = '', statusMessage = '') => {
                this.setProgress(percent);   
                if (statusMessage) {
                    this.setStatus(statusMessage);
                }
            },
            
            complete: async (completionMessage = 'Complete') => {
                this.setProgress(100);
                this.setStatus(completionMessage);
                await new Promise(resolve => setTimeout(resolve, 500));
                this.hide();
            }
        };
    }

    showSimpleLoading(message = 'Loading...') {
        this.overlay.style.display = 'flex';
        this.progressBar.style.display = 'none';
        this.setStatus(message);
    }

    restoreProgressBar() {
        this.progressBar.style.display = 'block';
    }
}
