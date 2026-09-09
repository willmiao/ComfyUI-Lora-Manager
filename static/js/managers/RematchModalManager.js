import { modalManager } from './ModalManager.js';
import { translate } from '../utils/i18nHelpers.js';

/**
 * Owns the recipe-rematch options modal (rematchOptionsModal), shown BEFORE
 * a global/bulk/single rematch run; collects the "relaxed matching" opt-in
 * and only then invokes the run callback. Post-run reporting lives in
 * static/js/components/RematchSummaryModal.js.
 */
export class RematchModalManager {
    constructor() {
        this._optionsConfirmCallback = null;
    }

    /**
     * Open the options modal. `onConfirm({ relaxed })` fires only when the
     * user clicks Rematch — Cancel/X runs nothing.
     *
     * @param {{ scope?: 'global'|'bulk'|'single', recipeCount?: number|null, onConfirm?: function }} options
     */
    showOptionsModal({ scope = null, recipeCount = null, onConfirm } = {}) {
        const resolvedScope = scope || (recipeCount != null ? 'bulk' : 'global');
        const message = document.getElementById('rematchOptionsMessage');
        if (message) {
            if (resolvedScope === 'bulk') {
                message.textContent = translate(
                    'modals.rematchOptions.messageBulk',
                    { count: recipeCount },
                    `${recipeCount} selected recipe(s) will be scanned against your local model library.`
                );
            } else if (resolvedScope === 'single') {
                message.textContent = translate(
                    'modals.rematchOptions.messageSingle',
                    {},
                    'This recipe will be scanned against your local model library.'
                );
            } else {
                message.textContent = translate(
                    'modals.rematchOptions.messageGlobal',
                    {},
                    'All recipes will be scanned against your local model library.'
                );
            }
        }
        const checkbox = document.getElementById('rematchOptionsRelaxed');
        if (checkbox) {
            checkbox.checked = false;
        }
        this._optionsConfirmCallback = typeof onConfirm === 'function' ? onConfirm : null;
        modalManager.showModal('rematchOptionsModal');
    }

    confirmOptions() {
        const checkbox = document.getElementById('rematchOptionsRelaxed');
        const relaxed = checkbox ? !!checkbox.checked : false;
        const callback = this._optionsConfirmCallback;
        this._optionsConfirmCallback = null;
        modalManager.closeModal('rematchOptionsModal');
        if (callback) {
            // Returned so callers (and tests) can await the started run.
            return callback({ relaxed });
        }
        return undefined;
    }

    cancelOptions() {
        this._optionsConfirmCallback = null;
        modalManager.closeModal('rematchOptionsModal');
    }
}

export const rematchModalManager = new RematchModalManager();
