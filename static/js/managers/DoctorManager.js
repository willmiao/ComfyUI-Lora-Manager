import { modalManager } from './ModalManager.js';
import { showToast } from '../utils/uiHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { escapeHtml } from '../components/shared/utils.js';

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
            .map((action) => `
                <button class="${action.id === 'repair-cache' || action.id === 'reload-page' ? 'primary-btn' : 'secondary-btn'}" data-doctor-action="${escapeHtml(action.id)}">
                    ${escapeHtml(action.label)}
                </button>
            `)
            .join('');

        return `
            <section class="doctor-issue-card" data-status="${escapeHtml(status)}" data-issue-id="${escapeHtml(item.id || '')}">
                <div class="doctor-issue-header">
                    <div>
                        <h3>${escapeHtml(item.title || '')}</h3>
                        <p class="doctor-issue-summary">${escapeHtml(item.summary || '')}</p>
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
                    const input = document.getElementById('civitaiApiKey');
                    if (input) {
                        input.focus();
                        input.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
                break;
            case 'repair-cache':
                await this.repairCache();
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
