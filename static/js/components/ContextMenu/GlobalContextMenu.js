import { BaseContextMenu } from './BaseContextMenu.js';
import { showToast } from '../../utils/uiHelpers.js';

export class GlobalContextMenu extends BaseContextMenu {
    constructor() {
        super('globalContextMenu');
        this._cleanupInProgress = false;
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
            default:
                console.warn(`Unhandled global context menu action: ${action}`);
                break;
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
}
