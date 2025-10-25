import { BaseContextMenu } from './BaseContextMenu.js';
import { showToast } from '../../utils/uiHelpers.js';
import { state } from '../../state/index.js';
import { translate } from '../../utils/i18nHelpers.js';
import { getCompleteApiConfig, getCurrentModelType } from '../../api/apiConfig.js';
import { resetAndReload } from '../../api/modelApiFactory.js';

export class GlobalContextMenu extends BaseContextMenu {
    constructor() {
        super('globalContextMenu');
        this._cleanupInProgress = false;
        this._updateCheckInProgress = false;
    }

    showMenu(x, y, origin = null) {
        const contextOrigin = origin || { type: 'global' };
        super.showMenu(x, y, contextOrigin);
    }

    handleMenuAction(action, menuItem) {
        switch (action) {
            case 'cleanup-example-images-folders':
                this.cleanupExampleImagesFolders(menuItem).catch((error) => {
                    console.error('Failed to trigger example images cleanup:', error);
                });
                break;
            case 'download-example-images':
                this.downloadExampleImages(menuItem).catch((error) => {
                    console.error('Failed to trigger example images download:', error);
                });
                break;
            case 'check-model-updates':
                this.checkModelUpdates(menuItem).catch((error) => {
                    console.error('Failed to check model updates:', error);
                });
                break;
            default:
                console.warn(`Unhandled global context menu action: ${action}`);
                break;
        }
    }

    async downloadExampleImages(menuItem) {
        const exampleImagesManager = window.exampleImagesManager;

        if (!exampleImagesManager) {
            showToast('globalContextMenu.downloadExampleImages.unavailable', {}, 'error');
            return;
        }

        const downloadPath = state?.global?.settings?.example_images_path;
        if (!downloadPath) {
            showToast('globalContextMenu.downloadExampleImages.missingPath', {}, 'warning');
            return;
        }

        menuItem?.classList.add('disabled');

        try {
            await exampleImagesManager.handleDownloadButton();
        } finally {
            menuItem?.classList.remove('disabled');
        }
    }

    async cleanupExampleImagesFolders(menuItem) {
        if (this._cleanupInProgress) {
            return;
        }

        this._cleanupInProgress = true;
        menuItem?.classList.add('disabled');

        try {
            const response = await fetch('/api/lm/cleanup-example-image-folders', {
                method: 'POST',
            });

            let payload;
            try {
                payload = await response.json();
            } catch (parseError) {
                payload = { error: 'Unexpected response format.' };
            }

            if (response.ok && (payload.success || payload.partial_success)) {
                const movedTotal = payload.moved_total || 0;

                if (movedTotal > 0) {
                    showToast('globalContextMenu.cleanupExampleImages.success', { count: movedTotal }, 'success');
                } else {
                    showToast('globalContextMenu.cleanupExampleImages.none', {}, 'info');
                }

                if (payload.partial_success) {
                    showToast(
                        'globalContextMenu.cleanupExampleImages.partial',
                        { failures: payload.move_failures ?? 0 },
                        'warning',
                    );
                }
            } else {
                const message = payload?.error || 'Unknown error';
                showToast('globalContextMenu.cleanupExampleImages.error', { message }, 'error');
            }
        } catch (error) {
            showToast('globalContextMenu.cleanupExampleImages.error', { message: error.message || 'Unknown error' }, 'error');
        } finally {
            this._cleanupInProgress = false;
            menuItem?.classList.remove('disabled');
        }
    }

    async checkModelUpdates(menuItem) {
        if (this._updateCheckInProgress) {
            return;
        }

        const modelType = getCurrentModelType();
        const apiConfig = getCompleteApiConfig(modelType);

        if (!apiConfig?.endpoints?.refreshUpdates) {
            console.warn('Refresh updates endpoint not configured for model type:', modelType);
            return;
        }

        this._updateCheckInProgress = true;
        menuItem?.classList.add('disabled');

        const displayName = apiConfig.config?.displayName ?? 'Model';
        const loadingMessage = translate(
            'globalContextMenu.checkModelUpdates.loading',
            { type: displayName },
            `Checking for ${displayName} updates...`
        );

        state.loadingManager?.showSimpleLoading?.(loadingMessage);

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

            const records = Array.isArray(payload.records) ? payload.records : [];

            if (records.length > 0) {
                showToast('globalContextMenu.checkModelUpdates.success', { count: records.length, type: displayName }, 'success');
            } else {
                showToast('globalContextMenu.checkModelUpdates.none', { type: displayName }, 'info');
            }

            await resetAndReload(false);
        } catch (error) {
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
            menuItem?.classList.remove('disabled');
            this._updateCheckInProgress = false;
        }
    }
}
