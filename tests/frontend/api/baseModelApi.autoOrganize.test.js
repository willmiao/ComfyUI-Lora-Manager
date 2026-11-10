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
const showWithProgressMock = vi.fn(async (callback) => {
  await callback({
    showCancelButton: showCancelButtonMock,
    setProgress: setProgressMock,
    setStatus: setStatusMock,
  });
});

vi.mock(STATE_MODULE, () => ({
  state: {
    global: { settings: { auto_organize_exclusions: [] } },
    loadingManager: { showWithProgress: showWithProgressMock },
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
    endpoints: { autoOrganize: '/api/lm/loras/auto-organize' },
    config: { displayName: 'LoRA', singularName: 'LoRA' },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  WS_ENDPOINTS: { fetchProgress: '/ws/fetch-progress' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

class FakeWebSocket {
  static instances = [];
  static failOnConnect = false;
  static OPEN = 1;

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.onerror = null;
    this.onmessage = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    if (FakeWebSocket.failOnConnect) {
      queueMicrotask(() => this.onerror?.(new Event('error')));
    }
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

describe('BaseModelApiClient.autoOrganizeModels progress fallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeWebSocket.instances = [];
    FakeWebSocket.failOnConnect = false;
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    delete global.fetch;
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('uses the completed REST result when the progress socket fails', async () => {
    FakeWebSocket.failOnConnect = true;
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        status: 'success',
        summary: {
          total: 1,
          success: 1,
          skipped: 0,
          failures: 0,
          operation_type: 'bulk',
        },
      }),
    });
    const client = await createClient();

    await expect(client.autoOrganizeModels(['/models/old.safetensors'])).resolves.toBeUndefined();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.autoOrganizeProgressUnavailable',
      { success: 1, failures: 0, total: 1 },
      'warning'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.loras.autoOrganizeFailed',
      expect.anything(),
      'error'
    );
  });

  it('keeps using the WebSocket result when progress is available', async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
    const client = await createClient();
    const promise = client.autoOrganizeModels(['/models/old.safetensors']);
    const socket = FakeWebSocket.instances[0];

    socket.emit({
      type: 'auto_organize_progress',
      status: 'completed',
      success: 2,
      failures: 0,
      total: 2,
      operation_type: 'bulk',
    });
    await vi.advanceTimersByTimeAsync(1500);
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.autoOrganizeSuccess',
      { count: 2, type: 'selected models' },
      'success'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.loras.autoOrganizeProgressUnavailable',
      expect.anything(),
      'warning'
    );
  });

  it('still reports a REST failure as an operation failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'Backend failed' }),
    });
    const client = await createClient();

    await expect(client.autoOrganizeModels()).rejects.toThrow('Backend failed');

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.autoOrganizeFailed',
      { error: 'Backend failed' },
      'error'
    );
  });
});
