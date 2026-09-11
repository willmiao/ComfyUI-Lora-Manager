import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  DOWNLOAD_MANAGER_MODULE,
  MODAL_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  STATE_MODULE,
  LOADING_MANAGER_MODULE,
  API_FACTORY_MODULE,
  STORAGE_HELPERS_MODULE,
  FOLDER_TREE_MANAGER_MODULE,
  I18N_HELPERS_MODULE,
  SUMMARY_MODULE,
} = vi.hoisted(() => ({
  DOWNLOAD_MANAGER_MODULE: new URL('../../../static/js/managers/DownloadManager.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  LOADING_MANAGER_MODULE: new URL('../../../static/js/managers/LoadingManager.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  STORAGE_HELPERS_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  FOLDER_TREE_MANAGER_MODULE: new URL('../../../static/js/components/FolderTreeManager.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  SUMMARY_MODULE: new URL('../../../static/js/components/DownloadBatchSummaryModal.js', import.meta.url).pathname,
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));
vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  setupAutoNewlineOnPaste: vi.fn(),
}));
vi.mock(STATE_MODULE, () => ({
  state: { global: { settings: {} }, loadingManager: {} },
}));
vi.mock(LOADING_MANAGER_MODULE, () => ({
  LoadingManager: vi.fn(() => ({})),
}));
vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(),
  resetAndReload: vi.fn(),
}));
vi.mock(STORAGE_HELPERS_MODULE, () => ({
  getStorageItem: vi.fn((_key, defaultValue) => defaultValue),
  setStorageItem: vi.fn(),
}));
vi.mock(FOLDER_TREE_MANAGER_MODULE, () => ({
  FolderTreeManager: vi.fn(() => ({})),
}));
vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_key, _vars, fallback) => fallback ?? ''),
}));
vi.mock(SUMMARY_MODULE, () => ({
  showDownloadBatchSummary: vi.fn(),
}));

const { DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE);

describe('DownloadManager._resolveIsDiffusionModel', () => {
  let manager;
  let fetchMock;

  beforeEach(() => {
    manager = new DownloadManager();
    manager.apiClient = { modelType: 'checkpoints' };
    manager.selectedFile = null;
    manager.selectedFiles = [];
    manager.currentVersion = null;
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mockRoutingResponse(data, ok = true) {
    fetchMock.mockResolvedValue({
      ok,
      status: ok ? 200 : 500,
      json: async () => data,
    });
  }

  it('asks the backend and routes baseModel-only diffusion models to unet roots', async () => {
    // The reported Anima case: file type is plain "Model".
    manager.currentVersion = { baseModel: 'Anima', files: [{ type: 'Model' }] };
    mockRoutingResponse({ success: true, is_diffusion_model: true, root_kind: 'unet' });

    expect(await manager._resolveIsDiffusionModel()).toBe(true);

    expect(fetchMock).toHaveBeenCalledWith('/api/lm/download/routing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_type: 'checkpoint',
        base_model: 'Anima',
        file_types: ['Model'],
      }),
    });
  });

  it('returns the backend decision for regular checkpoints', async () => {
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'Model' }] };
    mockRoutingResponse({ success: true, is_diffusion_model: false, root_kind: 'checkpoint' });

    expect(await manager._resolveIsDiffusionModel()).toBe(false);
  });

  it('sends only the selected file type when a file is selected', async () => {
    manager.currentVersion = { baseModel: 'Flux.1 D', files: [{ type: 'Model' }, { type: 'UNet' }] };
    manager.selectedFile = { type: 'UNet' };
    mockRoutingResponse({ success: true, is_diffusion_model: true, root_kind: 'unet' });

    expect(await manager._resolveIsDiffusionModel()).toBe(true);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).file_types).toEqual(['UNet']);
  });

  it('falls back to the local file-type check when the endpoint fails', async () => {
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'UNet' }] };
    fetchMock.mockRejectedValue(new Error('network down'));

    expect(await manager._resolveIsDiffusionModel()).toBe(true);
  });

  it('falls back to false when the endpoint fails and no local signal exists', async () => {
    manager.currentVersion = { baseModel: 'Anima', files: [{ type: 'Model' }] };
    mockRoutingResponse({}, false);

    expect(await manager._resolveIsDiffusionModel()).toBe(false);
  });

  it('never calls the endpoint for non-checkpoint pages', async () => {
    manager.apiClient = { modelType: 'loras' };
    manager.currentVersion = { baseModel: 'Anima', files: [{ type: 'Model' }] };

    expect(await manager._resolveIsDiffusionModel()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('never calls the endpoint without version metadata (e.g. Hugging Face)', async () => {
    expect(await manager._resolveIsDiffusionModel()).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
