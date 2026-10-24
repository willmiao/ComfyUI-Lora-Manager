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
const showCancelButtonMock = vi.fn();
const setProgressMock = vi.fn();
const setStatusMock = vi.fn();
const resetAndReloadMock = vi.fn();
const showWithProgressMock = vi.fn(async (callback) => {
  await callback({
    showCancelButton: showCancelButtonMock,
    setProgress: setProgressMock,
    setStatus: setStatusMock,
  });
});

vi.mock(STATE_MODULE, () => ({
  state: {
    loadingManager: {
      showWithProgress: showWithProgressMock,
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
    endpoints: { fetchAllCivitai: '/api/lm/loras/fetch-all-civitai' },
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

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onerror = null;
    this.onmessage = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.onopen?.();
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

describe('BaseModelApiClient.fetchCivitaiMetadata rate limiting', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    showCancelButtonMock.mockReset();
    setProgressMock.mockReset();
    setStatusMock.mockReset();
    resetAndReloadMock.mockReset();
    showWithProgressMock.mockClear();
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    document.body.innerHTML = '';
  });

  afterEach(() => {
    delete global.fetch;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  function mockFetchPending() {
    let resolveFetch;
    global.fetch = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve; }));
    return {
      resolveOk: (payload = { status: 'success' }) =>
        resolveFetch({ ok: true, json: async () => payload }),
    };
  }

  async function startFetch(client) {
    const promise = client.fetchCivitaiMetadata();
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

  it('settles the operation and shows a summary when the backend aborts on rate limiting', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise, socket } = await startFetch(client);

    expect(socket.url).toBe(`ws://${window.location.host}/ws/fetch-progress`);

    socket.emit({
      status: 'started', total: 10, processed: 0, success: 0,
      failure_count: 0, skipped_count: 0, handled: 0, elapsed_seconds: 0,
    });
    socket.emit({
      status: 'processing', total: 10, processed: 5, success: 4,
      failure_count: 1, skipped_count: 0, handled: 5,
      current_name: 'style.safetensors', elapsed_seconds: 5,
    });
    socket.emit({
      status: 'rate_limited', total: 10, processed: 7, success: 5,
      failure_count: 3, skipped_count: 2, handled: 7, elapsed_seconds: 12,
      failures: [
        { name: 'a.safetensors', error: 'Rate limited' },
        { name: 'b.safetensors', error: 'Rate limited' },
        { name: 'c.safetensors', error: 'Rate limited' },
      ],
    });

    fetchControl.resolveOk();
    // Must resolve: before the fix this promise never settled and the
    // loading overlay stayed up forever.
    await promise;

    const lastStatus = setStatusMock.mock.calls.at(-1)[0];
    expect(lastStatus).toContain('rate limited');
    expect(lastStatus).toContain('5 of 7 LoRAs');
    expect(lastStatus).toContain('3 failed');
    expect(lastStatus).toContain('2 skipped');

    expect(resetAndReloadMock).toHaveBeenCalledWith(false);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.metadataFetchRateLimited',
      { success: 5, total: 10, failed: 3, skipped: 2 },
      'warning'
    );
    expect(socket.close).toHaveBeenCalled();

    const modal = document.getElementById('metadataRefreshResultModal');
    expect(modal).not.toBeNull();
    expect(modal.textContent).toContain('rate limit was reached');
    expect(modal.textContent).toContain('a.safetensors');
  });

  it('does not show the rate-limited toast for a normal completion', async () => {
    const fetchControl = mockFetchPending();
    const client = await createClient();
    const { promise, socket } = await startFetch(client);

    socket.emit({
      status: 'completed', total: 10, processed: 10, success: 10,
      failure_count: 0, skipped_count: 0, handled: 10, elapsed_seconds: 20,
    });

    fetchControl.resolveOk();
    await promise;

    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.metadataFetchRateLimited',
      expect.anything(),
      expect.anything()
    );
    const modal = document.getElementById('metadataRefreshResultModal');
    expect(modal).not.toBeNull();
    expect(modal.textContent).toContain('All 10 LoRAs updated successfully!');
  });
});
