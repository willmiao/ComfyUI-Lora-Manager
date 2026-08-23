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
  state: {
    global: { settings: {} },
  },
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
    config: { displayName: 'LoRA', singularName: 'LoRA', supportsLetterFilter: false },
  })),
  getCurrentModelType: vi.fn(() => 'loras'),
  isValidModelType: vi.fn(() => true),
  DOWNLOAD_ENDPOINTS: {},
  HF_ENDPOINTS: {},
  WS_ENDPOINTS: {},
}));

vi.mock(API_FACTORY_MODULE, () => ({
  resetAndReload: vi.fn(),
}));

vi.mock(SIDEBAR_MANAGER_MODULE, () => ({
  sidebarManager: { refresh: vi.fn() },
}));

async function createClient() {
  const { BaseModelApiClient } = await import(BASE_MODEL_API_MODULE);
  class TestClient extends BaseModelApiClient {}
  return new TestClient('loras');
}

function makePageState(searchOptions) {
  return {
    viewMode: 'active',
    activeFolder: null,
    showFavoritesOnly: false,
    showUpdateAvailableOnly: false,
    filters: { search: 'abc123' },
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

describe('BaseModelApiClient._buildQueryParams hash search option', () => {
  it('appends search_hash=true when the hash option is enabled', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({ hash: true }));

    expect(params.get('search_hash')).toBe('true');
    expect(params.get('search')).toBe('abc123');
  });

  it('appends search_hash=false when the hash option is disabled', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({ hash: false }));

    expect(params.get('search_hash')).toBe('false');
  });

  it('omits search_hash when the option is absent (backend defaults to false)', async () => {
    const client = await createClient();
    const params = client._buildQueryParams({}, makePageState({}));

    expect(params.get('search_hash')).toBeNull();
  });

  it('does not send search_hash without an active search term', async () => {
    const client = await createClient();
    const pageState = makePageState({ hash: true });
    pageState.filters.search = '';
    const params = client._buildQueryParams({}, pageState);

    expect(params.get('search_hash')).toBeNull();
  });
});
