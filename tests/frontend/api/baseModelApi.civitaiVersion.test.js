import { describe, it, afterEach, expect, vi } from 'vitest';

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
  BASE_MODEL_API_MODULE: new URL('../../../static/js/api/baseModelApi.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
}));

vi.mock(STATE_MODULE, () => ({
  state: {},
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key) => key),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: vi.fn(),
  getSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
  saveMapToStorage: vi.fn(),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  getCompleteApiConfig: vi.fn(() => ({
    endpoints: { civitaiModelByVersion: '/api/lm/loras/civitai/model/version' },
    config: { displayName: 'LoRA', singularName: 'LoRA' },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  MODEL_SOURCE_ENDPOINTS: {},
  WS_ENDPOINTS: {},
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));


describe('Civitai version lookup for download URLs', () => {
  afterEach(() => vi.unstubAllGlobals());

  async function createClient() {
    const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
    class TestClient extends BaseModelApiClient {}
    return new TestClient('loras');
  }

  it('uses the version endpoint and returns the parent model ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ id: 3409322, modelId: 123 }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = await createClient();
    await expect(client.fetchCivitaiModelByVersion('3409322')).resolves.toEqual({ id: 3409322, modelId: 123 });
    expect(fetchMock).toHaveBeenCalledWith('/api/lm/loras/civitai/model/version/3409322');
  });

  it('preserves the API error message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, json: async () => ({ error: 'Version not found' }),
    }));
    const client = await createClient();
    await expect(client.fetchCivitaiModelByVersion('3409322')).rejects.toThrow('Version not found');
  });

  it('handles non-JSON error responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, json: async () => { throw new SyntaxError('not JSON'); },
    }));
    const client = await createClient();
    await expect(client.fetchCivitaiModelByVersion('3409322')).rejects.toThrow('Failed to fetch model version');
  });

  it('exposes the version endpoint for every model category', async () => {
    const { getApiEndpoints } = await vi.importActual(API_CONFIG_MODULE);
    for (const type of ['loras', 'checkpoints', 'embeddings', 'other']) {
      expect(getApiEndpoints(type).civitaiModelByVersion).toBe(`/api/lm/${type}/civitai/model/version`);
    }
  });
});
