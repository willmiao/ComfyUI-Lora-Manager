import { state } from '../state/index.js';
import { translate } from './i18nHelpers.js';
import { showToast } from './uiHelpers.js';
import { getCompleteApiConfig, getCurrentModelType } from '../api/apiConfig.js';
import { resetAndReload } from '../api/modelApiFactory.js';

/**
 * Perform a model update check using the shared backend endpoint.
 * @param {Object} [options]
 * @param {Function} [options.onStart] - Callback invoked before the request is sent.
 * @param {Function} [options.onComplete] - Callback invoked after the request settles.
 * @returns {Promise<{status: 'success' | 'error' | 'unsupported', displayName: string, records: Array, error: Error | null}>}
 */
export async function performModelUpdateCheck({ onStart, onComplete } = {}) {
    const modelType = getCurrentModelType();
    const apiConfig = getCompleteApiConfig(modelType);
    const displayName = apiConfig?.config?.displayName ?? 'Model';

    if (!apiConfig?.endpoints?.refreshUpdates) {
        console.warn('Refresh updates endpoint not configured for model type:', modelType);
        onComplete?.({ status: 'unsupported', displayName, records: [], error: null });
        return { status: 'unsupported', displayName, records: [], error: null };
    }

    const loadingMessage = translate(
        'globalContextMenu.checkModelUpdates.loading',
        { type: displayName },
        `Checking for ${displayName} updates...`
    );

    onStart?.({ displayName, loadingMessage });

    state.loadingManager?.showSimpleLoading?.(loadingMessage);

    let status = 'success';
    let records = [];
    let error = null;

    try {
        const response = await fetch(apiConfig.endpoints.refreshUpdates, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: false })
        });

        let payload = {};
        try {
            payload = await response.json();
        } catch {
            payload = {};
        }

        if (!response.ok || payload.success !== true) {
            const errorMessage = payload?.error || response.statusText || 'Unknown error';
            throw new Error(errorMessage);
        }

        records = Array.isArray(payload.records) ? payload.records : [];

        if (records.length > 0) {
            showToast('globalContextMenu.checkModelUpdates.success', { count: records.length, type: displayName }, 'success');
        } else {
            showToast('globalContextMenu.checkModelUpdates.none', { type: displayName }, 'info');
        }

        await resetAndReload(false);
    } catch (err) {
        status = 'error';
        error = err instanceof Error ? err : new Error(String(err));
        console.error('Error checking model updates:', error);
        showToast(
            'globalContextMenu.checkModelUpdates.error',
            { message: error?.message ?? 'Unknown error', type: displayName },
            'error'
        );
    } finally {
        state.loadingManager?.hide?.();
        if (typeof state.loadingManager?.restoreProgressBar === 'function') {
            state.loadingManager.restoreProgressBar();
        }
        onComplete?.({ status, displayName, records, error });
    }

    return { status, displayName, records, error };
}
