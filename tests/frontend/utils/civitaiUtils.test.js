import { describe, it, expect } from 'vitest';
import {
    rewriteCivitaiUrl,
    getOptimizedUrl,
    getShowcaseUrl,
    getThumbnailUrl,
    extractCivitaiImageId,
    extractCivitaiModelUrlParts,
    isCivitaiUrl,
    isSupportedCivitaiPageHost,
    OptimizationMode
} from '../../../static/js/utils/civitaiUtils.js';

describe('civitaiUtils', () => {
    describe('OptimizationMode', () => {
        it('should have correct mode values', () => {
            expect(OptimizationMode.SHOWCASE).toBe('showcase');
            expect(OptimizationMode.THUMBNAIL).toBe('thumbnail');
        });
    });

    describe('rewriteCivitaiUrl', () => {
        it('should rewrite image URLs with /original=true for thumbnail mode', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.THUMBNAIL);

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/width=450,optimized=true/12345.jpeg');
        });

        it('should rewrite image URLs with /original=true for showcase mode (no width)', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.SHOWCASE);

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/optimized=true/12345.jpeg');
        });

        it('should rewrite video URLs with /original=true for thumbnail mode', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.mp4';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'video', OptimizationMode.THUMBNAIL);

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/transcode=true,width=450,optimized=true/12345.mp4');
        });

        it('should rewrite video URLs with /original=true for showcase mode (no width/transcode)', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.mp4';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'video', OptimizationMode.SHOWCASE);

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/optimized=true/12345.mp4');
        });

        it('should default to thumbnail mode when mode is not specified', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image');

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/width=450,optimized=true/12345.jpeg');
        });

        it('should not rewrite URLs without /original=true', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/width=450/12345.jpeg';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.THUMBNAIL);

            expect(wasRewritten).toBe(false);
            expect(rewritten).toBe(originalUrl);
        });

        it('should not rewrite non-CivitAI URLs', () => {
            const originalUrl = 'https://example.com/image.jpg';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.SHOWCASE);

            expect(wasRewritten).toBe(false);
            expect(rewritten).toBe(originalUrl);
        });

        it('should handle null/undefined URLs', () => {
            const [rewritten1, wasRewritten1] = rewriteCivitaiUrl(null, 'image');
            expect(wasRewritten1).toBe(false);
            expect(rewritten1).toBe(null);

            const [rewritten2, wasRewritten2] = rewriteCivitaiUrl(undefined, 'image');
            expect(wasRewritten2).toBe(false);
            expect(rewritten2).toBe(undefined);
        });

        it('should handle empty strings', () => {
            const [rewritten, wasRewritten] = rewriteCivitaiUrl('', 'image');
            expect(wasRewritten).toBe(false);
            expect(rewritten).toBe('');
        });

        it('should handle invalid URLs gracefully', () => {
            const [rewritten, wasRewritten] = rewriteCivitaiUrl('not-a-valid-url', 'image');
            expect(wasRewritten).toBe(false);
            expect(rewritten).toBe('not-a-valid-url');
        });

        it('should rewrite URLs from CivitAI CDN subdomains', () => {
            const originalUrl = 'https://image-b2.civitai.com/file/civitai-media-cache/original=true/sample.png';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.THUMBNAIL);

            expect(wasRewritten).toBe(true);
            expect(rewritten).toBe('https://image-b2.civitai.com/file/civitai-media-cache/width=450,optimized=true/sample.png');
        });

        it('should handle URLs with explicit port numbers', () => {
            const originalUrl = 'https://image.civitai.com:443/checkpoints/original=true/test.png';
            const [rewritten, wasRewritten] = rewriteCivitaiUrl(originalUrl, 'image', OptimizationMode.THUMBNAIL);

            expect(wasRewritten).toBe(true);
            // JavaScript URL.toString() removes default HTTPS port (443)
            expect(rewritten).toBe('https://image.civitai.com/checkpoints/width=450,optimized=true/test.png');
        });

        it('should handle case-insensitive hostnames', () => {
            const testCases = [
                'https://IMAGE.CIVITAI.COM/original=true/test.png',
                'https://Image.Civitai.Com/original=true/test.png',
                'https://image-b2.CIVITAI.com/original=true/test.png',
            ];

            for (const url of testCases) {
                const [rewritten, wasRewritten] = rewriteCivitaiUrl(url, 'image', OptimizationMode.THUMBNAIL);
                expect(wasRewritten).toBe(true);
                expect(rewritten).toContain('width=450,optimized=true');
            }
        });
    });

    describe('getOptimizedUrl', () => {
        it('should return optimized URL for CivitAI images in thumbnail mode', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const optimized = getOptimizedUrl(originalUrl, 'image', OptimizationMode.THUMBNAIL);

            expect(optimized).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/width=450,optimized=true/12345.jpeg');
        });

        it('should return optimized URL for CivitAI images in showcase mode', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const optimized = getOptimizedUrl(originalUrl, 'image', OptimizationMode.SHOWCASE);

            expect(optimized).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/optimized=true/12345.jpeg');
        });

        it('should return original URL for non-CivitAI URLs', () => {
            const originalUrl = 'https://example.com/image.jpg';
            const optimized = getOptimizedUrl(originalUrl, 'image');

            expect(optimized).toBe(originalUrl);
        });
    });

    describe('getShowcaseUrl', () => {
        it('should return showcase-optimized URL (full quality)', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const showcaseUrl = getShowcaseUrl(originalUrl, 'image');

            expect(showcaseUrl).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/optimized=true/12345.jpeg');
        });

        it('should handle videos for showcase', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.mp4';
            const showcaseUrl = getShowcaseUrl(originalUrl, 'video');

            expect(showcaseUrl).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/optimized=true/12345.mp4');
        });
    });

    describe('getThumbnailUrl', () => {
        it('should return thumbnail-optimized URL (width=450)', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg';
            const thumbnailUrl = getThumbnailUrl(originalUrl, 'image');

            expect(thumbnailUrl).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/width=450,optimized=true/12345.jpeg');
        });

        it('should handle videos for thumbnails', () => {
            const originalUrl = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.mp4';
            const thumbnailUrl = getThumbnailUrl(originalUrl, 'video');

            expect(thumbnailUrl).toBe('https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/transcode=true,width=450,optimized=true/12345.mp4');
        });
    });

    describe('isCivitaiUrl', () => {
        it('should return true for CivitAI URLs', () => {
            expect(isCivitaiUrl('https://image.civitai.com/something')).toBe(true);
            expect(isCivitaiUrl('https://image.civitai.com/')).toBe(true);
        });

        it('should return true for CivitAI CDN subdomains', () => {
            expect(isCivitaiUrl('https://image-b2.civitai.com/file/test.png')).toBe(true);
            expect(isCivitaiUrl('https://image-b3.civitai.com/test.jpg')).toBe(true);
            expect(isCivitaiUrl('https://cdn.civitai.com/test.png')).toBe(true);
        });

        it('should return true for CivitAI URLs with explicit ports', () => {
            expect(isCivitaiUrl('https://image.civitai.com:443/test.png')).toBe(true);
            expect(isCivitaiUrl('https://image-b2.civitai.com:443/file/test.jpg')).toBe(true);
        });

        it('should handle case-insensitive hostnames', () => {
            expect(isCivitaiUrl('https://IMAGE.CIVITAI.COM/test.png')).toBe(true);
            expect(isCivitaiUrl('https://Image.Civitai.Com/test.png')).toBe(true);
            expect(isCivitaiUrl('https://image-b2.CIVITAI.com/test.png')).toBe(true);
        });

        it('should return false for non-CivitAI URLs', () => {
            expect(isCivitaiUrl('https://example.com/image.jpg')).toBe(false);
            expect(isCivitaiUrl('https://civitai.com/image.jpg')).toBe(false);
            expect(isCivitaiUrl('')).toBe(false);
            expect(isCivitaiUrl(null)).toBe(false);
            expect(isCivitaiUrl(undefined)).toBe(false);
        });

        it('should handle invalid URLs gracefully', () => {
            expect(isCivitaiUrl('not-a-url')).toBe(false);
        });
    });

    describe('isSupportedCivitaiPageHost', () => {
        it('accepts civitai.com and civitai.red page hosts', () => {
            expect(isSupportedCivitaiPageHost('civitai.com')).toBe(true);
            expect(isSupportedCivitaiPageHost('civitai.red')).toBe(true);
        });

        it('rejects unrelated hosts', () => {
            expect(isSupportedCivitaiPageHost('www.civitai.com')).toBe(false);
            expect(isSupportedCivitaiPageHost('www.civitai.red')).toBe(false);
            expect(isSupportedCivitaiPageHost('example.com')).toBe(false);
            expect(isSupportedCivitaiPageHost('')).toBe(false);
            expect(isSupportedCivitaiPageHost(null)).toBe(false);
        });
    });

    describe('extractCivitaiModelUrlParts', () => {
        it('extracts model and version ids from civitai.red model URLs', () => {
            expect(
                extractCivitaiModelUrlParts('https://civitai.red/models/65423/name?modelVersionId=98765')
            ).toEqual({ modelId: '65423', modelVersionId: '98765' });
        });

        it('rejects model-like URLs from unsupported hosts', () => {
            expect(
                extractCivitaiModelUrlParts('https://example.com/models/65423?modelVersionId=98765')
            ).toEqual({ modelId: null, modelVersionId: null });
        });
    });

    describe('extractCivitaiImageId', () => {
        it('extracts image ids from civitai.red image URLs', () => {
            expect(extractCivitaiImageId('https://civitai.red/images/126920345')).toBe('126920345');
        });

        it('rejects image-like URLs from unsupported hosts', () => {
            expect(extractCivitaiImageId('https://example.com/images/126920345')).toBe(null);
        });
    });
});
