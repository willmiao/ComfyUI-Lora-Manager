import { state } from '../state/index.js';
import { translate } from './i18nHelpers.js';
import { showToast } from './uiHelpers.js';
import { getCompleteApiConfig, getCurrentModelType } from '../api/apiConfig.js';
import { resetAndReload, getModelApiClient } from '../api/modelApiFactory.js';
import { getStorageItem, setStorageItem } from './storageHelpers.js';
import { modalManager } from '../managers/ModalManager.js';

const CHECK_UPDATES_CONFIRMATION_KEY = 'ack_check_updates_for_all_models';

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
    const apiClient = getModelApiClient(modelType);
    const displayName = apiConfig?.config?.displayName ?? 'Model';

    if (!apiConfig?.endpoints?.refreshUpdates) {
        console.warn('Refresh updates endpoint not configured for model type:', modelType);
        onComplete?.({ status: 'unsupported', displayName, records: [], error: null });
        return { status: 'unsupported', displayName, records: [], error: null };
    }

    const proceed = await ensureCheckUpdatesConfirmation(displayName);
    if (!proceed) {
        onComplete?.({ status: 'cancelled', displayName, records: [], error: null });
        return { status: 'cancelled', displayName, records: [], error: null };
    }

    const loadingMessage = translate(
        'globalContextMenu.checkModelUpdates.loading',
        { type: displayName },
        `Checking for ${displayName} updates...`
    );

    onStart?.({ displayName, loadingMessage });

    state.loadingManager?.showSimpleLoading?.(loadingMessage);
    state.loadingManager?.showCancelButton?.(() => apiClient.cancelTask());

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
            if (payload?.status === 'cancelled') {
                showToast('toast.api.operationCancelled', {}, 'info');
                return { status: 'cancelled', displayName, records: [], error: null };
            }
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

function getTypePlural(displayName) {
    if (!displayName) {
        return 'models';
    }

    const lower = displayName.toLowerCase();
    if (lower.endsWith('s')) {
        return displayName;
    }

    return `${displayName}s`;
}

async function ensureCheckUpdatesConfirmation(displayName) {
    const hasConfirmed = getStorageItem(CHECK_UPDATES_CONFIRMATION_KEY, false);
    if (hasConfirmed) {
        return true;
    }

    const modalElement = document.getElementById('checkUpdatesConfirmModal');
    if (!modalElement) {
        return true;
    }

    const typePlural = getTypePlural(displayName);

    const titleElement = modalElement.querySelector('[data-role="title"]');
    if (titleElement) {
        titleElement.textContent = translate(
            'modals.checkUpdates.title',
            { type: displayName, typePlural },
            `Check updates for all ${typePlural}?`
        );
    }

    const messageElement = modalElement.querySelector('[data-role="message"]');
    if (messageElement) {
        messageElement.textContent = translate(
            'modals.checkUpdates.message',
            { type: displayName, typePlural },
            `This checks every ${typePlural} in your library for updates. Large collections may take a little longer.`
        );
    }

    const tipElement = modalElement.querySelector('[data-role="tip"]');
    if (tipElement) {
        tipElement.textContent = translate(
            'modals.checkUpdates.tip',
            { type: displayName, typePlural },
            'To work in smaller batches, switch to bulk mode, pick the ones you need, then use "Check Updates for Selected".'
        );
    }

    const confirmButton = modalElement.querySelector('[data-action="confirm-check-updates"]');
    const cancelButton = modalElement.querySelector('[data-action="cancel-check-updates"]');

    if (!confirmButton || !cancelButton) {
        return true;
    }

    return new Promise((resolve) => {
        let resolved = false;

        const cleanup = () => {
            confirmButton.removeEventListener('click', handleConfirm);
            cancelButton.removeEventListener('click', handleCancel);
        };

        const finalize = (proceed) => {
            if (resolved) {
                return;
            }

            resolved = true;
            cleanup();
            resolve(proceed);
        };

        const handleConfirm = (event) => {
            event.preventDefault();
            setStorageItem(CHECK_UPDATES_CONFIRMATION_KEY, true);
            finalize(true);
            modalManager.closeModal('checkUpdatesConfirmModal');
        };

        const handleCancel = (event) => {
            event.preventDefault();
            finalize(false);
            modalManager.closeModal('checkUpdatesConfirmModal');
        };

        confirmButton.addEventListener('click', handleConfirm);
        cancelButton.addEventListener('click', handleCancel);

        modalManager.showModal('checkUpdatesConfirmModal', null, () => finalize(false));
    });
}
