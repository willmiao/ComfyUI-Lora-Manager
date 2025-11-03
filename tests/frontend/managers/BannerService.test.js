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

describe('BannerService', () => {
    beforeEach(() => {
        // Clear all mocks
        vi.clearAllMocks();
        
        // Reset banner service state
        bannerService.banners.clear();
        bannerService.initialized = false;
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