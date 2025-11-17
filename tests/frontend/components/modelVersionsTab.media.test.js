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

const stateMock = {
  global: {
    settings: {
      autoplay_on_hover: false,
      update_flag_strategy: 'any',
    },
  },
};
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
    stateMock.global.settings.update_flag_strategy = 'any';
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

  it('shows a stable label with a short state indicator', async () => {
    stateMock.global.settings.update_flag_strategy = 'any';
    fetchModelUpdateVersions.mockResolvedValue({
      success: true,
      record: {
        shouldIgnore: false,
        inLibraryVersionIds: [5],
        versions: [
          {
            versionId: 5,
            name: 'base',
            baseModel: 'SDXL',
            previewUrl: '/api/lm/previews/v-base.png',
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
      modelId: 321,
      currentVersionId: 5,
    });

    await controller.load();

    const toggleText = document.querySelector('.versions-filter-toggle .sr-only');
    expect(toggleText?.textContent?.trim()).toBe('Base filter: All versions');
  });

  it('filters versions to the current base model when strategy is same_base', async () => {
    stateMock.global.settings.update_flag_strategy = 'same_base';
    fetchModelUpdateVersions.mockResolvedValue({
      success: true,
      record: {
        shouldIgnore: false,
        inLibraryVersionIds: [10],
        versions: [
          {
            versionId: 10,
            name: 'v1.0',
            baseModel: 'SDXL',
            previewUrl: '/api/lm/previews/v1.png',
            sizeBytes: 1024,
            isInLibrary: true,
            shouldIgnore: false,
          },
          {
            versionId: 11,
            name: 'v1.1',
            baseModel: 'Realistic',
            previewUrl: '/api/lm/previews/v1-1.png',
            sizeBytes: 2048,
            isInLibrary: false,
            shouldIgnore: false,
          },
        ],
      },
    });

    const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
    const controller = initVersionsTab({
      modalId: 'model-versions-modal',
      modelType: 'loras',
      modelId: 789,
      currentVersionId: 10,
    });

    await controller.load();

    expect(document.querySelectorAll('.model-version-row').length).toBe(1);
  });

  it('toggle button can switch to display all versions', async () => {
    stateMock.global.settings.update_flag_strategy = 'same_base';
    fetchModelUpdateVersions.mockResolvedValue({
      success: true,
      record: {
        shouldIgnore: false,
        inLibraryVersionIds: [10],
        versions: [
          {
            versionId: 10,
            name: 'v1.0',
            baseModel: 'SDXL',
            previewUrl: '/api/lm/previews/v1.png',
            sizeBytes: 1024,
            isInLibrary: true,
            shouldIgnore: false,
          },
          {
            versionId: 11,
            name: 'v1.1',
            baseModel: 'Realistic',
            previewUrl: '/api/lm/previews/v1-1.png',
            sizeBytes: 2048,
            isInLibrary: false,
            shouldIgnore: false,
          },
        ],
      },
    });

    const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
    const controller = initVersionsTab({
      modalId: 'model-versions-modal',
      modelType: 'loras',
      modelId: 987,
      currentVersionId: 10,
    });

    await controller.load();

    expect(document.querySelectorAll('.model-version-row').length).toBe(1);
    const toggleButton = document.querySelector('[data-versions-action="toggle-version-display-mode"]');
    expect(toggleButton).toBeTruthy();
    const toggleTextBefore = document.querySelector('.versions-filter-toggle .sr-only');
    expect(toggleTextBefore?.textContent?.trim()).toContain('Same base');
    toggleButton?.click();
    expect(document.querySelectorAll('.model-version-row').length).toBe(2);
    const toggleTextAfter = document.querySelector('.versions-filter-toggle .sr-only');
    expect(toggleTextAfter?.textContent?.trim()).toContain('All versions');
  });
});
