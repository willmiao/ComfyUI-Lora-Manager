import { translate } from '../utils/i18nHelpers.js';
import { showToast, openHuggingFace } from '../utils/uiHelpers.js';

/**
 * Escape HTML entities in a string to prevent injection when interpolating into innerHTML.
 * Safe for both text content and attribute values (quotes are escaped too).
 * @param {string} str - The string to escape
 * @returns {string} - The escaped string
 */
function _escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * Resolve the display name of a failed download entry.
 * Prefers the resolved name carried on the entry, then known item fields,
 * then derives a name from the item URL as a last resort.
 * @param {Object} entry - The failed entry ({ item, error, name? })
 * @returns {string} - The best available display name
 */
function _resolveItemName(entry) {
    if (entry?.name) {
        return entry.name;
    }
    const item = entry?.item ?? entry;
    const direct = item?.displayName || item?.name || item?.file_name || item?.filename || item?.selectedVersion?.name;
    if (direct) {
        return direct;
    }
    if (item?.url) {
        try {
            const segments = new URL(item.url).pathname.split('/').filter(Boolean);
            if (segments.length > 0) {
                return decodeURIComponent(segments[segments.length - 1]);
            }
        } catch (e) {
            // Unparseable URL — fall through to 'Unknown'
        }
    }
    return 'Unknown';
}

/**
 * Resolve the URL to open for a failed item — always the original item URL.
 * @param {Object} item - The failed item payload
 * @returns {string|null} - A URL string, or null when nothing is available
 */
function _resolveItemUrl(item) {
    return item?.url || null;
}

/**
 * Format a raw failure error into a concise human-readable message.
 * Unwraps JSON envelopes and extracts HTTP status/body details when present.
 * @param {*} error - The raw error (usually a string)
 * @returns {string} - The formatted error message
 */
function _formatError(error) {
    if (!error) {
        return 'Unknown error';
    }
    let base = typeof error === 'string' ? error : String(error);

    // Unwrap JSON envelope: { "success": false, "error": "...", ... }
    try {
        const parsed = JSON.parse(base);
        if (parsed && typeof parsed.error === 'string' && parsed.error) {
            base = parsed.error;
        }
    } catch (e) {
        // Not a JSON envelope — keep the raw string
    }

    // Extract HTTP status and JSON body details, e.g. "status=403 body={...}"
    let result = base;
    const statusMatch = base.match(/status=(\d{3})/);
    const bodyMatch = base.match(/body=(\{.*\})/s);
    if (bodyMatch) {
        try {
            const body = JSON.parse(bodyMatch[1]);
            const detail = (typeof body?.message === 'string' && body.message)
                || (typeof body?.error === 'string' && body.error)
                || null;
            if (detail) {
                const status = statusMatch ? statusMatch[1] : null;
                result = `${status ? `HTTP ${status} — ` : ''}${detail}`;
            }
        } catch (e) {
            // Body is not valid JSON — keep the base string
        }
    }

    // Truncate overly long messages
    if (result.length > 220) {
        result = result.slice(0, 220) + '…';
    }
    return result;
}

/**
 * Build a plain-text report of the batch download results.
 * @param {number} total - Total number of models attempted
 * @param {number} completed - Number of models successfully downloaded
 * @param {Array} failedItems - Array of failed items ({ item, error })
 * @returns {string} - The report text
 */
function _buildReportText(total, completed, failedItems) {
    const lines = [
        '=== Batch Download Report ===',
        `Date: ${new Date().toLocaleString()}`,
        `Total: ${total}`,
        `Successfully downloaded: ${completed}`,
        `Failed: ${failedItems.length}`,
        '',
    ];
    if (failedItems.length > 0) {
        lines.push('--- Failed Items ---');
        failedItems.forEach((entry, i) => {
            const name = _resolveItemName(entry);
            const error = _formatError(entry?.error);
            lines.push(`${i + 1}. ${name} — ${error}`);
            const itemUrl = _resolveItemUrl(entry?.item ?? entry);
            if (itemUrl) {
                lines.push(`   URL: ${itemUrl}`);
            }
        });
        lines.push('');
    }
    lines.push('====================');
    return lines.join('\n');
}

/**
 * Handle a successful clipboard write: confirm via toast and briefly swap the
 * trigger button to a "Copied!" state.
 * @param {HTMLElement|null} btn - The button that triggered the copy action
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
 * contexts over LAN http where `navigator.clipboard` is undefined): copy via a
 * hidden textarea and `document.execCommand('copy')`.
 * @param {string} text - The report text to copy
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

/**
 * Copy the batch download report to the clipboard.
 * Uses the async Clipboard API when available, otherwise falls back to a hidden
 * textarea + execCommand so the action still works in insecure contexts.
 * @param {HTMLElement} btn - The button that triggered the copy action
 * @param {number} total - Total number of models attempted
 * @param {number} completed - Number of models successfully downloaded
 * @param {Array} failedItems - Array of failed items
 */
function _copyReport(btn, total, completed, failedItems) {
    const text = _buildReportText(total, completed, failedItems);
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        navigator.clipboard.writeText(text)
            .then(() => _onCopyReportSuccess(btn))
            .catch(() => _copyReportWithExecCommand(text));
    } else {
        _copyReportWithExecCommand(text);
    }
}

/**
 * Show the batch download summary modal after a batch download completes.
 * Mirrors the Metadata Fetch Summary modal lifecycle: the modal element is
 * appended directly to document.body and removed on close; it is not
 * registered with ModalManager.
 * @param {Object} options - Summary options
 * @param {number} options.total - Total number of models attempted
 * @param {number} options.completed - Number of models successfully downloaded
 * @param {Array} options.failedItems - Array of failed items ({ item, error })
 * @param {Function} options.onRetry - Callback invoked with failedItems to retry the failed subset
 */
export function showDownloadBatchSummary({ total, completed, failedItems, onRetry }) {
    const failures = failedItems || [];
    const failedCount = failures.length;

    // 3-state summary header semantics (mirrors BatchImportManager results header)
    let headerState;
    let headerIcon;
    let headerText;
    if (completed === 0) {
        headerState = 'error';
        headerIcon = 'fa-times-circle';
        headerText = translate('modals.downloadBatchSummary.failed', {}, 'Download failed');
    } else if (failedCount > 0) {
        headerState = 'warning';
        headerIcon = 'fa-exclamation-circle';
        headerText = translate('modals.downloadBatchSummary.completedWithErrors', {}, 'Completed with errors');
    } else {
        headerState = 'success';
        headerIcon = 'fa-check-circle';
        headerText = translate('modals.downloadBatchSummary.successMessage', { count: completed }, 'All ' + completed + ' models downloaded successfully');
    }

    // Build failure table rows
    const failureRows = failures.map((entry, i) => {
        const item = entry?.item ?? entry;
        const name = _resolveItemName(entry);
        const itemUrl = _resolveItemUrl(item);
        const rawError = entry?.error ? String(entry.error) : '';
        const error = _formatError(entry?.error);
        const nameCell = itemUrl
            ? `<td class="failure-name"><a href="#" class="failure-link" data-action="open-model" data-index="${i}" title="${_escapeHtml(itemUrl)}">${_escapeHtml(name)}</a></td>`
            : `<td class="failure-name" title="${_escapeHtml(name)}">${_escapeHtml(name)}</td>`;
        return `<tr>
                <td class="failure-index">${i + 1}</td>
                ${nameCell}
                <td class="failure-error" title="${_escapeHtml(rawError)}">${_escapeHtml(error)}</td>
            </tr>`;
    }).join('');

    const modalHtml = `
        <div id="downloadBatchSummaryModal" class="modal" style="display: block;">
            <div class="modal-content download-batch-summary-modal">
                <button class="close" data-action="close-modal">&times;</button>

                <h2>${translate('modals.downloadBatchSummary.title', {}, 'Batch Download Summary')}</h2>

                <div class="summary-header ${headerState}">
                    <i class="fas ${headerIcon}"></i>
                    <span class="summary-title">${headerText}</span>
                    <span class="summary-hint">${completed}/${total}</span>
                </div>

                <div class="refresh-summary-stats">
                    <div class="stat-card stat-card-success">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.downloadBatchSummary.statSuccess', {}, 'Success')}</span>
                            <span class="stat-card-value">${completed}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-failure">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.downloadBatchSummary.statFailed', {}, 'Failed')}</span>
                            <span class="stat-card-value">${failedCount}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-total">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.downloadBatchSummary.statTotal', {}, 'Total')}</span>
                            <span class="stat-card-value">${total}</span>
                        </div>
                    </div>
                </div>

                ${failedCount > 0 ? `
                <div class="refresh-failures-section">
                    <h4><i class="fas fa-exclamation-triangle"></i> ${translate('modals.downloadBatchSummary.failedItems', { count: failedCount }, 'Failed Items (' + failedCount + ')')}</h4>
                    <div class="failure-table-wrapper">
                        <table class="failure-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>${translate('modals.downloadBatchSummary.columnName', {}, 'Model Name')}</th>
                                    <th>${translate('modals.downloadBatchSummary.columnError', {}, 'Error')}</th>
                                </tr>
                            </thead>
                            <tbody>${failureRows}</tbody>
                        </table>
                    </div>
                </div>
                ` : `
                <div class="refresh-success-message">
                    <i class="fas fa-check-circle"></i> ${translate('modals.downloadBatchSummary.successMessage', { count: completed }, 'All ' + completed + ' models downloaded successfully')}
                </div>
                `}

                <div class="modal-actions">
                    ${failedCount > 0 ? `
                    <button class="btn-retry" data-action="retry-failed"><i class="fas fa-redo"></i> ${translate('modals.downloadBatchSummary.retryFailed', { count: failedCount }, 'Retry Failed (' + failedCount + ')')}</button>
                    <button class="secondary-btn" data-action="copy-report"><i class="fas fa-copy"></i> ${translate('modals.downloadBatchSummary.copyReport', {}, 'Copy Report')}</button>
                    ` : ''}
                    <button class="cancel-btn" data-action="close-modal">${translate('modals.downloadBatchSummary.close', {}, 'Close')}</button>
                </div>
            </div>
        </div>
    `;

    const existing = document.getElementById('downloadBatchSummaryModal');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.innerHTML = modalHtml;
    const modal = container.firstElementChild;
    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => {
        const actionEl = e.target.closest('[data-action]');
        const action = actionEl?.dataset.action;
        if (!action) return;
        e.preventDefault();

        switch (action) {
            case 'close-modal':
                modal.remove();
                break;
            case 'retry-failed':
                modal.remove();
                if (typeof onRetry === 'function') {
                    onRetry(failures);
                }
                break;
            case 'copy-report':
                _copyReport(actionEl, total, completed, failures);
                break;
            case 'open-model': {
                // Keep the modal open; just open the item's original URL in a new tab
                const entry = failures[Number(actionEl.dataset.index)];
                const item = entry?.item;
                if (!item?.url) break;
                openHuggingFace(item.url);
                break;
            }
        }
    });
}
