import { translate } from '../utils/i18nHelpers.js';
import { showToast } from '../utils/uiHelpers.js';

const PAGE_SIZE = 50;

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(value);
    return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function copyWithExecCommand(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
}

async function copyText(text) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch (error) {
            console.warn('Clipboard API failed; using the copy fallback:', error);
        }
    }
    copyWithExecCommand(text);
}

export class AutoOrganizePreviewModal {
    constructor({ onApply, onRefresh, onClose } = {}) {
        this.onApply = onApply;
        this.onRefresh = onRefresh;
        this.onClose = onClose;
        this.modal = null;
        this.result = null;
        this.activeTab = 'moves';
        this.searchQuery = '';
        this.currentPage = 1;
        this.previousActiveElement = null;
        this.bodyHadModalOpen = false;
        this.handleEscape = this.handleEscape.bind(this);
    }

    showLoading() {
        this.ensureModal();
        this.result = null;
        this.renderShell(`
            <div class="auto-organize-preview-loading" role="status" aria-live="polite">
                <i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i>
                <h3>${this.t('loadingTitle', 'Calculating preview…')}</h3>
                <p>${this.t('loadingMessage', 'No files are being changed.')}</p>
            </div>
        `);
    }

    showError(error) {
        if (!this.modal) return;
        this.result = null;
        const message = error instanceof Error ? error.message : String(error);
        this.renderShell(`
            <div class="auto-organize-preview-notice error" role="alert">
                <i class="fas fa-exclamation-circle" aria-hidden="true"></i>
                <div>
                    <strong>${this.t('previewFailed', 'Preview failed')}</strong>
                    <p>${escapeHtml(message)}</p>
                </div>
            </div>
            <div class="modal-actions">
                <button class="cancel-btn" data-action="close-modal">${translate('common.actions.cancel', {}, 'Cancel')}</button>
                <button class="primary-btn" data-action="refresh">
                    <i class="fas fa-redo" aria-hidden="true"></i>
                    ${this.t('retry', 'Retry')}
                </button>
            </div>
        `);
    }

    showResult(result) {
        if (!this.modal) return;
        this.result = result;
        this.activeTab = 'moves';
        this.searchQuery = '';
        this.currentPage = 1;

        const summary = this.summary;
        const scope = summary.operationType === 'all'
            ? this.t('scopeAll', 'All models')
            : this.t('scopeSelected', 'Selected models');
        const canApply = summary.success > 0;
        const notice = this.getNotice();

        this.renderShell(`
            <div class="auto-organize-preview-meta">
                <span>${this.t('scope', 'Scope: {scope} · {count} models', { scope, count: summary.total })}</span>
            </div>
            <div class="auto-organize-preview-notice ${notice.type}" role="status">
                <i class="fas ${notice.icon}" aria-hidden="true"></i>
                <span>${notice.text}</span>
            </div>
            <div class="refresh-summary-stats auto-organize-preview-stats">
                <div class="stat-card auto-organize-stat-moves">
                    <div class="stat-card-body">
                        <span class="stat-card-label">${this.t('statWillMove', 'Will move')}</span>
                        <span class="stat-card-value">${summary.success}</span>
                    </div>
                </div>
                <div class="stat-card stat-card-skipped">
                    <div class="stat-card-body">
                        <span class="stat-card-label">${this.t('statSkipped', 'Skipped')}</span>
                        <span class="stat-card-value">${summary.skipped}</span>
                    </div>
                </div>
                <div class="stat-card stat-card-failure">
                    <div class="stat-card-body">
                        <span class="stat-card-label">${this.t('statIssues', 'Issues')}</span>
                        <span class="stat-card-value">${summary.failures}</span>
                    </div>
                </div>
            </div>
            ${summary.failures > 0 && summary.success > 0 ? `
                <p class="auto-organize-preview-warning">
                    <i class="fas fa-exclamation-triangle" aria-hidden="true"></i>
                    ${this.t('issuesWarning', '{count} model(s) are expected to fail; the remaining models will still be processed.', { count: summary.failures })}
                </p>
            ` : ''}
            <div class="auto-organize-preview-toolbar">
                <div class="auto-organize-preview-tabs" role="tablist" aria-label="${this.t('detailsLabel', 'Preview details')}">
                    <button id="autoOrganizeMovesTab" class="auto-organize-preview-tab active" data-action="tab" data-tab="moves" role="tab" aria-selected="true" aria-controls="autoOrganizePreviewList">
                        ${this.t('movesTab', 'Moves ({count})', { count: this.plannedMoves.length })}
                    </button>
                    <button id="autoOrganizeSkippedTab" class="auto-organize-preview-tab" data-action="tab" data-tab="skipped" role="tab" aria-selected="false" aria-controls="autoOrganizePreviewList">
                        ${this.t('skippedTab', 'Skipped ({count})', { count: this.skippedResults.length })}
                    </button>
                    <button id="autoOrganizeIssuesTab" class="auto-organize-preview-tab" data-action="tab" data-tab="issues" role="tab" aria-selected="false" aria-controls="autoOrganizePreviewList">
                        ${this.t('issuesTab', 'Issues ({count})', { count: this.issueResults.length })}
                    </button>
                </div>
                <input type="search" class="auto-organize-preview-search" data-role="search"
                    placeholder="${this.t('searchPlaceholder', 'Search model or path…')}"
                    aria-label="${this.t('searchPlaceholder', 'Search model or path…')}">
            </div>
            <div id="autoOrganizePreviewList" class="auto-organize-preview-list" role="tabpanel" aria-labelledby="autoOrganizeMovesTab"></div>
            <p class="auto-organize-preview-footnote">${this.t('replanNote', 'Execution recalculates from the latest library state, so actual results may differ from this preview.')}</p>
            <div class="modal-actions auto-organize-preview-actions">
                <button class="secondary-btn" data-action="copy-report">
                    <i class="fas fa-copy" aria-hidden="true"></i>
                    ${this.t('copyReport', 'Copy Report')}
                </button>
                <button class="secondary-btn" data-action="refresh">
                    <i class="fas fa-redo" aria-hidden="true"></i>
                    ${this.t('refresh', 'Refresh Preview')}
                </button>
                <span class="auto-organize-preview-actions-spacer"></span>
                <button class="cancel-btn" data-action="close-modal">${translate('common.actions.cancel', {}, 'Cancel')}</button>
                <button class="primary-btn" data-action="apply" ${canApply ? '' : 'disabled'}>
                    <i class="fas fa-magic" aria-hidden="true"></i>
                    ${canApply
                        ? this.t('apply', 'Organize ({count})', { count: summary.success })
                        : this.t('noMoves', 'No Moves to Apply')}
                </button>
            </div>
        `);
        this.renderList();
    }

    close() {
        if (!this.modal) return;
        document.removeEventListener('keydown', this.handleEscape, true);
        this.modal.remove();
        this.modal = null;
        this.result = null;
        if (!this.bodyHadModalOpen) {
            document.body.classList.remove('modal-open');
        }
        if (this.previousActiveElement?.isConnected) {
            this.previousActiveElement.focus();
        }
        this.onClose?.();
    }

    get summary() {
        const summary = this.result?.summary || {};
        return {
            total: Number(summary.total) || 0,
            success: Number(summary.success) || 0,
            skipped: Number(summary.skipped) || 0,
            failures: Number(summary.failures) || 0,
            operationType: summary.operation_type || 'bulk',
            organizationType: summary.organization_type || 'structured',
            pathTemplate: typeof summary.path_template === 'string' ? summary.path_template : null,
        };
    }

    get plannedMoves() {
        return Array.isArray(this.result?.planned_moves) ? this.result.planned_moves : [];
    }

    get results() {
        return Array.isArray(this.result?.results) ? this.result.results : [];
    }

    get skippedResults() {
        return this.results.filter((item) => this.isSkippedResult(item));
    }

    get issueResults() {
        return this.results.filter((item) => !this.isSkippedResult(item));
    }

    isSkippedResult(result) {
        return result.status === 'skipped' || (
            !result.status && ['already_organized', 'missing_metadata', 'path_too_long'].includes(result.reason)
        );
    }

    t(key, fallback, params = {}) {
        return translate(`modals.autoOrganizePreview.${key}`, params, fallback);
    }

    ensureModal() {
        if (this.modal) return;
        document.getElementById('autoOrganizePreviewModal')?.remove();
        this.previousActiveElement = document.activeElement;
        this.bodyHadModalOpen = document.body.classList.contains('modal-open');
        this.modal = document.createElement('div');
        this.modal.id = 'autoOrganizePreviewModal';
        this.modal.className = 'modal auto-organize-preview';
        this.modal.style.display = 'block';
        this.modal.setAttribute('role', 'dialog');
        this.modal.setAttribute('aria-modal', 'true');
        this.modal.setAttribute('aria-labelledby', 'autoOrganizePreviewTitle');
        this.modal.innerHTML = '<div class="modal-content auto-organize-preview-modal"></div>';
        document.body.appendChild(this.modal);
        document.body.classList.add('modal-open');
        document.addEventListener('keydown', this.handleEscape, true);

        this.modal.addEventListener('click', (event) => {
            const actionElement = event.target.closest('[data-action]');
            if (!actionElement || actionElement.disabled) return;
            this.handleAction(actionElement).catch((error) => {
                console.error('Auto-organize preview action failed:', error);
            });
        });
        this.modal.addEventListener('input', (event) => {
            if (!event.target.matches('[data-role="search"]')) return;
            this.searchQuery = event.target.value.trim().toLocaleLowerCase();
            this.currentPage = 1;
            this.renderList();
        });
    }

    renderShell(content) {
        const contentElement = this.modal?.querySelector('.modal-content');
        if (!contentElement) return;
        contentElement.innerHTML = `
            <button class="close" data-action="close-modal" aria-label="${translate('common.actions.close', {}, 'Close')}">&times;</button>
            <h2 id="autoOrganizePreviewTitle">${this.t('title', 'Preview Auto-Organize')}</h2>
            ${content}
        `;
        contentElement.querySelector('[data-action="close-modal"]')?.focus();
    }

    getNotice() {
        const summary = this.summary;
        if (summary.total === 0) {
            return {
                type: 'neutral',
                icon: 'fa-info-circle',
                text: this.t('emptyPreview', 'No models are available for this preview.'),
            };
        }
        if (
            summary.success === 0
            && summary.failures === 0
            && this.results.every((item) => item.reason === 'already_organized')
        ) {
            return {
                type: 'neutral',
                icon: 'fa-check-circle',
                text: this.t('alreadyOrganized', 'All models are already in the correct location.'),
            };
        }
        return {
            type: summary.failures > 0 ? 'warning' : 'info',
            icon: summary.failures > 0 ? 'fa-exclamation-circle' : 'fa-eye',
            text: this.t('previewNotice', 'Preview only. No files have been moved and no directories have been cleaned.'),
        };
    }

    getFilteredItems() {
        const itemsByTab = {
            moves: this.plannedMoves,
            skipped: this.skippedResults,
            issues: this.issueResults,
        };
        const items = itemsByTab[this.activeTab] || [];
        if (!this.searchQuery) return items;
        return items.filter((item) => {
            const reason = this.activeTab === 'moves' ? '' : this.getReasonLabel(item.reason);
            return [item.model, item.from, item.to, item.message, reason]
                .filter(Boolean)
                .some((value) => String(value).toLocaleLowerCase().includes(this.searchQuery));
        });
    }

    renderList() {
        const container = this.modal?.querySelector('#autoOrganizePreviewList');
        if (!container || !this.result) return;
        const items = this.getFilteredItems();
        const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
        this.currentPage = Math.min(this.currentPage, totalPages);
        const start = (this.currentPage - 1) * PAGE_SIZE;
        const pageItems = items.slice(start, start + PAGE_SIZE);
        const tabIds = {
            moves: 'autoOrganizeMovesTab',
            skipped: 'autoOrganizeSkippedTab',
            issues: 'autoOrganizeIssuesTab',
        };
        const emptyStates = {
            moves: ['emptyMoves', 'No models need to be moved.'],
            skipped: ['emptySkipped', 'No models will be skipped.'],
            issues: ['emptyIssues', 'No issues to review.'],
        };
        const organizationRule = this.activeTab === 'moves' ? this.renderOrganizationRule() : '';

        container.setAttribute('aria-labelledby', tabIds[this.activeTab]);
        if (pageItems.length === 0) {
            const [key, fallback] = this.searchQuery
                ? ['emptySearch', 'No results match your search.']
                : emptyStates[this.activeTab];
            container.innerHTML = `${organizationRule}<div class="auto-organize-preview-empty">${this.t(key, fallback)}</div>`;
            return;
        }

        const rows = pageItems.map((item) => this.activeTab === 'moves'
            ? this.renderMoveRow(item)
            : this.renderIssueRow(item)).join('');
        const end = Math.min(start + PAGE_SIZE, items.length);
        container.innerHTML = `
            ${organizationRule}
            <div class="auto-organize-preview-rows">${rows}</div>
            <div class="auto-organize-preview-pagination">
                <button class="secondary-btn" data-action="previous-page" ${this.currentPage === 1 ? 'disabled' : ''}>
                    <i class="fas fa-chevron-left" aria-hidden="true"></i>
                    ${translate('common.actions.back', {}, 'Back')}
                </button>
                <span>${this.t('pageStatus', '{from}–{to} of {total}', { from: start + 1, to: end, total: items.length })}</span>
                <button class="secondary-btn" data-action="next-page" ${this.currentPage === totalPages ? 'disabled' : ''}>
                    ${translate('common.actions.next', {}, 'Next')}
                    <i class="fas fa-chevron-right" aria-hidden="true"></i>
                </button>
            </div>
        `;
    }

    renderOrganizationRule() {
        const summary = this.summary;
        if (summary.organizationType !== 'flat' && summary.pathTemplate === null) return '';
        const rule = summary.organizationType === 'flat'
            ? this.t('flatStructureRule', 'Flat structure (library root)')
            : summary.pathTemplate;
        return `
            <div class="auto-organize-preview-rule">
                <span>${this.t('organizingWith', 'Organizing with:')}</span>
                <code>${escapeHtml(rule)}</code>
            </div>
        `;
    }

    renderMoveRow(move) {
        return `
            <article class="auto-organize-preview-row">
                <h3 class="auto-organize-preview-model" title="${escapeHtml(move.model)}">${escapeHtml(move.model)}</h3>
                <div class="auto-organize-preview-paths">
                    <div class="auto-organize-preview-path">
                        <span>${this.t('from', 'From')}</span>
                        <code title="${escapeHtml(move.from)}">${escapeHtml(move.from)}</code>
                    </div>
                    <i class="fas fa-arrow-right auto-organize-preview-arrow" aria-hidden="true"></i>
                    <div class="auto-organize-preview-path">
                        <span>${this.t('to', 'To')}</span>
                        <code title="${escapeHtml(move.to)}">${escapeHtml(move.to)}</code>
                    </div>
                </div>
            </article>
        `;
    }

    renderIssueRow(result) {
        return `
            <article class="auto-organize-preview-row">
                <div class="auto-organize-preview-issue-header">
                    <h3 class="auto-organize-preview-model" title="${escapeHtml(result.model)}">${escapeHtml(result.model)}</h3>
                    <span class="auto-organize-preview-reason reason-${escapeHtml(result.reason || 'error')}">${escapeHtml(this.getReasonLabel(result.reason))}</span>
                </div>
                ${result.reason !== 'already_organized' ? `<p class="auto-organize-preview-message">${escapeHtml(result.message)}</p>` : ''}
                ${result.from ? `
                    <div class="auto-organize-preview-current-path">
                        <span>${this.t('location', 'Location')}</span>
                        <code title="${escapeHtml(result.from)}">${escapeHtml(result.from)}</code>
                    </div>
                ` : ''}
            </article>
        `;
    }

    getReasonLabel(reason) {
        const fallbacks = {
            already_organized: 'Already organized',
            no_file_path: 'No file path',
            outside_roots: 'Outside library roots',
            missing_metadata: 'Missing metadata',
            path_too_long: 'Target path too long',
            target_exists: 'Target already exists',
            planned_collision: 'Planned move collision',
            move_failed: 'Move failed',
            error: 'Error',
        };
        const normalizedReason = reason && fallbacks[reason] ? reason : 'error';
        return this.t(`reasons.${normalizedReason}`, fallbacks[normalizedReason]);
    }

    async handleAction(element) {
        const action = element.dataset.action;
        if (action === 'close-modal') {
            this.close();
        } else if (action === 'refresh') {
            await this.onRefresh?.();
        } else if (action === 'apply') {
            const onApply = this.onApply;
            this.close();
            await onApply?.();
        } else if (action === 'tab') {
            this.activeTab = element.dataset.tab;
            this.currentPage = 1;
            this.modal.querySelectorAll('[data-action="tab"]').forEach((tab) => {
                const selected = tab.dataset.tab === this.activeTab;
                tab.classList.toggle('active', selected);
                tab.setAttribute('aria-selected', String(selected));
            });
            this.renderList();
        } else if (action === 'previous-page' || action === 'next-page') {
            this.currentPage += action === 'next-page' ? 1 : -1;
            this.renderList();
            this.modal.querySelector('#autoOrganizePreviewList')?.scrollIntoView({ block: 'nearest' });
        } else if (action === 'copy-report') {
            await copyText(this.buildReport());
            showToast('toast.api.copiedToClipboard', {}, 'success');
        }
    }

    buildReport() {
        const summary = this.summary;
        const lines = [
            '=== Auto-Organize Preview Report ===',
            `Date: ${new Date().toLocaleString()}`,
            `Scope: ${summary.operationType}`,
            `Total: ${summary.total}`,
            `Would move: ${summary.success}`,
            `Skipped: ${summary.skipped}`,
            `Issues: ${summary.failures}`,
            '',
            '--- Planned Moves ---',
        ];
        this.plannedMoves.forEach((move, index) => {
            const reason = move.reason || (
                this.result?.summary?.organization_type === 'flat' ? 'flat_structure' : 'path_template'
            );
            lines.push(
                `${index + 1}. ${move.model} [${reason}]`,
                `   From: ${move.from}`,
                `   To: ${move.to}`,
            );
        });
        lines.push('', '--- Skipped ---');
        this.skippedResults.forEach((result, index) => {
            lines.push(`${index + 1}. ${result.model} [${result.reason || 'error'}]`, `   ${result.message}`);
        });
        lines.push('', '--- Issues ---');
        this.issueResults.forEach((result, index) => {
            lines.push(`${index + 1}. ${result.model} [${result.reason || 'error'}]`, `   ${result.message}`);
        });
        lines.push('', '====================================');
        return lines.join('\n');
    }

    handleEscape(event) {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        event.stopPropagation();
        this.close();
    }
}
