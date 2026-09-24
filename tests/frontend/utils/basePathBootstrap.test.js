import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');

const extractBootstrapScript = () => {
    const html = readFileSync(
        resolve(repoRoot, 'templates/components/base_path_bootstrap.html'),
        'utf8',
    );
    const match = html.match(/<script>([\s\S]*?)<\/script>/);
    if (!match) {
        throw new Error('bootstrap <script> block not found');
    }
    return match[1];
};

const PATCHED_PROTOS = () => [
    [Element.prototype, ['innerHTML', 'outerHTML']],
    [HTMLImageElement.prototype, ['src']],
    [HTMLMediaElement.prototype, ['src']],
    [HTMLSourceElement.prototype, ['src']],
    [HTMLVideoElement.prototype, ['poster']],
    [HTMLAnchorElement.prototype, ['href']],
    [HTMLScriptElement.prototype, ['src']],
    [HTMLLinkElement.prototype, ['href']],
];

describe('base_path_bootstrap.html', () => {
    let savedGlobals;
    let savedDescriptors;
    let savedMethods;

    beforeEach(() => {
        savedGlobals = {
            fetch: window.fetch,
            WebSocket: window.WebSocket,
        };
        savedDescriptors = PATCHED_PROTOS().flatMap(([proto, props]) =>
            props.map((prop) => [proto, prop, Object.getOwnPropertyDescriptor(proto, prop)]),
        );
        savedMethods = {
            xhrOpen: XMLHttpRequest.prototype.open,
            insertAdjacentHTML: Element.prototype.insertAdjacentHTML,
            setAttribute: Element.prototype.setAttribute,
        };
    });

    afterEach(() => {
        window.fetch = savedGlobals.fetch;
        window.WebSocket = savedGlobals.WebSocket;
        for (const [proto, prop, desc] of savedDescriptors) {
            if (desc) {
                Object.defineProperty(proto, prop, desc);
            }
        }
        XMLHttpRequest.prototype.open = savedMethods.xhrOpen;
        Element.prototype.insertAdjacentHTML = savedMethods.insertAdjacentHTML;
        Element.prototype.setAttribute = savedMethods.setAttribute;
        delete window.LM_BASE_PATH;
        delete window.lmWithBasePath;
        window.history.replaceState({}, '', '/');
    });

    const runBootstrap = (pathname) => {
        window.history.replaceState({}, '', pathname);
        (0, eval)(extractBootstrapScript());
    };

    it('detects no prefix for root-mounted pages and patches nothing', () => {
        const nativeFetch = window.fetch;
        runBootstrap('/loras');
        expect(window.LM_BASE_PATH).toBe('');
        expect(window.fetch).toBe(nativeFetch);

        runBootstrap('/');
        expect(window.LM_BASE_PATH).toBe('');
    });

    it.each([
        ['/comfyui/loras', '/comfyui'],
        ['/comfyui/loras/', '/comfyui'],
        ['/comfyui/loras/recipes', '/comfyui'],
        ['/comfyui/checkpoints', '/comfyui'],
        ['/comfyui/embeddings', '/comfyui'],
        ['/comfyui/other', '/comfyui'],
        ['/comfyui/statistics', '/comfyui'],
        ['/ComfyBackendDirect/loras', '/ComfyBackendDirect'],
        ['/proxy/nested/loras', '/proxy/nested'],
    ])('detects prefix for %s', (pathname, expected) => {
        runBootstrap(pathname);
        expect(window.LM_BASE_PATH).toBe(expected);
    });

    it('does not mistake similar paths for manager pages', () => {
        runBootstrap('/comfyui/lorasgallery');
        expect(window.LM_BASE_PATH).toBe('');
        runBootstrap('/comfyui/foo-loras');
        expect(window.LM_BASE_PATH).toBe('');
    });

    it('prefixes root-absolute fetch URLs only', async () => {
        const fetchSpy = vi.fn().mockResolvedValue({ ok: true });
        window.fetch = fetchSpy;
        runBootstrap('/comfyui/loras');

        await window.fetch('/api/lm/loras/list');
        await window.fetch('/loras_static/images/no-preview.png');
        await window.fetch('https://civitai.com/api/v1/models');
        await window.fetch('//cdn.example.com/x.js');
        await window.fetch('relative/path');

        expect(fetchSpy.mock.calls.map((call) => call[0])).toEqual([
            '/comfyui/api/lm/loras/list',
            '/comfyui/loras_static/images/no-preview.png',
            'https://civitai.com/api/v1/models',
            '//cdn.example.com/x.js',
            'relative/path',
        ]);
    });

    it('prefixes same-origin absolute fetch URLs', async () => {
        const fetchSpy = vi.fn().mockResolvedValue({ ok: true });
        window.fetch = fetchSpy;
        runBootstrap('/comfyui/loras');

        const absolute = `${window.location.origin}/api/lm/init-status`;
        await window.fetch(absolute);
        expect(fetchSpy).toHaveBeenCalledWith(
            `${window.location.origin}/comfyui/api/lm/init-status`,
            undefined,
        );
    });

    it('prefixes fetch() called with a URL object', async () => {
        const fetchSpy = vi.fn().mockResolvedValue({ ok: true });
        window.fetch = fetchSpy;
        runBootstrap('/comfyui/loras');

        await window.fetch(new URL('/api/lm/base-models', window.location.origin));
        expect(fetchSpy).toHaveBeenCalledWith(
            `${window.location.origin}/comfyui/api/lm/base-models`,
            undefined,
        );

        await window.fetch(new URL('https://civitai.com/api/v1/models'));
        expect(fetchSpy).toHaveBeenLastCalledWith('https://civitai.com/api/v1/models', undefined);
    });

    it('prefixes WebSocket URLs', () => {
        const constructed = [];
        class FakeWebSocket {
            constructor(url, protocols) {
                constructed.push([url, protocols]);
            }
        }
        FakeWebSocket.CONNECTING = 0;
        FakeWebSocket.OPEN = 1;
        FakeWebSocket.CLOSING = 2;
        FakeWebSocket.CLOSED = 3;
        window.WebSocket = FakeWebSocket;

        runBootstrap('/comfyui/loras');

        new window.WebSocket('/ws/fetch-progress');
        new window.WebSocket('wss://other.example.com/socket', ['a']);
        expect(constructed).toEqual([
            ['/comfyui/ws/fetch-progress', undefined],
            ['wss://other.example.com/socket', ['a']],
        ]);
    });

    it('rewrites root-absolute URLs inside innerHTML markup', () => {
        runBootstrap('/comfyui/loras');

        const container = document.createElement('div');
        container.innerHTML = `<img src="/api/lm/previews?path=x" onerror="this.src='/loras_static/images/no-preview.png'">`
            + `<a href="/api/lm/download-model/1">dl</a>`
            + `<video poster="/loras_static/p.png"><source src="/example_images_static/a/b.mp4"></video>`;

        const html = container.innerHTML;
        expect(html).toContain('src="/comfyui/api/lm/previews?path=x"');
        expect(html).toContain("this.src='/comfyui/loras_static/images/no-preview.png'");
        expect(html).toContain('href="/comfyui/api/lm/download-model/1"');
        expect(html).toContain('poster="/comfyui/loras_static/p.png"');
        expect(html).toContain('src="/comfyui/example_images_static/a/b.mp4"');
    });

    it('does not double-prefix markup that already carries the prefix', () => {
        runBootstrap('/comfyui/loras');

        const container = document.createElement('div');
        container.innerHTML = '<img src="/api/lm/previews?path=x">';
        const once = container.innerHTML;
        container.innerHTML = once;
        expect(container.innerHTML).toBe(once);
        expect(once).not.toContain('/comfyui/comfyui/');
    });

    it('prefixes direct DOM URL assignments', () => {
        runBootstrap('/comfyui/loras');

        const img = document.createElement('img');
        img.src = '/loras_static/images/no-preview.png';
        expect(img.getAttribute('src')).toBe('/comfyui/loras_static/images/no-preview.png');

        const anchor = document.createElement('a');
        anchor.setAttribute('href', '/api/lm/download-model/1');
        expect(anchor.getAttribute('href')).toBe('/comfyui/api/lm/download-model/1');

        const video = document.createElement('video');
        video.poster = '/loras_static/p.png';
        expect(video.getAttribute('poster')).toBe('/comfyui/loras_static/p.png');
    });
});
