import { beforeEach, describe, expect, it, vi } from 'vitest';
import { bannerService } from '../../../static/js/managers/BannerService.js';
import * as storageHelpers from '../../../static/js/utils/storageHelpers.js';
import * as i18nHelpers from '../../../static/js/utils/i18nHelpers.js';
import { state } from '../../../static/js/state/index.js';

// Mock storage helpers
vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getStorageItem: vi.fn(),
    setStorageItem: vi.fn(),
    removeStorageItem: vi.fn()
}));

// Mock i18n helpers
vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: vi.fn((key, params, defaultValue) => defaultValue || key)
}));

// Mock state
vi.mock('../../../static/js/state/index.js', () => ({
    state: {
        global: {
            settings: {
                language: 'en'
            }
        }
    }
}));

// Mock the shared Other Models helpers (exercised by their own tests)
vi.mock('../../../static/js/utils/otherModels.js', () => ({
    enableOtherModels: vi.fn().mockResolvedValue(),
    openOtherModelsSettings: vi.fn(),
}));

import { enableOtherModels, openOtherModelsSettings } from '../../../static/js/utils/otherModels.js';

describe('BannerService', () => {
    beforeEach(() => {
        // Clear all mocks
        vi.clearAllMocks();
        
        // Reset banner service state
        bannerService.banners.clear();
        bannerService.initialized = false;
        bannerService.currentBannerIndex = 0;
        bannerService.recentHistory = []; // Clear history for each test
        
        // Clear DOM
        document.body.innerHTML = '<div id="banner-container"></div>';
    });

    describe('Community Support Banner', () => {
        const COMMUNITY_SUPPORT_BANNER_ID = 'community-support';
        const COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY = 'community_support_banner_first_seen_at';
        const COMMUNITY_SUPPORT_VERSION_KEY = 'community_support_banner_state_version';
        
        beforeEach(() => {
            // Mock the version check to avoid resetting state
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === COMMUNITY_SUPPORT_VERSION_KEY) {
                    return 'v2'; // Current version
                }
                return defaultValue;
            });
            
            // Initialize the banner service
            bannerService.initializeCommunitySupportState();
        });

        it('should not show community support banner before 5 days have passed', () => {
            const now = Date.now();
            const firstSeenAt = now - (3 * 24 * 60 * 60 * 1000); // 3 days ago
            
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY) {
                    return firstSeenAt;
                }
                if (key === COMMUNITY_SUPPORT_VERSION_KEY) {
                    return 'v2';
                }
                if (key === 'dismissed_banners') {
                    return [];
                }
                return defaultValue;
            });
            
            // Mock Date.now to control time
            const originalNow = Date.now;
            global.Date.now = vi.fn(() => now);
            
            try {
                bannerService.prepareCommunitySupportBanner();
                
                // Banner should not be registered yet
                expect(bannerService.banners.has(COMMUNITY_SUPPORT_BANNER_ID)).toBe(false);
            } finally {
                global.Date.now = originalNow;
            }
        });

        it('should show community support banner after 5 days have passed', () => {
            const now = Date.now();
            const firstSeenAt = now - (6 * 24 * 60 * 60 * 1000); // 6 days ago
            
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY) {
                    return firstSeenAt;
                }
                if (key === COMMUNITY_SUPPORT_VERSION_KEY) {
                    return 'v2';
                }
                if (key === 'dismissed_banners') {
                    return [];
                }
                return defaultValue;
            });
            
            // Mock Date.now to control time
            const originalNow = Date.now;
            global.Date.now = vi.fn(() => now);
            
            try {
                bannerService.prepareCommunitySupportBanner();
                
                // Banner should be registered
                expect(bannerService.banners.has(COMMUNITY_SUPPORT_BANNER_ID)).toBe(true);
            } finally {
                global.Date.now = originalNow;
            }
        });

        it('should not show community support banner if it has been dismissed', () => {
            const now = Date.now();
            const firstSeenAt = now - (6 * 24 * 60 * 60 * 1000); // 6 days ago
            
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY) {
                    return firstSeenAt;
                }
                if (key === COMMUNITY_SUPPORT_VERSION_KEY) {
                    return 'v2';
                }
                if (key === 'dismissed_banners') {
                    return [COMMUNITY_SUPPORT_BANNER_ID]; // Dismissed
                }
                return defaultValue;
            });
            
            // Mock Date.now to control time
            const originalNow = Date.now;
            global.Date.now = vi.fn(() => now);
            
            try {
                bannerService.prepareCommunitySupportBanner();
                
                // Banner should not be registered because it's dismissed
                expect(bannerService.banners.has(COMMUNITY_SUPPORT_BANNER_ID)).toBe(false);
            } finally {
                global.Date.now = originalNow;
            }
        });

        it('should set first seen time if not already set', () => {
            const now = Date.now();
            
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY) {
                    return null; // Not set
                }
                if (key === COMMUNITY_SUPPORT_VERSION_KEY) {
                    return 'v2';
                }
                if (key === 'dismissed_banners') {
                    return [];
                }
                return defaultValue;
            });
            
            // Mock Date.now to control time
            const originalNow = Date.now;
            global.Date.now = vi.fn(() => now);
            
            try {
                bannerService.prepareCommunitySupportBanner();
                
                // Should have set the first seen time
                expect(storageHelpers.setStorageItem).toHaveBeenCalledWith(
                    COMMUNITY_SUPPORT_FIRST_SEEN_AT_KEY,
                    now
                );
            } finally {
                global.Date.now = originalNow;
            }
        });
    });

    describe('Other Models announcement', () => {
        const OTHER_MODELS_BANNER_ID = 'other-models-announcement';

        const prepareBanner = (dismissed = []) => {
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'dismissed_banners') {
                    return dismissed;
                }
                return defaultValue;
            });
            bannerService.container = document.getElementById('banner-container');
            bannerService.initialized = true;
            bannerService.prepareOtherModelsBanner();
        };

        const bannerElement = () =>
            document.querySelector(`[data-banner-id="${OTHER_MODELS_BANNER_ID}"]`);

        beforeEach(() => {
            state.global.settings.enable_other_models = false;
            state.global.settings.other_models_paths_available = true;
        });

        it('announces the feature while it is switched off', () => {
            prepareBanner();

            const element = bannerElement();
            expect(element).not.toBeNull();
            expect(element.querySelector('.banner-title').textContent)
                .toContain('Other Models Management is available');
        });

        it('stays silent when the host exposes no other-model folders', () => {
            // Standalone installs without the folder_paths keys in
            // settings.json would land on an empty page, so do not announce.
            state.global.settings.other_models_paths_available = false;

            prepareBanner();

            expect(bannerElement()).toBeNull();
            expect(bannerService.banners.has(OTHER_MODELS_BANNER_ID)).toBe(false);
        });

        it('still announces when availability is unknown (older payload)', () => {
            delete state.global.settings.other_models_paths_available;

            prepareBanner();

            expect(bannerElement()).not.toBeNull();
        });

        it('stays silent once the feature is enabled', () => {
            state.global.settings.enable_other_models = true;

            prepareBanner();

            expect(bannerElement()).toBeNull();
        });

        it('stays silent when it was dismissed before', () => {
            prepareBanner([OTHER_MODELS_BANNER_ID]);

            expect(bannerElement()).toBeNull();
        });

        it('enables the feature from the primary action', () => {
            prepareBanner();

            const button = bannerElement().querySelector(
                '.banner-action[data-action="enable-other-models"]'
            );
            expect(button).not.toBeNull();

            button.dispatchEvent(new MouseEvent('click', { bubbles: true }));

            expect(enableOtherModels).toHaveBeenCalledTimes(1);
        });

        it('opens the settings section from the secondary action', () => {
            prepareBanner();

            const button = bannerElement().querySelector(
                '.banner-action[data-action="open-other-models-settings"]'
            );
            expect(button).not.toBeNull();

            button.dispatchEvent(new MouseEvent('click', { bubbles: true }));

            expect(openOtherModelsSettings).toHaveBeenCalledTimes(1);
        });

        it('can drop the announcement without dismissing it', () => {
            prepareBanner();
            expect(bannerService.banners.has(OTHER_MODELS_BANNER_ID)).toBe(true);

            bannerService.removeOtherModelsAnnouncement();

            expect(bannerService.banners.has(OTHER_MODELS_BANNER_ID)).toBe(false);
            expect(storageHelpers.setStorageItem).not.toHaveBeenCalledWith(
                'dismissed_banners',
                expect.arrayContaining([OTHER_MODELS_BANNER_ID])
            );
        });
    });

    describe('Banner Dismissal', () => {
        it('should add banner to dismissed_banners array when dismissed', () => {
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'dismissed_banners') {
                    return [];
                }
                return defaultValue;
            });
            
            bannerService.dismissBanner('test-banner');
            
            expect(storageHelpers.setStorageItem).toHaveBeenCalledWith(
                'dismissed_banners',
                ['test-banner']
            );
        });

        it('should not add duplicate banner IDs to dismissed_banners array', () => {
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'dismissed_banners') {
                    return ['test-banner'];
                }
                return defaultValue;
            });
            
            bannerService.dismissBanner('test-banner');
            
            // Should not have been called again since it's already dismissed
            expect(storageHelpers.setStorageItem).not.toHaveBeenCalled();
        });
    });

    describe('Banner Rotation', () => {
        const registerTestBanner = (id, priority) => {
            bannerService.registerBanner(id, {
                id,
                title: `Banner ${id}`,
                content: `Content ${id}`,
                dismissible: true,
                priority
            });
        };

        const displayedBannerId = () =>
            document.querySelector('#banner-container .banner-item')
                ?.getAttribute('data-banner-id');

        let dismissedStore;

        beforeEach(() => {
            dismissedStore = [];
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'dismissed_banners') {
                    return dismissedStore;
                }
                return defaultValue;
            });
            storageHelpers.setStorageItem.mockImplementation((key, value) => {
                if (key === 'dismissed_banners') {
                    dismissedStore = value;
                }
            });
            bannerService.container = document.getElementById('banner-container');
            bannerService.initialized = true;
        });

        it('renders only the highest priority banner when multiple are active', () => {
            registerTestBanner('low', 1);
            registerTestBanner('high', 10);

            const rendered = document.querySelectorAll('#banner-container .banner-item');
            expect(rendered).toHaveLength(1);
            expect(displayedBannerId()).toBe('high');
        });

        it('shows a pager with position indicator when multiple banners are active', () => {
            registerTestBanner('a', 1);
            registerTestBanner('b', 2);

            const pager = document.querySelector('.banner-pager');
            expect(pager).not.toBeNull();
            expect(pager.querySelector('.banner-pager-indicator').textContent.trim())
                .toBe('1 / 2');
        });

        it('does not show a pager for a single banner', () => {
            registerTestBanner('only', 1);

            expect(document.querySelector('.banner-pager')).toBeNull();
        });

        it('cycles to the next banner and wraps around', () => {
            registerTestBanner('a', 1);
            registerTestBanner('b', 2);

            document.querySelector('[data-pager="next"]')
                .dispatchEvent(new MouseEvent('click', { bubbles: true }));
            expect(displayedBannerId()).toBe('a');
            expect(document.querySelector('.banner-pager-indicator').textContent.trim())
                .toBe('2 / 2');

            document.querySelector('[data-pager="next"]')
                .dispatchEvent(new MouseEvent('click', { bubbles: true }));
            expect(displayedBannerId()).toBe('b');
            expect(document.querySelector('.banner-pager-indicator').textContent.trim())
                .toBe('1 / 2');
        });

        it('cycles backwards with the previous button', () => {
            registerTestBanner('a', 1);
            registerTestBanner('b', 2);

            document.querySelector('[data-pager="prev"]')
                .dispatchEvent(new MouseEvent('click', { bubbles: true }));
            expect(displayedBannerId()).toBe('a');
        });

        it('shows the next banner after the displayed one is dismissed', async () => {
            vi.useFakeTimers();
            try {
                registerTestBanner('a', 1);
                registerTestBanner('b', 2);
                expect(displayedBannerId()).toBe('b');

                await bannerService.dismissBanner('b');
                vi.advanceTimersByTime(300);

                expect(displayedBannerId()).toBe('a');
            } finally {
                vi.useRealTimers();
            }
        });

        it('records all active banners in history, not just the displayed one', () => {
            registerTestBanner('a', 1);
            registerTestBanner('b', 2);

            const historyIds = bannerService.recentHistory.map(entry => entry.id);
            expect(historyIds).toEqual(expect.arrayContaining(['a', 'b']));
        });
    });

    describe('Banner History', () => {
        const testBanner = {
            id: 'test-banner',
            title: 'Test Banner',
            content: 'This is a test banner',
            actions: [
                {
                    text: 'Action 1',
                    icon: 'fas fa-check',
                    url: 'https://example.com',
                    type: 'primary'
                }
            ]
        };

        it('should add banner to history when first recorded', () => {
            // Mock storage to return empty array
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'banner_history') {
                    return [];
                }
                return defaultValue;
            });

            // Record the banner appearance
            bannerService.recordBannerAppearance(testBanner);

            // Should have added the banner to history
            expect(bannerService.recentHistory).toHaveLength(1);
            expect(bannerService.recentHistory[0].id).toBe('test-banner');
            expect(bannerService.recentHistory[0].title).toBe('Test Banner');
        });

        it('should not add duplicate banner to history when recorded multiple times', () => {
            // Mock storage to return empty array
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'banner_history') {
                    return [];
                }
                return defaultValue;
            });

            // Record the same banner twice
            bannerService.recordBannerAppearance(testBanner);
            bannerService.recordBannerAppearance(testBanner);

            // Should only have one entry in history
            expect(bannerService.recentHistory).toHaveLength(1);
            expect(bannerService.recentHistory[0].id).toBe('test-banner');
        });

        it('should add different banners to history', () => {
            // Mock storage to return empty array
            storageHelpers.getStorageItem.mockImplementation((key, defaultValue) => {
                if (key === 'banner_history') {
                    return [];
                }
                return defaultValue;
            });

            const anotherBanner = {
                id: 'another-banner',
                title: 'Another Banner',
                content: 'This is another test banner'
            };

            // Record two different banners
            bannerService.recordBannerAppearance(testBanner);
            bannerService.recordBannerAppearance(anotherBanner);

            // Should have two entries in history
            expect(bannerService.recentHistory).toHaveLength(2);
            expect(bannerService.recentHistory[0].id).toBe('another-banner');
            expect(bannerService.recentHistory[1].id).toBe('test-banner');
        });
    });
});