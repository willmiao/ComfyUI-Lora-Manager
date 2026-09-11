import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderTemplate } from '../utils/domFixtures.js';

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
  setupAutoNewlineOnPaste: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (key, params = {}, fallback = null) => fallback ?? key,
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  WS_ENDPOINTS: {},
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  getStorageItem: vi.fn(() => true),
  setStorageItem: vi.fn(),
}));

describe('BatchImportManager directory browser (#1106)', () => {
  let batchImportManager;
  let fetchMock;
  let showToast;

  beforeEach(async () => {
    vi.clearAllMocks();
    vi.resetModules();

    document.body.innerHTML = '';
    renderTemplate('components/batch_import_modal.html');

    fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const uiHelpers = await import('../../../static/js/utils/uiHelpers.js');
    showToast = uiHelpers.showToast;

    const batchModule = await import('../../../static/js/managers/BatchImportManager.js');
    batchImportManager = new batchModule.BatchImportManager();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function lastRequestBody() {
    return JSON.parse(fetchMock.mock.calls.at(-1)[1].body);
  }

  it('opens the browser with an empty path so the server picks the default', async () => {
    // The old POSIX-only "/" initial path fails the access check on Windows.
    document.getElementById('batchDirectoryInput').value = '';

    batchImportManager.toggleDirectoryBrowser();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('');
    expect(document.getElementById('batchDirectoryBrowser').style.display).toBe('block');
  });

  it('navigates to the parent using the server-provided path (Windows-safe)', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        current_path: 'C:\\Users\\miao\\Pictures',
        parent_path: 'C:\\Users\\miao',
        directories: [],
        image_files: [],
        image_count: 0,
        directory_count: 0,
      }),
    }));

    await batchImportManager.loadDirectory('C:\\Users\\miao\\Pictures');
    fetchMock.mockClear();

    batchImportManager.navigateToParentDirectory();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('C:\\Users\\miao');
  });

  it('refuses to select a virtual level that has no current path (drive list)', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        current_path: '',
        parent_path: null,
        directories: [{ name: 'C:\\', path: 'C:\\', is_parent: false }],
        image_files: [],
        image_count: 0,
        directory_count: 1,
      }),
    }));

    await batchImportManager.loadDirectory('__drives__');
    batchImportManager.selectCurrentDirectory();

    expect(showToast).toHaveBeenCalledWith('toast.recipes.batchImportNoDirectory', {}, 'error');
    expect(document.getElementById('batchDirectoryInput').value).toBe('');
  });
});
