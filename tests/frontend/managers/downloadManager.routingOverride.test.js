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
const { setStorageItem } = await import(STORAGE_HELPERS_MODULE);

describe('DownloadManager checkpoint/diffusion routing override', () => {
  let manager;

  function setupDom() {
    document.body.innerHTML = `
      <div id="routingOverrideGroup" style="display:none">
        <button class="routing-override-option" data-routing="checkpoint"></button>
        <button class="routing-override-option" data-routing="diffusion"></button>
      </div>
      <select id="modelRoot"></select>
      <label id="modelRootLabel"></label>
      <input id="folderPath" />
      <input type="checkbox" id="useDefaultPath" />
      <div id="manualPathSelection"></div>
      <div id="targetPathDisplay"></div>
    `;
  }

  function createManager(modelType, displayName = 'Model') {
    manager = new DownloadManager();
    manager.apiClient = {
      modelType,
      apiConfig: { config: { displayName } },
      fetchModelRoots: vi.fn(),
    };
    manager.selectedFile = null;
    manager.selectedFiles = [];
    manager.currentVersion = null;
    manager.initializeFolderTree = vi.fn().mockResolvedValue();
    manager.folderTreeManager = { init: vi.fn(), getSelectedPath: vi.fn(() => '') };
    manager.loadDefaultPathSetting = vi.fn();
    vi.spyOn(manager, '_resolveOtherSubType').mockResolvedValue(null);
  }

  beforeEach(() => {
    setupDom();
    state.global.settings = {};
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the toggle for diffusion-routed checkpoints and marks diffusion active', async () => {
    createManager('checkpoints', 'Checkpoint');
    vi.spyOn(manager, '_resolveIsDiffusionModel').mockResolvedValue(true);
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/unet'],
    });
    state.global.settings.default_unet_root = '/models/unet';

    await manager.proceedToLocationContent();

    const group = document.getElementById('routingOverrideGroup');
    expect(group.style.display).not.toBe('none');
    const [checkpointBtn, diffusionBtn] = group.querySelectorAll('.routing-override-option');
    expect(diffusionBtn.classList.contains('active')).toBe(true);
    expect(diffusionBtn.getAttribute('aria-pressed')).toBe('true');
    expect(checkpointBtn.classList.contains('active')).toBe(false);
    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith('diffusion_model');
    expect(document.getElementById('modelRoot').value).toBe('/models/unet');
  });

  it('keeps the toggle hidden on non-checkpoints pages', async () => {
    createManager('loras', 'LoRA');
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/loras'],
    });

    await manager.proceedToLocationContent();

    expect(document.getElementById('routingOverrideGroup').style.display).toBe('none');
    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith();
  });

  it('re-fetches diffusion roots and preselects the unet default when overriding to diffusion', async () => {
    createManager('checkpoints', 'Checkpoint');
    vi.spyOn(manager, '_resolveIsDiffusionModel').mockResolvedValue(false);
    manager.apiClient.fetchModelRoots
      .mockResolvedValueOnce({ success: true, roots: ['/models/checkpoints'] })
      .mockResolvedValueOnce({ success: true, roots: ['/models/unet'] });
    state.global.settings.default_unet_root = '/models/unet';

    await manager.proceedToLocationContent();
    expect(document.getElementById('modelRoot').value).toBe('/models/checkpoints');

    await manager.handleRoutingOverrideChange(true);

    expect(manager.apiClient.fetchModelRoots).toHaveBeenLastCalledWith('diffusion_model');
    const modelRoot = document.getElementById('modelRoot');
    expect(Array.from(modelRoot.options).map(o => o.value)).toEqual(['/models/unet']);
    expect(modelRoot.value).toBe('/models/unet');
    const group = document.getElementById('routingOverrideGroup');
    const [checkpointBtn, diffusionBtn] = group.querySelectorAll('.routing-override-option');
    expect(checkpointBtn.classList.contains('active')).toBe(false);
    expect(diffusionBtn.classList.contains('active')).toBe(true);
  });

  it('turns off Use Default Path for the session without persisting when overriding', async () => {
    createManager('checkpoints', 'Checkpoint');
    vi.spyOn(manager, '_resolveIsDiffusionModel').mockResolvedValue(false);
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/checkpoints'],
    });

    await manager.proceedToLocationContent();

    manager.useDefaultPath = true;
    document.getElementById('useDefaultPath').checked = true;

    await manager.handleRoutingOverrideChange(true);

    expect(manager.useDefaultPath).toBe(false);
    expect(document.getElementById('useDefaultPath').checked).toBe(false);
    expect(setStorageItem).not.toHaveBeenCalled();
  });

  it('clears the override when switching back to the auto-classified side', async () => {
    createManager('checkpoints', 'Checkpoint');
    vi.spyOn(manager, '_resolveIsDiffusionModel').mockResolvedValue(false);
    manager.apiClient.fetchModelRoots.mockResolvedValue({
      success: true,
      roots: ['/models/checkpoints'],
    });

    await manager.proceedToLocationContent();
    await manager.handleRoutingOverrideChange(true);
    expect(manager._routingOverride).toBe(true);

    manager.apiClient.fetchModelRoots.mockClear();
    await manager.handleRoutingOverrideChange(false);

    expect(manager._routingOverride).toBeNull();
    // Back on the checkpoint group: no routing argument
    expect(manager.apiClient.fetchModelRoots).toHaveBeenCalledWith();
  });
});
