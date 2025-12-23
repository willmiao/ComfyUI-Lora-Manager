import { BaseContextMenu } from './BaseContextMenu.js';
import { showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';
import { state } from '../../state/index.js';
import { getCompleteApiConfig, getCurrentModelType } from '../../api/apiConfig.js';
import { performModelUpdateCheck } from '../../utils/updateCheckHelpers.js';

export class GlobalContextMenu extends BaseContextMenu {
    constructor() {
        super('globalContextMenu');
        this._cleanupInProgress = false;
        this._updateCheckInProgress = false;
        this._licenseRefreshInProgress = false;
    }

    showMenu(x, y, origin = null) {
        const contextOrigin = origin || { type: 'global' };

        // Conditional visibility for recipes page
        const isRecipesPage = state.currentPageType === 'recipes';
        const modelUpdateItem = this.menu.querySelector('[data-action="check-model-updates"]');
        const licenseRefreshItem = this.menu.querySelector('[data-action="fetch-missing-licenses"]');
        const downloadExamplesItem = this.menu.querySelector('[data-action="download-example-images"]');
        const cleanupExamplesItem = this.menu.querySelector('[data-action="cleanup-example-images-folders"]');
        const repairRecipesItem = this.menu.querySelector('[data-action="repair-recipes"]');

        if (isRecipesPage) {
            modelUpdateItem?.classList.add('hidden');
            licenseRefreshItem?.classList.add('hidden');
            downloadExamplesItem?.classList.add('hidden');
            cleanupExamplesItem?.classList.add('hidden');
            repairRecipesItem?.classList.remove('hidden');
        } else {
            modelUpdateItem?.classList.remove('hidden');
            licenseRefreshItem?.classList.remove('hidden');
            downloadExamplesItem?.classList.remove('hidden');
            cleanupExamplesItem?.classList.remove('hidden');
            repairRecipesItem?.classList.add('hidden');
        }

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
            case 'fetch-missing-licenses':
                this.fetchMissingLicenses(menuItem).catch((error) => {
                    console.error('Failed to refresh missing license metadata:', error);
                });
                break;
            case 'repair-recipes':
                this.repairRecipes(menuItem).catch((error) => {
                    console.error('Failed to repair recipes:', error);
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

        this._updateCheckInProgress = true;
        menuItem?.classList.add('disabled');

        try {
            await performModelUpdateCheck({
                onComplete: () => {
                    menuItem?.classList.remove('disabled');
                    this._updateCheckInProgress = false;
                }
            });
        } catch (error) {
            console.error('Failed to check model updates:', error);
        } finally {
            if (this._updateCheckInProgress) {
                this._updateCheckInProgress = false;
                menuItem?.classList.remove('disabled');
            }
        }
    }

    async fetchMissingLicenses(menuItem) {
        if (this._licenseRefreshInProgress) {
            return;
        }

        const modelType = getCurrentModelType();
        const apiConfig = getCompleteApiConfig(modelType);
        const displayName = apiConfig?.config?.displayName ?? 'Model';
        const typePlural = this._buildTypePlural(displayName);
        const loadingMessage = translate(
            'globalContextMenu.fetchMissingLicenses.loading',
            { type: displayName, typePlural },
            `Refreshing license metadata for ${typePlural}...`
        );

        const endpoint = apiConfig?.endpoints?.fetchMissingLicenses;
        if (!endpoint) {
            console.warn('Fetch missing license endpoint not configured for model type:', modelType);
            showToast(
                'globalContextMenu.fetchMissingLicenses.error',
                { message: 'Endpoint unavailable', type: displayName, typePlural },
                'warning'
            );
            return;
        }

        this._licenseRefreshInProgress = true;
        menuItem?.classList?.add('disabled');
        state.loadingManager?.showSimpleLoading?.(loadingMessage);

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
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

            const updated = Array.isArray(payload.updated) ? payload.updated : [];
            if (updated.length > 0) {
                showToast(
                    'globalContextMenu.fetchMissingLicenses.success',
                    { count: updated.length, type: displayName, typePlural },
                    'success'
                );
            } else {
                showToast(
                    'globalContextMenu.fetchMissingLicenses.none',
                    { type: displayName, typePlural },
                    'info'
                );
            }
        } catch (error) {
            console.error('Failed to refresh missing license metadata:', error);
            showToast(
                'globalContextMenu.fetchMissingLicenses.error',
                { message: error?.message ?? 'Unknown error', type: displayName, typePlural },
                'error'
            );
        } finally {
            state.loadingManager?.hide?.();
            if (typeof state.loadingManager?.restoreProgressBar === 'function') {
                state.loadingManager.restoreProgressBar();
            }

            this._licenseRefreshInProgress = false;
            menuItem?.classList?.remove('disabled');
        }
    }

    _buildTypePlural(displayName) {
        if (!displayName) {
            return 'models';
        }

        const lower = displayName.toLowerCase();
        if (lower.endsWith('s')) {
            return displayName;
        }

        return `${displayName}s`;
    }

    async repairRecipes(menuItem) {
        if (this._repairInProgress) {
            return;
        }

        this._repairInProgress = true;
        menuItem?.classList.add('disabled');

        const loadingMessage = translate(
            'globalContextMenu.repairRecipes.loading',
            {},
            'Repairing recipe data...'
        );

        const progressUI = state.loadingManager?.showEnhancedProgress(loadingMessage);

        try {
            const response = await fetch('/api/lm/recipes/repair', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Failed to start repair');
            }

            // Poll for progress (or wait for WebSocket if preferred, but polling is simpler for this implementation)
            let isComplete = false;
            while (!isComplete && this._repairInProgress) {
                const progressResponse = await fetch('/api/lm/recipes/repair-progress');
                if (progressResponse.ok) {
                    const progressResult = await progressResponse.json();
                    if (progressResult.success && progressResult.progress) {
                        const p = progressResult.progress;
                        if (p.status === 'processing') {
                            const percent = (p.current / p.total) * 100;
                            progressUI?.updateProgress(percent, p.recipe_name, `${loadingMessage} (${p.current}/${p.total})`);
                        } else if (p.status === 'completed') {
                            isComplete = true;
                            progressUI?.complete(translate(
                                'globalContextMenu.repairRecipes.success',
                                { count: p.repaired },
                                `Repaired ${p.repaired} recipes.`
                            ));
                            showToast('globalContextMenu.repairRecipes.success', { count: p.repaired }, 'success');
                            // Refresh recipes page if active
                            if (window.recipesPage) {
                                window.recipesPage.refresh();
                            }
                        } else if (p.status === 'error') {
                            throw new Error(p.error || 'Repair failed');
                        }
                    } else if (progressResponse.status === 404) {
                        // Progress might have finished quickly and been cleaned up
                        isComplete = true;
                        progressUI?.complete();
                    }
                }

                if (!isComplete) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
        } catch (error) {
            console.error('Recipe repair failed:', error);
            progressUI?.complete(translate('globalContextMenu.repairRecipes.error', { message: error.message }, 'Repair failed: {message}'));
            showToast('globalContextMenu.repairRecipes.error', { message: error.message }, 'error');
        } finally {
            this._repairInProgress = false;
            menuItem?.classList.remove('disabled');
        }
    }
}
