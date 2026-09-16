import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  mockApiClient,
  mockLoadingManager,
  showDownloadBatchSummaryMock,
} = vi.hoisted(() => {
  const mockApiClient = {
    apiConfig: { config: { displayName: 'LoRA', singularName: 'lora' } },
    downloadModel: vi.fn(),
    downloadModelSource: vi.fn(),
    fetchModelSourceFiles: vi.fn(),
    cancelDownload: vi.fn(),
    getPageState: vi.fn(() => ({})),
  };

  const mockLoadingManager = {
    showSimpleLoading: vi.fn(),
    hide: vi.fn(),
    restoreProgressBar: vi.fn(),
    showDownloadProgress: vi.fn(() => vi.fn()),
    setStatus: vi.fn(),
    showCancelButton: vi.fn(),
  };

  return {
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
    mockApiClient,
    mockLoadingManager,
    showDownloadBatchSummaryMock: vi.fn(),
  };
});

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

vi.mock(UI_HELPERS_MODULE, () => ({ showToast: vi.fn() }));

vi.mock(STATE_MODULE, () => ({
  state: { global: { settings: {} }, loadingManager: mockLoadingManager },
}));

vi.mock(LOADING_MANAGER_MODULE, () => ({
  LoadingManager: vi.fn(() => mockLoadingManager),
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => mockApiClient),
  resetAndReload: vi.fn(),
}));

vi.mock(STORAGE_HELPERS_MODULE, () => ({
  getStorageItem: vi.fn((_key, defaultValue) => defaultValue),
  setStorageItem: vi.fn(),
}));

vi.mock(FOLDER_TREE_MANAGER_MODULE, () => ({
  FolderTreeManager: vi.fn(() => ({ clearSelection: vi.fn(), init: vi.fn() })),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock(SUMMARY_MODULE, () => ({
  showDownloadBatchSummary: showDownloadBatchSummaryMock,
}));

class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.close = vi.fn();
    queueMicrotask(() => {
      if (this.onopen) this.onopen();
    });
  }
}

const MS_REPO_URL = 'https://modelscope.cn/models/jj3550945163/Krea-2-LORA';

describe('DownloadManager external model source downloads', () => {
  let DownloadManager;
  let manager;

  beforeEach(async () => {
    document.body.innerHTML = '';
    vi.stubGlobal('WebSocket', FakeWebSocket);
    mockApiClient.downloadModelSource.mockReset();
    mockApiClient.fetchModelSourceFiles.mockReset();
    mockLoadingManager.showSimpleLoading.mockReset();

    ({ DownloadManager } = await import(DOWNLOAD_MANAGER_MODULE));
    manager = new DownloadManager();
    manager.apiClient = mockApiClient;
    manager.showBatchPreviewStep = vi.fn();
    manager.proceedToLocation = vi.fn();
  });

  it('loads a ModelScope repo as batch items on the master revision', async () => {
    mockApiClient.fetchModelSourceFiles.mockResolvedValue([
      { filename: 'a.safetensors', size: 10 },
      { filename: 'sub/b.safetensors', size: 20 },
    ]);
    const errorElement = { textContent: '' };

    await manager._validateAndFetchExternalRepo([MS_REPO_URL], errorElement);

    expect(mockApiClient.fetchModelSourceFiles).toHaveBeenCalledWith(
      'jj3550945163/Krea-2-LORA',
      'modelscope',
      'master'
    );
    expect(errorElement.textContent).toBe('');
    expect(manager.source).toBe('modelscope');
    expect(manager.isBatchMode).toBe(true);
    expect(manager.batchModels).toHaveLength(2);
    expect(manager.batchModels[0]).toMatchObject({
      source: 'modelscope',
      platform: 'modelscope',
      repo: 'jj3550945163/Krea-2-LORA',
      revision: 'master',
      filename: 'a.safetensors',
      fileSizeBytes: 10,
      displayName: 'a.safetensors',
    });
    expect(manager.showBatchPreviewStep).toHaveBeenCalled();
  });

  it('keeps Hugging Face on its own revision', async () => {
    mockApiClient.fetchModelSourceFiles.mockResolvedValue([
      { filename: 'a.safetensors', size: 10 },
    ]);

    await manager._validateAndFetchExternalRepo(
      ['https://huggingface.co/user/repo'],
      { textContent: '' }
    );

    expect(mockApiClient.fetchModelSourceFiles).toHaveBeenCalledWith(
      'user/repo',
      'huggingface',
      'main'
    );
    expect(manager.batchModels[0].revision).toBe('main');
  });

  it('surfaces a listing failure on the URL field', async () => {
    mockApiClient.fetchModelSourceFiles.mockRejectedValue(new Error('Repository not found'));
    const errorElement = { textContent: '' };

    await manager._validateAndFetchExternalRepo([MS_REPO_URL], errorElement);

    expect(errorElement.textContent).toBe('Repository not found');
    expect(manager.showBatchPreviewStep).not.toHaveBeenCalled();
  });

  it('skips file selection for a direct ModelScope file URL', async () => {
    await manager._validateAndFetchExternalRepo(
      [`${MS_REPO_URL}/resolve/master/Krea-2-LORA_c1-st1000.safetensors`],
      { textContent: '' }
    );

    expect(manager.isBatchMode).toBe(false);
    expect(manager.sourcePlatform).toBe('modelscope');
    expect(manager.sourceRepoId).toBe('jj3550945163/Krea-2-LORA');
    expect(manager.sourceSelectedFiles).toEqual(['Krea-2-LORA_c1-st1000.safetensors']);
    expect(manager.proceedToLocation).toHaveBeenCalled();
  });

  it('downloads a single ModelScope file through the generic endpoint', async () => {
    mockApiClient.downloadModelSource.mockResolvedValue({ success: true });
    manager.sourcePlatform = 'modelscope';
    manager.sourceRepoId = 'jj3550945163/Krea-2-LORA';
    manager.sourceSelectedFiles = ['Krea-2-LORA_c1-st1000.safetensors'];

    await manager._downloadExternalRepoFiles({
      modelRoot: '/models/loras',
      targetFolder: '',
      useDefaultPaths: true,
    });

    expect(mockApiClient.downloadModelSource).toHaveBeenCalledTimes(1);
    expect(mockApiClient.downloadModelSource.mock.calls[0][0]).toMatchObject({
      platform: 'modelscope',
      repo: 'jj3550945163/Krea-2-LORA',
      filename: 'Krea-2-LORA_c1-st1000.safetensors',
      revision: 'master',
    });
  });

  it('carries the platform through a batch download', async () => {
    mockApiClient.downloadModelSource.mockResolvedValue({ success: true });
    manager.showBatchPreviewStep = vi.fn();

    await manager.executeBatchDownload(
      [
        {
          source: 'modelscope',
          platform: 'modelscope',
          repo: 'u/r',
          filename: 'f.safetensors',
          revision: 'master',
          displayName: 'f.safetensors',
          checked: true,
        },
      ],
      { modelRoot: '/models/loras', targetFolder: '', useDefaultPaths: true }
    );

    expect(mockApiClient.downloadModelSource).toHaveBeenCalledTimes(1);
    expect(mockApiClient.downloadModelSource.mock.calls[0][0]).toMatchObject({
      platform: 'modelscope',
      repo: 'u/r',
      filename: 'f.safetensors',
      revision: 'master',
    });
    expect(mockApiClient.downloadModel).not.toHaveBeenCalled();
  });

  it('links failures to the ModelScope file page', async () => {
    expect(
      manager._buildSingleItemUrl({
        source: 'modelscope',
        repo: 'u/r',
        filename: 'sub/f.safetensors',
      })
    ).toBe('https://modelscope.cn/models/u/r/file/view/master/sub/f.safetensors');

    expect(
      manager._buildSingleItemUrl({
        source: 'huggingface',
        repo: 'u/r',
        filename: 'f.safetensors',
      })
    ).toBe('https://huggingface.co/u/r/blob/main/f.safetensors');
  });

  it('groups the same repo name on two platforms separately', () => {
    const hf = { source: 'huggingface', repo: 'u/r' };
    const ms = { source: 'modelscope', repo: 'u/r' };

    expect(manager._externalGroupKey(hf)).toBe('huggingface:u/r');
    expect(manager._externalGroupKey(ms)).toBe('modelscope:u/r');
    expect(manager._externalGroupKey(hf)).not.toBe(manager._externalGroupKey(ms));
  });

  describe('post-transfer stage reporting', () => {
    it('ignores ordinary frames', () => {
      const updateProgress = vi.fn();

      expect(
        manager._applyMetadataStage(
          { status: 'progress', progress: 40, bytes_per_second: 10 },
          updateProgress,
          0,
          'f.safetensors'
        )
      ).toBe(false);
      expect(updateProgress).not.toHaveBeenCalled();
    });

    it('routes a metadata stage to the progress bar at 100%', () => {
      const updateProgress = vi.fn();

      expect(
        manager._applyMetadataStage(
          { status: 'metadata', stage: 'source', platform: 'modelscope' },
          updateProgress,
          3,
          'f.safetensors'
        )
      ).toBe(true);
      expect(updateProgress).toHaveBeenCalledWith(100, 3, 'f.safetensors', {}, {
        phase: 'metadata',
        stage: 'source',
        platform: 'modelscope',
      });
    });

    it('tolerates a stage frame with no stage or platform', () => {
      const updateProgress = vi.fn();

      expect(
        manager._applyMetadataStage({ status: 'metadata' }, updateProgress, 0, 'f')
      ).toBe(true);
      expect(updateProgress).toHaveBeenCalledWith(100, 0, 'f', {}, {
        phase: 'metadata',
        stage: '',
        platform: '',
      });
    });

    it('surfaces a metadata frame received while the request is in flight', async () => {
      // End-to-end through the websocket handler: the backend keeps the socket
      // open while it hydrates, and the frame has to reach the progress bar.
      const sockets = [];
      class RecordingWebSocket {
        constructor(url) {
          this.url = url;
          this.onopen = null;
          this.onmessage = null;
          this.onerror = null;
          this.close = vi.fn();
          sockets.push(this);
          queueMicrotask(() => this.onopen && this.onopen());
        }
      }
      vi.stubGlobal('WebSocket', RecordingWebSocket);

      const updateProgress = vi.fn();
      mockLoadingManager.showDownloadProgress.mockReturnValue(updateProgress);

      mockApiClient.downloadModelSource.mockImplementation(async () => {
        sockets.at(-1).onmessage({
          data: JSON.stringify({
            status: 'metadata',
            stage: 'source',
            platform: 'modelscope',
          }),
        });
        return { success: true };
      });

      manager.sourcePlatform = 'modelscope';
      manager.sourceRepoId = 'u/r';
      manager.sourceSelectedFiles = ['a.safetensors'];

      await manager._downloadExternalRepoFiles({
        modelRoot: '/models',
        targetFolder: '',
        useDefaultPaths: false,
      });

      expect(updateProgress).toHaveBeenCalledWith(100, 0, 'a.safetensors', {}, {
        phase: 'metadata',
        stage: 'source',
        platform: 'modelscope',
      });

      mockLoadingManager.showDownloadProgress.mockReturnValue(vi.fn());
    });
  });
});
