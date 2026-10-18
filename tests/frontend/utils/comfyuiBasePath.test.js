import { describe, it, expect, afterEach } from 'vitest';

import { getComfyUIBasePath, lmUrl } from '../../../web/comfyui/base_path.js';

describe('web/comfyui/base_path.js', () => {
    afterEach(() => {
        window.history.replaceState({}, '', '/');
    });

    it.each([
        ['/', ''],
        ['/comfyui/', '/comfyui'],
        ['/comfyui', '/comfyui'],
        ['/ComfyBackendDirect/', '/ComfyBackendDirect'],
    ])('maps %s to base path %s', (pathname, expected) => {
        window.history.replaceState({}, '', pathname);
        expect(getComfyUIBasePath()).toBe(expected);
    });

    it('builds prefixed URLs', () => {
        window.history.replaceState({}, '', '/comfyui/');
        expect(lmUrl('/api/lm/version-info')).toBe('/comfyui/api/lm/version-info');
        expect(lmUrl('/loras')).toBe('/comfyui/loras');

        window.history.replaceState({}, '', '/');
        expect(lmUrl('/api/lm/version-info')).toBe('/api/lm/version-info');
    });
});
