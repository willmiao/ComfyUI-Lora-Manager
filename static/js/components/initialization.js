/**
 * Initialization Component
 * Manages the display of initialization progress and status
 */
import { appCore } from '../core.js';
import { getSessionItem, setSessionItem } from '../utils/storageHelpers.js';

class InitializationManager {
    constructor() {
        this.currentTipIndex = 0;
        this.tipInterval = null;
        this.websocket = null;
        this.progress = 0;
        this.processingStartTime = null;
        this.processedFilesCount = 0;
        this.totalFilesCount = 0;
        this.bytesDone = 0;
        this.totalBytes = 0;
        this.averageProcessingTime = null;
        this.averageTimePerByte = null;
        this.pageType = null; // Added page type property
    }

    /**
     * Initialize the component
     */
    initialize() {
        // Initialize core application for theme and header functionality
        appCore.initialize().then(() => {
            console.log('Core application initialized for initialization component');
        });

        // Detect the current page type
        this.detectPageType();

        // Check session storage for saved progress
        this.restoreProgress();

        // Wire up the error retry button
        const retryBtn = document.getElementById('initRetryBtn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => window.location.reload());
        }

        // A server-rendered error means the failure happened while this page
        // was being generated (e.g. the cache read threw). Polling would
        // report "complete" for the idle scanner and reload straight back
        // into the same failure, so stay on the error state until the user
        // retries manually.
        const serverError = document.getElementById('initError');
        if (serverError && !serverError.hidden) {
            return;
        }

        // Setup the tip carousel
        this.setupTipCarousel();

        // Connect to WebSocket for progress updates
        this.connectWebSocket();

        // Add event listeners for tip navigation
        this.setupTipNavigation();

        // Show first tip as active
        document.querySelector('.tip-item').classList.add('active');
    }

    /**
     * Detect the current page type
     */
    detectPageType() {
        // Get the current page type from URL or data attribute
        const path = window.location.pathname;
        // The recipes page lives at /loras/recipes, so it must be matched
        // before the generic '/loras' check.
        if (path.includes('/recipes')) {
            this.pageType = 'recipes';
        } else if (path.includes('/checkpoints')) {
            this.pageType = 'checkpoints';
        } else if (path.includes('/other')) {
            this.pageType = 'other';
        } else if (path.includes('/loras')) {
            this.pageType = 'loras';
        } else if (path.includes('/embeddings')) {
            this.pageType = 'embeddings';
        } else {
            // Default to loras if can't determine
            this.pageType = 'loras';
        }
        console.log(`Initialization component detected page type: ${this.pageType}`);
    }

    /**
     * Get the storage key with page type prefix
     */
    getStorageKey(key) {
        return `${this.pageType}_${key}`;
    }

    /**
     * Restore progress from session storage if available
     */
    restoreProgress() {
        const savedProgress = getSessionItem(this.getStorageKey('initProgress'));
        if (savedProgress) {
            console.log(`Restoring ${this.pageType} progress from session storage:`, savedProgress);
            
            // Restore progress percentage
            if (savedProgress.progress !== undefined) {
                this.updateProgress(savedProgress.progress);
            }
            
            // Restore processed files count and total files
            if (savedProgress.processedFiles !== undefined) {
                this.processedFilesCount = savedProgress.processedFiles;
            }

            if (savedProgress.totalFiles !== undefined) {
                this.totalFilesCount = savedProgress.totalFiles;
            }

            if (savedProgress.bytesDone !== undefined) {
                this.bytesDone = savedProgress.bytesDone;
            }

            if (savedProgress.totalBytes !== undefined) {
                this.totalBytes = savedProgress.totalBytes;
            }

            // Restore processing time metrics if available
            if (savedProgress.averageProcessingTime !== undefined) {
                this.averageProcessingTime = savedProgress.averageProcessingTime;
            }

            if (savedProgress.averageTimePerByte !== undefined) {
                this.averageTimePerByte = savedProgress.averageTimePerByte;
            }

            if (savedProgress.averageProcessingTime !== undefined || savedProgress.averageTimePerByte !== undefined) {
                this.updateRemainingTime();
            }
            
            // Restore progress status message
            if (savedProgress.details) {
                this.updateStatusMessage(savedProgress.details);
            }
        }
    }

    /**
     * Connect to WebSocket for initialization progress updates
     */
    connectWebSocket() {
        try {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
            this.websocket = new WebSocket(`${wsProtocol}${window.location.host}/ws/init-progress`);
            
            this.websocket.onopen = () => {
                console.log('Connected to initialization progress WebSocket');
            };
            
            this.websocket.onmessage = (event) => {
                this.handleProgressUpdate(JSON.parse(event.data));
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                // Fall back to polling if WebSocket fails
                this.fallbackToPolling();
            };
            
            this.websocket.onclose = () => {
                console.log('WebSocket connection closed');
                // Check if we need to fall back to polling
                if (!this.pollingActive) {
                    this.fallbackToPolling();
                }
            };
        } catch (error) {
            console.error('Failed to connect to WebSocket:', error);
            this.fallbackToPolling();
        }
    }

    /**
     * Fall back to polling if WebSocket connection fails
     */
    fallbackToPolling() {
        this.pollingActive = true;
        this.pollProgress();
        
        // Set a simulated progress that moves forward slowly
        // This gives users feedback even if the backend isn't providing updates
        let simulatedProgress = this.progress || 0;
        const simulateInterval = setInterval(() => {
            simulatedProgress += 0.5;
            if (simulatedProgress > 95) {
                clearInterval(simulateInterval);
                return;
            }
            
            // Only use simulated progress if we haven't received a real update
            if (this.progress < simulatedProgress) {
                this.updateProgress(simulatedProgress);
            }
        }, 1000);
    }

    /**
     * Poll for progress updates from the server
     */
    pollProgress() {
        const checkProgress = () => {
            // Scope the status check to this page's scanner(s), mirroring the
            // WebSocket completion semantics (per-pageType broadcasts).
            fetch(`/api/lm/init-status?page=${encodeURIComponent(this.pageType)}`)
                .then(response => response.json())
                .then(data => {
                    this.handleProgressUpdate(data);

                    if (data.status === 'complete') {
                        // Initialization is complete, stop polling
                        window.location.reload();
                    } else if (data.status !== 'error') {
                        // Errors are already displayed by handleProgressUpdate;
                        // polling again would just reload into the same failure.
                        setTimeout(checkProgress, 2000);
                    }
                })
                .catch(error => {
                    console.error('Error polling for progress:', error);
                    setTimeout(checkProgress, 3000); // Try again after a longer delay
                });
        };

        checkProgress();
    }

    /**
     * Handle progress updates from WebSocket or polling
     */
    handleProgressUpdate(data) {
        if (!data) return;
        console.log('Received progress update:', data);

        // Handle cache health warning messages
        if (data.type === 'cache_health_warning') {
            this.handleCacheHealthWarning(data);
            return;
        }

        // The first-run welcome page owns the pre-scan state; once the scan
        // starts the page reloads into the progress view on its own.
        if (data.stage === 'scan_started') {
            return;
        }
        
        // Check if this update is for our page type
        if (data.pageType && data.pageType !== this.pageType) {
            console.log(`Ignoring update for ${data.pageType}, we're on ${this.pageType}`);
            return;
        }

        // If no pageType is specified in the data but we have scanner_type, map it to pageType
        if (!data.pageType && data.scanner_type) {
            const scannerTypeToPageType = {
                'lora': 'loras',
                'checkpoint': 'checkpoints',
                'embedding': 'embeddings',
                'other': 'other',
                'recipe': 'recipes'
            };
            
            if (scannerTypeToPageType[data.scanner_type] !== this.pageType) {
                console.log(`Ignoring update for ${data.scanner_type}, we're on ${this.pageType}`);
                return;
            }
        }

        // Show scan failures instead of silently sitting on the progress view
        if (data.status === 'error') {
            this.showError(data.details);
            return;
        }
        
        // Save progress data to session storage
        setSessionItem(this.getStorageKey('initProgress'), {
            ...data,
            averageProcessingTime: this.averageProcessingTime,
            averageTimePerByte: this.averageTimePerByte,
            processedFiles: this.processedFilesCount,
            totalFiles: this.totalFilesCount,
            bytesDone: this.bytesDone,
            totalBytes: this.totalBytes
        });
        
        // Update progress percentage
        if (data.progress !== undefined) {
            this.updateProgress(data.progress);
        }
        
        // Update stage-specific details
        if (data.details) {
            this.updateStatusMessage(data.details);
        }
        
        // Structured progress fields broadcast by the backend; the English
        // `details` string is display-only and never parsed here.
        if (data.stage === 'count_models') {
            if (typeof data.total === 'number') {
                this.totalFilesCount = data.total;
            }
            if (typeof data.bytes_total === 'number') {
                this.totalBytes = data.bytes_total;
            }
        }

        // Track processed files/bytes for time estimation
        if (data.stage === 'process_models') {
            const processed = typeof data.processed === 'number' ? data.processed : null;
            const total = typeof data.total === 'number' ? data.total : null;
            const bytesDone = typeof data.bytes_done === 'number' ? data.bytes_done : null;
            const bytesTotal = typeof data.bytes_total === 'number' ? data.bytes_total : null;

            if (total > 0 && this.totalFilesCount === 0) {
                this.totalFilesCount = total;
            }
            if (bytesTotal > 0 && this.totalBytes === 0) {
                this.totalBytes = bytesTotal;
            }

            // Byte-weighted ETA when sizes are available: a 7 GB file and a
            // 100 KB file must not advance the estimate by the same amount.
            if (bytesDone > 0) {
                if (!this.processingStartTime && this.bytesDone === 0) {
                    this.processingStartTime = Date.now();
                }

                if (this.processingStartTime && bytesDone > this.bytesDone) {
                    const elapsedTime = Date.now() - this.processingStartTime;
                    const timePerByte = elapsedTime / bytesDone; // ms per byte

                    // Simple exponential moving average
                    if (!this.averageTimePerByte) {
                        this.averageTimePerByte = timePerByte;
                    } else {
                        this.averageTimePerByte = this.averageTimePerByte * 0.7 + timePerByte * 0.3;
                    }

                    this.updateRemainingTime();
                }

                this.bytesDone = bytesDone;
            } else if (processed !== null) {
                // File-count fallback for progress sources without byte data
                if (processed > 0 && !this.processingStartTime && this.processedFilesCount === 0) {
                    this.processingStartTime = Date.now();
                }

                if (this.processingStartTime && processed > this.processedFilesCount) {
                    const elapsedTime = Date.now() - this.processingStartTime;
                    const timePerFile = elapsedTime / processed; // ms per file

                    // Simple exponential moving average
                    if (!this.averageProcessingTime) {
                        this.averageProcessingTime = timePerFile;
                    } else {
                        this.averageProcessingTime = this.averageProcessingTime * 0.7 + timePerFile * 0.3;
                    }

                    this.updateRemainingTime();
                }
            }

            if (processed !== null) {
                this.processedFilesCount = processed;
            }
        }
        
        // If initialization is complete, reload the page
        if (data.status === 'complete') {
            this.showCompletionMessage();
            
            // Remove session storage data since we're done
            setSessionItem(this.getStorageKey('initProgress'), null);
            
            // Give the user a moment to see the completion message
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        }
    }

    /**
     * Update the remaining time display based on current progress
     */
    updateRemainingTime() {
        // Byte-weighted estimate when sizes are known, file-count fallback
        // otherwise.
        let remainingTimeMs = null;
        if (this.averageTimePerByte && this.totalBytes > 0) {
            remainingTimeMs = (this.totalBytes - this.bytesDone) * this.averageTimePerByte;
        } else if (this.averageProcessingTime && this.totalFilesCount > 0) {
            const remainingFiles = this.totalFilesCount - this.processedFilesCount;
            remainingTimeMs = remainingFiles * this.averageProcessingTime;
        }

        if (remainingTimeMs === null) {
            document.getElementById('remainingTime').textContent = 'Estimating...';
            return;
        }

        if (remainingTimeMs <= 0) {
            document.getElementById('remainingTime').textContent = 'Almost done...';
            return;
        }
        
        // Format the time for display
        let formattedTime;
        if (remainingTimeMs < 60000) {
            // Less than a minute
            formattedTime = 'Less than a minute';
        } else if (remainingTimeMs < 3600000) {
            // Less than an hour
            const minutes = Math.round(remainingTimeMs / 60000);
            formattedTime = `~${minutes} minute${minutes !== 1 ? 's' : ''}`;
        } else {
            // Hours and minutes
            const hours = Math.floor(remainingTimeMs / 3600000);
            const minutes = Math.round((remainingTimeMs % 3600000) / 60000);
            formattedTime = `~${hours} hour${hours !== 1 ? 's' : ''} ${minutes} minute${minutes !== 1 ? 's' : ''}`;
        }
        
        document.getElementById('remainingTime').textContent = formattedTime + ' remaining';
    }

    /**
     * Update status message
     */
    updateStatusMessage(message) {
        const progressStatus = document.getElementById('progressStatus');
        if (progressStatus) {
            progressStatus.textContent = message;
        }
    }

    /**
     * Update the progress bar and percentage
     */
    updateProgress(progress) {
        this.progress = progress;
        const progressBar = document.getElementById('initProgressBar');
        const progressPercentage = document.getElementById('progressPercentage');
        
        if (progressBar && progressPercentage) {
            progressBar.style.width = `${progress}%`;
            progressPercentage.textContent = `${Math.round(progress)}%`;
        }
    }

    /**
     * Setup the tip carousel to rotate through tips
     */
    setupTipCarousel() {
        const tipItems = document.querySelectorAll('.tip-item');
        if (tipItems.length === 0) return;
        
        // Show the first tip
        tipItems[0].classList.add('active');
        document.querySelector('.tip-dot').classList.add('active');
        
        // Set up automatic rotation
        this.tipInterval = setInterval(() => {
            this.showNextTip();
        }, 8000); // Change tip every 8 seconds
    }

    /**
     * Setup tip navigation dots
     */
    setupTipNavigation() {
        const tipDots = document.querySelectorAll('.tip-dot');
        
        tipDots.forEach((dot, index) => {
            dot.addEventListener('click', () => {
                this.showTipByIndex(index);
            });
        });
    }

    /**
     * Show the next tip in the carousel
     */
    showNextTip() {
        const tipItems = document.querySelectorAll('.tip-item');
        const tipDots = document.querySelectorAll('.tip-dot');
        
        if (tipItems.length === 0) return;
        
        // Hide current tip
        tipItems[this.currentTipIndex].classList.remove('active');
        tipDots[this.currentTipIndex].classList.remove('active');
        
        // Calculate next index
        this.currentTipIndex = (this.currentTipIndex + 1) % tipItems.length;
        
        // Show next tip
        tipItems[this.currentTipIndex].classList.add('active');
        tipDots[this.currentTipIndex].classList.add('active');
    }

    /**
     * Show a specific tip by index
     */
    showTipByIndex(index) {
        const tipItems = document.querySelectorAll('.tip-item');
        const tipDots = document.querySelectorAll('.tip-dot');
        
        if (index >= tipItems.length || index < 0) return;
        
        // Hide current tip
        tipItems[this.currentTipIndex].classList.remove('active');
        tipDots[this.currentTipIndex].classList.remove('active');
        
        // Update index and show selected tip
        this.currentTipIndex = index;
        
        // Show selected tip
        tipItems[this.currentTipIndex].classList.add('active');
        tipDots[this.currentTipIndex].classList.add('active');
        
        // Reset interval to prevent quick tip change
        if (this.tipInterval) {
            clearInterval(this.tipInterval);
            this.tipInterval = setInterval(() => {
                this.showNextTip();
            }, 8000);
        }
    }

    /**
     * Show an initialization error with a retry button
     */
    showError(details) {
        const loadingContent = document.querySelector('.initialization-container .loading-content');
        const errorEl = document.getElementById('initError');
        const errorText = document.getElementById('initErrorText');

        if (loadingContent) {
            loadingContent.style.display = 'none';
        }

        if (errorText) {
            errorText.textContent = details || '';
        }

        if (errorEl) {
            errorEl.hidden = false;
        }
    }

    /**
     * Show completion message
     */
    showCompletionMessage() {
        // Update progress to 100%
        this.updateProgress(100);
        
        // Update status message
        this.updateStatusMessage('Initialization complete!');
        
        // Update title and subtitle
        const initTitle = document.getElementById('initTitle');
        const initSubtitle = document.getElementById('initSubtitle');
        const remainingTime = document.getElementById('remainingTime');
        
        if (initTitle) {
            initTitle.textContent = 'Initialization Complete';
        }
        
        if (initSubtitle) {
            initSubtitle.textContent = 'Reloading page...';
        }
        
        if (remainingTime) {
            remainingTime.textContent = 'Done!';
        }
    }

    /**
     * Handle cache health warning messages from WebSocket
     */
    handleCacheHealthWarning(data) {
        console.log('Cache health warning received:', data);

        // Import bannerService dynamically to avoid circular dependencies
        import('../managers/BannerService.js').then(({ bannerService }) => {
            // Initialize banner service if not already done
            if (!bannerService.initialized) {
                bannerService.initialize().then(() => {
                    bannerService.registerCacheHealthBanner(data);
                }).catch(err => {
                    console.error('Failed to initialize banner service:', err);
                });
            } else {
                bannerService.registerCacheHealthBanner(data);
            }
        }).catch(err => {
            console.error('Failed to load banner service:', err);
        });
    }

    /**
     * Clean up resources when the component is destroyed
     */
    cleanup() {
        if (this.tipInterval) {
            clearInterval(this.tipInterval);
        }
        
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.close();
        }
    }
}

// Create and export the initialization manager
export const initManager = new InitializationManager();

// Initialize the component when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're in initialization mode
    const initContainer = document.getElementById('initializationContainer');
    if (initContainer) {
        initManager.initialize();
    }
});

// Clean up when the page is unloaded
window.addEventListener('beforeunload', () => {
    initManager.cleanup();
});