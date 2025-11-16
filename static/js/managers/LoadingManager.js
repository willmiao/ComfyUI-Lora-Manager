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
        this.isMinimized = false;
        this.minimizedWidget = null;
        this.currentFileName = '';
        this.currentProgress = 0;
        this.queueContainer = null; // Container for download queue display
        this.activeDownloadId = null; // ID of currently active download
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
        this.removeMinimizedWidget();
        this.isMinimized = false;
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
        this.queueContainer = null;
        this.queueList = null;
        this.activeDownloadId = null;
    }
    
    // Show enhanced progress for downloads
    showDownloadProgress(totalItems = 1) {
        this.show(translate('modals.download.status.preparing', {}, 'Preparing download...'), 0);
        this.progressBar.style.display = 'none';
        this.isMinimized = false;
        
        // Create details container
        const detailsContainer = this.createDetailsContainer();
        
        // Add minimize button
        this.loadingContent.style.position = 'relative';
        const minimizeButton = document.createElement('button');
        minimizeButton.className = 'download-minimize-btn';
        minimizeButton.innerHTML = '−'; // Unicode minus sign as fallback
        minimizeButton.title = translate('modals.download.minimize', {}, 'Minimize');
        minimizeButton.style.cssText = `
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: rgba(255, 255, 255, 0.9);
            cursor: pointer;
            padding: 6px 10px;
            font-size: 18px;
            line-height: 1;
            border-radius: 4px;
            opacity: 0.8;
            transition: opacity 0.2s, background 0.2s;
            z-index: 10;
            font-weight: bold;
            min-width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
        `;
        minimizeButton.addEventListener('mouseenter', () => {
            minimizeButton.style.opacity = '1';
            minimizeButton.style.background = 'rgba(0, 0, 0, 0.5)';
        });
        minimizeButton.addEventListener('mouseleave', () => {
            minimizeButton.style.opacity = '0.8';
            minimizeButton.style.background = 'rgba(0, 0, 0, 0.3)';
        });
        minimizeButton.addEventListener('click', (e) => {
            e.stopPropagation();
            this.minimize();
        });
        this.loadingContent.appendChild(minimizeButton);
        
        // Create current item progress
        const currentItemContainer = document.createElement('div');
        currentItemContainer.className = 'current-item-progress';
        
        const currentItemLabel = document.createElement('div');
        currentItemLabel.className = 'current-item-label';
        currentItemLabel.textContent = translate('modals.download.progress.currentFile', {}, 'Current file:');
        
        // Create version name label (shown below model name)
        const currentItemVersionLabel = document.createElement('div');
        currentItemVersionLabel.className = 'current-item-version-label';
        currentItemVersionLabel.style.cssText = `
            font-size: 12px;
            color: rgba(255, 255, 255, 0.7);
            margin-top: 2px;
        `;
        currentItemVersionLabel.textContent = '';
        
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
        currentItemContainer.appendChild(currentItemVersionLabel);
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
        
        // Store references for minimize widget updates
        this.currentItemProgress = currentItemProgress;
        this.currentItemLabel = currentItemLabel;
        this.currentItemVersionLabel = currentItemVersionLabel;
        this.currentItemPercent = currentItemPercent;
        
        // Return update function
        return (currentProgress, currentIndex = 0, currentName = '', metrics = {}) => {
            // Store current state for minimized widget
            this.currentProgress = currentProgress;
            if (currentName) {
                this.currentFileName = currentName;
            }
            
            // Update current item progress
            currentItemProgress.style.width = `${currentProgress}%`;
            currentItemPercent.textContent = `${Math.floor(currentProgress)}%`;
            
            // Note: Labels are updated from queue polling which has both model_name and version_name
            // This function is called from WebSocket updates, but queue polling will override with correct values
            
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
            
            // Update minimized widget if it exists
            if (this.isMinimized && this.minimizedWidget) {
                this.updateMinimizedWidget();
            }
        };
    }

    createQueueContainer() {
        if (this.queueContainer) {
            return this.queueContainer;
        }
        
        if (!this.detailsContainer) {
            this.detailsContainer = this.createDetailsContainer();
        }
        
        this.queueContainer = document.createElement('div');
        this.queueContainer.className = 'download-queue-container';
        this.queueContainer.style.cssText = `
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        `;
        
        const queueTitle = document.createElement('div');
        queueTitle.className = 'download-queue-title';
        queueTitle.style.cssText = `
            font-weight: 600;
            margin-bottom: 12px;
            color: rgba(255, 255, 255, 0.9);
            font-size: 14px;
        `;
        queueTitle.textContent = translate('modals.download.queue.title', {}, 'Download Queue');
        
        this.queueList = document.createElement('div');
        this.queueList.className = 'download-queue-list';
        this.queueList.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 8px;
        `;
        
        this.queueContainer.appendChild(queueTitle);
        this.queueContainer.appendChild(this.queueList);
        
        // Insert queue container before cancel button (if it exists) or at the end
        const cancelButton = this.detailsContainer.querySelector('.download-cancel-btn');
        if (cancelButton && cancelButton.parentNode === this.detailsContainer) {
            this.detailsContainer.insertBefore(this.queueContainer, cancelButton);
        } else {
            this.detailsContainer.appendChild(this.queueContainer);
        }
        
        return this.queueContainer;
    }

    updateQueueDisplay(downloads) {
        if (!downloads || !Array.isArray(downloads)) {
            return;
        }
        
        // Create queue container if it doesn't exist
        if (!this.queueContainer) {
            this.createQueueContainer();
        }
        
        // Clear existing queue items
        this.queueList.innerHTML = '';
        
        // Separate active and queued downloads
        // 'downloading' = actively downloading
        // 'waiting' = waiting for semaphore (should be shown as active/next in queue)
        // 'queued' = queued but not yet waiting (should be shown as queued)
        const activeDownloads = downloads.filter(d => 
            d.status === 'downloading'
        );
        const waitingDownloads = downloads.filter(d => 
            d.status === 'waiting'
        );
        const queuedDownloads = downloads.filter(d => 
            d.status === 'queued'
        );
        
        // Clamp all download counts to ensure they're never negative (defensive programming)
        const activeCount = Math.max(0, activeDownloads.length);
        const waitingCount = Math.max(0, waitingDownloads.length);
        const queuedCount = Math.max(0, queuedDownloads.length);
        
        // Combine waiting and queued for display - waiting is next to download, queued are after
        const allQueued = [...waitingDownloads, ...queuedDownloads];
        
        // Update main progress indicator with active download (if any)
        // The active download should be shown in the main progress area, NOT in the queue
        if (activeCount > 0) {
            const active = activeDownloads[0];
            this.activeDownloadId = active.download_id;
            
            // Update main progress display with active download info
            if (this.currentItemProgress && this.currentItemLabel && this.currentItemPercent) {
                // Always show model name (no switching)
                const modelName = active.model_name || 
                                 `Model #${active.model_id || active.download_id}`;
                const versionName = active.version_name || '';
                
                // Use model name for display name (for minimized widget)
                this.currentFileName = modelName;
                this.currentProgress = active.progress || 0;
                
                this.currentItemProgress.style.width = `${active.progress || 0}%`;
                this.currentItemPercent.textContent = `${Math.floor(active.progress || 0)}%`;
                
                // Show model name on main label
                this.currentItemLabel.textContent = translate(
                    'modals.download.progress.downloading',
                    { name: modelName },
                    `Downloading: ${modelName}`
                );
                
                // Show version name on separate line below (if available)
                if (this.currentItemVersionLabel) {
                    if (versionName) {
                        this.currentItemVersionLabel.textContent = versionName;
                        this.currentItemVersionLabel.style.display = '';
                    } else {
                        this.currentItemVersionLabel.textContent = '';
                        this.currentItemVersionLabel.style.display = 'none';
                    }
                }
                
                // Update transfer stats if available
                const bytesDetail = this.detailsContainer?.querySelector('.download-transfer-bytes');
                const speedDetail = this.detailsContainer?.querySelector('.download-transfer-speed');
                
                if (bytesDetail || speedDetail) {
                    const formatMetricSize = (value) => {
                        if (value === undefined || value === null || isNaN(value)) {
                            return '--';
                        }
                        if (value < 1) {
                            return '0 B';
                        }
                        return formatFileSize(value);
                    };
                    
                    if (bytesDetail) {
                        const formattedDownloaded = formatMetricSize(active.bytes_downloaded);
                        const formattedTotal = formatMetricSize(active.total_bytes);
                        
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
                        const formattedSpeed = formatMetricSize(active.bytes_per_second);
                        const displaySpeed = formattedSpeed === '--' ? '--' : `${formattedSpeed}/s`;
                        speedDetail.textContent = translate(
                            'modals.download.progress.speed',
                            { speed: displaySpeed },
                            `Speed: ${displaySpeed}`
                        );
                    }
                }
            }
        } else {
            // No active download - clear the active download ID
            // Main progress will remain at whatever it was (or show "Preparing...")
            this.activeDownloadId = null;
        }
        
        // Queue should ONLY show queued/waiting downloads, NOT the active one
        // Show waiting download (next in queue, waiting for semaphore)
        if (waitingCount > 0) {
            waitingDownloads.forEach((download, index) => {
                const waitingItem = this.createQueueItem(download, false, index + 1);
                this.queueList.appendChild(waitingItem);
            });
        }
        
        // Show queued downloads (after waiting)
        if (queuedCount > 0) {
            const startPosition = waitingCount + 1;
            queuedDownloads.forEach((download, index) => {
                const queueItem = this.createQueueItem(download, false, startPosition + index);
                this.queueList.appendChild(queueItem);
            });
        }
        
        // If one or less downloads, hide queue container
        if (activeCount <= 1 && waitingCount === 0 && queuedCount === 0) {
            if (this.queueContainer) {
                this.queueContainer.style.display = 'none';
            }
        } else {
            if (this.queueContainer) {
                this.queueContainer.style.display = 'block';
            }
        }
    }

    createQueueItem(download, isActive = false, queuePosition = null) {
        const item = document.createElement('div');
        item.className = `download-queue-item ${isActive ? 'active' : 'queued'}`;
        item.style.cssText = `
            padding: 10px;
            background: ${isActive ? 'rgba(74, 158, 255, 0.1)' : 'rgba(255, 255, 255, 0.05)'};
            border: 1px solid ${isActive ? 'rgba(74, 158, 255, 0.3)' : 'rgba(255, 255, 255, 0.1)'};
            border-radius: 4px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        `;
        
        const itemHeader = document.createElement('div');
        itemHeader.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            font-size: ${isActive ? '13px' : '12px'};
        `;
        
        const itemNameContainer = document.createElement('div');
        itemNameContainer.style.cssText = `
            display: flex;
            flex-direction: column;
            gap: 2px;
            flex: 1;
        `;
        
        // Model name line
        const itemModelName = document.createElement('div');
        itemModelName.style.cssText = `
            color: rgba(255, 255, 255, 0.9);
            font-weight: ${isActive ? '600' : '500'};
            font-size: ${isActive ? '13px' : '12px'};
        `;
        
        // Version name line (smaller, lighter)
        const itemVersionName = document.createElement('div');
        itemVersionName.style.cssText = `
            color: rgba(255, 255, 255, 0.7);
            font-size: ${isActive ? '11px' : '10px'};
            font-weight: 400;
        `;
        
        // Get model name and version name
        const modelName = download.model_name || 
                         `Model #${download.model_id || download.download_id}`;
        const versionName = download.version_name || '';
        
        // Set model name
        if (isActive) {
            itemModelName.textContent = translate('modals.download.queue.downloading', { name: modelName }, `Downloading: ${modelName}`);
        } else {
            itemModelName.textContent = translate('modals.download.queue.queued', { name: modelName, position: queuePosition }, `Queued #${queuePosition}: ${modelName}`);
        }
        
        // Set version name (if available)
        if (versionName) {
            itemVersionName.textContent = versionName;
        } else {
            itemVersionName.style.display = 'none';
        }
        
        itemNameContainer.appendChild(itemModelName);
        itemNameContainer.appendChild(itemVersionName);
        
        const itemStatus = document.createElement('div');
        itemStatus.style.cssText = `
            color: rgba(255, 255, 255, 0.7);
            font-size: ${isActive ? '11px' : '10px'};
            margin-left: 8px;
            white-space: nowrap;
        `;
        
        if (isActive) {
            if (download.status === 'waiting') {
                itemStatus.textContent = translate('modals.download.queue.waiting', {}, 'Waiting...');
            } else {
                itemStatus.textContent = `${download.progress || 0}%`;
            }
        } else {
            itemStatus.textContent = translate('modals.download.queue.pending', {}, 'Pending');
        }
        
        itemHeader.appendChild(itemNameContainer);
        itemHeader.appendChild(itemStatus);
        item.appendChild(itemHeader);
        
        // Add progress bar for active download
        if (isActive && download.status === 'downloading') {
            const progressBar = document.createElement('div');
            progressBar.style.cssText = `
                width: 100%;
                height: 4px;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 2px;
                overflow: hidden;
            `;
            
            const progressFill = document.createElement('div');
            progressFill.style.cssText = `
                width: ${download.progress || 0}%;
                height: 100%;
                background-color: var(--lora-accent, #4a9eff);
                transition: width 200ms ease-out;
            `;
            
            progressBar.appendChild(progressFill);
            item.appendChild(progressBar);
        }
        
        return item;
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
    
    minimize() {
        if (this.isMinimized) return;
        
        this.isMinimized = true;
        this.overlay.style.display = 'none';
        this.createMinimizedWidget();
    }
    
    restore() {
        if (!this.isMinimized) return;
        
        this.isMinimized = false;
        this.removeMinimizedWidget();
        this.overlay.style.display = 'flex';
    }
    
    createMinimizedWidget() {
        // Remove existing widget if any
        this.removeMinimizedWidget();
        
        // Create minimized widget container
        this.minimizedWidget = document.createElement('div');
        this.minimizedWidget.className = 'download-minimized-widget';
        this.minimizedWidget.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 300px;
            background: var(--lora-surface, rgba(30, 30, 30, 0.95));
            backdrop-filter: blur(24px);
            border: 1px solid var(--lora-border, rgba(255, 255, 255, 0.1));
            border-radius: var(--border-radius-base, 8px);
            padding: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: calc(var(--z-overlay, 1000) - 1);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        `;
        this.minimizedWidget.addEventListener('click', () => {
            this.restore();
        });
        this.minimizedWidget.addEventListener('mouseenter', () => {
            this.minimizedWidget.style.transform = 'scale(1.02)';
            this.minimizedWidget.style.boxShadow = '0 6px 16px rgba(0, 0, 0, 0.4)';
        });
        this.minimizedWidget.addEventListener('mouseleave', () => {
            this.minimizedWidget.style.transform = 'scale(1)';
            this.minimizedWidget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
        });
        
        // Create file name display
        const fileNameDisplay = document.createElement('div');
        fileNameDisplay.className = 'minimized-file-name';
        fileNameDisplay.style.cssText = `
            font-size: 13px;
            color: var(--text-color, rgba(255, 255, 255, 0.9));
            margin-bottom: 8px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-weight: 500;
        `;
        fileNameDisplay.textContent = this.currentFileName || translate('modals.download.status.preparing', {}, 'Preparing download...');
        
        // Create progress bar container
        const progressContainer = document.createElement('div');
        progressContainer.className = 'minimized-progress-container';
        progressContainer.style.cssText = `
            width: 100%;
            height: 6px;
            background-color: var(--lora-border, rgba(255, 255, 255, 0.1));
            border-radius: 3px;
            overflow: hidden;
            margin-bottom: 4px;
        `;
        
        // Create progress bar
        const progressBar = document.createElement('div');
        progressBar.className = 'minimized-progress-bar';
        progressBar.style.cssText = `
            width: ${this.currentProgress}%;
            height: 100%;
            background-color: var(--lora-accent, #4a9eff);
            transition: width 200ms ease-out;
        `;
        
        // Create progress percentage
        const progressPercent = document.createElement('div');
        progressPercent.className = 'minimized-progress-percent';
        progressPercent.style.cssText = `
            font-size: 11px;
            color: var(--text-color-secondary, rgba(255, 255, 255, 0.7));
            text-align: right;
        `;
        progressPercent.textContent = `${Math.floor(this.currentProgress)}%`;
        
        progressContainer.appendChild(progressBar);
        
        // Store references for updates
        this.minimizedFileNameDisplay = fileNameDisplay;
        this.minimizedProgressBar = progressBar;
        this.minimizedProgressPercent = progressPercent;
        
        // Assemble widget
        this.minimizedWidget.appendChild(fileNameDisplay);
        this.minimizedWidget.appendChild(progressContainer);
        this.minimizedWidget.appendChild(progressPercent);
        
        // Add restore hint
        const restoreHint = document.createElement('div');
        restoreHint.style.cssText = `
            font-size: 10px;
            color: var(--text-color-secondary, rgba(255, 255, 255, 0.5));
            text-align: center;
            margin-top: 4px;
        `;
        restoreHint.textContent = translate('modals.download.clickToRestore', {}, 'Click to restore');
        this.minimizedWidget.appendChild(restoreHint);
        
        document.body.appendChild(this.minimizedWidget);
    }
    
    updateMinimizedWidget() {
        if (!this.minimizedWidget || !this.isMinimized) return;
        
        if (this.minimizedFileNameDisplay && this.currentFileName) {
            this.minimizedFileNameDisplay.textContent = translate(
                'modals.download.progress.downloading',
                { name: this.currentFileName },
                `Downloading: ${this.currentFileName}`
            );
        }
        
        if (this.minimizedProgressBar) {
            this.minimizedProgressBar.style.width = `${this.currentProgress}%`;
        }
        
        if (this.minimizedProgressPercent) {
            this.minimizedProgressPercent.textContent = `${Math.floor(this.currentProgress)}%`;
        }
    }
    
    removeMinimizedWidget() {
        if (this.minimizedWidget) {
            this.minimizedWidget.remove();
            this.minimizedWidget = null;
            this.minimizedFileNameDisplay = null;
            this.minimizedProgressBar = null;
            this.minimizedProgressPercent = null;
        }
    }
}
