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
const removeItemByFilePathMock = vi.fn();
const showSimpleLoadingMock = vi.fn();
const hideLoadingMock = vi.fn();

vi.mock(STATE_MODULE, () => ({
  state: {
    loadingManager: {
      showSimpleLoading: showSimpleLoadingMock,
      hide: hideLoadingMock,
    },
    virtualScroller: {
      removeItemByFilePath: removeItemByFilePathMock,
    },
  },
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
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
    endpoints: { delete: '/api/lm/loras/delete' },
    config: { displayName: 'LoRA', singularName: 'LoRA' },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  WS_ENDPOINTS: {},
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

describe('BaseModelApiClient.deleteModel undo contract', () => {
  beforeEach(() => {
    showToastMock.mockReset();
    removeItemByFilePathMock.mockReset();
    showSimpleLoadingMock.mockReset();
    hideLoadingMock.mockReset();
  });

  afterEach(() => {
    delete global.fetch;
  });

  async function createClient() {
    const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
    class TestClient extends BaseModelApiClient {}
    return new TestClient('loras');
  }

  it('returns the batch id and suppresses the legacy success toast when staged', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, deleted_files: [], batch_id: 'batch-42' }),
    });

    const client = await createClient();
    const result = await client.deleteModel('/models/foo.safetensors');

    expect(result).toEqual({ success: true, batch_id: 'batch-42' });
    // The card is still removed from the scroller — the file is gone either way
    expect(removeItemByFilePathMock).toHaveBeenCalledWith('/models/foo.safetensors');
    // No legacy toast: the caller shows the undo action toast instead
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.deleteSuccess',
      expect.anything(),
      expect.anything()
    );
    expect(hideLoadingMock).toHaveBeenCalledTimes(1);
  });

  it('keeps the legacy success toast when the delete was not staged', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, deleted_files: ['/models/foo.safetensors'] }),
    });

    const client = await createClient();
    const result = await client.deleteModel('/models/foo.safetensors');

    expect(result).toEqual({ success: true, batch_id: null });
    expect(removeItemByFilePathMock).toHaveBeenCalledWith('/models/foo.safetensors');
    expect(showToastMock).toHaveBeenCalledWith('toast.api.deleteSuccess', { type: 'LoRA' }, 'success');
  });

  it('returns a truthy result so undo-blind callers keep working (ModelVersionsTab)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, deleted_files: [], batch_id: 'batch-7' }),
    });

    const client = await createClient();
    const result = await client.deleteModel('/models/v2.safetensors');

    // ModelVersionsTab.js:1136-1144 awaits deleteModel and treats any truthy
    // result as success — the new object must satisfy that check shape.
    expect(result).toBeTruthy();
    expect(Boolean(result && result.success)).toBe(true);
  });

  it('returns false and shows the failure toast when the server reports failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: false, error: 'disk error' }),
    });

    const client = await createClient();
    const result = await client.deleteModel('/models/foo.safetensors');

    expect(result).toBe(false);
    expect(removeItemByFilePathMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.deleteFailed',
      expect.objectContaining({ type: 'LoRA' }),
      'error'
    );
  });
});
