import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const initializeAppMock = vi.fn();
const translateMock = vi.fn((key, _params, fallback) => fallback ?? key);

vi.mock('../../../static/js/core.js', () => ({
    appCore: {
        initialize: initializeAppMock,
    },
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: translateMock,
}));

vi.mock('../../../static/js/utils/formatters.js', () => ({
    formatFileSize: (bytes) => `${bytes} B`,
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

const INFO_RESPONSE = {
    status: 'awaiting_first_scan',
    standalone: false,
    sidecar_storage_mode: 'alongside',
    sidecar_storage_path: '',
    estimated_seconds: 120,
    loras: {
        roots: [
            { path: '/models/loras', exists: true },
            { path: '/models/missing', exists: false },
        ],
        file_count: 42,
        total_bytes: 123456,
    },
    checkpoints: {
        roots: [{ path: '/models/checkpoints', exists: true }],
        file_count: 3,
        total_bytes: 999,
    },
    file_count: 45,
    total_bytes: 124455,
};

function setupDom() {
    document.body.innerHTML = `
        <div id="firstRunContainer">
            <select id="firstRunLanguage">
                <option value="en">English</option>
                <option value="zh-CN">简体中文</option>
            </select>
            <div id="firstRunLibraries"></div>
            <div id="firstRunEstimate" hidden><span id="firstRunEstimateText"></span></div>
            <div id="firstRunNoRoots" hidden><p id="firstRunNoRootsText"></p></div>
            <input type="radio" name="sidecarStorageMode" value="alongside" checked>
            <input type="radio" name="sidecarStorageMode" value="centralized">
            <div id="firstRunSidecarPathRow" hidden><input type="text" id="firstRunSidecarPath"></div>
            <button id="firstRunStart"></button>
            <button id="firstRunDefer"></button>
            <div id="firstRunError" hidden><span id="firstRunErrorText"></span></div>
        </div>
    `;
}

function jsonResponse(payload, ok = true) {
    return Promise.resolve({
        ok,
        json: () => Promise.resolve(payload),
    });
}

describe('FirstRunManager', () => {
    const originalLocation = window.location;
    let reloadMock;
    let fetchMock;
    let firstRunManager;

    beforeEach(async () => {
        vi.resetModules();
        vi.clearAllMocks();
        MockWebSocket.instances = [];
        initializeAppMock.mockResolvedValue(undefined);
        setupDom();

        reloadMock = vi.fn();
        Object.defineProperty(window, 'location', {
            value: {
                ...originalLocation,
                reload: reloadMock,
                host: originalLocation.host,
                protocol: originalLocation.protocol,
            },
            configurable: true,
            writable: true,
        });

        fetchMock = vi.fn().mockImplementation((url) => {
            if (url === '/api/lm/first-run-info') {
                return jsonResponse(INFO_RESPONSE);
            }
            return jsonResponse({ success: true });
        });
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('WebSocket', MockWebSocket);

        ({ firstRunManager } = await import('../../../static/js/components/first_run.js'));
        await firstRunManager.initialize();
    });

    afterEach(() => {
        Object.defineProperty(window, 'location', {
            value: originalLocation,
            configurable: true,
            writable: true,
        });
        vi.unstubAllGlobals();
        document.body.innerHTML = '';
    });

    it('boots the shared app core so theme and header stay consistent', () => {
        expect(initializeAppMock).toHaveBeenCalledTimes(1);
    });

    it('renders library roots and marks missing directories', () => {
        const roots = document.querySelectorAll('#firstRunLibraries .first-run-root');
        expect(roots).toHaveLength(3);
        const missing = document.querySelectorAll('.first-run-root-missing');
        expect(missing).toHaveLength(1);
        expect(missing[0].textContent).toContain('/models/missing');

        const statsCalls = translateMock.mock.calls.filter(([key]) => key === 'firstRun.libraryStats');
        expect(statsCalls).toHaveLength(2);
        expect(statsCalls[0][1]).toEqual({ count: 42, size: '123456 B' });
    });

    it('renders the scan estimate line', () => {
        const estimateEl = document.getElementById('firstRunEstimate');
        expect(estimateEl.hidden).toBe(false);

        const estimateCall = translateMock.mock.calls.find(([key]) => key === 'firstRun.estimate');
        expect(estimateCall).toBeDefined();
        expect(estimateCall[1]).toEqual({ count: 45, size: '124455 B', minutes: 2 });
    });

    it('saves the language choice, marks onboarding language as set, and reloads', async () => {
        const select = document.getElementById('firstRunLanguage');
        select.value = 'zh-CN';
        select.dispatchEvent(new Event('change'));

        await vi.waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1));

        const settingsCall = fetchMock.mock.calls.find(([url]) => url === '/api/lm/settings');
        expect(settingsCall).toBeDefined();
        expect(settingsCall[1].method).toBe('POST');
        expect(JSON.parse(settingsCall[1].body)).toEqual({ language: 'zh-CN' });
        expect(localStorage.getItem('lora_manager_onboarding_language_set')).toBe('true');
    });

    it('starts the scan with the selected sidecar options and reloads', async () => {
        document.querySelector('input[name="sidecarStorageMode"][value="centralized"]').click();
        document.getElementById('firstRunSidecarPath').value = '/central/meta';

        document.getElementById('firstRunStart').click();
        await vi.waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1));

        const startCall = fetchMock.mock.calls.find(([url]) => url === '/api/lm/first-scan/start');
        expect(startCall).toBeDefined();
        expect(startCall[1].method).toBe('POST');
        expect(JSON.parse(startCall[1].body)).toEqual({
            sidecar_storage_mode: 'centralized',
            sidecar_storage_path: '/central/meta',
            defer: false,
        });
    });

    it('defers the scan when the defer button is clicked', async () => {
        document.getElementById('firstRunDefer').click();
        await vi.waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1));

        const startCall = fetchMock.mock.calls.find(([url]) => url === '/api/lm/first-scan/start');
        expect(startCall).toBeDefined();
        expect(JSON.parse(startCall[1].body).defer).toBe(true);
    });

    it('reloads instead of rendering when the scan is no longer awaiting', async () => {
        vi.resetModules();
        fetchMock.mockImplementation(() => jsonResponse({ status: 'completed' }));
        document.getElementById('firstRunLibraries').innerHTML = '';

        const module = await import('../../../static/js/components/first_run.js');
        await module.firstRunManager.initialize();

        expect(reloadMock).toHaveBeenCalledTimes(1);
        expect(document.querySelectorAll('#firstRunLibraries .first-run-library')).toHaveLength(0);
    });

    it('requires a path when centralized storage is selected', async () => {
        document.querySelector('input[name="sidecarStorageMode"][value="centralized"]').click();

        document.getElementById('firstRunStart').click();
        await Promise.resolve();

        const startCall = fetchMock.mock.calls.find(([url]) => url === '/api/lm/first-scan/start');
        expect(startCall).toBeUndefined();
        expect(document.getElementById('firstRunError').hidden).toBe(false);
    });

    it('shows the start error returned by the backend', async () => {
        fetchMock.mockImplementation((url) => {
            if (url === '/api/lm/first-scan/start') {
                return jsonResponse({ success: false, error: 'bad path' }, false);
            }
            return jsonResponse(INFO_RESPONSE);
        });

        document.getElementById('firstRunStart').click();
        await vi.waitFor(() => {
            expect(document.getElementById('firstRunErrorText').textContent).toBe('bad path');
        });
        expect(reloadMock).not.toHaveBeenCalled();
        expect(document.getElementById('firstRunStart').disabled).toBe(false);
    });

    it('shows the no-roots hint and disables start when no valid root exists', async () => {
        vi.resetModules();
        fetchMock.mockImplementation((url) => {
            if (url === '/api/lm/first-run-info') {
                return jsonResponse({
                    ...INFO_RESPONSE,
                    loras: {
                        roots: [{ path: '/missing', exists: false }],
                        file_count: 0,
                        total_bytes: 0,
                    },
                    checkpoints: undefined,
                    file_count: 0,
                    total_bytes: 0,
                });
            }
            return jsonResponse({ success: true });
        });

        const module = await import('../../../static/js/components/first_run.js');
        await module.firstRunManager.initialize();

        expect(document.getElementById('firstRunNoRoots').hidden).toBe(false);
        expect(document.getElementById('firstRunStart').disabled).toBe(true);
    });

    it('reloads when another client starts the scan', () => {
        const socket = MockWebSocket.instances[0];
        expect(socket.url).toBe(`ws://${window.location.host}/ws/init-progress`);

        socket.onmessage({ data: JSON.stringify({ stage: 'scan_started' }) });
        expect(reloadMock).toHaveBeenCalledTimes(1);
    });
});
