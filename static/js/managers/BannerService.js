import {
    getStorageItem,
    setStorageItem,
    removeStorageItem
} from '../utils/storageHelpers.js';
import { translate } from '../utils/i18nHelpers.js';
import { state } from '../state/index.js';
import { getModelApiClient } from '../api/modelApiFactory.js';

const COMMUNITY_SUPPORT_BANNER_ID = 'community-support';
const CACHE_HEALTH_BANNER_ID = 'cache-health-warning';
const COMMUNITY_SUPPORT_BANNER_DELAY_MS = 5 * 24 * 60 * 60 * 1000; // 5 days
const COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY = 'community_support_banner_first_seen_at';
const COMMUNITY_SUPPORT_VERSION_KEY = 'community_support_banner_state_version';
// Increment this version to reset the banner schedule after significant updates
const COMMUNITY_SUPPORT_STATE_VERSION = 'v2';
const KO_FI_URL = 'https://ko-fi.com/pixelpawsai';
const AFDIAN_URL = 'https://afdian.com/a/pixelpawsai';
const BANNER_HISTORY_KEY = 'banner_history';
const BANNER_HISTORY_VIEWED_AT_KEY = 'banner_history_viewed_at';
const BANNER_HISTORY_LIMIT = 20;
const HISTORY_EXCLUDED_IDS = new Set([]);

/**
 * Banner Service for managing notification banners
 */
class BannerService {
    constructor() {
        this.banners = new Map();
        this.container = null;
        this.initialized = false;
        this.recentHistory = this.loadBannerHistory();
        this.bannerHistoryViewedAt = this.loadBannerHistoryViewedAt();

        this.initializeCommunitySupportState();
    }

    /**
     * Initialize the banner service
     */
    async initialize() {
        if (this.initialized) return;

        this.container = document.getElementById('banner-container');
        if (!this.container) {
            console.warn('Banner container not found');
            return;
        }

        // Load dismissed banners from backend first (for persistence across browser modes)
        await this.loadDismissedBannersFromBackend();

        // Register default banners
        this.registerBanner('civitai-extension', {
            id: 'civitai-extension',
            title: 'New Tool Available: LM Civitai Extension!',
            content: 'LM Civitai Extension is a browser extension designed to work seamlessly with LoRA Manager to significantly enhance your Civitai browsing experience! See which models you already have, download new ones with a single click, and manage your downloads efficiently.',
            actions: [
                {
                    text: 'Chrome Web Store',
                    icon: 'fab fa-chrome',
                    url: 'https://chromewebstore.google.com/detail/capigligggeijgmocnaflanlbghnamgm?utm_source=item-share-cb',
                    type: 'secondary'
                },
                {
                    text: 'Firefox Extension',
                    icon: 'fab fa-firefox-browser',
                    url: 'https://github.com/willmiao/lm-civitai-extension-firefox/releases/latest/download/extension.xpi',
                    type: 'secondary'
                },
                {
                    text: 'Read more...',
                    icon: 'fas fa-book',
                    url: 'https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/LoRA-Manager-Civitai-Extension-(Chrome-Extension)',
                    type: 'tertiary'
                }
            ],
            dismissible: true,
            priority: 1
        });

        this.prepareCommunitySupportBanner();

        await this.showActiveBanners();
        this.initialized = true;
    }

    /**
     * Load dismissed banners from backend settings
     * Falls back to localStorage if backend is unavailable
     */
    async loadDismissedBannersFromBackend() {
        try {
            const response = await fetch('/api/lm/settings');
            const data = await response.json();
            if (data.success && data.settings && Array.isArray(data.settings.dismissed_banners)) {
                // Merge backend dismissed banners with localStorage
                const backendDismissed = data.settings.dismissed_banners;
                const localDismissed = getStorageItem('dismissed_banners', []);
                
                // Use Set to get unique banner IDs
                const mergedDismissed = [...new Set([...backendDismissed, ...localDismissed])];
                
                // Save merged list to localStorage as cache
                if (mergedDismissed.length > 0) {
                    setStorageItem('dismissed_banners', mergedDismissed);
                }
            }
        } catch (e) {
            console.debug('Failed to fetch dismissed banners from backend, using localStorage');
        }
    }

    /**
     * Register a new banner
     * @param {string} id - Unique banner ID
     * @param {Object} bannerConfig - Banner configuration
     */
    registerBanner(id, bannerConfig) {
        this.banners.set(id, bannerConfig);
        
        // If already initialized, render the banner immediately
        if (this.initialized && !this.isBannerDismissed(id) && this.container) {
            this.renderBanner(bannerConfig);
            this.updateContainerVisibility();
        }
    }

    /**
     * Check if a banner has been dismissed
     * @param {string} bannerId - Banner ID
     * @returns {boolean}
     */
    isBannerDismissed(bannerId) {
        // Check localStorage (which is synced with backend on load)
        const dismissedBanners = getStorageItem('dismissed_banners', []);
        return dismissedBanners.includes(bannerId);
    }

    /**
     * Dismiss a banner
     * @param {string} bannerId - Banner ID
     */
    async dismissBanner(bannerId) {
        const dismissedBanners = getStorageItem('dismissed_banners', []);
        let bannerAlreadyDismissed = dismissedBanners.includes(bannerId);
        
        if (!bannerAlreadyDismissed) {
            dismissedBanners.push(bannerId);
            setStorageItem('dismissed_banners', dismissedBanners);
            
            // Save to backend for persistence (survives incognito/private mode)
            await this.saveDismissedBannersToBackend(dismissedBanners);
        }

        // Remove banner from DOM
        const bannerElement = document.querySelector(`[data-banner-id="${bannerId}"]`);
        if (bannerElement) {
            // Call onRemove callback if provided
            const banner = this.banners.get(bannerId);
            if (banner && typeof banner.onRemove === 'function') {
                banner.onRemove(bannerElement);
            }
            
            bannerElement.style.animation = 'banner-slide-up 0.3s ease-in-out forwards';
            setTimeout(() => {
                bannerElement.remove();
                this.updateContainerVisibility();
            }, 300);
        }

        if (!bannerAlreadyDismissed) {
            this.markBannerDismissed(bannerId);
        }
    }

    /**
     * Save dismissed banners to backend settings
     * @param {string[]} dismissedBanners - Array of dismissed banner IDs
     */
    async saveDismissedBannersToBackend(dismissedBanners) {
        try {
            await fetch('/api/lm/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dismissed_banners: dismissedBanners })
            });
        } catch (e) {
            console.error('Failed to save dismissed banners to backend:', e);
        }
    }

    /**
     * Show all active (non-dismissed) banners
     */
    async showActiveBanners() {
        if (!this.container) return;

        const activeBanners = Array.from(this.banners.values())
            .filter(banner => !this.isBannerDismissed(banner.id))
            .sort((a, b) => (b.priority || 0) - (a.priority || 0));

        activeBanners.forEach(banner => {
            this.renderBanner(banner);
        });

        this.updateContainerVisibility();
    }

    /**
     * Render a banner to the DOM
     * @param {Object} banner - Banner configuration
     */
    renderBanner(banner) {
        const bannerElement = document.createElement('div');
        bannerElement.className = 'banner-item';
        bannerElement.setAttribute('data-banner-id', banner.id);

        const actionsHtml = banner.actions ? banner.actions.map(action => {
            const actionAttribute = action.action ? `data-action="${action.action}"` : '';
            const href = action.url ? `href="${action.url}"` : 'href="#"';
            const target = action.url ? 'target="_blank" rel="noopener noreferrer"' : '';
            
            return `<a ${href} ${target} class="banner-action banner-action-${action.type}" ${actionAttribute}>
                <i class="${action.icon}"></i>
                <span>${action.text}</span>
            </a>`;
        }).join('') : '';

        const dismissButtonHtml = banner.dismissible ? 
            `<button class="banner-dismiss" onclick="bannerService.dismissBanner('${banner.id}').catch(console.error)" title="Dismiss">
                <i class="fas fa-times"></i>
            </button>` : '';

        bannerElement.innerHTML = `
            <div class="banner-content">
                <div class="banner-text">
                    <h4 class="banner-title">${banner.title}</h4>
                    <p class="banner-description">${banner.content}</p>
                </div>
                <div class="banner-actions">
                    ${actionsHtml}
                </div>
            </div>
            ${dismissButtonHtml}
        `;

        this.container.appendChild(bannerElement);

        this.recordBannerAppearance(banner);

        // Call onRegister callback if provided
        if (typeof banner.onRegister === 'function') {
            banner.onRegister(bannerElement);
        }
    }

    /**
     * Check if a banner is currently rendered and visible
     * @param {string} bannerId
     * @returns {boolean}
     */
    isBannerVisible(bannerId) {
        const el = document.querySelector(`[data-banner-id="${bannerId}"]`);
        return !!el && el.offsetParent !== null;
    }

    /**
     * Update container visibility based on active banners
     */
    updateContainerVisibility() {
        if (!this.container) return;

        const hasActiveBanners = this.container.children.length > 0;
        this.container.style.display = hasActiveBanners ? 'block' : 'none';
    }

    /**
     * Clear all dismissed banners (for testing/admin purposes)
     */
    async clearDismissedBanners() {
        setStorageItem('dismissed_banners', []);
        
        // Also clear on backend
        try {
            await fetch('/api/lm/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dismissed_banners: [] })
            });
        } catch (e) {
            console.error('Failed to clear dismissed banners on backend:', e);
        }
        
        location.reload();
    }

    /**
     * Register a cache health warning banner
     * @param {Object} healthData - Health data from WebSocket
     */
    registerCacheHealthBanner(healthData) {
        if (!healthData || healthData.status === 'healthy') {
            return;
        }

        // Remove existing cache health banner if any
        this.removeBannerElement(CACHE_HEALTH_BANNER_ID);

        const isCorrupted = healthData.status === 'corrupted';
        const titleKey = isCorrupted
            ? 'banners.cacheHealth.corrupted.title'
            : 'banners.cacheHealth.degraded.title';
        const defaultTitle = isCorrupted
            ? 'Cache Corruption Detected'
            : 'Cache Issues Detected';

        const title = translate(titleKey, {}, defaultTitle);

        const contentKey = 'banners.cacheHealth.content';
        const defaultContent = 'Found {invalid} of {total} cache entries are invalid ({rate}). This may cause missing models or errors. Rebuilding the cache is recommended.';
        const content = translate(contentKey, {
            invalid: healthData.details?.invalid || 0,
            total: healthData.details?.total || 0,
            rate: healthData.details?.corruption_rate || '0%'
        }, defaultContent);

        this.registerBanner(CACHE_HEALTH_BANNER_ID, {
            id: CACHE_HEALTH_BANNER_ID,
            title: title,
            content: content,
            pageType: healthData.pageType,
            actions: [
                {
                    text: translate('banners.cacheHealth.rebuildCache', {}, 'Rebuild Cache'),
                    icon: 'fas fa-sync-alt',
                    action: 'rebuild-cache',
                    type: 'primary'
                },
                {
                    text: translate('banners.cacheHealth.dismiss', {}, 'Dismiss'),
                    icon: 'fas fa-times',
                    action: 'dismiss',
                    type: 'secondary'
                }
            ],
            dismissible: true,
            priority: 10, // High priority
            onRegister: (bannerElement) => {
                // Attach click handlers for actions
                const rebuildBtn = bannerElement.querySelector('[data-action="rebuild-cache"]');
                const dismissBtn = bannerElement.querySelector('[data-action="dismiss"]');

                if (rebuildBtn) {
                    rebuildBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.handleRebuildCache(bannerElement, healthData.pageType);
                    });
                }

                if (dismissBtn) {
                    dismissBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.dismissBanner(CACHE_HEALTH_BANNER_ID);
                    });
                }
            }
        });
    }

    /**
     * Handle rebuild cache action from banner
     * @param {HTMLElement} bannerElement - The banner element
     * @param {string} pageType - The page type (loras, checkpoints, embeddings)
     */
    async handleRebuildCache(bannerElement, pageType) {
        const currentPageType = pageType || this.getCurrentPageType();

        try {
            const apiClient = getModelApiClient(currentPageType);

            // Update banner to show rebuilding status
            const actionsContainer = bannerElement.querySelector('.banner-actions');
            if (actionsContainer) {
                actionsContainer.innerHTML = `
                    <span class="banner-loading">
                        <i class="fas fa-spinner fa-spin"></i>
                        <span>${translate('banners.cacheHealth.rebuilding', {}, 'Rebuilding cache...')}</span>
                    </span>
                `;
            }

            await apiClient.refreshModels(true);

            // Remove banner on success without marking as dismissed
            this.removeBannerElement(CACHE_HEALTH_BANNER_ID);
        } catch (error) {
            console.error('Cache rebuild failed:', error);

            const actionsContainer = bannerElement.querySelector('.banner-actions');
            if (actionsContainer) {
                actionsContainer.innerHTML = `
                    <span class="banner-error">
                        <i class="fas fa-exclamation-triangle"></i>
                        <span>${translate('banners.cacheHealth.rebuildFailed', {}, 'Rebuild failed. Please try again.')}</span>
                    </span>
                    <a href="#" class="banner-action banner-action-primary" data-action="rebuild-cache">
                        <i class="fas fa-sync-alt"></i>
                        <span>${translate('banners.cacheHealth.retry', {}, 'Retry')}</span>
                    </a>
                `;

                // Re-attach click handler
                const retryBtn = actionsContainer.querySelector('[data-action="rebuild-cache"]');
                if (retryBtn) {
                    retryBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        this.handleRebuildCache(bannerElement, pageType);
                    });
                }
            }
        }
    }

    /**
     * Get the current page type from the URL
     * @returns {string} Page type (loras, checkpoints, embeddings, recipes)
     */
    getCurrentPageType() {
        const path = window.location.pathname;
        if (path.includes('/checkpoints')) return 'checkpoints';
        if (path.includes('/embeddings')) return 'embeddings';
        if (path.includes('/recipes')) return 'recipes';
        return 'loras';
    }

    /**
     * Get the rebuild cache endpoint for the given page type
     * @param {string} pageType - The page type
     * @returns {string} The API endpoint URL
     */
    getRebuildEndpoint(pageType) {
        const endpoints = {
            'loras': '/api/lm/loras/reload?rebuild=true',
            'checkpoints': '/api/lm/checkpoints/reload?rebuild=true',
            'embeddings': '/api/lm/embeddings/reload?rebuild=true'
        };
        return endpoints[pageType] || endpoints['loras'];
    }

    /**
     * Remove a banner element from DOM without marking as dismissed
     * @param {string} bannerId - Banner ID to remove
     */
    removeBannerElement(bannerId) {
        const bannerElement = document.querySelector(`[data-banner-id="${bannerId}"]`);
        if (bannerElement) {
            bannerElement.style.animation = 'banner-slide-up 0.3s ease-in-out forwards';
            setTimeout(() => {
                bannerElement.remove();
                this.updateContainerVisibility();
            }, 300);
        }

        // Also remove from banners map
        this.banners.delete(bannerId);
    }

    prepareCommunitySupportBanner() {
        if (this.isBannerDismissed(COMMUNITY_SUPPORT_BANNER_ID)) {
            return;
        }

        const now = Date.now();
        let firstSeenAt = getStorageItem(COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY, null);

        if (typeof firstSeenAt !== 'number') {
            firstSeenAt = now;
            setStorageItem(COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY, firstSeenAt);
        }

        const availableAt = firstSeenAt + COMMUNITY_SUPPORT_BANNER_DELAY_MS;
        
        if (now >= availableAt) {
            this.registerCommunitySupportBanner();
        }
    }

    registerCommunitySupportBanner() {
        if (this.isBannerDismissed(COMMUNITY_SUPPORT_BANNER_ID)) {
            return;
        }

        // Determine support URL based on user language
        const currentLanguage = state.global.settings.language;
        const supportUrl = currentLanguage === 'zh-CN' ? AFDIAN_URL : KO_FI_URL;
        const tutorialUrl = currentLanguage === 'zh-CN' 
            ? 'https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/Lora-Manager-%E6%B5%8F%E8%A7%88%E5%99%A8%E6%8F%92%E4%BB%B6' 
            : 'https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/LoRA-Manager-Civitai-Extension-(Chrome-Extension)';

        this.registerBanner(COMMUNITY_SUPPORT_BANNER_ID, {
            id: COMMUNITY_SUPPORT_BANNER_ID,
            title: translate(
                'banners.communitySupport.title',
                {},
                'Keep LoRA Manager Thriving with Your Support ❤️'
            ),
            content: translate(
                'banners.communitySupport.content',
                {},
                'LoRA Manager is a passion project maintained full-time by a solo developer. Your support on Ko-fi helps cover development costs, keeps new updates coming, and unlocks a license key for the LM Civitai Extension as a thank-you gift. Every contribution truly makes a difference.'
            ),
            actions: [
                {
                    text: translate(
                        'banners.communitySupport.supportCta',
                        {},
                        'Support on Ko-fi'
                    ),
                    icon: 'fas fa-heart',
                    url: supportUrl,
                    type: 'primary'
                },
                {
                    text: translate(
                        'banners.communitySupport.learnMore',
                        {},
                        'LM Civitai Extension Tutorial'
                    ),
                    icon: 'fas fa-book',
                    url: tutorialUrl,
                    type: 'tertiary'
                }
            ],
            dismissible: true,
            priority: 2
        });

        this.updateContainerVisibility();
    }

    initializeCommunitySupportState() {
        const storedVersion = getStorageItem(COMMUNITY_SUPPORT_VERSION_KEY, null);

        if (storedVersion === COMMUNITY_SUPPORT_STATE_VERSION) {
            return;
        }

        setStorageItem(COMMUNITY_SUPPORT_VERSION_KEY, COMMUNITY_SUPPORT_STATE_VERSION);
        setStorageItem(COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY, Date.now());
    }

    loadBannerHistory() {
        const stored = getStorageItem(BANNER_HISTORY_KEY, []);
        if (!Array.isArray(stored)) {
            return [];
        }

        return stored.slice(0, BANNER_HISTORY_LIMIT).map(entry => ({
            ...entry,
            timestamp: typeof entry.timestamp === 'number' ? entry.timestamp : Date.now(),
            dismissedAt: typeof entry.dismissedAt === 'number' ? entry.dismissedAt : null,
            actions: Array.isArray(entry.actions) ? entry.actions : []
        }));
    }

    loadBannerHistoryViewedAt() {
        const stored = getStorageItem(BANNER_HISTORY_VIEWED_AT_KEY, 0);
        return typeof stored === 'number' ? stored : 0;
    }

    saveBannerHistory() {
        setStorageItem(BANNER_HISTORY_KEY, this.recentHistory.slice(0, BANNER_HISTORY_LIMIT));
    }

    notifyBannerHistoryUpdated() {
        window.dispatchEvent(new CustomEvent('lm:banner-history-updated'));
    }

    recordBannerAppearance(banner) {
        if (!banner?.id || HISTORY_EXCLUDED_IDS.has(banner.id)) {
            return;
        }

        // Check if banner with this ID already exists in recent history
        // Only record if it's not already in history (prevents duplicates on page refresh)
        const existingEntry = this.recentHistory.find(entry => entry.id === banner.id);
        if (existingEntry) {
            return; // Banner already exists in history, don't add again
        }

        const sanitizedActions = Array.isArray(banner.actions)
            ? banner.actions.map(action => ({
                text: action.text,
                icon: action.icon,
                url: action.url || null,
                type: action.type || 'secondary'
            }))
            : [];

        const entry = {
            id: banner.id,
            title: banner.title,
            content: banner.content,
            actions: sanitizedActions,
            timestamp: Date.now(),
            dismissedAt: null
        };

        this.recentHistory.unshift(entry);
        if (this.recentHistory.length > BANNER_HISTORY_LIMIT) {
            this.recentHistory.length = BANNER_HISTORY_LIMIT;
        }

        this.saveBannerHistory();
        this.notifyBannerHistoryUpdated();
    }

    markBannerDismissed(bannerId) {
        if (!bannerId || HISTORY_EXCLUDED_IDS.has(bannerId)) {
            return;
        }

        for (const entry of this.recentHistory) {
            if (entry.id === bannerId && !entry.dismissedAt) {
                entry.dismissedAt = Date.now();
                break;
            }
        }

        this.saveBannerHistory();
        this.notifyBannerHistoryUpdated();
    }

    getRecentBanners() {
        return this.recentHistory.slice();
    }

    getUnreadBannerCount() {
        return this.recentHistory.filter(entry => entry.timestamp > this.bannerHistoryViewedAt).length;
    }

    markBannerHistoryViewed() {
        this.bannerHistoryViewedAt = Date.now();
        setStorageItem(BANNER_HISTORY_VIEWED_AT_KEY, this.bannerHistoryViewedAt);
        this.notifyBannerHistoryUpdated();
    }
}

// Create and export singleton instance
export const bannerService = new BannerService();

// Make it globally available
window.bannerService = bannerService;
