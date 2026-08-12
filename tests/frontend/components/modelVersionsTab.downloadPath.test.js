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

const downloadVersionWithDefaults = vi.fn();

vi.mock(DOWNLOAD_MANAGER_MODULE, () => ({
  downloadManager: {
    downloadVersionWithDefaults,
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  openCivitaiUrl: vi.fn(),
}));

const stateMock = {
  global: {
    settings: {
      autoplay_on_hover: false,
      version_grouping: 'any',
      download_path_templates: {
        lora: '{base_model}/{first_tag}',
        checkpoint: '{base_model}/{first_tag}',
        embedding: '{base_model}/{first_tag}',
      },
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

const LORA_ROOT = '/models/loras';

function buildRecord(targetBaseModel = 'Anima') {
  return {
    success: true,
    record: {
      shouldIgnore: false,
      inLibraryVersionIds: [10],
      versions: [
        {
          versionId: 10,
          name: 'v1.0',
          baseModel: 'Illustrious',
          sizeBytes: 1024,
          isInLibrary: true,
          shouldIgnore: false,
          filePath: `${LORA_ROOT}/Illustrious/works/file.safetensors`,
        },
        {
          versionId: 11,
          name: 'v1.1',
          baseModel: targetBaseModel,
          sizeBytes: 2048,
          isInLibrary: false,
          shouldIgnore: false,
        },
      ],
    },
  };
}

async function renderAndClickDownload({ currentVersionId = 10, record = null } = {}) {
  const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
  const controller = initVersionsTab({
    modalId: 'model-versions-modal',
    modelType: 'loras',
    modelId: 123,
    currentVersionId,
  });
  await controller.load();
  const downloadButton = document.querySelector(
    '.model-version-row[data-version-id="11"] [data-version-action="download"]'
  );
  downloadButton?.click();
  await new Promise(resolve => setTimeout(resolve, 0));
  return controller;
}

describe('ModelVersionsTab update download path resolution', () => {
  let getModelApiClient;
  let fetchModelUpdateVersions;
  let fetchModelRoots;

  beforeEach(async () => {
    vi.resetModules();
    downloadVersionWithDefaults.mockReset();
    downloadVersionWithDefaults.mockResolvedValue(true);
    document.body.innerHTML = `
      <div id="model-versions-modal">
        <div id="versions-tab">
          <div class="model-versions-tab"></div>
        </div>
      </div>
    `;
    stateMock.global.settings.version_grouping = 'any';
    stateMock.global.settings.download_path_templates.lora = '{base_model}/{first_tag}';
    ({ getModelApiClient } = await import(API_FACTORY_MODULE));
    fetchModelUpdateVersions = vi.fn();
    fetchModelRoots = vi.fn();
    fetchModelRoots.mockResolvedValue({ roots: [LORA_ROOT] });
    getModelApiClient.mockReturnValue({
      fetchModelUpdateVersions,
      fetchModelRoots,
      setModelUpdateIgnore: vi.fn(),
      setVersionUpdateIgnore: vi.fn(),
      deleteModel: vi.fn(),
    });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('keeps the current folder when the target version has the same base model', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord('Illustrious'));

    await renderAndClickDownload();

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({
        modelRoot: LORA_ROOT,
        targetFolder: 'Illustrious/works',
        useDefaultPaths: null,
        useSaveDirAsRoot: false,
      })
    );
  });

  it('resolves the template path when the target base model differs and a template is configured', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord());

    await renderAndClickDownload();

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({
        modelRoot: LORA_ROOT,
        targetFolder: '',
        useDefaultPaths: true,
        useSaveDirAsRoot: true,
      })
    );
  });

  it('keeps the current folder when the target base model differs but no template is configured', async () => {
    stateMock.global.settings.download_path_templates.lora = '';
    fetchModelUpdateVersions.mockResolvedValue(buildRecord());

    await renderAndClickDownload();

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({
        modelRoot: LORA_ROOT,
        targetFolder: 'Illustrious/works',
        useDefaultPaths: null,
        useSaveDirAsRoot: false,
      })
    );
  });

  it('falls back to default paths when no local version exists', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord());

    await renderAndClickDownload({ currentVersionId: null });

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({
        modelRoot: '',
        targetFolder: '',
        useDefaultPaths: null,
        useSaveDirAsRoot: false,
      })
    );
  });
});
