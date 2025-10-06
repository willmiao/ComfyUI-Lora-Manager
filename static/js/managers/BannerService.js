import {
    getStorageItem,
    setStorageItem
} from '../utils/storageHelpers.js';
import { translate } from '../utils/i18nHelpers.js';

const COMMUNITY_SUPPORT_BANNER_ID = 'community-support';
const COMMUNITY_SUPPORT_BANNER_DELAY_MS = 5 * 24 * 60 * 60 * 1000; // 5 days
const COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY = 'community_support_banner_first_seen_at';
const COMMUNITY_SUPPORT_SHOWN_KEY = 'community_support_banner_shown';
const KO_FI_URL = 'https://ko-fi.com/pixelpawsai';

/**
 * Banner Service for managing notification banners
 */
class BannerService {
    constructor() {
        this.banners = new Map();
        this.container = null;
        this.initialized = false;
        this.communitySupportBannerTimer = null;
        this.communitySupportBannerRegistered = false;
    }

    /**
     * Initialize the banner service
     */
    initialize() {
        if (this.initialized) return;

        this.container = document.getElementById('banner-container');
        if (!this.container) {
            console.warn('Banner container not found');
            return;
        }

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

        this.showActiveBanners();
        this.initialized = true;
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
        const dismissedBanners = getStorageItem('dismissed_banners', []);
        return dismissedBanners.includes(bannerId);
    }

    /**
     * Dismiss a banner
     * @param {string} bannerId - Banner ID
     */
    dismissBanner(bannerId) {
        const dismissedBanners = getStorageItem('dismissed_banners', []);
        if (!dismissedBanners.includes(bannerId)) {
            dismissedBanners.push(bannerId);
            setStorageItem('dismissed_banners', dismissedBanners);
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
    }

    /**
     * Show all active (non-dismissed) banners
     */
    showActiveBanners() {
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
            `<button class="banner-dismiss" onclick="bannerService.dismissBanner('${banner.id}')" title="Dismiss">
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
    clearDismissedBanners() {
        setStorageItem('dismissed_banners', []);
        location.reload();
    }

    prepareCommunitySupportBanner() {
        if (this.communitySupportBannerTimer) {
            clearTimeout(this.communitySupportBannerTimer);
            this.communitySupportBannerTimer = null;
        }

        if (getStorageItem(COMMUNITY_SUPPORT_SHOWN_KEY, false)) {
            return;
        }

        const now = Date.now();
        let firstSeenAt = getStorageItem(COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY, null);

        if (typeof firstSeenAt !== 'number') {
            firstSeenAt = now;
            setStorageItem(COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY, firstSeenAt);
        }

        const availableAt = firstSeenAt + COMMUNITY_SUPPORT_BANNER_DELAY_MS;
        const delay = Math.max(availableAt - now, 0);

        if (delay === 0) {
            this.registerCommunitySupportBanner();
        } else {
            this.communitySupportBannerTimer = setTimeout(() => {
                this.registerCommunitySupportBanner();
            }, delay);
        }
    }

    registerCommunitySupportBanner() {
        if (this.communitySupportBannerRegistered || getStorageItem(COMMUNITY_SUPPORT_SHOWN_KEY, false)) {
            return;
        }

        if (this.communitySupportBannerTimer) {
            clearTimeout(this.communitySupportBannerTimer);
            this.communitySupportBannerTimer = null;
        }

        this.communitySupportBannerRegistered = true;
        setStorageItem(COMMUNITY_SUPPORT_SHOWN_KEY, true);

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
                    url: KO_FI_URL,
                    type: 'primary'
                },
                {
                    text: translate(
                        'banners.communitySupport.learnMore',
                        {},
                        'LM Civitai Extension Tutorial'
                    ),
                    icon: 'fas fa-book',
                    url: 'https://github.com/willmiao/ComfyUI-Lora-Manager/wiki/LoRA-Manager-Civitai-Extension-(Chrome-Extension)',
                    type: 'tertiary'
                }
            ],
            dismissible: true,
            priority: 2
        });

        this.updateContainerVisibility();
    }
}

// Create and export singleton instance
export const bannerService = new BannerService();

// Make it globally available
window.bannerService = bannerService;
