import { translate } from '../utils/i18nHelpers.js';
import { showToast } from '../utils/uiHelpers.js';

/**
 * Escape HTML entities in a string to prevent injection when interpolating
 * into innerHTML (same approach as DownloadBatchSummaryModal).
 * @param {string} str - The string to escape
 * @returns {string} - The escaped string
 */
function _escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * Resolve the 3-state summary header (mirrors the batch download/import
 * summary semantics).
 *
 * - error: nothing matched and at least one recipe errored
 * - warning: errors, unresolved entries, filename-level (L4) matches to
 *   review, or a cancelled run
 * - success: otherwise
 */
function _resolveHeader({ matchedEntries, errors, unresolvedEntries, l4Count, cancelled }) {
    if (matchedEntries === 0 && errors > 0) {
        return {
            state: 'error',
            icon: 'fa-times-circle',
            text: translate('modals.rematchSummary.failed', {}, 'Rematch failed'),
        };
    }
    if (errors > 0 || unresolvedEntries > 0 || l4Count > 0 || cancelled) {
        return {
            state: 'warning',
            icon: 'fa-exclamation-circle',
            text: translate('modals.rematchSummary.completedWithWarnings', {}, 'Rematch completed — review recommended'),
        };
    }
    return {
        state: 'success',
        icon: 'fa-check-circle',
        text: translate('modals.rematchSummary.successMessage', { entries: matchedEntries }, `Matched ${matchedEntries} entries`),
    };
}

/**
 * Build a plain-text report of the rematch run. `undoneIndexes` carries the
 * L4 rows undone so far, so the report reflects the undo status at copy time.
 */
function _buildReportText({ scope, cancelled, total, matchedRecipes, matchedEntries, unresolvedRecipes, unresolvedEntries, skipped, errors, l4Matches, undoneIndexes }) {
    const scopeFallbacks = {
        global: 'All recipes',
        bulk: 'Selected recipes',
        single: 'Single recipe',
    };
    const scopeLabel = translate(
        `modals.rematchSummary.scope_${scope}`,
        {},
        scopeFallbacks[scope] || scope
    );
    const lines = [
        '=== Recipe Rematch Report ===',
        `Date: ${new Date().toLocaleString()}`,
        `Scope: ${scopeLabel}`,
        `Cancelled: ${cancelled ? 'yes' : 'no'}`,
        `Total recipes: ${total}`,
        `Matched recipes: ${matchedRecipes}`,
        `Matched entries: ${matchedEntries}`,
        `Needs review (filename matches): ${l4Matches.length}`,
        `Unresolved entries: ${unresolvedEntries} (in ${unresolvedRecipes} recipes)`,
        `Skipped: ${skipped}`,
        `Errors: ${errors}`,
        '',
    ];
    if (l4Matches.length > 0) {
        lines.push('--- Filename matches (L4) ---');
        l4Matches.forEach((match, i) => {
            const undone = undoneIndexes.has(i) ? ' [undone]' : '';
            lines.push(`${i + 1}. [${match.recipe_id}] ${match.entry} -> ${match.file_name}${undone}`);
        });
        lines.push('');
    }
    lines.push('====================');
    return lines.join('\n');
}

/**
 * Handle a successful clipboard write: confirm via toast and briefly swap the
 * trigger button to a "Copied!" state (mirrors the batch summary modal).
 */
function _onCopyReportSuccess(btn) {
    showToast('toast.api.copiedToClipboard', {}, 'success');
    if (btn) {
        const origHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => { btn.innerHTML = origHTML; }, 2000);
    }
}

/**
 * Fallback for environments without the async Clipboard API (e.g. insecure
 * contexts over LAN http): copy via a hidden textarea and execCommand.
 */
function _copyReportWithExecCommand(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showToast('toast.api.copiedToClipboard', {}, 'success');
}

function _copyReport(btn, reportArgs) {
    const text = _buildReportText(reportArgs);
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        navigator.clipboard.writeText(text)
            .then(() => _onCopyReportSuccess(btn))
            .catch(() => _copyReportWithExecCommand(text));
    } else {
        _copyReportWithExecCommand(text);
    }
}

/**
 * Undo a single L4 match via the existing restore endpoints (moved from
 * RematchModalManager). Checkpoint restore needs only recipe_id; lora
 * restore additionally takes lora_index.
 */
async function _undoMatch(match) {
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
}

/**
 * Show the post-run rematch summary modal. Mirrors the batch download
 * summary lifecycle: the modal element is appended directly to
 * document.body and removed on close; it is not registered with
 * ModalManager.
 *
 * @param {Object} options
 * @param {'global'|'bulk'|'single'} options.scope - Which entry point ran
 * @param {boolean} options.cancelled - Whether the run was cancelled
 * @param {number} options.total - Recipes scanned
 * @param {number} options.matchedRecipes - Recipes updated
 * @param {number} options.matchedEntries - Entries reconnected
 * @param {number} options.unresolvedRecipes - Recipes with unresolved entries
 * @param {number} options.unresolvedEntries - Candidate entries with no local match
 * @param {number} options.skipped - Recipes left untouched
 * @param {number} options.errors - Per-recipe errors
 * @param {Array} options.l4Matches - Filename-level matches for review/undo
 *   ({ recipe_id, type, entry, file_name, lora_index? })
 */
export function showRematchSummary({
    scope = 'global',
    cancelled = false,
    total = 0,
    matchedRecipes = 0,
    matchedEntries = 0,
    unresolvedRecipes = 0,
    unresolvedEntries = 0,
    skipped = 0,
    errors = 0,
    l4Matches = [],
} = {}) {
    const matches = Array.isArray(l4Matches) ? l4Matches : [];
    const undoneIndexes = new Set();
    const header = _resolveHeader({
        matchedEntries,
        errors,
        unresolvedEntries,
        l4Count: matches.length,
        cancelled,
    });

    const matchRows = matches.map((match, i) => `
            <tr data-l4-index="${i}">
                <td class="failure-index">${i + 1}</td>
                <td class="failure-name" title="${_escapeHtml(match.recipe_id)}">${_escapeHtml(match.recipe_id)}</td>
                <td class="failure-name" title="${_escapeHtml(match.entry)}">${_escapeHtml(match.entry)}</td>
                <td class="failure-name" title="${_escapeHtml(match.file_name)}">${_escapeHtml(match.file_name)}</td>
                <td class="rematch-undo-cell">
                    <button class="secondary-btn rematch-undo-btn" data-action="undo-match" data-index="${i}">
                        ${translate('modals.rematchResults.undo', {}, 'Undo')}
                    </button>
                </td>
            </tr>`).join('');

    const modalHtml = `
        <div id="rematchSummaryModal" class="modal" style="display: block;">
            <div class="modal-content rematch-summary-modal">
                <button class="close" data-action="close-modal">&times;</button>

                <h2>${translate('modals.rematchSummary.title', {}, 'Rematch Summary')}</h2>

                <div class="summary-header ${header.state}">
                    <i class="fas ${header.icon}"></i>
                    <span class="summary-title">${header.text}</span>
                    <span class="summary-hint">${matchedRecipes}/${total}</span>
                </div>
                ${cancelled ? `
                <p class="rematch-cancelled-note">
                    <i class="fas fa-info-circle"></i>
                    ${translate('modals.rematchSummary.cancelledNote', {}, 'Run cancelled before completion — counts are partial.')}
                </p>` : ''}

                <div class="refresh-summary-stats">
                    <div class="stat-card stat-card-success">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.rematchSummary.statMatched', {}, 'Matched entries')}</span>
                            <span class="stat-card-value">${matchedEntries}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-skipped">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.rematchSummary.statReview', {}, 'Needs review')}</span>
                            <span class="stat-card-value">${matches.length}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-total">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.rematchSummary.statUnresolved', {}, 'Unresolved')}</span>
                            <span class="stat-card-value">${unresolvedEntries}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-failure">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.rematchSummary.statErrors', {}, 'Errors')}</span>
                            <span class="stat-card-value">${errors}</span>
                        </div>
                    </div>
                </div>

                ${matches.length > 0 ? `
                <div class="refresh-failures-section rematch-review-section">
                    <h4><i class="fas fa-exclamation-triangle"></i> ${translate('modals.rematchSummary.reviewSection', { count: matches.length }, `Filename matches to review (${matches.length})`)}</h4>
                    <div class="failure-table-wrapper">
                        <table class="failure-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>${translate('modals.rematchSummary.columnRecipe', {}, 'Recipe')}</th>
                                    <th>${translate('modals.rematchSummary.columnEntry', {}, 'Entry')}</th>
                                    <th>${translate('modals.rematchSummary.columnFile', {}, 'Matched file')}</th>
                                    <th>${translate('modals.rematchSummary.columnUndo', {}, 'Undo')}</th>
                                </tr>
                            </thead>
                            <tbody>${matchRows}</tbody>
                        </table>
                    </div>
                </div>
                ` : ''}

                <div class="modal-actions">
                    <button class="secondary-btn" data-action="copy-report"><i class="fas fa-copy"></i> ${translate('modals.rematchSummary.copyReport', {}, 'Copy Report')}</button>
                    <button class="cancel-btn" data-action="close-modal">${translate('modals.rematchSummary.close', {}, 'Close')}</button>
                </div>
            </div>
        </div>
    `;

    const existing = document.getElementById('rematchSummaryModal');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.innerHTML = modalHtml;
    const modal = container.firstElementChild;
    document.body.appendChild(modal);

    const reportArgs = {
        scope,
        cancelled,
        total,
        matchedRecipes,
        matchedEntries,
        unresolvedRecipes,
        unresolvedEntries,
        skipped,
        errors,
        l4Matches: matches,
        undoneIndexes,
    };

    modal.addEventListener('click', async (e) => {
        const actionEl = e.target.closest('[data-action]');
        const action = actionEl?.dataset.action;
        if (!action) return;
        e.preventDefault();

        switch (action) {
            case 'close-modal':
                modal.remove();
                break;
            case 'copy-report':
                _copyReport(actionEl, reportArgs);
                break;
            case 'undo-match': {
                const index = Number(actionEl.dataset.index);
                const match = matches[index];
                if (!match || actionEl.disabled) break;
                const row = modal.querySelector(`tr[data-l4-index="${index}"]`);
                try {
                    await _undoMatch(match);
                    undoneIndexes.add(index);
                    row?.classList.add('undone');
                    actionEl.disabled = true;
                    actionEl.textContent = translate('modals.rematchResults.undone', {}, 'Undone');
                } catch (error) {
                    console.error('Failed to undo rematch match:', error);
                    showToast(
                        'modals.rematchResults.undoFailed',
                        { message: error.message },
                        'error'
                    );
                }
                break;
            }
        }
    });
}
