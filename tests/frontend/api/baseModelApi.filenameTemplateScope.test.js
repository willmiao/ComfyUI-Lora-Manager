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
    global: { settings: {} },
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
    endpoints: { applyFilenameTemplate: '/api/lm/loras/apply-filename-template' },
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
  static OPEN = 1;

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.onerror = null;
    this.onmessage = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
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

describe('BaseModelApiClient.previewFilenameTemplate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    delete global.fetch;
  });

  it('requests a dry run for the given file selection without progress UI', async () => {
    const payload = {
      success: true,
      dry_run: true,
      summary: { total: 2, success: 2, skipped: 0, failures: 0 },
      planned_moves: [{ model: 'A', from: '/a.st', to: '/A.st' }],
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    const client = await createClient();

    await expect(
      client.previewFilenameTemplate({ filePaths: ['/a.st', '/b.st'] })
    ).resolves.toBe(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/apply-filename-template',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: true, file_paths: ['/a.st', '/b.st'] }),
      }
    );
    expect(showWithProgressMock).not.toHaveBeenCalled();
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it('sends absolute folder scopes for a folder dry run', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary: {} }) });
    const client = await createClient();

    await client.previewFilenameTemplate({
      folderPaths: ['/models/loras/random', '/other/loras/random'],
    });

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/apply-filename-template',
      expect.objectContaining({
        body: JSON.stringify({
          dry_run: true,
          folder_paths: ['/models/loras/random', '/other/loras/random'],
        }),
      })
    );
  });

  it('surfaces backend rejections to the caller', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'Another library operation is already running.' }),
    });
    const client = await createClient();

    await expect(client.previewFilenameTemplate({ filePaths: ['/a.st'] })).rejects.toThrow(
      'Another library operation is already running.'
    );
  });
});

describe('BaseModelApiClient.applyFilenameTemplate scoped apply', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
  });

  afterEach(() => {
    delete global.fetch;
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  async function runApply(client, args) {
    vi.useFakeTimers();
    const promise = client.applyFilenameTemplate(...args);
    const socket = FakeWebSocket.instances[0];
    expect(socket).toBeDefined();
    socket.emit({
      type: 'filename_template_progress',
      status: 'started',
      total: 2,
      processed: 0,
      success: 0,
      skipped: 0,
      failures: 0,
    });
    socket.emit({
      type: 'filename_template_progress',
      status: 'completed',
      total: 2,
      processed: 2,
      success: 2,
      skipped: 0,
      failures: 0,
    });
    await vi.advanceTimersByTimeAsync(1500);
    await promise;
  }

  it('posts folder_paths and reports the folder as the scope', async () => {
    const client = await createClient();

    await runApply(client, [null, { folderPaths: ['/models/loras/random'] }]);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/apply-filename-template',
      expect.objectContaining({
        body: JSON.stringify({ folder_paths: ['/models/loras/random'] }),
      })
    );
    expect(setStatusMock).toHaveBeenCalledWith('Applying filename template to this folder...');
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateScopedSuccess',
      { count: 2 },
      'success'
    );
  });

  it('posts file_paths and reports the selection as the scope', async () => {
    const client = await createClient();

    await runApply(client, [['/models/loras/a.safetensors']]);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/apply-filename-template',
      expect.objectContaining({
        body: JSON.stringify({ file_paths: ['/models/loras/a.safetensors'] }),
      })
    );
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateScopedSuccess',
      { count: 2 },
      'success'
    );
  });

  it('keeps the library-wide wording when no scope is given', async () => {
    const client = await createClient();

    await runApply(client, []);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/apply-filename-template',
      expect.objectContaining({ body: JSON.stringify({}) })
    );
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.loras.filenameTemplateSuccess',
      { count: 2, type: 'all models' },
      'success'
    );
  });
});
