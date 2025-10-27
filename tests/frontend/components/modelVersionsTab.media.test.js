import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  MODEL_VERSIONS_MODULE,
  API_FACTORY_MODULE,
  DOWNLOAD_MANAGER_MODULE,
  UI_HELPERS_MODULE,
  STATE_MODULE,
  I18N_HELPERS_MODULE,
  UTILS_MODULE,
} = vi.hoisted(() => ({
  MODEL_VERSIONS_MODULE: new URL('../../../static/js/components/shared/ModelVersionsTab.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  DOWNLOAD_MANAGER_MODULE: new URL('../../../static/js/managers/DownloadManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../static/js/components/shared/utils.js', import.meta.url).pathname,
}));

vi.mock(DOWNLOAD_MANAGER_MODULE, () => ({
  downloadManager: {
    downloadVersionWithDefaults: vi.fn(),
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
}));

const stateMock = { global: { settings: { autoplay_on_hover: false } } };
vi.mock(STATE_MODULE, () => ({
  state: stateMock,
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock(UTILS_MODULE, () => ({
  formatFileSize: vi.fn(() => '1 MB'),
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(),
}));

describe('ModelVersionsTab media rendering', () => {
  let getModelApiClient;
  let fetchModelUpdateVersions;

  beforeEach(async () => {
    vi.resetModules();
    document.body.innerHTML = `
      <div id="model-versions-modal">
        <div id="versions-tab">
          <div class="model-versions-tab"></div>
        </div>
      </div>
    `;
    stateMock.global.settings.autoplay_on_hover = false;
    ({ getModelApiClient } = await import(API_FACTORY_MODULE));
    fetchModelUpdateVersions = vi.fn();
    getModelApiClient.mockReturnValue({
      fetchModelUpdateVersions,
      setModelUpdateIgnore: vi.fn(),
      setVersionUpdateIgnore: vi.fn(),
      deleteModel: vi.fn(),
    });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders video preview when preview URL references a video file in a query parameter', async () => {
    const previewUrl = '/api/lm/previews?path=%2Fhome%2Fexample%2Fvideo-preview.mp4';
    fetchModelUpdateVersions.mockResolvedValue({
      success: true,
      record: {
        shouldIgnore: false,
        inLibraryVersionIds: [2],
        versions: [
          {
            versionId: 2,
            name: 'v1.0',
            previewUrl,
            baseModel: 'SDXL',
            sizeBytes: 1024,
            isInLibrary: true,
            shouldIgnore: false,
          },
        ],
      },
    });

    const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
    const controller = initVersionsTab({
      modalId: 'model-versions-modal',
      modelType: 'loras',
      modelId: 123,
      currentVersionId: null,
    });

    await controller.load();

    const videoElement = document.querySelector('.version-media video');
    expect(videoElement).toBeTruthy();
    expect(videoElement?.getAttribute('src')).toBe(previewUrl);
    expect(document.querySelector('.version-media img')).toBeFalsy();
  });

  it('renders image preview when preview URL does not reference a video', async () => {
    const previewUrl = '/api/lm/previews?path=%2Fhome%2Fexample%2Fpreview-image.png';
    fetchModelUpdateVersions.mockResolvedValue({
      success: true,
      record: {
        shouldIgnore: false,
        inLibraryVersionIds: [3],
        versions: [
          {
            versionId: 3,
            name: 'v1.1',
            previewUrl,
            baseModel: 'SDXL',
            sizeBytes: 2048,
            isInLibrary: true,
            shouldIgnore: false,
          },
        ],
      },
    });

    const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
    const controller = initVersionsTab({
      modalId: 'model-versions-modal',
      modelType: 'loras',
      modelId: 456,
      currentVersionId: null,
    });

    await controller.load();

    const imageElement = document.querySelector('.version-media img');
    expect(imageElement).toBeTruthy();
    expect(imageElement?.getAttribute('src')).toBe(previewUrl);
    expect(document.querySelector('.version-media video')).toBeFalsy();
  });
});
