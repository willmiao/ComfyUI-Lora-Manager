import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  BASE_MODEL_API_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  STORAGE_MODULE,
  API_CONFIG_MODULE,
  API_FACTORY_MODULE,
  SIDEBAR_MANAGER_MODULE,
} = vi.hoisted(() => ({
  BASE_MODEL_API_MODULE: new URL('../../../static/js/api/baseModelApi.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();
const showMock = vi.fn();
const showCancelButtonMock = vi.fn();
const hideMock = vi.fn();
const restoreProgressBarMock = vi.fn();
const setProgressMock = vi.fn();
const setStatusMock = vi.fn();
const resetAndReloadMock = vi.fn();

vi.mock(STATE_MODULE, () => ({
  state: {
    loadingManager: {
      show: showMock,
      showCancelButton: showCancelButtonMock,
      hide: hideMock,
      restoreProgressBar: restoreProgressBarMock,
      setProgress: setProgressMock,
      setStatus: setStatusMock,
    },
  },
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => {
    if (fallback) {
      return Object.entries(params || {}).reduce(
        (text, [name, value]) => text.replaceAll(`{${name}}`, value),
        fallback
      );
    }
    return key;
  }),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: vi.fn(),
  getSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
  saveMapToStorage: vi.fn(),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  getCompleteApiConfig: vi.fn(() => ({
    endpoints: { scan: '/api/lm/loras/scan' },
    config: { displayName: 'LoRA', singularName: 'lora' },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  WS_ENDPOINTS: { fetchProgress: '/ws/fetch-progress' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: resetAndReloadMock,
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

class FakeWebSocket {
  static instances = [];
  static failNextConnection = false;

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onerror = null;
    this.onmessage = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    const shouldFail = FakeWebSocket.failNextConnection;
    FakeWebSocket.failNextConnection = false;
    queueMicrotask(() => {
      if (shouldFail) {
        this.onerror?.(new Error('connection refused'));
      } else {
        this.onopen?.();
      }
    });
  }

  emit(data) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

async function createClient() {
  const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
  class TestClient extends BaseModelApiClient {}
  return new TestClient('loras');
}

async function flushMicrotasks() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('BaseModelApiClient.refreshModels scan progress', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    showMock.mockReset();
    showCancelButtonMock.mockReset();
    hideMock.mockReset();
    restoreProgressBarMock.mockReset();
    setProgressMock.mockReset();
    setStatusMock.mockReset();
    resetAndReloadMock.mockReset();
    FakeWebSocket.instances = [];
    FakeWebSocket.failNextConnection = false;
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    delete global.fetch;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function mockFetchPending() {
    let resolveFetch;
    global.fetch = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve; }));
    return {
      resolveOk: (payload = { status: 'success' }) =>
        resolveFetch({ ok: true, json: async () => payload }),
    };
  }

  async function startRefresh(client, fullRebuild = false, options = {}) {
    const promise = client.refreshModels(fullRebuild, options);
    await vi.waitFor(() => {
      expect(FakeWebSocket.instances.length).toBe(1);
    });
    await flushMicrotasks();
    const socket = FakeWebSocket.instances[0];
    await vi.waitFor(() => {
      expect(socket.onmessage).toBeTruthy();
    });
    return { promise, socket };
  }

  it('shows scan progress updates from the WebSocket channel', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise, socket } = await startRefresh(client);

    expect(socket.url).toBe(`ws://${window.location.host}/ws/fetch-progress`);

    socket.emit({
      type: 'scan_progress',
      status: 'started',
      stage: 'scan_folders',
      model_type: 'lora',
      pageType: 'loras',
      full_rebuild: false,
      progress: 0,
    });
    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'process_models',
      model_type: 'lora',
      pageType: 'loras',
      full_rebuild: false,
      progress: 50,
      processed: 5,
      total: 10,
      current_name: 'style.safetensors',
    });

    expect(setProgressMock).toHaveBeenCalledWith(0);
    expect(setProgressMock).toHaveBeenCalledWith(50);
    const lastStatus = setStatusMock.mock.calls.at(-1)[0];
    expect(lastStatus).toContain('(5/10)');
    expect(lastStatus).toContain('style.safetensors');
    // First ETA sample only anchors the timer
    expect(lastStatus).toContain('Estimating time...');

    fetchControl.resolveOk();
    await promise;

    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      { action: 'Refresh' },
      'success'
    );
    expect(socket.close).toHaveBeenCalled();
    expect(hideMock).toHaveBeenCalled();
  });

  it('ignores messages for other types or other model types', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise, socket } = await startRefresh(client);

    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'process_models',
      model_type: 'checkpoint',
      progress: 33,
      processed: 1,
      total: 3,
    });
    socket.emit({
      type: 'example_images_progress',
      status: 'running',
      model_type: 'lora',
      progress: 66,
      processed: 2,
      total: 3,
    });

    expect(setProgressMock).not.toHaveBeenCalled();
    expect(setStatusMock).not.toHaveBeenCalled();

    fetchControl.resolveOk();
    await promise;
  });

  it('falls back to plain loading when the WebSocket connection fails', async () => {
    FakeWebSocket.failNextConnection = true;
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success' }),
    });

    const client = await createClient();
    await client.refreshModels(true);

    expect(global.fetch).toHaveBeenCalled();
    const [url] = global.fetch.mock.calls[0];
    expect(url.searchParams.get('full_rebuild')).toBe('true');
    expect(showMock).toHaveBeenCalledWith('Full rebuild LoRAs...', 0);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      { action: 'Full rebuild' },
      'success'
    );
  });

  it('computes an ETA with EMA smoothing once enough samples arrive', async () => {
    const fetchControl = mockFetchPending();
    let now = 1000;
    vi.spyOn(Date, 'now').mockImplementation(() => now);

    const client = await createClient();
    const { promise, socket } = await startRefresh(client);

    const emitProcessing = (processed, total) => socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'process_models',
      model_type: 'lora',
      progress: Math.floor((processed / total) * 100),
      processed,
      total,
    });

    // First sample anchors the timer
    emitProcessing(1, 10);
    expect(setStatusMock.mock.calls.at(-1)[0]).toContain('Estimating time...');

    // 100s elapsed for 2 files -> 50s per file -> 400s remaining -> ~7 min
    now = 101000;
    emitProcessing(2, 10);
    expect(setStatusMock.mock.calls.at(-1)[0]).toContain('~7 min remaining');

    // 110s elapsed for 4 files -> EMA = 50000*0.7 + 27500*0.3 = 43250ms/file
    // remaining 6 files -> 259.5s -> ~4 min
    now = 111000;
    emitProcessing(4, 10);
    expect(setStatusMock.mock.calls.at(-1)[0]).toContain('~4 min remaining');

    fetchControl.resolveOk();
    await promise;
  });

  it('shows the walked roots and file count during the reconcile walk', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise, socket } = await startRefresh(client);

    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'reconcile_scan',
      model_type: 'lora',
      pageType: 'loras',
      full_rebuild: false,
      progress: 12,
      processed: 1234,
      total: 2000,
      files_seen: 1234,
      roots_total: 3,
      roots_done: 0,
      active_roots: ['G:', 'Y:'],
      current_name: 'G:',
    });

    expect(setProgressMock).toHaveBeenCalledWith(12);
    const walkStatus = setStatusMock.mock.calls.at(-1)[0];
    expect(walkStatus).toContain('G:, Y:');
    expect(walkStatus).toContain('1,234 files');
    // No processed/total ratio: the real file count is unknown mid-walk.
    expect(walkStatus).not.toContain('(1234/2000)');
    expect(walkStatus).toContain('Estimating time...');

    // Walk finished: no ETA once the counters meet the estimate.
    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'reconcile_scan',
      model_type: 'lora',
      full_rebuild: false,
      progress: 50,
      processed: 2000,
      total: 2000,
      files_seen: 2000,
      active_roots: [],
      current_name: 'Y:',
    });

    const finalWalkStatus = setStatusMock.mock.calls.at(-1)[0];
    expect(finalWalkStatus).toContain('2,000 files');
    expect(finalWalkStatus).not.toContain('Estimating time...');

    fetchControl.resolveOk();
    await promise;
  });

  it('drops the ETA samples when the scan moves to another stage', async () => {
    const fetchControl = mockFetchPending();
    let now = 1000;
    vi.spyOn(Date, 'now').mockImplementation(() => now);

    const client = await createClient();
    const { promise, socket } = await startRefresh(client);

    const emit = (stage, processed, total, extra = {}) => socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage,
      model_type: 'lora',
      full_rebuild: false,
      progress: 50,
      processed,
      total,
      ...extra,
    });

    emit('process_models', 1, 10);
    now = 101000;
    emit('process_models', 2, 10);
    expect(setStatusMock.mock.calls.at(-1)[0]).toContain('~7 min remaining');

    // Same counters on the walk stage: without the reset the old per-file rate
    // (50s/file for 2 files) would be reused and produce a huge ETA.
    now = 102000;
    emit('reconcile_scan', 2, 100, { files_seen: 2, active_roots: ['G:'] });
    expect(setStatusMock.mock.calls.at(-1)[0]).toContain('Estimating time...');

    fetchControl.resolveOk();
    await promise;
  });

  it('requests a scoped scan when roots are passed', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success' }),
    });

    const client = await createClient();
    await client.refreshModels(false, { roots: ['/mnt/a/loras', '/mnt/b/loras'] });

    const [url] = global.fetch.mock.calls[0];
    expect(url.searchParams.getAll('roots')).toEqual(['/mnt/a/loras', '/mnt/b/loras']);
    expect(url.searchParams.get('full_rebuild')).toBe('false');
  });

  it('reports the scoped scan summary and the entries kept unreachable', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise } = await startRefresh(client, false, { roots: ['/mnt/a/loras'] });

    fetchControl.resolveOk({
      status: 'success',
      scanned_roots: ['a/loras'],
      added: 2,
      removed: 1,
      kept_unreachable: 5,
      unavailable_paths: [
        { path: '/mnt/g/loras', reason: 'root_unreachable', kept: 5 },
      ],
      skipped_roots: [{ path: '/mnt/g/loras', label: 'g/loras' }],
    });
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshCompleteScoped',
      { scope: 'a/loras', added: 2, removed: 1 },
      'success'
    );
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshKeptUnreachable',
      { count: '5', paths: 'g/loras' },
      'info'
    );
  });

  it('requests a folder scan without a root', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'success' }),
    });

    const client = await createClient();
    await client.refreshModels(false, { folder: 'pack/sub' });

    const [url] = global.fetch.mock.calls[0];
    // The backend walks this relative path under every root that holds it.
    expect(url.searchParams.get('folder')).toBe('pack/sub');
    expect(url.searchParams.getAll('roots')).toEqual([]);
  });

  it('names a folder scan by the folder, not by the roots it walked', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise } = await startRefresh(client, false, { folder: 'pack' });

    fetchControl.resolveOk({
      status: 'success',
      scope_label: 'pack',
      scanned_roots: ['a/loras', 'usb/loras'],
      added: 3,
      removed: 0,
      kept_unreachable: 0,
    });
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshCompleteScoped',
      { scope: 'pack', added: 3, removed: 0 },
      'success'
    );
  });

  it('keeps the generic completion toast for a full-library scan', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise } = await startRefresh(client);

    fetchControl.resolveOk({
      status: 'success',
      scanned_roots: ['a/loras', 'b/loras'],
      added: 0,
      removed: 0,
    });
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      { action: 'Refresh' },
      'success'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.refreshCompleteScoped',
      expect.anything(),
      expect.anything()
    );
  });

  it('shows the cancelled toast when the server reports cancellation', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise } = await startRefresh(client);

    fetchControl.resolveOk({ status: 'cancelled' });
    await promise;

    expect(showToastMock).toHaveBeenCalledWith('toast.api.operationCancelled', {}, 'info');
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });
});

describe('createScanEtaTracker / formatScanRemainingTime', () => {
  it('estimates remaining time from EMA of per-file cost', async () => {
    const { createScanEtaTracker } = await import(BASE_MODEL_API_MODULE);
    let now = 0;
    vi.spyOn(Date, 'now').mockImplementation(() => now);

    const tracker = createScanEtaTracker();
    expect(tracker.update(1, 10)).toBe('Estimating time...');

    now = 60000; // 60s for 3 files -> 20s/file -> 7 * 20s = 140s -> ~2 min
    expect(tracker.update(3, 10)).toBe('~2 min remaining');

    now = 61000; // tiny delta keeps EMA near 20s/file
    expect(tracker.update(4, 10)).toBe('~2 min remaining');

    // Done: no ETA
    expect(tracker.update(10, 10)).toBeNull();
    expect(tracker.update(0, 0)).toBeNull();

    vi.restoreAllMocks();
  });

  it('formats hours and sub-minute remainders', async () => {
    const { formatScanRemainingTime } = await import(BASE_MODEL_API_MODULE);
    expect(formatScanRemainingTime(30000)).toBe('Less than a minute remaining');
    expect(formatScanRemainingTime(5 * 60000)).toBe('~5 min remaining');
    expect(formatScanRemainingTime(3600000 + 30 * 60000)).toBe('~1 hr 30 min remaining');
  });
});
