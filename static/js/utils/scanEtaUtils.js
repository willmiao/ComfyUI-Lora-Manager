import { translate } from './i18nHelpers.js';

/**
 * Format a remaining-time estimate for scan progress display.
 * @param {number} remainingMs - Estimated remaining time in milliseconds
 * @returns {string} Localized ETA text
 */
export function formatScanRemainingTime(remainingMs) {
    if (remainingMs < 60000) {
        return translate('common.scanProgress.eta.lessThanMinute', {}, 'Less than a minute remaining');
    }
    if (remainingMs < 3600000) {
        const minutes = Math.round(remainingMs / 60000);
        return translate('common.scanProgress.eta.minutes', { minutes }, `~${minutes} min remaining`);
    }
    const hours = Math.floor(remainingMs / 3600000);
    const minutes = Math.round((remainingMs % 3600000) / 60000);
    return translate('common.scanProgress.eta.hours', { hours, minutes }, `~${hours} hr ${minutes} min remaining`);
}

/**
 * Create an ETA tracker for scan progress. Uses an exponential moving
 * average (0.7/0.3) over the observed per-file processing time, mirroring
 * the estimator in components/initialization.js.
 * @returns {{ update: (processed: number, total: number) => (string|null) }}
 */
export function createScanEtaTracker() {
    let startTime = null;
    let lastProcessed = 0;
    let averageMsPerFile = null;

    return {
        /**
         * Update with the latest counters.
         * @returns {string|null} Localized ETA text, or null when not applicable
         */
        update(processed, total) {
            if (!total || total <= 0 || processed >= total) {
                return null;
            }
            const now = Date.now();
            if (startTime === null) {
                // First sample only anchors the timer; not enough data yet
                startTime = now;
                lastProcessed = processed;
                return translate('initialization.estimatingTime', {}, 'Estimating time...');
            }
            if (processed > lastProcessed) {
                const msPerFile = (now - startTime) / processed;
                averageMsPerFile = averageMsPerFile === null
                    ? msPerFile
                    : averageMsPerFile * 0.7 + msPerFile * 0.3;
                lastProcessed = processed;
            }
            if (averageMsPerFile === null) {
                return translate('initialization.estimatingTime', {}, 'Estimating time...');
            }
            return formatScanRemainingTime((total - lastProcessed) * averageMsPerFile);
        }
    };
}
