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
const showSimpleLoadingMock = vi.fn();
const showCancelButtonMock = vi.fn();
const hideLoadingMock = vi.fn();

vi.mock(STATE_MODULE, () => ({
  state: {
    loadingManager: {
      showSimpleLoading: showSimpleLoadingMock,
      showCancelButton: showCancelButtonMock,
      hide: hideLoadingMock,
    },
    virtualScroller: {
      removeItemByFilePath: vi.fn(),
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
    endpoints: { bulkDelete: '/api/lm/loras/bulk-delete' },
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

describe('BaseModelApiClient.bulkDeleteModels undo contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    delete global.fetch;
  });

  async function createClient() {
    const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
    class TestClient extends BaseModelApiClient {}
    return new TestClient('loras');
  }

  function mockBulkDeleteResponse(payload) {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    });
  }

  it('posts the file paths and defaults both batch fields to null', async () => {
    mockBulkDeleteResponse({
      success: true,
      status: 'success',
      total_deleted: 3,
      total_attempted: 3,
      cache_updated: true,
      results: [],
    });

    const client = await createClient();
    const result = await client.bulkDeleteModels(['/models/a.safetensors', '/models/b.safetensors']);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/bulk-delete',
      expect.objectContaining({ method: 'POST' })
    );
    expect(result).toEqual({
      success: true,
      deleted_count: 3,
      failed_count: 0,
      errors: [],
      batch_id: null,
      batch_ids: null,
    });
    expect(hideLoadingMock).toHaveBeenCalledTimes(1);
  });

  it('passes through the merged batch_id when the backend staged the bulk delete', async () => {
    mockBulkDeleteResponse({
      success: true,
      status: 'success',
      total_deleted: 2,
      total_attempted: 2,
      cache_updated: true,
      results: [],
      batch_id: 'merged-batch-1',
    });

    const client = await createClient();
    const result = await client.bulkDeleteModels(['/models/a.safetensors', '/models/b.safetensors']);

    expect(result.batch_id).toBe('merged-batch-1');
    expect(result.batch_ids).toBeNull();
  });

  it('passes through the batch_ids fallback array when the merge failed', async () => {
    mockBulkDeleteResponse({
      success: true,
      status: 'success',
      total_deleted: 2,
      total_attempted: 2,
      cache_updated: true,
      results: [],
      batch_ids: ['batch-1', 'batch-2'],
    });

    const client = await createClient();
    const result = await client.bulkDeleteModels(['/models/a.safetensors', '/models/b.safetensors']);

    expect(result.batch_id).toBeNull();
    expect(result.batch_ids).toEqual(['batch-1', 'batch-2']);
  });

  it('keeps the batch field on the cancelled-status path (staged subset is undoable)', async () => {
    mockBulkDeleteResponse({
      success: true,
      status: 'cancelled',
      total_deleted: 1,
      total_attempted: 2,
      cache_updated: true,
      results: [],
      batch_id: 'partial-batch',
    });

    const client = await createClient();
    const result = await client.bulkDeleteModels(['/models/a.safetensors', '/models/b.safetensors']);

    expect(result.success).toBe(true);
    expect(result.deleted_count).toBe(1);
    expect(result.batch_id).toBe('partial-batch');
    expect(result.batch_ids).toBeNull();
  });

  it('returns the cancelled marker when the user aborts the fetch', async () => {
    const abortError = new Error('The user aborted a request.');
    abortError.name = 'AbortError';
    global.fetch = vi.fn().mockRejectedValue(abortError);

    const client = await createClient();
    const result = await client.bulkDeleteModels(['/models/a.safetensors']);

    expect(result).toEqual({ success: false, cancelled: true });
    expect(hideLoadingMock).toHaveBeenCalledTimes(1);
  });

  it('throws the backend error message when the bulk delete fails', async () => {
    mockBulkDeleteResponse({ success: false, error: 'disk full' });

    const client = await createClient();
    await expect(client.bulkDeleteModels(['/models/a.safetensors'])).rejects.toThrow('disk full');
  });
});
