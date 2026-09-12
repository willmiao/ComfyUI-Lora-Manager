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
  OTHER_MODELS_MODULE,
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
  OTHER_MODELS_MODULE: new URL('../../../static/js/utils/otherModels.js', import.meta.url).pathname,
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));
vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  showActionToast: vi.fn(),
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
vi.mock(OTHER_MODELS_MODULE, () => ({
  enableOtherModels: vi.fn(),
  openOtherModelsSettings: vi.fn(),
}));

const { DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE);
const { state } = await import(STATE_MODULE);
const { showActionToast } = await import(UI_HELPERS_MODULE);
const { openOtherModelsSettings } = await import(OTHER_MODELS_MODULE);

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

describe('DownloadManager._resolveOtherSubType', () => {
  let manager;
  let fetchMock;

  beforeEach(() => {
    manager = new DownloadManager();
    manager.apiClient = { modelType: 'other' };
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

  it('returns the backend sub_type for other downloads', async () => {
    manager.currentVersion = { baseModel: 'Flux.1 D', files: [{ type: 'VAE' }] };
    mockRoutingResponse({ success: true, root_kind: 'other', sub_type: 'vae' });

    expect(await manager._resolveOtherSubType()).toBe('vae');

    expect(fetchMock).toHaveBeenCalledWith('/api/lm/download/routing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_type: 'other',
        base_model: 'Flux.1 D',
        file_types: ['VAE'],
      }),
    });
  });

  it('sends selected_file_type plus all version file types when a file is selected', async () => {
    manager.currentVersion = { baseModel: 'Flux.1 D', files: [{ type: 'Model' }, { type: 'VAE' }] };
    manager.selectedFile = { type: 'VAE' };
    mockRoutingResponse({ success: true, root_kind: 'other', sub_type: 'vae' });

    expect(await manager._resolveOtherSubType()).toBe('vae');
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.selected_file_type).toBe('VAE');
    expect(body.file_types).toEqual(['Model', 'VAE']);
  });

  it('omits selected_file_type when no file is selected', async () => {
    manager.currentVersion = { baseModel: 'Flux.1 D', files: [{ type: 'Model' }, { type: 'VAE' }] };
    mockRoutingResponse({ success: true, root_kind: 'other', sub_type: 'vae' });

    await manager._resolveOtherSubType();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect('selected_file_type' in body).toBe(false);
    expect(body.file_types).toEqual(['Model', 'VAE']);
  });

  it('returns null when the backend cannot decide a sub_type', async () => {
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'Model' }] };
    mockRoutingResponse({ success: true, root_kind: 'other', sub_type: null });

    expect(await manager._resolveOtherSubType()).toBeNull();
  });

  it('offers the settings shortcut when the feature is disabled for this type', async () => {
    showActionToast.mockClear();
    openOtherModelsSettings.mockClear();

    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'VAE' }] };
    mockRoutingResponse({
      success: true,
      root_kind: 'other',
      sub_type: null,
      disabled: true,
      reason: 'other_sub_type_disabled',
    });

    expect(await manager._resolveOtherSubType()).toBeNull();

    expect(showActionToast).toHaveBeenCalledWith(
      'other.disabled.downloadBlocked',
      {},
      'warning',
      expect.objectContaining({
        actionText: expect.any(String),
        onAction: expect.any(Function),
      }),
    );

    showActionToast.mock.calls.at(-1)[3].onAction();
    expect(openOtherModelsSettings).toHaveBeenCalledTimes(1);
  });

  it('returns null when the endpoint fails', async () => {
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'VAE' }] };
    fetchMock.mockRejectedValue(new Error('network down'));

    expect(await manager._resolveOtherSubType()).toBeNull();
  });

  it('returns null on a non-ok response', async () => {
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'VAE' }] };
    mockRoutingResponse({}, false);

    expect(await manager._resolveOtherSubType()).toBeNull();
  });

  it('never calls the endpoint for non-other pages', async () => {
    manager.apiClient = { modelType: 'loras' };
    manager.currentVersion = { baseModel: 'SDXL 1.0', files: [{ type: 'VAE' }] };

    expect(await manager._resolveOtherSubType()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('never calls the endpoint without version metadata (e.g. Hugging Face)', async () => {
    expect(await manager._resolveOtherSubType()).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('DownloadManager.proceedToLocationContent (other page)', () => {
  let manager;

  beforeEach(() => {
    document.body.innerHTML = `
      <select id="modelRoot"></select>
      <label id="modelRootLabel"></label>
      <input id="folderPath" />
    `;
    state.global.settings = {};

    manager = new DownloadManager();
    manager.apiClient = {
      modelType: 'other',
      apiConfig: { config: { displayName: 'Other Model' } },
      fetchModelRoots: vi.fn(),
    };
    manager.selectedFile = null;
    manager.selectedFiles = [];
    manager.currentVersion = { baseModel: 'Flux.1 D', files: [{ type: 'VAE' }] };
    manager.initializeFolderTree = vi.fn().mockResolvedValue();
    manager.folderTreeManager = { init: vi.fn() };
    manager.loadDefaultPathSetting = vi.fn();
    manager.updateTargetPath = vi.fn();
    vi.spyOn(manager, '_resolveIsDiffusionModel').mockResolvedValue(false);
  });

  it('fetches sub_type roots and preselects the configured default root', async () => {
    vi.spyOn(manager, '_resolveOtherSubType').mockResolvedValue('vae');
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/vae-a', '/models/vae-b'],
    });
    state.global.settings.default_other_roots = { vae: '/models/vae-b' };

    await manager.proceedToLocationContent();

    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith('vae');
    const modelRoot = document.getElementById('modelRoot');
    expect(Array.from(modelRoot.options).map(o => o.value)).toEqual([
      '/models/vae-a',
      '/models/vae-b',
    ]);
    expect(modelRoot.value).toBe('/models/vae-b');
  });

  it('lists all other roots for manual selection when the sub_type is undecidable', async () => {
    vi.spyOn(manager, '_resolveOtherSubType').mockResolvedValue(null);
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/vae', '/models/upscale'],
    });
    state.global.settings.default_other_roots = { vae: '/models/upscale' };

    await manager.proceedToLocationContent();

    // No argument: the merged /api/lm/other/roots list
    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith();
    const modelRoot = document.getElementById('modelRoot');
    expect(Array.from(modelRoot.options).map(o => o.value)).toEqual([
      '/models/vae',
      '/models/upscale',
    ]);
    // Without a resolved sub_type no default_other_roots entry applies,
    // so the first option stays selected even though a vae default exists.
    expect(modelRoot.value).toBe('/models/vae');
  });

  it('leaves the first root selected when no default is configured for the sub_type', async () => {
    vi.spyOn(manager, '_resolveOtherSubType').mockResolvedValue('upscaler');
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/upscale'],
    });
    state.global.settings.default_other_roots = { vae: '/models/vae-a' };

    await manager.proceedToLocationContent();

    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith('upscaler');
    expect(document.getElementById('modelRoot').value).toBe('/models/upscale');
  });
});
