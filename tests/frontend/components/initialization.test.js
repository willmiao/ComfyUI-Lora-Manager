import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../static/js/core.js', () => ({
    appCore: {
        initialize: vi.fn(() => Promise.resolve()),
    },
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getSessionItem: vi.fn(() => null),
    setSessionItem: vi.fn(),
}));

class MockWebSocket {
    static instances = [];
    static OPEN = 1;

    constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.OPEN;
        MockWebSocket.instances.push(this);
    }

    close() {
        this.readyState = 3;
    }
}

function setupDom({ serverError = null } = {}) {
    document.body.innerHTML = `
        <div class="initialization-container" id="initializationContainer">
            <div class="loading-content"${serverError ? ' hidden' : ''}>
                <div class="loading-status" id="progressStatus"></div>
                <div class="init-progress-bar" id="initProgressBar"></div>
                <span id="progressPercentage">0%</span>
                <span id="remainingTime"></span>
            </div>
            <div class="init-error" id="initError"${serverError ? '' : ' hidden'}>
                <p id="initErrorText">${serverError ?? ''}</p>
                <button type="button" id="initRetryBtn"></button>
            </div>
            <div class="tip-item"></div>
            <span class="tip-dot"></span>
        </div>
    `;
}

function jsonResponse(payload) {
    return Promise.resolve({ json: () => Promise.resolve(payload) });
}

describe('InitializationManager', () => {
    let initManager;

    beforeEach(async () => {
        vi.useFakeTimers();
        MockWebSocket.instances = [];
        vi.stubGlobal('WebSocket', MockWebSocket);
        ({ initManager } = await import('../../../static/js/components/initialization.js'));
        initManager.websocket = null;
        initManager.pollingActive = false;
        initManager.progress = 0;
        initManager.pageType = null;
        initManager.tipInterval = null;
    });

    afterEach(() => {
        initManager.cleanup();
        vi.clearAllTimers();
        vi.useRealTimers();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
        document.body.innerHTML = '';
    });

    it('stays on a server-rendered error instead of polling into a reload loop', () => {
        setupDom({ serverError: 'corrupt snapshot' });
        const fetchSpy = vi.fn();
        vi.stubGlobal('fetch', fetchSpy);

        initManager.initialize();

        expect(fetchSpy).not.toHaveBeenCalled();
        expect(MockWebSocket.instances).toHaveLength(0);
        expect(initManager.tipInterval).toBeNull();
    });

    it('scopes the polling fallback to the current page type', () => {
        setupDom();
        initManager.pageType = 'loras';
        const fetchSpy = vi.fn(() => jsonResponse({ status: 'initializing' }));
        vi.stubGlobal('fetch', fetchSpy);

        initManager.pollProgress();

        expect(fetchSpy).toHaveBeenCalledWith('/api/lm/init-status?page=loras');
    });

    it('stops polling when the server reports an error', async () => {
        setupDom();
        initManager.pageType = 'checkpoints';
        const fetchSpy = vi.fn(() =>
            jsonResponse({ status: 'error', details: 'Checkpoint cache initialization failed: boom' })
        );
        vi.stubGlobal('fetch', fetchSpy);

        initManager.pollProgress();
        await vi.advanceTimersByTimeAsync(0);

        // The error state is shown...
        expect(document.getElementById('initError').hidden).toBe(false);
        expect(document.getElementById('initErrorText').textContent)
            .toContain('boom');

        // ...and no further poll is scheduled.
        await vi.advanceTimersByTimeAsync(10000);
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('keeps polling while initialization is in progress', async () => {
        setupDom();
        initManager.pageType = 'loras';
        const fetchSpy = vi.fn(() => jsonResponse({ status: 'initializing' }));
        vi.stubGlobal('fetch', fetchSpy);

        initManager.pollProgress();
        await vi.advanceTimersByTimeAsync(0);
        await vi.advanceTimersByTimeAsync(2000);

        expect(fetchSpy).toHaveBeenCalledTimes(2);
    });
});
