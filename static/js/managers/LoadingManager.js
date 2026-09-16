import { translate } from '../utils/i18nHelpers.js';
import { formatFileSize } from '../utils/formatters.js';
import { getModelSource } from '../utils/modelSourceHelpers.js';

// Loading management
export class LoadingManager {
    constructor() {
        if (LoadingManager.instance) {
            return LoadingManager.instance;
        }

        // Delay DOM creation until first use to ensure i18n is ready
        this._initialized = false;
        this.overlay = null;
        this.loadingContent = null;
        this.progressBar = null;
        this.statusText = null;
        this.cancelButton = null;
        this.onCancelCallback = null;
        this.detailsContainer = null;

        LoadingManager.instance = this;
    }

    _ensureInitialized() {
        if (this._initialized) return;

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

        this.cancelButton = this.loadingContent.querySelector('.loading-cancel');
        if (!this.cancelButton) {
            this.cancelButton = document.createElement('button');
            this.cancelButton.className = 'loading-cancel secondary-btn';
            this.cancelButton.style.display = 'none';
            this.cancelButton.style.margin = 'var(--space-2) auto 0';
            this.cancelButton.textContent = translate('common.actions.cancel', {}, 'Cancel');
            this.loadingContent.appendChild(this.cancelButton);
        }

        this.cancelButton.onclick = () => {
            if (this.onCancelCallback) {
                this.onCancelCallback();
                this.cancelButton.disabled = true;
                this.cancelButton.textContent = translate('common.status.cancelling', {}, 'Cancelling...');
            }
        };

        this._initialized = true;
    }

    show(message = 'Loading...', progress = 0) {
        this._ensureInitialized();
        this.overlay.style.display = 'flex';
        this.setProgress(progress);
        this.setStatus(message);

        // Remove any existing details container
        this.removeDetailsContainer();
    }

    hide() {
        if (!this._initialized) return;
        this.overlay.style.display = 'none';
        this.reset();
        this.removeDetailsContainer();
    }

    setProgress(percent) {
        if (!this._initialized) return;
        this.progressBar.style.width = `${percent}%`;
        this.progressBar.setAttribute('aria-valuenow', percent);
    }

    setStatus(message) {
        if (!this._initialized) return;
        this.statusText.textContent = message;
    }

    reset() {
        if (!this._initialized) return;
        this.setProgress(0);
        this.setStatus('');
        this.removeDetailsContainer();
        this.hideCancelButton();
        this.progressBar.style.display = 'block';
    }

    showCancelButton(onCancel) {
        this._ensureInitialized();
        if (this.cancelButton) {
            this.onCancelCallback = onCancel;
            this.cancelButton.style.display = 'flex';
            this.cancelButton.disabled = false;
            this.cancelButton.textContent = translate('common.actions.cancel', {}, 'Cancel');
        }
    }

    hideCancelButton() {
        if (!this._initialized) return;
        if (this.cancelButton) {
            this.cancelButton.style.display = 'none';
            this.onCancelCallback = null;
        }
    }

    // Create a details container for enhanced progress display
    createDetailsContainer() {
        this._ensureInitialized();
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

        /**
         * Describe a post-transfer stage in the status line.
         *
         * The byte counter stops as soon as the last byte lands, but the
         * backend still hashes the file and reads the model site's API. Naming
         * that work is what stops the bar looking frozen at 100%.
         */
        const describeMetadataStage = (stage, platform) => {
            if (stage === 'indexing') {
                return translate(
                    'modals.download.progress.indexingFile',
                    {},
                    'Reading model file...'
                );
            }
            const label = getModelSource(platform)?.label || platform || '';
            return label
                ? translate(
                    'modals.download.progress.fetchingSourceMetadata',
                    { source: label },
                    `Fetching metadata from ${label}...`
                )
                : translate(
                    'modals.download.progress.fetchingMetadata',
                    {},
                    'Fetching metadata...'
                );
        };

        // Initialize transfer stats with empty data
        updateTransferStats();

        if (this.cancelButton) {
            this.loadingContent.appendChild(this.cancelButton);
        }

        /**
         * Update the progress UI.
         *
         * @param {number} currentProgress Percentage of the current item.
         * @param {number} [currentIndex] Items finished so far.
         * @param {string} [currentName] File being processed.
         * @param {object} [metrics] Byte counters; only meaningful while
         *   transferring.
         * @param {object} [phase] `{ phase: 'metadata', stage, platform }` once
         *   the transfer has finished, so the UI can show what is still running
         *   instead of a 0 B/s speed.
         */
        return (
            currentProgress,
            currentIndex = 0,
            currentName = '',
            metrics = {},
            phase = null
        ) => {
            const isMetadata = phase?.phase === 'metadata';

            // Update current item progress
            currentItemProgress.style.width = `${currentProgress}%`;
            currentItemPercent.textContent = `${Math.floor(currentProgress)}%`;
            currentItemProgress.classList.toggle('is-indeterminate', isMetadata);

            // Update current item label if name provided
            if (currentName) {
                currentItemLabel.textContent = isMetadata
                    ? translate(
                        'modals.download.progress.metadata',
                        { name: currentName },
                        `Metadata: ${currentName}`
                    )
                    : translate(
                        'modals.download.progress.downloading',
                        { name: currentName },
                        `Downloading: ${currentName}`
                    );
            }

            // No bytes are moving any more, so report the stage instead of a
            // rate that has dropped to zero.
            if (isMetadata) {
                updateTransferStats({ bytesDownloaded: metrics.bytesDownloaded, totalBytes: metrics.totalBytes });
                const stageText = describeMetadataStage(phase.stage, phase.platform);
                speedDetail.textContent = stageText;
                // Keep the batch position visible; the status line is the one
                // place a caller also writes to.
                this.setStatus(
                    totalItems > 1
                        ? `${Math.min(currentIndex + 1, totalItems)}/${totalItems}: ${stageText}`
                        : stageText
                );
            } else {
                updateTransferStats(metrics);
            }

            // Update overall label if multiple items
            if (totalItems > 1 && overallLabel) {
                overallLabel.textContent = `Overall progress (${currentIndex}/${totalItems} complete):`;

                // Calculate and update overall progress
                const overallProgress = Math.floor((currentIndex + currentProgress / 100) / totalItems * 100);
                this.setProgress(overallProgress);
            } else {
                // Single item, just update main progress
                this.setProgress(currentProgress);
            }
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

            showCancelButton: (onCancel) => {
                this.showCancelButton(onCancel);
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
        this._ensureInitialized();
        this.overlay.style.display = 'flex';
        this.progressBar.style.display = 'none';
        this.setStatus(message);
    }

    restoreProgressBar() {
        if (!this._initialized) return;
        this.progressBar.style.display = 'block';
    }
}
