import { describe, it, expect, vi, beforeEach } from 'vitest';

const {
  BASE_MODEL_API_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  STORAGE_MODULE,
  API_CONFIG_MODULE,
  API_FACTORY_MODULE,
  SIDEBAR_MANAGER_MODULE,
  sessionStore,
} = vi.hoisted(() => ({
  BASE_MODEL_API_MODULE: new URL('../../../static/js/api/baseModelApi.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
  // Page-level state that survives a page load lives in sessionStorage; keep a
  // stand-in that behaves like the real helper (absent key -> defaultValue).
  sessionStore: new Map(),
}));

vi.mock(STATE_MODULE, () => ({
  state: { currentPageType: 'loras', global: { settings: { group_by_model: false } } },
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key) => key),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: vi.fn(() => null),
  setStorageItem: vi.fn(),
  removeStorageItem: vi.fn(),
  getSessionItem: vi.fn((key, defaultValue = null) => (
    sessionStore.has(key) ? sessionStore.get(key) : defaultValue
  )),
  setSessionItem: vi.fn((key, value) => { sessionStore.set(key, value); }),
  removeSessionItem: vi.fn((key) => { sessionStore.delete(key); }),
  saveMapToStorage: vi.fn(),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  getCompleteApiConfig: vi.fn(() => ({
    endpoints: {},
    config: { displayName: 'LoRA', singularName: 'LoRA' },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  MODEL_SOURCE_ENDPOINTS: {},
  WS_ENDPOINTS: {},
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

function makePageState(activeFolder = 'Styles') {
  return {
    activeFolder,
    filters: {},
    searchOptions: {
      filename: true,
      modelname: true,
      tags: false,
      creator: false,
      recursive: true,
    },
  };
}

async function createClient(modelType = 'loras') {
  const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
  class TestClient extends BaseModelApiClient {}
  return new TestClient(modelType);
}

describe('BaseModelApiClient View Local Versions folder scope', () => {
  beforeEach(() => {
    sessionStore.clear();
  });

  it('sends the browsing folder when View Local Versions is inactive', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState('Styles'));

    expect(params.get('folder')).toBe('Styles');
    expect(params.has('civitai_model_id')).toBe(false);
  });

  it('omits the folder while View Local Versions is active', async () => {
    sessionStore.set('vlm_model_id', '1234');
    sessionStore.set('vlm_model_name', 'Pose Pack');
    sessionStore.set('vlm_page_type', 'loras');

    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState('Styles'));

    // A version moved to another folder is still a local version of the model
    expect(params.has('folder')).toBe(false);
    expect(params.get('civitai_model_id')).toBe('1234');
  });

  it('keeps the folder when the stored filter belongs to another page', async () => {
    sessionStore.set('vlm_model_id', '1234');
    sessionStore.set('vlm_model_name', 'A Checkpoint');
    sessionStore.set('vlm_page_type', 'checkpoints');

    const client = await createClient('loras');
    const params = client._buildQueryParams({}, makePageState('Styles'));

    expect(params.get('folder')).toBe('Styles');
    expect(params.has('civitai_model_id')).toBe(false);
    // Stale keys are dropped instead of leaking into the next page
    expect(sessionStore.has('vlm_model_id')).toBe(false);
    expect(sessionStore.has('vlm_page_type')).toBe(false);
  });
});
