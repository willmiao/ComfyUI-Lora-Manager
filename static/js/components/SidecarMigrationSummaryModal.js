import { translate } from '../utils/i18nHelpers.js';

/**
 * Escape HTML entities in a string to prevent injection when interpolating into innerHTML.
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
 * Show the sidecar migration summary modal after a migration completes.
 * Mirrors the Metadata Fetch Summary / Batch Download Summary lifecycle: the
 * modal element is appended directly to document.body and removed on close;
 * it is not registered with ModalManager.
 * @param {Object} options - Summary options
 * @param {Object} options.result - Migration result payload from /api/lm/sidecars/migrate
 * @param {Function} options.onClose - Callback invoked after the modal is dismissed
 * @param {Function} [options.onOpenLocation] - Callback for the "Open Folder" action; the modal stays open
 */
export function showSidecarMigrationSummary({ result, onClose, onOpenLocation }) {
    const errorCount = result.error_count || 0;
    const errors = Array.isArray(result.errors) ? result.errors : [];
    const moved = result.moved || 0;
    const modelsMoved = result.models_moved || 0;
    const modelsTotal = result.models_total || 0;
    const skipped = result.skipped || 0;
    const conflicts = result.conflicts || 0;

    const showLocation = result.direction !== 'to_alongside' && !!result.sidecar_root;

    // 3-state summary header semantics (mirrors DownloadBatchSummaryModal)
    let headerState;
    let headerIcon;
    let headerText;
    if (errorCount > 0) {
        headerState = 'warning';
        headerIcon = 'fa-exclamation-circle';
        headerText = translate('modals.sidecarMigrationResult.completedWithErrors', { count: errorCount }, 'Completed with ' + errorCount + ' error(s)');
    } else {
        headerState = 'success';
        headerIcon = 'fa-check-circle';
        headerText = translate('modals.sidecarMigrationResult.completedSuccessfully', {}, 'Migration completed successfully');
    }

    const failureRows = errors.map((entry, i) => {
        const name = entry?.model || 'Unknown';
        const error = entry?.error ? String(entry.error) : 'Unknown error';
        return `<tr>
                <td class="failure-index">${i + 1}</td>
                <td class="failure-name" title="${_escapeHtml(name)}">${_escapeHtml(name)}</td>
                <td class="failure-error" title="${_escapeHtml(error)}">${_escapeHtml(error)}</td>
            </tr>`;
    }).join('');

    const modalHtml = `
        <div id="sidecarMigrationSummaryModal" class="modal" style="display: block;">
            <div class="modal-content sidecar-migration-summary-modal">
                <button class="close" data-action="close-modal">&times;</button>

                <h2>${translate('modals.sidecarMigrationResult.title', {}, 'Sidecar Migration Summary')}</h2>

                <div class="summary-header ${headerState}">
                    <i class="fas ${headerIcon}"></i>
                    <span class="summary-title">${headerText}</span>
                    <span class="summary-hint">${modelsMoved}/${modelsTotal}</span>
                </div>

                <div class="refresh-summary-stats">
                    <div class="stat-card stat-card-success">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.sidecarMigrationResult.statMoved', {}, 'Moved Files')}</span>
                            <span class="stat-card-value">${moved}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-total">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.sidecarMigrationResult.statModels', {}, 'Models')}</span>
                            <span class="stat-card-value">${modelsMoved}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-skipped">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.sidecarMigrationResult.statSkipped', {}, 'Skipped')}</span>
                            <span class="stat-card-value">${skipped}</span>
                        </div>
                    </div>
                    <div class="stat-card stat-card-time">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.sidecarMigrationResult.statConflicts', {}, 'Conflicts Resolved')}</span>
                            <span class="stat-card-value">${conflicts}</span>
                        </div>
                    </div>
                    ${errorCount > 0 ? `
                    <div class="stat-card stat-card-failure">
                        <div class="stat-card-body">
                            <span class="stat-card-label">${translate('modals.sidecarMigrationResult.statErrors', {}, 'Errors')}</span>
                            <span class="stat-card-value">${errorCount}</span>
                        </div>
                    </div>
                    ` : ''}
                </div>

                ${errorCount > 0 ? `
                <div class="refresh-failures-section">
                    <h4><i class="fas fa-exclamation-triangle"></i> ${translate('modals.sidecarMigrationResult.failedItems', { count: errorCount }, 'Failed Items (' + errorCount + ')')}</h4>
                    <div class="failure-table-wrapper">
                        <table class="failure-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>${translate('modals.sidecarMigrationResult.columnModel', {}, 'Model')}</th>
                                    <th>${translate('modals.sidecarMigrationResult.columnError', {}, 'Error')}</th>
                                </tr>
                            </thead>
                            <tbody>${failureRows}</tbody>
                        </table>
                    </div>
                </div>
                ` : `
                <div class="refresh-success-message">
                    <i class="fas fa-check-circle"></i> ${translate('modals.sidecarMigrationResult.successMessage', { moved: moved, models: modelsMoved }, 'Moved ' + moved + ' files for ' + modelsMoved + ' models')}
                </div>
                `}

                ${showLocation ? `
                <p class="sidecar-migration-location">
                    ${translate('modals.sidecarMigrationResult.location', { path: result.sidecar_root }, 'Storage location: ' + result.sidecar_root)}
                </p>
                ` : ''}

                <div class="modal-actions">
                    ${showLocation ? `
                    <button class="secondary-btn" data-action="open-sidecar-location"><i class="fas fa-folder-open"></i> ${translate('settings.sidecarStorage.openFolderButton', {}, 'Open Folder')}</button>
                    ` : ''}
                    <button class="cancel-btn" data-action="close-modal">${translate('common.actions.close', {}, 'Close')}</button>
                </div>
            </div>
        </div>
    `;

    const existing = document.getElementById('sidecarMigrationSummaryModal');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.innerHTML = modalHtml;
    const modal = container.firstElementChild;
    document.body.appendChild(modal);

    const close = () => {
        document.removeEventListener('keydown', handleEscape, true);
        modal.remove();
        if (typeof onClose === 'function') {
            onClose();
        }
    };

    // Capture phase + stopPropagation so ESC never reaches the settings
    // modal's own ESC handler underneath.
    const handleEscape = (event) => {
        if (event.key === 'Escape') {
            event.stopPropagation();
            event.preventDefault();
            close();
        }
    };
    document.addEventListener('keydown', handleEscape, true);

    modal.addEventListener('click', (e) => {
        const actionEl = e.target.closest('[data-action]');
        const action = actionEl?.dataset.action;
        if (!action) return;
        e.preventDefault();

        switch (action) {
            case 'close-modal':
                close();
                break;
            case 'open-sidecar-location':
                // Keep the modal open; only trigger the file-manager action.
                if (typeof onOpenLocation === 'function') {
                    onOpenLocation();
                }
                break;
        }
    });

    return modal;
}
