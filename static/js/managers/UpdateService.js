import { modalManager } from './ModalManager.js';
import {
    getStorageItem,
    setStorageItem,
    getStoredVersionInfo,
    setStoredVersionInfo,
    isVersionMatch
} from '../utils/storageHelpers.js';
import { state } from '../state/index.js';
import { bannerService } from './BannerService.js';
import { translate } from '../utils/i18nHelpers.js';
import { showModelModal } from '../components/shared/ModelModal.js';

/** Global endpoint: the alerts panel spans every model type. */
const PRICE_ALERTS_ENDPOINT = '/api/lm/price-alerts';
/** localStorage watermark of the newest alert the user has already seen. */
const PRICE_ALERTS_VIEWED_KEY = 'lm_price_alerts_viewed_at';

async function fetchPriceAlerts(limit = 200) {
    const response = await fetch(
        `${PRICE_ALERTS_ENDPOINT}?limit=${encodeURIComponent(limit)}`
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.success !== true) {
        throw new Error(payload?.error || response.statusText || 'Failed to load price alerts');
    }
    return {
        alerts: Array.isArray(payload.alerts) ? payload.alerts : [],
        enabled: payload.enabled === true,
        thresholdBuzz: payload.thresholdBuzz ?? 0,
        newestCheckedAt: payload.newestCheckedAt ?? null,
        unavailableCount: payload.unavailableCount ?? 0
    };
}

/** POSIX seconds of the moment an alert started, for unread/sorting comparisons. */
function priceAlertTimestamp(alert) {
    if (typeof alert?.priceAlertSince === 'number') {
        return alert.priceAlertSince;
    }
    if (alert?.gateLapsedAt) {
        const parsed = Date.parse(alert.gateLapsedAt);
        if (!Number.isNaN(parsed)) {
            return parsed / 1000;
        }
    }
    return 0;
}

function formatRelativeTime(timestampSeconds) {
    if (!timestampSeconds) return '';
    const elapsedMs = Date.now() - timestampSeconds * 1000;
    const minutes = Math.floor(elapsedMs / 60000);
    if (minutes < 1) return translate('update.priceAlerts.justNow', {}, 'just now');
    if (minutes < 60) {
        return translate('update.priceAlerts.minutesAgo', { count: minutes }, `${minutes} min ago`);
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
        return translate('update.priceAlerts.hoursAgo', { count: hours }, `${hours} h ago`);
    }
    const days = Math.floor(hours / 24);
    return translate('update.priceAlerts.daysAgo', { count: days }, `${days} d ago`);
}

function formatShortDate(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '';
    return parsed.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Open the notification bell on the Buzz price alerts tab.
 * Shared by the controls dropdown item and the global context menu item.
 */
export function openPriceAlertsPanel() {
    updateService.openPriceAlertsTab();
}

export class UpdateService {
    constructor() {
        this.updateCheckInterval = 60 * 60 * 1000; // 1 hour
        this.currentVersion = "v0.0.0";  // Initialize with default values
        this.latestVersion = "v0.0.0";   // Initialize with default values
        this.updateInfo = null;
        this.updateAvailable = false;
        this.gitInfo = {
            short_hash: "unknown",
            branch: "unknown",
            commit_date: "unknown"
        };
        this.updateNotificationsEnabled = getStorageItem('show_update_notifications', true);
        this.lastCheckTime = parseInt(getStorageItem('last_update_check') || '0');
        this.isUpdating = false;
        this.channelMode = null;
        this.hasGit = false;
        this.nightlyNotifyDate = getStorageItem('nightly_notify_date', '');
        this.nightlyBadgeShown = false;
        this.progressKeepVisible = false;
        this.currentVersionInfo = null;
        this.versionMismatch = false;
        this.activeNotificationTab = 'updates';
        this.handleBannerHistoryUpdated = this.handleBannerHistoryUpdated.bind(this);
        this.handleNotificationTabKeydown = this.handleNotificationTabKeydown.bind(this);
        // Buzz price alerts (panel data, loaded on demand; the count is cached so
        // the bell badge and the context-menu label can share it).
        this.priceAlerts = null;
        this.priceAlertsEnabled = false;
        this.priceAlertsThreshold = 0;
        this.priceAlertsNewestCheckedAt = null;
        this.priceAlertsUnavailableCount = 0;
        this.priceAlertsLoading = false;
        this.priceAlertSegment = 'below_threshold';
        this.unreadPriceAlertCount = 0;
        this.handlePriceAlertSegmentClick = this.handlePriceAlertSegmentClick.bind(this);
    }

    initialize() {
        // Register event listener for update notification toggle
        const updateCheckbox = document.getElementById('updateNotifications');
        if (updateCheckbox) {
            updateCheckbox.checked = this.updateNotificationsEnabled;
            updateCheckbox.addEventListener('change', (e) => {
                this.updateNotificationsEnabled = e.target.checked;
                setStorageItem('show_update_notifications', e.target.checked);
                this.updateBadgeVisibility();
            });
        }

        const updateBtn = document.getElementById('updateBtn');
        if (updateBtn) {
            updateBtn.addEventListener('click', () => this.performUpdate());
        }
        
        this.wireChannelButtons();

        this.setupNotificationCenter();
        window.addEventListener('lm:banner-history-updated', this.handleBannerHistoryUpdated);
        this.updateTabBadges();
        
        // Perform update check if needed
        this.checkVersionInfo().then(() => {
            this.checkForUpdates().then(() => {
                this.updateBadgeVisibility();
            });
        });

        this.updateModalContent();
    }
    
    wireChannelButtons() {
        const releaseBtn = document.getElementById('channelRelease');
        const nightlyBtn = document.getElementById('channelNightly');
        if (releaseBtn) {
            releaseBtn.addEventListener('click', () => this.switchChannel('release'));
        }
        if (nightlyBtn) {
            nightlyBtn.addEventListener('click', () => this.switchChannel('nightly'));
        }
    }

    async switchChannel(channel) {
        if (channel === this.channelMode) {
            return;
        }
        if (this.isUpdating) {
            return;
        }
        if (!this.hasGit && channel === 'nightly') {
            const confirmed = await this._confirmChannelSwitch(
                'update.channelSwitch.nightlyTitle',
                'update.channelSwitch.nightlyMessage'
            );
            if (!confirmed) return;
        }
        if (this.hasGit && channel === 'release') {
            const confirmed = await this._confirmChannelSwitch(
                'update.channelSwitch.releaseTitle',
                'update.channelSwitch.releaseMessage'
            );
            if (!confirmed) return;
        }

        try {
            this.isUpdating = true;
            this.showUpdateProgress(true);
            this.updateProgress(10, translate('update.channelSwitch.switching', { channel }));

            const response = await fetch('/api/lm/switch-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel })
            });

            const data = await response.json();

            if (data.success) {
                this.channelMode = channel;
                // Persist channel preference to settings.json
                fetch('/api/lm/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ update_channel: channel })
                }).then(r => {
                    if (!r.ok) console.warn('Failed to persist update channel:', r.status);
                }).catch(e => console.warn('Failed to persist update channel:', e));
                await this.checkForUpdates({ force: true });
                this.updateModalContent();
                this.updateChannelUI();
                this._showSwitchCompleteMessage(data.new_version);
                this.progressKeepVisible = true;
            } else {
                throw new Error(data.error || translate('update.channelSwitch.failed'));
            }
        } catch (error) {
            console.error('Channel switch failed:', error);
            this.updateProgress(0, translate('update.channelSwitch.failed'));
        } finally {
            if (this.progressKeepVisible) {
                this.isUpdating = false;
                this.progressKeepVisible = false;
            } else {
                setTimeout(() => {
                    this.showUpdateProgress(false);
                    this.isUpdating = false;
                }, 2000);
            }
        }
    }

    updateChannelUI() {
        const releaseBtn = document.getElementById('channelRelease');
        const nightlyBtn = document.getElementById('channelNightly');

        if (releaseBtn) {
            releaseBtn.classList.toggle('active', this.channelMode === 'release');
        }
        if (nightlyBtn) {
            nightlyBtn.classList.toggle('active', this.channelMode === 'nightly');
        }
    }

    _resolveChannelFromSettings() {
        const stored = state?.global?.settings?.update_channel;
        if (stored === 'nightly' || stored === 'release') {
            return stored;
        }
        if (!this.hasGit) {
            return 'release';
        }
        if (this.gitInfo?.branch === 'detached') {
            return 'release';
        }
        return 'nightly';
    }

    async _confirmChannelSwitch(titleKey, messageKey) {
        return new Promise((resolve) => {
            const title = translate(titleKey);
            const message = translate(messageKey);
            const cancelText = translate('common.cancel');
            const confirmText = translate('common.confirm');

            const overlay = document.createElement('div');
            overlay.className = 'channel-switch-overlay';
            overlay.innerHTML = `
                <div class="channel-switch-dialog">
                    <h3>${title}</h3>
                    <p>${message}</p>
                    <div class="channel-switch-actions">
                        <button class="secondary-btn channel-switch-cancel">${cancelText}</button>
                        <button class="primary-btn channel-switch-confirm">${confirmText}</button>
                    </div>
                </div>
            `;

            const dismiss = (result) => {
                document.removeEventListener('keydown', onKeydown);
                overlay.remove();
                resolve(result);
            };

            const onKeydown = (e) => {
                if (e.key === 'Escape') {
                    e.stopPropagation();
                    e.preventDefault();
                    dismiss(false);
                }
            };

            document.addEventListener('keydown', onKeydown, { capture: true });

            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    dismiss(false);
                }
            });

            overlay.querySelector('.channel-switch-cancel').addEventListener('click', () => {
                dismiss(false);
            });

            overlay.querySelector('.channel-switch-confirm').addEventListener('click', () => {
                dismiss(true);
            });

            document.body.appendChild(overlay);
        });
    }

    setupNotificationCenter() {
        const modal = document.getElementById('updateModal');
        if (!modal) {
            this.notificationTabs = [];
            this.notificationPanels = [];
            return;
        }

        this.notificationTabs = Array.from(modal.querySelectorAll('[data-notification-tab]'));
        this.notificationPanels = Array.from(modal.querySelectorAll('[data-notification-panel]'));

        this.notificationTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.getAttribute('data-notification-tab');
                this.switchNotificationTab(tabName, { markRead: true });
            });
            tab.addEventListener('keydown', this.handleNotificationTabKeydown);
        });

        this.renderRecentBanners();
        this.wirePriceAlertsPanel();
        this.switchNotificationTab(this.activeNotificationTab);

        // One request, and only for users who turned price tracking on. It feeds
        // the tab badge and the global-context-menu count.
        if (state?.global?.settings?.price_tracking_enabled) {
            this.loadPriceAlerts().catch((error) => {
                console.warn('Failed to preload price alerts:', error);
            });
        }
    }

    wirePriceAlertsPanel() {
        const modal = document.getElementById('updateModal');
        if (!modal) return;

        this.priceAlertSegments = Array.from(
            modal.querySelectorAll('[data-price-alert-segment]')
        );
        this.priceAlertSegments.forEach((segment) => {
            segment.addEventListener('click', this.handlePriceAlertSegmentClick);
        });

        const settingsBtn = document.getElementById('priceAlertsSettingsBtn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => {
                this.toggleUpdateModal();
                if (window.settingsManager) {
                    window.settingsManager.toggleSettings();
                }
            });
        }
    }

    handlePriceAlertSegmentClick(event) {
        const segment = event?.currentTarget?.getAttribute('data-price-alert-segment');
        if (!segment) return;
        this.priceAlertSegment = segment;
        this.renderPriceAlerts();
    }

    /**
     * Open the bell on the price alerts tab.
     *
     * ``toggleUpdateModal()`` *closes* an open bell, so an entry point that called
     * it unconditionally would dismiss the modal instead of switching to the tab.
     */
    openPriceAlertsTab() {
        const modal = modalManager.getModal('updateModal');
        if (!modal || !modal.isOpen) {
            this.toggleUpdateModal();
        }
        this.switchNotificationTab('priceAlerts', { markRead: true });
    }

    /**
     * Load the global alerts payload (all model types in one query).
     * @param {{force?: boolean}} [options]
     */
    async loadPriceAlerts({ force = false } = {}) {
        if (this.priceAlertsLoading) return this.priceAlerts;
        if (!force && this.priceAlerts) {
            this.renderPriceAlerts();
            return this.priceAlerts;
        }

        this.priceAlertsLoading = true;
        try {
            const payload = await fetchPriceAlerts();
            this.priceAlerts = payload.alerts;
            this.priceAlertsEnabled = payload.enabled;
            this.priceAlertsThreshold = payload.thresholdBuzz;
            this.priceAlertsNewestCheckedAt = payload.newestCheckedAt;
            this.priceAlertsUnavailableCount = payload.unavailableCount || 0;
            this.refreshUnreadPriceAlertCount();
            this.renderPriceAlerts();
            return this.priceAlerts;
        } catch (error) {
            console.error('Failed to load price alerts:', error);
            // Keep whatever we already had: a stale list beats an empty panel.
            this.renderPriceAlerts({ error: true });
            return this.priceAlerts;
        } finally {
            this.priceAlertsLoading = false;
        }
    }

    /** Alerts newer than the last time the user opened the panel. */
    refreshUnreadPriceAlertCount() {
        const alerts = Array.isArray(this.priceAlerts) ? this.priceAlerts : [];
        const viewedAt = Number(getStorageItem(PRICE_ALERTS_VIEWED_KEY, 0)) || 0;
        this.unreadPriceAlertCount = alerts.filter(
            (alert) => priceAlertTimestamp(alert) > viewedAt
        ).length;
        this.updateTabBadges();
        return this.unreadPriceAlertCount;
    }

    getUnreadPriceAlertCount() {
        return this.unreadPriceAlertCount || 0;
    }

    markPriceAlertsViewed() {
        const alerts = Array.isArray(this.priceAlerts) ? this.priceAlerts : [];
        const newest = alerts.reduce(
            (latest, alert) => Math.max(latest, priceAlertTimestamp(alert)),
            0
        );
        if (newest > 0) {
            setStorageItem(PRICE_ALERTS_VIEWED_KEY, newest);
        }
        this.unreadPriceAlertCount = 0;
        this.updateTabBadges();
    }

    renderPriceAlerts({ error = false } = {}) {
        const list = document.getElementById('priceAlertsList');
        const empty = document.getElementById('priceAlertsEmpty');
        const disabled = document.getElementById('priceAlertsDisabled');
        const stale = document.getElementById('priceAlertsStale');
        const thresholdLabel = document.getElementById('priceAlertsThreshold');
        if (!list || !empty) return;

        if (disabled) {
            disabled.classList.toggle('hidden', this.priceAlertsEnabled !== false);
        }
        if (thresholdLabel) {
            thresholdLabel.textContent = this.priceAlertsEnabled
                ? translate(
                      'update.priceAlerts.thresholdLabel',
                      { buzz: this.priceAlertsThreshold },
                      `Alert threshold: ${this.priceAlertsThreshold} Buzz`
                  )
                : '';
        }
        if (stale) {
            const checkedAt = this.priceAlertsNewestCheckedAt;
            let staleText = error
                ? translate(
                      'update.priceAlerts.loadFailed',
                      {},
                      'Could not refresh the alerts; showing the last known list.'
                  )
                : checkedAt
                  ? translate(
                        'update.priceAlerts.lastChecked',
                        { when: formatRelativeTime(checkedAt) },
                        `Prices last checked ${formatRelativeTime(checkedAt)}`
                    )
                  : '';
            const unavailable = this.priceAlertsUnavailableCount;
            if (unavailable > 0) {
                const unavailableText = translate(
                    'update.priceAlerts.unavailable',
                    { count: unavailable },
                    `${unavailable} paid version(s) have no readable price (mature models can only be read in a browser)`
                );
                staleText = staleText ? `${staleText} · ${unavailableText}` : unavailableText;
            }
            stale.textContent = staleText;
            stale.classList.toggle('hidden', !staleText);
        }

        if (Array.isArray(this.priceAlertSegments)) {
            this.priceAlertSegments.forEach((segment) => {
                const isActive =
                    segment.getAttribute('data-price-alert-segment') ===
                    this.priceAlertSegment;
                segment.classList.toggle('active', isActive);
                segment.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
        }

        const alerts = (Array.isArray(this.priceAlerts) ? this.priceAlerts : []).filter(
            (alert) => (alert.kind || 'below_threshold') === this.priceAlertSegment
        );

        list.innerHTML = '';
        if (!alerts.length) {
            empty.textContent = this.priceAlertSegment === 'became_free'
                ? translate(
                      'update.priceAlerts.emptyFree',
                      {},
                      'No version has become free yet.'
                  )
                : translate(
                      'update.priceAlerts.empty',
                      {},
                      'Nothing is under your price threshold right now.'
                  );
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        alerts.forEach((alert) => {
            list.appendChild(this.buildPriceAlertItem(alert));
        });
    }

    buildPriceAlertItem(alert) {
        const item = document.createElement('li');
        item.className = 'price-alert-item';

        const head = document.createElement('div');
        head.className = 'price-alert-head';

        const name = document.createElement('span');
        name.className = 'price-alert-model';
        const modelLabel = alert.modelName || alert.versionName || `#${alert.modelId}`;
        name.textContent = alert.versionName
            ? `${modelLabel} · ${alert.versionName}`
            : modelLabel;
        head.appendChild(name);

        if (alert.kind === 'below_threshold') {
            const price = document.createElement('span');
            price.className = 'price-alert-price is-alert';
            price.textContent = `${Number(alert.priceBuzz).toLocaleString()} Buzz`;
            if (
                typeof alert.listPriceBuzz === 'number' &&
                alert.listPriceBuzz > alert.priceBuzz
            ) {
                const was = document.createElement('span');
                was.className = 'price-alert-was';
                was.textContent = `${alert.listPriceBuzz.toLocaleString()} Buzz`;
                price.appendChild(was);
            }
            head.appendChild(price);
        } else {
            const free = document.createElement('span');
            free.className = 'price-alert-price is-alert';
            free.textContent = translate('update.priceAlerts.freeNow', {}, 'Free now');
            head.appendChild(free);
        }
        item.appendChild(head);

        const meta = document.createElement('div');
        meta.className = 'price-alert-meta';
        const metaParts = [alert.modelType];
        if (alert.acceptsBlueBuzz) {
            metaParts.push(translate('update.priceAlerts.blueBuzz', {}, 'Blue Buzz OK'));
        }
        if (alert.earlyAccessEndsAt) {
            metaParts.push(
                translate(
                    'update.priceAlerts.earlyAccessUntil',
                    { date: formatShortDate(alert.earlyAccessEndsAt) },
                    `Early access until ${formatShortDate(alert.earlyAccessEndsAt)}`
                )
            );
        }
        metaParts.push(
            alert.isInLibrary
                ? translate('update.priceAlerts.inLibrary', {}, 'In library')
                : translate('update.priceAlerts.notInLibrary', {}, 'Not in library')
        );
        const since = priceAlertTimestamp(alert);
        if (since > 0) {
            metaParts.push(
                translate(
                    'update.priceAlerts.droppedAgo',
                    { when: formatRelativeTime(since) },
                    `dropped ${formatRelativeTime(since)}`
                )
            );
        }
        meta.textContent = metaParts.filter(Boolean).join(' · ');
        item.appendChild(meta);

        const actions = document.createElement('div');
        actions.className = 'price-alert-actions';

        if (alert.civitaiUrl) {
            actions.appendChild(
                this.buildPriceAlertAction(
                    'civitai',
                    translate('update.priceAlerts.openCivitai', {}, 'Open on CivitAI'),
                    'fa-external-link-alt',
                    () => window.open(alert.civitaiUrl, '_blank', 'noopener')
                )
            );
        }
        // Only possible for a model that is actually in the library: the modal
        // reads the local metadata by file path.
        if (alert.filePath) {
            actions.appendChild(
                this.buildPriceAlertAction(
                    'open',
                    translate('update.priceAlerts.openLocal', {}, 'Open'),
                    'fa-folder-open',
                    () => {
                        showModelModal(
                            {
                                model_name: alert.modelName || alert.versionName,
                                file_path: alert.filePath,
                                civitai: {},
                            },
                            alert.modelType
                        );
                    }
                )
            );
        }
        item.appendChild(actions);

        return item;
    }

    buildPriceAlertAction(name, label, icon, onClick) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'price-alert-action';
        button.dataset.priceAlertAction = name;

        const iconElement = document.createElement('i');
        iconElement.className = `fas ${icon}`;
        button.appendChild(iconElement);

        const text = document.createElement('span');
        text.textContent = label;
        button.appendChild(text);

        button.addEventListener('click', onClick);
        return button;
    }

    switchNotificationTab(tabName, { markRead = false } = {}) {
        if (!tabName) return;

        this.activeNotificationTab = tabName;

        if (Array.isArray(this.notificationTabs)) {
            this.notificationTabs.forEach(tab => {
                const isActive = tab.getAttribute('data-notification-tab') === tabName;
                tab.classList.toggle('active', isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
                tab.setAttribute('tabindex', isActive ? '0' : '-1');
            });
        }

        if (Array.isArray(this.notificationPanels)) {
            this.notificationPanels.forEach(panel => {
                const isActive = panel.getAttribute('data-notification-panel') === tabName;
                panel.classList.toggle('active', isActive);
                panel.setAttribute('aria-hidden', isActive ? 'false' : 'true');
                panel.setAttribute('tabindex', isActive ? '0' : '-1');
            });
        }

        if (tabName === 'banners') {
            this.renderRecentBanners();
            if (markRead && typeof bannerService.markBannerHistoryViewed === 'function') {
                bannerService.markBannerHistoryViewed();
            }
        }

        if (tabName === 'priceAlerts') {
            this.loadPriceAlerts().then(() => {
                if (markRead) {
                    this.markPriceAlertsViewed();
                }
            });
        }

        this.updateTabBadges();
    }

    handleNotificationTabKeydown(event) {
        if (!Array.isArray(this.notificationTabs) || this.notificationTabs.length === 0) {
            return;
        }

        const { key } = event;
        const supportedKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];

        if (!supportedKeys.includes(key)) {
            return;
        }

        event.preventDefault();

        const currentIndex = this.notificationTabs.indexOf(event.currentTarget);
        if (currentIndex === -1) {
            return;
        }

        let targetIndex = currentIndex;

        if (key === 'ArrowLeft' || key === 'ArrowUp') {
            targetIndex = (currentIndex - 1 + this.notificationTabs.length) % this.notificationTabs.length;
        } else if (key === 'ArrowRight' || key === 'ArrowDown') {
            targetIndex = (currentIndex + 1) % this.notificationTabs.length;
        } else if (key === 'Home') {
            targetIndex = 0;
        } else if (key === 'End') {
            targetIndex = this.notificationTabs.length - 1;
        }

        const nextTab = this.notificationTabs[targetIndex];
        if (!nextTab) {
            return;
        }

        const tabName = nextTab.getAttribute('data-notification-tab');
        nextTab.focus();
        this.switchNotificationTab(tabName, { markRead: true });
    }

    isNotificationModalOpen() {
        const updateModal = modalManager.getModal('updateModal');
        return !!(updateModal && updateModal.isOpen);
    }

    handleBannerHistoryUpdated() {
        this.updateBadgeVisibility();

        if (this.isNotificationModalOpen() && this.activeNotificationTab === 'banners') {
            this.renderRecentBanners();
        }
    }

    updateTabBadges() {
        const updatesBadge = document.getElementById('updatesTabBadge');
        const bannerBadge = document.getElementById('bannerTabBadge');
        const priceAlertsBadge = document.getElementById('priceAlertsTabBadge');
        const hasUpdate = this.updateNotificationsEnabled && this.updateAvailable;
        const unreadBanners = typeof bannerService.getUnreadBannerCount === 'function'
            ? bannerService.getUnreadBannerCount()
            : 0;
        const unreadAlerts = this.getUnreadPriceAlertCount();

        if (updatesBadge) {
            updatesBadge.classList.toggle('visible', hasUpdate);
            updatesBadge.classList.toggle('is-dot', hasUpdate);
            updatesBadge.textContent = '';
        }

        if (priceAlertsBadge) {
            priceAlertsBadge.textContent = unreadAlerts > 9 ? '9+' : unreadAlerts ? String(unreadAlerts) : '';
            priceAlertsBadge.classList.toggle('visible', unreadAlerts > 0);
            priceAlertsBadge.classList.remove('is-dot');
        }

        if (bannerBadge) {
            if (unreadBanners > 0) {
                bannerBadge.textContent = unreadBanners > 9 ? '9+' : unreadBanners.toString();
            } else {
                bannerBadge.textContent = '';
            }
            bannerBadge.classList.toggle('visible', unreadBanners > 0);
            bannerBadge.classList.remove('is-dot');
        }
    }

    renderRecentBanners() {
        const list = document.getElementById('bannerHistoryList');
        const emptyState = document.getElementById('bannerHistoryEmpty');

        if (!list || !emptyState) return;

        const banners = typeof bannerService.getRecentBanners === 'function'
            ? bannerService.getRecentBanners()
            : [];

        list.innerHTML = '';

        if (!banners.length) {
            emptyState.style.display = 'block';
            return;
        }

        emptyState.style.display = 'none';

        banners.forEach(banner => {
            const item = document.createElement('li');
            item.className = 'banner-history-item';

            const title = document.createElement('h4');
            title.className = 'banner-history-title';
            title.textContent = banner.title || translate('update.banners.recent', {}, 'Recent banners');
            item.appendChild(title);

            if (banner.content) {
                const description = document.createElement('p');
                description.className = 'banner-history-description';
                description.textContent = banner.content;
                item.appendChild(description);
            }

            const meta = document.createElement('div');
            meta.className = 'banner-history-meta';

            const status = document.createElement('span');
            status.className = 'banner-history-status';
            if (banner.dismissedAt) {
                status.classList.add('dismissed');
                const dismissedRelative = this.formatRelativeTime(banner.dismissedAt);
                status.textContent = translate('update.banners.dismissed', {
                    time: dismissedRelative
                }, `Dismissed ${dismissedRelative}`);
            } else {
                status.classList.add('active');
                status.textContent = translate('update.banners.active', {}, 'Active');
            }
            meta.appendChild(status);

            const shownRelative = this.formatRelativeTime(banner.timestamp);
            const timestamp = document.createElement('span');
            timestamp.className = 'banner-history-time';
            timestamp.textContent = translate('update.banners.shown', {
                time: shownRelative
            }, `Shown ${shownRelative}`);
            meta.appendChild(timestamp);

            item.appendChild(meta);

            if (Array.isArray(banner.actions) && banner.actions.length > 0) {
                const actionsContainer = document.createElement('div');
                actionsContainer.className = 'banner-history-actions';

                banner.actions.forEach(action => {
                    if (!action?.url) {
                        return;
                    }

                    const link = document.createElement('a');
                    link.className = `banner-history-action banner-history-action-${action.type || 'secondary'}`;
                    link.href = action.url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.textContent = action.text || action.url;

                    if (action.icon) {
                        const icon = document.createElement('i');
                        icon.className = action.icon;
                        link.prepend(icon);
                    }

                    actionsContainer.appendChild(link);
                });

                if (actionsContainer.children.length > 0) {
                    item.appendChild(actionsContainer);
                }
            }

            list.appendChild(item);
        });
    }

    formatRelativeTime(timestamp) {
        if (!timestamp) {
            return '';
        }

        const locale = window?.i18n?.getCurrentLocale?.() || navigator.language || 'en';

        try {
            const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
            const divisions = [
                { amount: 60, unit: 'second' },
                { amount: 60, unit: 'minute' },
                { amount: 24, unit: 'hour' },
                { amount: 7, unit: 'day' },
                { amount: 4.34524, unit: 'week' },
                { amount: 12, unit: 'month' },
                { amount: Infinity, unit: 'year' }
            ];

            let duration = (timestamp - Date.now()) / 1000;

            for (const division of divisions) {
                if (Math.abs(duration) < division.amount) {
                    return formatter.format(Math.round(duration), division.unit);
                }
                duration /= division.amount;
            }

            return formatter.format(Math.round(duration), 'year');
        } catch (error) {
            console.warn('RelativeTimeFormat not available, falling back to locale string.', error);
            return new Date(timestamp).toLocaleString(locale);
        }
    }
    
    async checkForUpdates({ force = false } = {}) {
        let needsMigration = false;
        if (this.channelMode === null) {
            const stored = state?.global?.settings?.update_channel;
            if (stored === 'nightly' || stored === 'release') {
                this.channelMode = stored;
            } else if (!this.hasGit) {
                this.channelMode = 'release';
                needsMigration = true;
            }
            // hasGit=true with no stored value: wait for gitInfo.branch
        }

        if (!force && !this.updateNotificationsEnabled) {
            return;
        }

        // Check if we should perform an update check
        const now = Date.now();
        const forceCheck = force || this.lastCheckTime === 0;

        if (!forceCheck && now - this.lastCheckTime < this.updateCheckInterval) {
            // If we already have update info, just update the UI
            if (this.updateAvailable) {
                this.updateBadgeVisibility();
            }
            return;
        }

        try {
            // Call backend API to check for updates with nightly flag
            const nightly = (this.channelMode ?? (this.hasGit ? 'nightly' : 'release')) === 'nightly';
            const response = await fetch(`/api/lm/check-updates?nightly=${nightly}`);
            const data = await response.json();
            
            if (data.success) {
                this.currentVersion = data.current_version || "v0.0.0";
                this.latestVersion = data.latest_version || "v0.0.0";
                this.updateInfo = data;
                this.gitInfo = data.git_info || this.gitInfo;
                this.hasGit = data.has_git || false;

                if (needsMigration || this.channelMode === null) {
                    this.channelMode = this._resolveChannelFromSettings();
                    if (state?.global?.settings) {
                        state.global.settings.update_channel = this.channelMode;
                    }
                    fetch('/api/lm/settings', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ update_channel: this.channelMode })
                    }).then(r => {
                        if (!r.ok) console.warn('Failed to persist update channel:', r.status);
                    }).catch(e => console.warn('Failed to persist update channel:', e));
                }

                this.updateAvailable = data.update_available;

                // Nightly channel: surface the update badge at most once per calendar day.
                if (this.updateAvailable && this.channelMode === 'nightly' && this.nightlyNotifyDate !== this._getTodayKey()) {
                    this._markNightlyNotified();
                }

                this.lastCheckTime = now;
                setStorageItem('last_update_check', now.toString());

                this.updateBadgeVisibility();
                this.updateModalContent();
                this.updateChannelUI();

                console.log("Update check complete:", {
                    currentVersion: this.currentVersion,
                    latestVersion: this.latestVersion,
                    updateAvailable: this.updateAvailable,
                    gitInfo: this.gitInfo
                });
            }
        } catch (error) {
            console.error('Failed to check for updates:', error);
        }
    }
    
    // Helper method to compare version strings
    isNewerVersion(latestVersion, currentVersion) {
        if (!latestVersion || !currentVersion) return false;
        
        // Remove 'v' prefix if present
        const latest = latestVersion.replace(/^v/, '');
        const current = currentVersion.replace(/^v/, '');
        
        // Split version strings into components
        const latestParts = latest.split(/[-\.]/);
        const currentParts = current.split(/[-\.]/);
        
        // Compare major, minor, patch versions
        for (let i = 0; i < 3; i++) {
            const latestNum = parseInt(latestParts[i] || '0', 10);
            const currentNum = parseInt(currentParts[i] || '0', 10);
            
            if (latestNum > currentNum) return true;
            if (latestNum < currentNum) return false;
        }
        
        // If numeric versions are the same, check for beta/alpha status
        const latestIsBeta = latest.includes('beta') || latest.includes('alpha');
        const currentIsBeta = current.includes('beta') || current.includes('alpha');
        
        // Release version is newer than beta/alpha
        if (!latestIsBeta && currentIsBeta) return true;
        
        return false;
    }

    _getTodayKey() {
        const now = new Date();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        return `${now.getFullYear()}-${month}-${day}`;
    }

    _isNightlyBadgeAllowed() {
        if (this.channelMode !== 'nightly') {
            return true;
        }
        // Keep the badge visible for the rest of the session once shown, but do
        // not show it again on later sessions within the same calendar day.
        return this.nightlyNotifyDate !== this._getTodayKey() || this.nightlyBadgeShown;
    }

    _markNightlyNotified() {
        this.nightlyNotifyDate = this._getTodayKey();
        this.nightlyBadgeShown = true;
        setStorageItem('nightly_notify_date', this.nightlyNotifyDate);
    }
    
    updateBadgeVisibility() {
        const updateToggle = document.querySelector('.update-toggle');
        const updateBadge = document.querySelector('.update-toggle .update-badge');
        const unreadBanners = typeof bannerService.getUnreadBannerCount === 'function'
            ? bannerService.getUnreadBannerCount()
            : 0;

        // Force updating badges visibility based on current state
        const shouldShowUpdate = this.updateNotificationsEnabled && this.updateAvailable && this._isNightlyBadgeAllowed();

        if (updateToggle) {
            let tooltipKey = 'header.actions.notifications';
            if (shouldShowUpdate) {
                tooltipKey = 'update.updateAvailable';
            } else if (unreadBanners > 0) {
                tooltipKey = 'update.tabs.messages';
            }
            updateToggle.title = translate(tooltipKey);
        }

        const shouldShow = shouldShowUpdate || unreadBanners > 0;

        if (updateBadge) {
            updateBadge.classList.toggle('visible', shouldShow);
        }

        this.updateTabBadges();
    }
    
    updateModalContent() {
        const modal = document.getElementById('updateModal');
        if (!modal) return;
        
        // Update title based on update availability
        const headerTitle = modal.querySelector('.update-header h2');
        if (headerTitle) {
            headerTitle.textContent = this.updateAvailable ?
                translate('update.updateAvailable') :
                translate('update.notificationsTitle');
        }
        
        // Always update version information, even if updateInfo is null
        const currentVersionEl = modal.querySelector('.current-version .version-number');
        const newVersionEl = modal.querySelector('.new-version .version-number');
        
        if (currentVersionEl) currentVersionEl.textContent = this.currentVersion;
        
        const newVersionLabel = modal.querySelector('.new-version .label');
        if (newVersionLabel) {
            newVersionLabel.textContent = (this.updateInfo?.nightly)
                ? `${translate('update.latestMain')}:`
                : `${translate('update.newVersion')}:`;
        }

        if (newVersionEl) {
            if (this.updateInfo?.nightly) {
                const behind = this.updateInfo.behind_by || 0;
                const remoteHash = this.latestVersion.replace('main-', '');
                const localHash = this.gitInfo.short_hash || '';
                const date = this.updateInfo.commit_date || '';
                const datePart = date ? ` · ${date}` : '';

                if (behind > 0) {
                    newVersionEl.textContent = `${behind} commit${behind !== 1 ? 's' : ''} behind main (${remoteHash}${datePart})`;
                } else if (localHash !== remoteHash) {
                    newVersionEl.textContent = `Behind main (${remoteHash}${datePart})`;
                } else {
                    newVersionEl.textContent = `Up to date (${remoteHash}${datePart})`;
                }
            } else {
                newVersionEl.textContent = this.latestVersion;
            }
        }
        
        // Update update button state
        const updateBtn = modal.querySelector('#updateBtn');
        if (updateBtn) {
            updateBtn.classList.toggle('disabled', !this.updateAvailable || this.isUpdating);
            updateBtn.disabled = !this.updateAvailable || this.isUpdating;
        }
        
        // Update git info
        const gitInfoEl = modal.querySelector('.git-info');
        if (gitInfoEl && this.gitInfo) {
            if (this.gitInfo.short_hash !== 'unknown') {
                let gitText = `${translate('update.commit')}: ${this.gitInfo.short_hash}`;
                if (this.gitInfo.commit_date !== 'unknown') {
                    gitText += ` - ${translate('common.status.date', {}, 'Date')}: ${this.gitInfo.commit_date}`;
                }
                gitInfoEl.textContent = gitText;
                gitInfoEl.style.display = 'block';
            } else {
                gitInfoEl.style.display = 'none';
            }
        }
        
        // Update changelog content if available
        if (this.updateInfo && (this.updateInfo.changelog || this.updateInfo.releases)) {
            const changelogContent = modal.querySelector('.changelog-content');
            if (changelogContent) {
                changelogContent.innerHTML = ''; // Clear existing content
                
                // Check if we have multiple releases
                const releases = this.updateInfo.releases;
                if (releases && Array.isArray(releases) && releases.length > 0) {
                    // Display multiple releases (up to 5)
                    releases.forEach(release => {
                        const changelogItem = document.createElement('div');
                        changelogItem.className = 'changelog-item';
                        if (release.is_latest) {
                            changelogItem.classList.add('latest');
                        }
                        
                        const versionHeader = document.createElement('h4');
                        
                        if (release.is_latest) {
                            const badge = document.createElement('span');
                            badge.className = 'latest-badge';
                            badge.textContent = translate('update.latestBadge', {}, 'Latest');
                            versionHeader.appendChild(badge);
                            versionHeader.appendChild(document.createTextNode(' '));
                        }
                        
                        const versionSpan = document.createElement('span');
                        versionSpan.className = 'version';
                        versionSpan.textContent = `${translate('common.status.version', {}, 'Version')} ${release.version}`;
                        versionHeader.appendChild(versionSpan);
                        
                        if (release.published_at) {
                            const dateSpan = document.createElement('span');
                            dateSpan.className = 'publish-date';
                            dateSpan.textContent = this.formatRelativeTime(new Date(release.published_at).getTime());
                            versionHeader.appendChild(dateSpan);
                        }
                        
                        changelogItem.appendChild(versionHeader);
                        
                        // Create changelog list
                        const changelogList = document.createElement('ul');
                        
                        if (release.changelog && release.changelog.length > 0) {
                            release.changelog.forEach(item => {
                                const listItem = document.createElement('li');
                                listItem.innerHTML = this.parseMarkdown(item);
                                changelogList.appendChild(listItem);
                            });
                        } else {
                            const listItem = document.createElement('li');
                            listItem.textContent = translate('update.noChangelogAvailable', {}, 'No detailed changelog available.');
                            changelogList.appendChild(listItem);
                        }
                        
                        changelogItem.appendChild(changelogList);
                        changelogContent.appendChild(changelogItem);
                    });
                } else {
                    // Fallback: display single changelog (old behavior)
                    const changelogItem = document.createElement('div');
                    changelogItem.className = 'changelog-item';
                    
                    const versionHeader = document.createElement('h4');
                    versionHeader.textContent = `${translate('common.status.version', {}, 'Version')} ${this.latestVersion}`;
                    changelogItem.appendChild(versionHeader);
                    
                    const changelogList = document.createElement('ul');
                    
                    if (this.updateInfo.changelog && this.updateInfo.changelog.length > 0) {
                        this.updateInfo.changelog.forEach(item => {
                            const listItem = document.createElement('li');
                            listItem.innerHTML = this.parseMarkdown(item);
                            changelogList.appendChild(listItem);
                        });
                    } else {
                        const listItem = document.createElement('li');
                        listItem.textContent = translate('update.noChangelogAvailable', {}, 'No detailed changelog available. Check GitHub for more information.');
                        changelogList.appendChild(listItem);
                    }
                    
                    changelogItem.appendChild(changelogList);
                    changelogContent.appendChild(changelogItem);
                }
            }
        }
        
        // Update GitHub link to point to the specific release if available
        const githubLink = modal.querySelector('.update-link');
        if (githubLink && this.latestVersion) {
            if (this.updateInfo?.nightly) {
                githubLink.href = 'https://github.com/willmiao/ComfyUI-Lora-Manager/commits/main';
            } else {
                const versionTag = this.latestVersion.replace(/^v/, '');
                githubLink.href = `https://github.com/willmiao/ComfyUI-Lora-Manager/releases/tag/v${versionTag}`;
            }
        }
    }
    
    async performUpdate() {
        if (!this.updateAvailable || this.isUpdating) {
            return;
        }
        
        try {
            this.isUpdating = true;
            this.updateUpdateUI('updating', translate('update.status.updating'));
            this.showUpdateProgress(true);
            
            // Update progress
            this.updateProgress(10, translate('update.updateProgress.preparing'));
            
            const response = await fetch('/api/lm/perform-update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    nightly: this.channelMode === 'nightly'
                })
            });
            
            this.updateProgress(50, translate('update.updateProgress.installing'));
            
            const data = await response.json();
            
            if (data.success) {
                this.updateProgress(100, translate('update.updateProgress.completed'));
                this.updateUpdateUI('success', translate('update.status.updated'));
                
                // Show success message and suggest restart
                setTimeout(() => {
                    this.showUpdateCompleteMessage(data.new_version);
                }, 1000);
                
            } else {
                throw new Error(data.error || translate('update.status.updateFailed'));
            }
            
        } catch (error) {
            console.error('Update failed:', error);
            this.updateUpdateUI('error', translate('update.status.updateFailed'));
            this.updateProgress(0, translate('update.updateProgress.failed', { error: error.message }));
            
            // Hide progress after error
            setTimeout(() => {
                this.showUpdateProgress(false);
            }, 3000);
        } finally {
            this.isUpdating = false;
        }
    }
    
    updateUpdateUI(state, text) {
        const updateBtn = document.getElementById('updateBtn');
        const updateBtnText = document.getElementById('updateBtnText');
        
        if (updateBtn && updateBtnText) {
            // Remove existing state classes
            updateBtn.classList.remove('updating', 'success', 'error', 'disabled');
            
            // Add new state class
            if (state !== 'normal') {
                updateBtn.classList.add(state);
            }
            
            // Update button text
            updateBtnText.textContent = text;
            
            // Update disabled state
            updateBtn.disabled = (state === 'updating' || state === 'disabled');
        }
    }
    
    showUpdateProgress(show) {
        const progressContainer = document.getElementById('updateProgress');
        if (progressContainer) {
            progressContainer.style.display = show ? 'block' : 'none';
        }
    }
    
    updateProgress(percentage, text) {
        const progressFill = document.getElementById('updateProgressFill');
        const progressText = document.getElementById('updateProgressText');
        
        if (progressFill) {
            progressFill.style.width = `${percentage}%`;
        }
        
        if (progressText) {
            progressText.textContent = text;
        }
    }

    _showSwitchCompleteMessage(version) {
        this.showUpdateProgress(true);
        this.updateProgress(100, '');
        const progressText = document.getElementById('updateProgressText');
        if (progressText) {
            progressText.innerHTML = `
                <div style="text-align: center; color: var(--lora-success);">
                    <i class="fas fa-check-circle" style="margin-right: 8px;"></i>
                    ${translate('update.completion.successMessage', { version })}
                    <br><br>
                    <div style="opacity: 0.95; color: var(--lora-error); font-size: 1em;">
                        ${translate('update.completion.restartMessage')}<br>
                        ${translate('update.completion.reloadMessage')}
                    </div>
                </div>
            `;
        }
    }

    showUpdateCompleteMessage(newVersion) {
        const modal = document.getElementById('updateModal');
        if (!modal) return;
        
        // Update the modal content to show completion
        const progressText = document.getElementById('updateProgressText');
        if (progressText) {
            progressText.innerHTML = `
                <div style="text-align: center; color: var(--lora-success);">
                    <i class="fas fa-check-circle" style="margin-right: 8px;"></i>
                    ${translate('update.completion.successMessage', { version: newVersion })}
                    <br><br>
                    <div style="opacity: 0.95; color: var(--lora-error); font-size: 1em;">
                        ${translate('update.completion.restartMessage')}<br>
                        ${translate('update.completion.reloadMessage')}
                    </div>
                </div>
            `;
        }
        
        // Update current version display
        this.currentVersion = newVersion;
        this.updateAvailable = false;
        
        // Refresh the modal content
        // setTimeout(() => {
        //     this.updateModalContent();
        //     this.showUpdateProgress(false);
        // }, 2000);
    }
    
    // Simple markdown parser for changelog items
    // Simple markdown parser for changelog items
    // Escape HTML entities first so angle brackets in content (e.g. `<lora:x>`)
    // aren't swallowed by innerHTML's HTML parser as invalid tags
    parseMarkdown(text) {
        if (!text) return '';
        
        text = text.replace(/&/g, '&amp;');
        text = text.replace(/</g, '&lt;');
        text = text.replace(/>/g, '&gt;');
        
        // Handle bold text (**text**)
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Handle italic text (*text*)
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Handle inline code (`code`)
        text = text.replace(/`(.*?)`/g, '<code>$1</code>');
        
        // Handle links [text](url)
        text = text.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
        
        return text;
    }
    
    toggleUpdateModal() {
        const updateModal = modalManager.getModal('updateModal');

        // If modal is already open, just close it
        if (updateModal && updateModal.isOpen) {
            modalManager.closeModal('updateModal');
            return;
        }

        if (!Array.isArray(this.notificationTabs) || !this.notificationTabs.length) {
            this.setupNotificationCenter();
        }

        // Update the modal content immediately with current data
        this.updateModalContent();
        this.updateChannelUI();
        this.renderRecentBanners();

        // Show the modal with current data
        modalManager.showModal('updateModal');
        this.switchNotificationTab(this.activeNotificationTab, { markRead: true });

        // Then check for updates in the background
        this.manualCheckForUpdates().then(() => {
            // Update the modal content again after the check completes
            this.updateModalContent();
            if (this.activeNotificationTab === 'banners' && this.isNotificationModalOpen()) {
                this.renderRecentBanners();
            }
        });
    }
    
    async manualCheckForUpdates() {
        await this.checkForUpdates({ force: true });
        // Ensure badge visibility is updated after manual check
        this.updateBadgeVisibility();
    }
    
    async checkVersionInfo() {
        try {
            // Call API to get current version info
            const response = await fetch('/api/lm/version-info');
            const data = await response.json();
            
            if (data.success) {
                this.currentVersionInfo = data.version;
                this.hasGit = data.has_git || false;

                this.versionMismatch = !isVersionMatch(this.currentVersionInfo);
                
                if (this.versionMismatch) {
                    console.log('Version mismatch detected:', {
                        current: this.currentVersionInfo,
                        stored: getStoredVersionInfo()
                    });
                    
                    // Silently update stored version info as cache busting handles the resource updates
                    setStoredVersionInfo(this.currentVersionInfo);
                }
            }
        } catch (error) {
            console.error('Failed to check version info:', error);
        }
    }
}

// Create and export singleton instance
export const updateService = new UpdateService();
