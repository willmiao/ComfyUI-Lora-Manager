import { describe, it, expect, vi } from 'vitest';

const {
  BASE_MODEL_API_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  STORAGE_MODULE,
  API_CONFIG_MODULE,
  API_FACTORY_MODULE,
  SIDEBAR_MANAGER_MODULE,
} = vi.hoisted(() => ({
  BASE_MODEL_API_MODULE: new URL('../../../static/js/api/baseModelApi.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  SIDEBAR_MANAGER_MODULE: new URL('../../../static/js/components/SidebarManager.js', import.meta.url).pathname,
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
  getStorageItem: vi.fn(),
  getSessionItem: vi.fn(() => null),
  removeSessionItem: vi.fn(),
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

function makePageState(searchOptions) {
  return {
    filters: { search: 'anime', tags: {} },
    searchOptions: {
      filename: true,
      modelname: true,
      tags: false,
      creator: false,
      recursive: true,
      ...searchOptions,
    },
  };
}

describe('BaseModelApiClient trigger-word search params', () => {
  async function createClient() {
    const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
    class TestClient extends BaseModelApiClient {}
    return new TestClient('loras');
  }

  it('sends search_trigger_words when the trigger-word option is enabled', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({ triggerWords: true }));

    expect(params.get('search')).toBe('anime');
    expect(params.get('search_trigger_words')).toBe('true');
  });

  it('sends search_trigger_words=false when the option is disabled', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({ triggerWords: false }));

    expect(params.get('search_trigger_words')).toBe('false');
  });

  it('omits the param on pages without the trigger-word option', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({}));

    expect(params.has('search_trigger_words')).toBe(false);
  });
});
