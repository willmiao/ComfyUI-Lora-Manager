import { modalManager } from './ModalManager.js';
import { translate } from '../utils/i18nHelpers.js';
import { showToast } from '../utils/uiHelpers.js';

/**
 * Owns the two recipe-rematch modals:
 *
 * - rematchOptionsModal — shown BEFORE a global/bulk/single rematch run;
 *   collects the "relaxed matching" opt-in and only then invokes the run
 *   callback.
 * - rematchResultsModal — shown AFTER a run that produced L4 (filename
 *   level) matches; lists them for review with a per-row Undo that calls
 *   the existing restore endpoints.
 */
export class RematchModalManager {
    constructor() {
        this._optionsConfirmCallback = null;
        this._resultsMatches = [];
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

    /**
     * Open the results modal listing L4 (filename-level) matches.
     *
     * @param {Array<{recipe_id: string, type: string, entry: string, file_name: string, lora_index?: number}>} l4Matches
     */
    showResultsModal(l4Matches) {
        if (!Array.isArray(l4Matches) || l4Matches.length === 0) {
            return;
        }
        const list = document.getElementById('rematchResultsList');
        if (!list) {
            return;
        }
        this._resultsMatches = l4Matches;
        list.innerHTML = '';

        l4Matches.forEach((match, index) => {
            const row = document.createElement('li');
            row.className = 'rematch-results-row';

            const info = document.createElement('div');
            info.className = 'rematch-results-info';

            const entryName = document.createElement('span');
            entryName.className = 'rematch-results-entry';
            entryName.textContent = match.entry || '';

            const matchedFile = document.createElement('span');
            matchedFile.className = 'rematch-results-file';
            matchedFile.textContent = `→ ${match.file_name || ''}`;

            const recipeRef = document.createElement('span');
            recipeRef.className = 'rematch-results-recipe';
            recipeRef.textContent = match.recipe_id || '';

            info.appendChild(entryName);
            info.appendChild(matchedFile);
            info.appendChild(recipeRef);

            const undoButton = document.createElement('button');
            undoButton.className = 'secondary-btn rematch-results-undo';
            undoButton.textContent = translate('modals.rematchResults.undo', {}, 'Undo');
            undoButton.addEventListener('click', () => this.undoMatch(index, row, undoButton));

            row.appendChild(info);
            row.appendChild(undoButton);
            list.appendChild(row);
        });

        modalManager.showModal('rematchResultsModal');
    }

    /**
     * Undo a single L4 match via the existing restore endpoints. On success
     * the row is struck through and its button disabled.
     */
    async undoMatch(index, row, button) {
        const match = this._resultsMatches[index];
        if (!match || button.disabled) {
            return;
        }
        try {
            const isCheckpoint = match.type === 'checkpoint';
            const body = isCheckpoint
                ? { recipe_id: match.recipe_id }
                : { recipe_id: match.recipe_id, lora_index: match.lora_index };
            const response = await fetch(
                isCheckpoint
                    ? '/api/lm/recipe/checkpoint/restore'
                    : '/api/lm/recipe/lora/restore',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                }
            );
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || 'Restore failed');
            }
            row.classList.add('undone');
            button.disabled = true;
            button.textContent = translate('modals.rematchResults.undone', {}, 'Undone');
        } catch (error) {
            console.error('Failed to undo rematch match:', error);
            showToast(
                'modals.rematchResults.undoFailed',
                { message: error.message },
                'error'
            );
        }
    }
}

export const rematchModalManager = new RematchModalManager();
