import { describe, it, expect } from 'vitest';

import { resolveExampleMedia, findLocalFile } from
    '../../../static/js/components/shared/showcase/exampleMediaResolver.js';

const LOCAL_FILES = [
    { name: 'image_0.webp', path: '/example_images_static/hash/image_0.webp', is_video: false },
    { name: 'image_1.mp4', path: '/example_images_static/hash/image_1.mp4', is_video: true },
    { name: 'custom_a1.webp', path: '/example_images_static/hash/custom_a1.webp', is_video: false },
];

describe('exampleMediaResolver', () => {
    it('pairs CivitAI entries with their local file by position', () => {
        expect(findLocalFile({ url: 'https://x/1.jpeg' }, 0, LOCAL_FILES))
            .toBe(LOCAL_FILES[0]);
        expect(findLocalFile({ url: 'https://x/2.mp4', type: 'video' }, 1, LOCAL_FILES))
            .toBe(LOCAL_FILES[1]);
        // A position with no downloaded file is not paired with a neighbour.
        expect(findLocalFile({ url: 'https://x/9.jpeg' }, 9, LOCAL_FILES)).toBeNull();
    });

    it('pairs custom entries with custom_<id> rather than by position', () => {
        expect(findLocalFile({ id: 'a1', url: '' }, 0, LOCAL_FILES)).toBe(LOCAL_FILES[2]);
    });

    it('prefers the downloaded local copy over the remote URL', () => {
        const resolved = resolveExampleMedia(
            { url: 'https://image.civitai.com/x/original=true/1.jpeg' },
            0,
            LOCAL_FILES
        );
        expect(resolved.localFile).toBe(LOCAL_FILES[0]);
        // Downloaded entries keep their CivitAI url in the sidecar, so this is
        // the case that used to send the card cycler to the CDN.
        expect(resolved.url).toBe('/example_images_static/hash/image_0.webp');
        expect(resolved.isVideo).toBe(false);
    });

    it('falls back to the remote URL when nothing was downloaded', () => {
        const resolved = resolveExampleMedia(
            { url: 'https://image.civitai.com/x/original=true/7.jpeg' },
            7,
            LOCAL_FILES
        );
        expect(resolved.localFile).toBeNull();
        expect(resolved.url).toBe('https://image.civitai.com/x/original=true/7.jpeg');
    });

    it('reports the local file as the video source when it is one', () => {
        const resolved = resolveExampleMedia({ url: '', id: 'v1' }, 0, [
            { name: 'custom_v1.mp4', path: '/example_images_static/hash/custom_v1.mp4', is_video: true },
        ]);
        expect(resolved.isVideo).toBe(true);
        expect(resolved.url).toContain('custom_v1.mp4');
    });

    it('resolves to an empty url when there is no local file and no remote URL', () => {
        const resolved = resolveExampleMedia({ nsfwLevel: 0 }, 3, []);
        expect(resolved.localFile).toBeNull();
        expect(resolved.url).toBe('');
        expect(resolved.isVideo).toBe(false);
    });
});
