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
const updateSingleItemMock = vi.fn();
const showSimpleLoadingMock = vi.fn();
const hideMock = vi.fn();
const restoreProgressBarMock = vi.fn();
const fetchMock = vi.fn();

vi.mock(STATE_MODULE, () => ({
  state: {
    loadingManager: {
      showSimpleLoading: showSimpleLoadingMock,
      hide: hideMock,
      restoreProgressBar: restoreProgressBarMock,
    },
    virtualScroller: {
      updateSingleItem: updateSingleItemMock,
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
    endpoints: { fetchCivitai: '/api/lm/checkpoints/fetch-civitai' },
    config: { displayName: 'Checkpoint', singularName: 'checkpoint' },
  })),
  getCurrentModelType: vi.fn(() => 'checkpoints'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  MODEL_SOURCE_ENDPOINTS: {},
  WS_ENDPOINTS: { fetchProgress: '/ws/fetch-progress' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

const FILE_PATH = 'Z:/Civitai_files/Sorted/checkpoints/GoodSoup_Q8.gguf';
const SHA256 = 'a'.repeat(64);

function jsonResponse(payload, ok = true) {
  return {
    ok,
    json: vi.fn().mockResolvedValue(payload),
  };
}

async function createClient() {
  const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
  class TestClient extends BaseModelApiClient {}
  return new TestClient('checkpoints');
}

describe('BaseModelApiClient.refreshSingleModelMetadata', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    updateSingleItemMock.mockReset();
    showSimpleLoadingMock.mockReset();
    hideMock.mockReset();
    restoreProgressBarMock.mockReset();
    fetchMock.mockReset();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    delete global.fetch;
    vi.restoreAllMocks();
  });

  it('applies the refreshed entry when the lookup succeeded', async () => {
    const metadata = { file_path: FILE_PATH, sha256: SHA256, hash_status: 'completed' };
    fetchMock.mockResolvedValue(jsonResponse({ success: true, metadata }));

    const client = await createClient();
    const result = await client.refreshSingleModelMetadata(FILE_PATH);

    expect(result).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/lm/checkpoints/fetch-civitai',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ file_path: FILE_PATH }),
      })
    );
    expect(updateSingleItemMock).toHaveBeenCalledWith(FILE_PATH, metadata);
    expect(showToastMock).toHaveBeenCalledWith('toast.api.metadataRefreshed', {}, 'success');
    expect(hideMock).toHaveBeenCalled();
    expect(restoreProgressBarMock).toHaveBeenCalled();
  });

  it('still applies the entry when the lookup failed after hashing', async () => {
    // Fetch computes the pending hash before the CivitAI lookup, so a "not
    // found" response carries the refreshed entry — the card must show the
    // new sha256 instead of keeping the stale empty value.
    const metadata = { file_path: FILE_PATH, sha256: SHA256, hash_status: 'completed' };
    fetchMock.mockResolvedValue(
      jsonResponse({ success: false, error: 'Model not found on CivitAI', metadata })
    );

    const client = await createClient();
    const result = await client.refreshSingleModelMetadata(FILE_PATH);

    expect(result).toBe(false);
    expect(updateSingleItemMock).toHaveBeenCalledWith(FILE_PATH, metadata);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.metadataRefreshFailed',
      { message: 'Model not found on CivitAI' },
      'error'
    );
  });

  it('does not touch the card when the failure carries no entry', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ success: false, error: 'Model not found in cache' })
    );

    const client = await createClient();
    const result = await client.refreshSingleModelMetadata(FILE_PATH);

    expect(result).toBe(false);
    expect(updateSingleItemMock).not.toHaveBeenCalled();
  });
});
