import { describe, it, expect } from 'vitest';
import {
    VIDEO_EXTENSIONS,
    extractMediaExtension,
    getPreviewMediaExtension,
    isVideoPreviewUrl,
} from '../../../static/js/utils/mediaTypes.js';

// Regression fixture for issue #1168: the preview URL is versioned with the
// file's mtime, so it no longer ends with the media extension.
const VERSIONED_VIDEO = '/api/lm/previews?path=%2Fhome%2Fmodels%2Fstyle%2Ffoo.mp4&v=1781613851611650515';

describe('extractMediaExtension', () => {
    it('reads the extension of a plain path', () => {
        expect(extractMediaExtension('/models/style/foo.mp4')).toBe('.mp4');
    });

    it('ignores the query string of a URL', () => {
        expect(extractMediaExtension('https://image.civitai.com/x/123.mp4?width=450')).toBe('.mp4');
        expect(extractMediaExtension('/api/lm/previews?path=x&v=1')).toBe('');
    });

    it('decodes percent-encoded paths', () => {
        expect(extractMediaExtension('%2Fhome%2Fmodels%2Ffoo.WEBM')).toBe('.webm');
    });

    it('rejects dots that belong to a directory name', () => {
        expect(extractMediaExtension('/home/user.name/preview')).toBe('');
    });

    it('returns an empty string when there is no extension', () => {
        expect(extractMediaExtension('/api/lm/previews')).toBe('');
        expect(extractMediaExtension('')).toBe('');
        expect(extractMediaExtension(null)).toBe('');
    });
});

describe('getPreviewMediaExtension', () => {
    it('resolves the encoded path parameter of a versioned preview URL', () => {
        expect(getPreviewMediaExtension(VERSIONED_VIDEO)).toBe('.mp4');
    });

    it('resolves image previews', () => {
        expect(getPreviewMediaExtension('/api/lm/previews?path=%2Fhome%2Fmodels%2Ffoo.jpeg&v=1')).toBe('.jpeg');
    });

    it('returns an empty string for missing or non-string values', () => {
        expect(getPreviewMediaExtension('')).toBe('');
        expect(getPreviewMediaExtension(null)).toBe('');
        expect(getPreviewMediaExtension(42)).toBe('');
    });
});

describe('isVideoPreviewUrl', () => {
    it('detects versioned mp4 previews', () => {
        expect(isVideoPreviewUrl(VERSIONED_VIDEO)).toBe(true);
    });

    it('detects webm previews behind the preview endpoint', () => {
        expect(isVideoPreviewUrl('/api/lm/previews?path=%2Fhome%2Fmodels%2Ffoo.webm&v=1')).toBe(true);
    });

    it('detects plain paths and remote URLs', () => {
        expect(isVideoPreviewUrl('/home/models/foo.mp4')).toBe(true);
        expect(isVideoPreviewUrl('https://image.civitai.com/x/123.mp4?width=450')).toBe(true);
    });

    it('does not treat image previews as videos', () => {
        expect(isVideoPreviewUrl('/api/lm/previews?path=%2Fhome%2Fmodels%2Ffoo.jpeg&v=1781613851611650515')).toBe(false);
        expect(isVideoPreviewUrl('/loras_static/images/no-preview.png')).toBe(false);
    });

    it('does not read a fractional version parameter as an extension', () => {
        expect(isVideoPreviewUrl('/api/lm/previews?path=%2Fhome%2Fmodels%2Ffoo.jpeg&v=1.5')).toBe(false);
    });

    it('handles empty or invalid input', () => {
        expect(isVideoPreviewUrl('')).toBe(false);
        expect(isVideoPreviewUrl(null)).toBe(false);
        expect(isVideoPreviewUrl(undefined)).toBe(false);
    });

    it('recognises the supported video extensions', () => {
        expect(VIDEO_EXTENSIONS).toEqual(expect.arrayContaining(['.mp4', '.webm']));
    });
});
