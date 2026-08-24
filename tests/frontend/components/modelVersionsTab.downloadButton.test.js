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
const openFileSelectionForVersion = vi.fn();

vi.mock(DOWNLOAD_MANAGER_MODULE, () => ({
  downloadManager: {
    downloadVersionWithDefaults,
    openFileSelectionForVersion,
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

function buildRecord(versions) {
  return {
    success: true,
    record: {
      shouldIgnore: false,
      inLibraryVersionIds: versions.filter(v => v.isInLibrary).map(v => v.versionId),
      versions,
    },
  };
}

async function renderVersions(record) {
  const { initVersionsTab } = await import(MODEL_VERSIONS_MODULE);
  const controller = initVersionsTab({
    modalId: 'model-versions-modal',
    modelType: 'loras',
    modelId: 123,
    currentVersionId: null,
  });
  await controller.load();
}

function downloadButtonFor(versionId) {
  return document.querySelector(
    `.model-version-row[data-version-id="${versionId}"] [data-version-action="download"]`
  );
}

function filesBadgeFor(versionId) {
  return document.querySelector(
    `.model-version-row[data-version-id="${versionId}"] [data-version-files]`
  );
}

describe('ModelVersionsTab download button visibility', () => {
  let getModelApiClient;
  let fetchModelUpdateVersions;

  beforeEach(async () => {
    vi.resetModules();
    downloadVersionWithDefaults.mockReset();
    downloadVersionWithDefaults.mockResolvedValue(true);
    openFileSelectionForVersion.mockReset();
    openFileSelectionForVersion.mockResolvedValue(undefined);
    document.body.innerHTML = `
      <div id="model-versions-modal">
        <div id="versions-tab">
          <div class="model-versions-tab"></div>
        </div>
      </div>
    `;
    ({ getModelApiClient } = await import(API_FACTORY_MODULE));
    fetchModelUpdateVersions = vi.fn();
    getModelApiClient.mockReturnValue({
      fetchModelUpdateVersions,
      fetchModelRoots: vi.fn(),
      setModelUpdateIgnore: vi.fn(),
      setVersionUpdateIgnore: vi.fn(),
      deleteModel: vi.fn(),
    });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('hides the download button for a single-file in-library version', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 10,
        name: 'v1.0',
        baseModel: 'Illustrious',
        isInLibrary: true,
        shouldIgnore: false,
        filePath: '/models/loras/file.safetensors',
        fileCount: 1,
      },
    ]));

    await renderVersions();

    expect(downloadButtonFor(10)).toBeFalsy();
    expect(filesBadgeFor(10)).toBeFalsy();
    // The delete affordance must remain for in-library versions.
    expect(document.querySelector(
      '.model-version-row[data-version-id="10"] [data-version-action="delete"]'
    )).toBeTruthy();
  });

  it('shows the files badge instead of a download button for a multi-file in-library version', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 10,
        name: 'v1.0',
        baseModel: 'Illustrious',
        isInLibrary: true,
        shouldIgnore: false,
        filePath: '/models/loras/file.safetensors',
        fileCount: 3,
      },
    ]));

    await renderVersions();

    expect(downloadButtonFor(10)).toBeFalsy();
    const badge = filesBadgeFor(10);
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain('3 files');
    expect(badge.getAttribute('title')).toBe('Choose which files to download');

    badge.click();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(openFileSelectionForVersion).toHaveBeenCalledWith('loras', 123, 10);
  });

  it('hides the download button when fileCount is unknown for an in-library version', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 10,
        name: 'v1.0',
        baseModel: 'Illustrious',
        isInLibrary: true,
        shouldIgnore: false,
        filePath: '/models/loras/file.safetensors',
      },
    ]));

    await renderVersions();

    expect(downloadButtonFor(10)).toBeFalsy();
    expect(filesBadgeFor(10)).toBeFalsy();
  });

  it('shows the download button for versions not in the library', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 11,
        name: 'v1.1',
        baseModel: 'Illustrious',
        isInLibrary: false,
        shouldIgnore: false,
        fileCount: 1,
      },
      {
        versionId: 12,
        name: 'v1.2',
        baseModel: 'Illustrious',
        isInLibrary: false,
        shouldIgnore: false,
      },
    ]));

    await renderVersions();

    expect(downloadButtonFor(11)).toBeTruthy();
    expect(downloadButtonFor(12)).toBeTruthy();
    // Single-file and unknown-count versions get no files badge.
    expect(filesBadgeFor(11)).toBeFalsy();
    expect(filesBadgeFor(12)).toBeFalsy();
  });

  it('keeps the default-file download button and offers the files badge for a multi-file version not in the library', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 11,
        name: 'v1.1',
        baseModel: 'Illustrious',
        isInLibrary: false,
        shouldIgnore: false,
        fileCount: 2,
      },
    ]));

    await renderVersions();

    // The Download button stays bound to the default (primary) file.
    const button = downloadButtonFor(11);
    expect(button).toBeTruthy();
    expect(button.getAttribute('title')).toBe('Download this version');

    button.click();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({ versionName: 'v1.1' })
    );
    expect(openFileSelectionForVersion).not.toHaveBeenCalled();

    // The badge is the advanced entry into the file-selection step.
    const badge = filesBadgeFor(11);
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain('2 files');

    badge.click();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(openFileSelectionForVersion).toHaveBeenCalledWith('loras', 123, 11);
  });

  it('keeps the direct default download for a single-file version not in the library', async () => {
    fetchModelUpdateVersions.mockResolvedValue(buildRecord([
      {
        versionId: 11,
        name: 'v1.1',
        baseModel: 'Illustrious',
        isInLibrary: false,
        shouldIgnore: false,
        fileCount: 1,
      },
    ]));

    await renderVersions();

    expect(filesBadgeFor(11)).toBeFalsy();
    downloadButtonFor(11).click();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(downloadVersionWithDefaults).toHaveBeenCalledWith(
      'loras', 123, 11,
      expect.objectContaining({ versionName: 'v1.1' })
    );
    expect(openFileSelectionForVersion).not.toHaveBeenCalled();
  });
});
