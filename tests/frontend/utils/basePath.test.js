import { describe, it, expect, afterEach } from 'vitest';

import { getBasePath, withBasePath } from '../../../static/js/utils/basePath.js';

describe('static/js/utils/basePath.js', () => {
    afterEach(() => {
        delete window.LM_BASE_PATH;
    });

    it('returns empty base path when bootstrap did not set one', () => {
        expect(getBasePath()).toBe('');
        expect(withBasePath('/loras')).toBe('/loras');
    });

    it('prepends the detected base path', () => {
        window.LM_BASE_PATH = '/comfyui';
        expect(getBasePath()).toBe('/comfyui');
        expect(withBasePath('/loras')).toBe('/comfyui/loras');
        expect(withBasePath('/loras/recipes')).toBe('/comfyui/loras/recipes');
    });
});
