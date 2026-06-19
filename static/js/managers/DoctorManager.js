import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { escapeHtml } from '../components/shared/utils.js';
import { state } from '../state/index.js';

const MAX_CONSOLE_ENTRIES = 200;

function stringifyConsoleArg(value) {
    if (typeof value === 'string') {
        return value;
    }

    try {
        return JSON.stringify(value);
    } catch (_error) {
        return String(value);
    }
}

export class DoctorManager {
    constructor() {
        this.initialized = false;
        this.lastDiagnostics = null;
        this.consoleEntries = [];
    }

    initialize() {
        if (this.initialized) {
            return;
        }

        this.triggerButton = document.getElementById('doctorTriggerBtn');
        this.badge = document.getElementById('doctorStatusBadge');
        this.modal = document.getElementById('doctorModal');
        this.issuesList = document.getElementById('doctorIssuesList');
        this.summaryText = document.getElementById('doctorSummaryText');
        this.summaryBadge = document.getElementById('doctorSummaryBadge');
        this.loadingState = document.getElementById('doctorLoadingState');
        this.refreshButton = document.getElementById('doctorRefreshBtn');
        this.exportButton = document.getElementById('doctorExportBtn');

        this.installConsoleCapture();
        this.bindEvents();
        this.initialized = true;
    }

    bindEvents() {
        if (this.triggerButton) {
            this.triggerButton.addEventListener('click', async () => {
                modalManager.showModal('doctorModal');
                await this.refreshDiagnostics();
            });
        }

        if (this.refreshButton) {
            this.refreshButton.addEventListener('click', async () => {
                await this.refreshDiagnostics();
            });
        }

        if (this.exportButton) {
            this.exportButton.addEventListener('click', async () => {
                await this.exportBundle();
            });
        }
    }

    installConsoleCapture() {
        if (window.__lmDoctorConsolePatched) {
            this.consoleEntries = window.__lmDoctorConsoleEntries || [];
            return;
        }

        const originalConsole = {};
        const levels = ['log', 'info', 'warn', 'error', 'debug'];
        window.__lmDoctorConsoleEntries = this.consoleEntries;

        levels.forEach((level) => {
            const original = console[level]?.bind(console);
            originalConsole[level] = original;

            console[level] = (...args) => {
                this.consoleEntries.push({
                    level,
                    timestamp: new Date().toISOString(),
                    message: args.map(stringifyConsoleArg).join(' '),
                });

                if (this.consoleEntries.length > MAX_CONSOLE_ENTRIES) {
                    this.consoleEntries.splice(0, this.consoleEntries.length - MAX_CONSOLE_ENTRIES);
                }

                if (original) {
                    original(...args);
                }
            };
        });

        window.__lmDoctorConsolePatched = true;
    }

    getClientVersion() {
        return document.body?.dataset?.appVersion || '';
    }

    buildReloadUrl() {
        const url = new URL(window.location.href);
        url.searchParams.set('_lm_reload', Date.now().toString());
        return url.toString();
    }

    reloadUi() {
        window.location.replace(this.buildReloadUrl());
    }

    setLoading(isLoading) {
        if (this.loadingState) {
            this.loadingState.classList.toggle('visible', isLoading);
        }
        if (this.refreshButton) {
            this.refreshButton.disabled = isLoading;
        }
        if (this.exportButton) {
            this.exportButton.disabled = isLoading;
        }
    }

    async refreshDiagnostics({ silent = false } = {}) {
        this.setLoading(true);
        try {
            const clientVersion = encodeURIComponent(this.getClientVersion());
            const response = await fetch(`/api/lm/doctor/diagnostics?clientVersion=${clientVersion}`);
            const payload = await response.json();

            if (!response.ok || payload.success === false) {
                throw new Error(payload.error || 'Failed to load doctor diagnostics');
            }

            this.lastDiagnostics = payload;
            this.updateTriggerState(payload.summary);
            this.renderDiagnostics(payload);
        } catch (error) {
            console.error('Doctor diagnostics failed:', error);
            if (!silent) {
                showToast('doctor.toast.loadFailed', { message: error.message }, 'error');
            }
        } finally {
            this.setLoading(false);
        }
    }

    updateTriggerState(summary = {}) {
        if (!this.badge || !this.triggerButton) {
            return;
        }

        const issueCount = Number(summary.issue_count || 0);
        this.badge.textContent = issueCount > 9 ? '9+' : String(issueCount);
        this.badge.classList.toggle('hidden', issueCount === 0);

        this.triggerButton.classList.remove('doctor-status-warning', 'doctor-status-error');
        if (summary.status === 'error') {
            this.triggerButton.classList.add('doctor-status-error');
        } else if (summary.status === 'warning') {
            this.triggerButton.classList.add('doctor-status-warning');
        }
    }

    renderDiagnostics(payload) {
        if (!this.modal || !this.issuesList || !this.summaryText || !this.summaryBadge) {
            return;
        }

        const { summary = {}, diagnostics = [] } = payload;
        this.summaryText.textContent = this.getSummaryText(summary);
        this.summaryBadge.className = `doctor-summary-badge ${this.getStatusClass(summary.status)}`;
        this.summaryBadge.innerHTML = `
            <i class="fas ${summary.status === 'error' ? 'fa-triangle-exclamation' : summary.status === 'warning' ? 'fa-stethoscope' : 'fa-heartbeat'}"></i>
            <span>${escapeHtml(this.getStatusLabel(summary.status))}</span>
        `;

        this.issuesList.innerHTML = diagnostics.map((item) => this.renderIssueCard(item)).join('');
        this.attachIssueActions();
    }

    getSummaryText(summary) {
        if (summary.status === 'error') {
            return translate(
                'doctor.summary.error',
                { count: summary.issue_count || 0 },
                `${summary.issue_count || 0} issue(s) need attention before the app is fully healthy.`
            );
        }

        if (summary.status === 'warning') {
            return translate(
                'doctor.summary.warning',
                { count: summary.issue_count || 0 },
                `${summary.issue_count || 0} issue(s) were found. Most can be fixed directly from this panel.`
            );
        }

        return translate(
            'doctor.summary.ok',
            {},
            'No active issues were found in the current environment.'
        );
    }

    getStatusClass(status) {
        if (status === 'error') {
            return 'doctor-status-error';
        }
        if (status === 'warning') {
            return 'doctor-status-warning';
        }
        return 'doctor-status-ok';
    }

    getStatusLabel(status) {
        return translate(`doctor.status.${status || 'ok'}`, {}, status || 'ok');
    }

    renderIssueCard(item) {
        const status = item.status || 'ok';
        const tagLabel = this.getStatusLabel(status);

        const titleKey = `doctor.issues.${item.id || ''}.title`;
        const displayTitle = translate(titleKey, {}, item.title || '');

        const summaryKey = `doctor.issues.${item.id || ''}.summary.${status}`;
        const displaySummary = translate(summaryKey, {}, item.summary || '');

        const details = Array.isArray(item.details) ? item.details : [];
        const listItems = details
            .filter((detail) => typeof detail === 'string')
            .map((detail) => `<li>${escapeHtml(detail)}</li>`)
            .join('');
        const inlineDetails = details
            .filter((detail) => detail && typeof detail === 'object')
            .map((detail) => this.renderInlineDetail(detail))
            .join('');
        const actions = (item.actions || [])
            .map((action) => {
                const actionLabel = translate(`doctor.actions.${action.id}`, {}, action.label);
                return `
                <button class="${action.id === 'repair-cache' || action.id === 'reload-page' ? 'primary-btn' : 'secondary-btn'}" data-doctor-action="${escapeHtml(action.id)}">
                    ${escapeHtml(actionLabel)}
                </button>
            `;
            })
            .join('');

        return `
            <section class="doctor-issue-card" data-status="${escapeHtml(status)}" data-issue-id="${escapeHtml(item.id || '')}">
                <div class="doctor-issue-header">
                    <div>
                        <h3>${escapeHtml(displayTitle)}</h3>
                        <p class="doctor-issue-summary">${escapeHtml(displaySummary)}</p>
                    </div>
                    <span class="doctor-issue-tag">${escapeHtml(tagLabel)}</span>
                </div>
                ${inlineDetails ? `<div class="doctor-inline-detail-grid">${inlineDetails}</div>` : ''}
                ${listItems ? `<ul class="doctor-issue-details">${listItems}</ul>` : ''}
                ${actions ? `<div class="doctor-issue-actions">${actions}</div>` : ''}
            </section>
        `;
    }

    renderInlineDetail(detail) {
        if (detail.conflict_groups || detail.total_conflict_files) {
            return `
                <div class="doctor-inline-detail">
                    <strong>${escapeHtml(translate('doctor.labels.conflicts', {}, 'Conflicts'))}</strong>
                    <div>${escapeHtml(`${detail.conflict_groups || 0} filenames, ${detail.total_conflict_files || 0} files`)}</div>
                </div>
            `;
        }

        if (detail.client_version || detail.server_version) {
            return `
                <div class="doctor-inline-detail">
                    <strong>${escapeHtml(translate('common.status.version', {}, 'Version'))}</strong>
                    <div>${escapeHtml(`Client: ${detail.client_version || 'unknown'}`)}</div>
                    <div>${escapeHtml(`Server: ${detail.server_version || 'unknown'}`)}</div>
                </div>
            `;
        }

        const label = detail.label || detail.model_type || detail.client_version || detail.server_version || 'Detail';
        const message = detail.message
            || detail.corruption_rate
            || detail.server_version
            || detail.client_version
            || '';

        if (detail.model_type) {
            return `
                <div class="doctor-inline-detail">
                    <strong>${escapeHtml(detail.label || detail.model_type)}</strong>
                    <div>${escapeHtml(detail.message || '')}</div>
                    ${detail.corruption_rate ? `<div>${escapeHtml(detail.corruption_rate)} invalid</div>` : ''}
                </div>
            `;
        }

        return `
            <div class="doctor-inline-detail">
                <strong>${escapeHtml(label)}</strong>
                <div>${escapeHtml(message)}</div>
            </div>
        `;
    }

    attachIssueActions() {
        this.issuesList.querySelectorAll('[data-doctor-action]').forEach((button) => {
            button.addEventListener('click', async (event) => {
                const action = event.currentTarget.dataset.doctorAction;
                await this.handleAction(action);
            });
        });
    }

    async handleAction(action) {
        switch (action) {
            case 'open-settings':
                modalManager.showModal('settingsModal');
                window.setTimeout(() => {
                    // Open the API key editor directly
                    if (typeof settingsManager.editApiKey === 'function') {
                        settingsManager.editApiKey();
                    } else {
                        const input = document.getElementById('civitaiApiKey');
                        if (input) {
                            input.focus();
                            input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    }
                }, 100);
                break;
            case 'open-settings-syntax-format':
                modalManager.showModal('settingsModal');
                window.setTimeout(() => {
                    // Switch to Interface section
                    document.querySelectorAll('.settings-section').forEach((s) => s.classList.remove('active'));
                    const interfaceSection = document.getElementById('section-interface');
                    if (interfaceSection) {
                        interfaceSection.classList.add('active');
                    }
                    document.querySelectorAll('.settings-nav-item').forEach((n) => n.classList.remove('active'));
                    const interfaceNav = document.querySelector('.settings-nav-item[data-section="interface"]');
                    if (interfaceNav) {
                        interfaceNav.classList.add('active');
                    }

                    // Focus and scroll to the LoRA Syntax Format dropdown
                    const select = document.getElementById('loraSyntaxFormat');
                    if (select) {
                        select.focus();
                        select.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        // Add temporary highlight animation
                        const settingItem = select.closest('.setting-item');
                        if (settingItem) {
                            settingItem.classList.add('settings-setting-highlight');
                            setTimeout(() => {
                                settingItem.classList.remove('settings-setting-highlight');
                            }, 4500);
                        }
                    }
                }, 100);
                break;
            case 'repair-cache':
                await this.repairCache();
                break;
            case 'resolve-filename-conflicts':
                await this.promptResolveConflicts();
                break;
            case 'reload-page':
                this.reloadUi();
                break;
            default:
                break;
        }
    }

    async repairCache() {
        try {
            this.setLoading(true);
            const response = await fetch('/api/lm/doctor/repair-cache', { method: 'POST' });
            const payload = await response.json();

            if (!response.ok || payload.success === false) {
                throw new Error(payload.error || translate('doctor.toast.repairFailed', {}, 'Cache rebuild failed.'));
            }

            showToast('doctor.toast.repairSuccess', {}, 'success');
            await this.refreshDiagnostics({ silent: true });
        } catch (error) {
            console.error('Doctor cache repair failed:', error);
            showToast('doctor.toast.repairFailed', { message: error.message }, 'error');
        } finally {
            this.setLoading(false);
        }
    }

    _getConflictStats() {
        const conflict = (this.lastDiagnostics?.diagnostics || []).find(
            (d) => d.id === 'filename_conflicts'
        );
        if (!conflict || !Array.isArray(conflict.details)) {
            return { groups: 0, files: 0 };
        }
        const summary = conflict.details.find(
            (d) => d && typeof d === 'object' && d.conflict_groups !== undefined
        );
        return {
            groups: summary?.conflict_groups || 0,
            files: summary?.total_conflict_files || 0,
        };
    }

    async promptResolveConflicts() {
        const stats = this._getConflictStats();
        if (stats.groups === 0) {
            return;
        }

        const detailEl = document.getElementById('resolveConflictsDetail');
        if (detailEl) {
            detailEl.innerHTML = translate(
                'conflictConfirm.detail',
                {},
                'Example: <code>Add_Details_v1.2</code> \u2192 <code>Add_Details_v1.2-a3f7</code>'
            );
        }

        const impactEl = document.getElementById('resolveConflictsImpact');
        if (impactEl) {
            impactEl.innerHTML = translate(
                'conflictConfirm.impact',
                { count: stats.files, groups: stats.groups },
                `Will rename <strong>${stats.files}</strong> file(s) across <strong>${stats.groups}</strong> duplicate group(s).`
            );
        }

        this._confirmResolveResolve = null;
        modalManager.showModal('resolveFilenameConflictsModal');
        return new Promise((resolve) => {
            this._confirmResolveResolve = resolve;
        });
    }

    async confirmResolveConflicts() {
        modalManager.closeModal('resolveFilenameConflictsModal');
        if (this._confirmResolveResolve) {
            this._confirmResolveResolve(true);
            this._confirmResolveResolve = null;
        }
        await this.resolveFilenameConflicts();
    }

    async resolveFilenameConflicts() {
        try {
            this.setLoading(true);
            const response = await fetch('/api/lm/doctor/resolve-filename-conflicts', { method: 'POST' });
            const payload = await response.json();

            if (!response.ok || payload.success === false) {
                throw new Error(payload.error || 'Failed to resolve filename conflicts.');
            }

            const renamedCount = payload.count || 0;
            showToast(
                'doctor.toast.conflictsResolved',
                { count: renamedCount },
                'success'
            );

            // Update scroller items so model cards reflect new filenames immediately
            if (state.virtualScroller && payload.renamed) {
                for (const renamed of payload.renamed) {
                    const baseName = renamed.new_filename.replace(/\.[^.]+$/, '');
                    state.virtualScroller.updateSingleItem(renamed.old_path, {
                        file_name: baseName,
                        file_path: renamed.new_path,
                    });
                }
            }

            await this.refreshDiagnostics({ silent: true });
        } catch (error) {
            console.error('Doctor filename conflict resolution failed:', error);
            showToast(
                'doctor.toast.conflictsResolveFailed',
                { message: error.message },
                'error'
            );
        } finally {
            this.setLoading(false);
        }
    }

    async exportBundle() {
        try {
            this.setLoading(true);
            const response = await fetch('/api/lm/doctor/export-bundle', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    summary: this.lastDiagnostics?.summary || null,
                    diagnostics: this.lastDiagnostics?.diagnostics || [],
                    frontend_logs: this.consoleEntries,
                    client_context: {
                        url: window.location.href,
                        user_agent: navigator.userAgent,
                        language: navigator.language,
                        app_version: this.getClientVersion(),
                    },
                }),
            });

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.error || 'Failed to export diagnostics bundle');
            }

            const blob = await response.blob();
            const disposition = response.headers.get('Content-Disposition') || '';
            const match = disposition.match(/filename=\"([^\"]+)\"/);
            const filename = match?.[1] || 'lora-manager-doctor.zip';
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);

            showToast('doctor.toast.exportSuccess', {}, 'success');
        } catch (error) {
            console.error('Doctor export failed:', error);
            showToast('doctor.toast.exportFailed', { message: error.message }, 'error');
        } finally {
            this.setLoading(false);
        }
    }
}

export const doctorManager = new DoctorManager();

// Make available globally for HTML onclick handlers
if (typeof window !== 'undefined') {
    window.doctorManager = doctorManager;
}
