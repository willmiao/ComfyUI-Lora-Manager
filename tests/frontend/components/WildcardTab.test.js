import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { API_FACTORY, UI_HELPERS, I18N_HELPERS, apiMock } = vi.hoisted(() => {
  const api = {
    fetchEntryValues: vi.fn(),
    fetchSource: vi.fn(),
    activate: vi.fn(),
    deactivate: vi.fn(),
    loadMoreWithVirtualScroll: vi.fn(),
  };
  return {
    API_FACTORY: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    UI_HELPERS: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    I18N_HELPERS: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    apiMock: api,
  };
});

vi.mock(API_FACTORY, () => ({
  getModelApiClient: () => apiMock,
}));
vi.mock(UI_HELPERS, () => ({
  showToast: vi.fn(),
}));
vi.mock(I18N_HELPERS, () => ({
  translate: (key, params, fallback) => fallback || key,
}));

function model(overrides = {}) {
  return {
    file_path: '/models/wild.zip',
    model_name: 'Wild',
    active: false,
    activation_namespace: '',
    activation_aliases: {},
    entries: [
      { key: 'anime/warm', effective_key: 'anime/warm', values_count: 3, source_path: 'anime.txt' },
      { key: 'anime/cool', effective_key: 'anime/cool', values_count: 2, source_path: 'anime.txt' },
    ],
    entry_count: 2,
    files: ['anime.txt'],
    errors: [],
    ...overrides,
  };
}

describe('WildcardTab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    apiMock.fetchEntryValues.mockResolvedValue({ values: ['a', 'b'] });
    apiMock.fetchSource.mockResolvedValue({ content: 'source content' });
    apiMock.activate.mockResolvedValue({ success: true });
    apiMock.deactivate.mockResolvedValue({ success: true });
    apiMock.loadMoreWithVirtualScroll.mockResolvedValue();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ resources: [model({ active: true })] }),
    }));
    document.body.innerHTML = '<div id="modelModal"></div>';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  it('renders activation state, namespace and key count', async () => {
    const { renderWildcardTab } = await import('../../../static/js/components/shared/WildcardTab.js');
    const html = renderWildcardTab(model({ active: true, activation_namespace: 'jp' }));
    document.getElementById('modelModal').innerHTML = html;

    expect(document.querySelector('.wildcard-tab__badge').textContent).toBe('Active');
    expect(document.querySelector('.wildcard-tab__namespace').textContent).toContain('jp');
    expect(document.querySelector('.wildcard-tab__keys-head').textContent).toContain('2');
    expect(document.querySelector('[data-wildcard-field="namespace"]').disabled).toBe(true);
  });

  it('previews source values, filters keys and activates an inactive resource', async () => {
    const { renderWildcardTab, setupWildcardTab } = await import('../../../static/js/components/shared/WildcardTab.js');
    document.getElementById('modelModal').innerHTML = renderWildcardTab(model());
    const onRefresh = vi.fn().mockResolvedValue();
    setupWildcardTab({ model: model(), modalId: 'modelModal', onRefresh });
    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('source content');
    });

    document.querySelector('[data-wildcard-filter]').value = 'cool';
    document.querySelector('[data-wildcard-filter]').dispatchEvent(new Event('input'));
    const rows = document.querySelectorAll('.wildcard-key-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('anime/cool');

    document.querySelector('[data-wildcard-field="namespace"]').value = 'jp';
    document.querySelector('[data-wildcard-action="toggle"]').click();

    await vi.waitFor(() => {
      expect(apiMock.activate).toHaveBeenCalledWith('/models/wild.zip', 'jp', {});
      expect(onRefresh).toHaveBeenCalled();
    });
    expect(apiMock.loadMoreWithVirtualScroll).toHaveBeenCalledWith(true, false);
  });

  it('flags keys that cannot be referenced through __key__ syntax', async () => {
    const { renderWildcardTab, setupWildcardTab } = await import('../../../static/js/components/shared/WildcardTab.js');
    const broken = model({
      entries: [
        { key: 'anime/warm', effective_key: 'anime/warm', values_count: 3 },
        {
          key: 'anime/a__b',
          effective_key: 'anime/a__b',
          values_count: 1,
          reference_problem: "contains '__', which closes the token early",
        },
      ],
    });
    document.getElementById('modelModal').innerHTML = renderWildcardTab(broken);
    setupWildcardTab({ model: broken, modalId: 'modelModal' });

    expect(document.querySelector('.wildcard-tab__warning').textContent).toContain('Some keys (1)');

    const rows = document.querySelectorAll('.wildcard-key-row');
    expect(rows[0].classList.contains('is-unreferenceable')).toBe(false);
    expect(rows[1].classList.contains('is-unreferenceable')).toBe(true);
    expect(rows[1].textContent).toContain('⚠');
    expect(rows[1].title).toContain('closes the token early');
  });
});
