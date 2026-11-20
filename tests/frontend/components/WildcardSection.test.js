import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { API_FACTORY, UI_HELPERS, I18N_HELPERS, apiMock, copyToClipboardMock, showToastMock } = vi.hoisted(() => {
  const api = {
    fetchEntryValues: vi.fn(),
    activate: vi.fn(),
  };
  return {
    API_FACTORY: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    UI_HELPERS: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    I18N_HELPERS: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    apiMock: api,
    copyToClipboardMock: vi.fn(),
    showToastMock: vi.fn(),
  };
});

vi.mock(API_FACTORY, () => ({
  getModelApiClient: () => apiMock,
}));
vi.mock(UI_HELPERS, () => ({
  copyToClipboard: copyToClipboardMock,
  showToast: showToastMock,
}));
vi.mock(I18N_HELPERS, () => ({
  translate: (key, params, fallback) => fallback || key,
}));

function model(overrides = {}) {
  return {
    file_path: '/models/wild.zip',
    model_name: 'Wild',
    active: false,
    activated_at: null,
    activation_namespace: '',
    activation_aliases: {},
    entries: [
      { key: 'anime/warm', effective_key: 'anime/warm', values_count: 3, source_path: 'anime.txt' },
      { key: 'anime/cool', effective_key: 'anime/cool', values_count: 2, source_path: 'anime.txt' },
    ],
    entry_count: 2,
    errors: [],
    ...overrides,
  };
}

async function renderSection(resource = model(), onRefresh = vi.fn(), { expanded = true, viewState = {} } = {}) {
  const { renderWildcardSection, setupWildcardSection } = await import(
    '../../../static/js/components/shared/WildcardSection.js'
  );
  document.getElementById('modelModal').innerHTML = renderWildcardSection(resource, { expanded });
  setupWildcardSection({
    model: resource,
    modalId: 'modelModal',
    onRefresh,
    viewState: { expanded, ...viewState },
  });
  return { onRefresh };
}

describe('WildcardSection', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    apiMock.fetchEntryValues.mockImplementation(async (_, key) => ({
      values: key.endsWith('cool') ? ['cool value'] : ['a', 'b'],
    }));
    apiMock.activate.mockResolvedValue({
      success: true,
      resource: model({ active: true, activated_at: '2026-01-01T00:00:00Z' }),
    });
    copyToClipboardMock.mockResolvedValue(true);
    document.body.innerHTML = '<div id="modelModal"></div>';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('renders a key browser without duplicated activation state or controls', async () => {
    await renderSection(model({ active: true, activation_namespace: 'jp' }));

    expect(document.querySelector('.wildcard-section__count').textContent).toBe('2');
    expect(document.querySelector('[data-wildcard-filter]')).not.toBeNull();
    expect(document.querySelector('[data-wildcard-settings]')).not.toBeNull();
    expect(document.querySelector('.wildcard-section__badge')).toBeNull();
    expect(document.querySelector('[data-wildcard-action="toggle"]')).toBeNull();
    expect(document.querySelector('.wildcard-tab')).toBeNull();
  });

  it('loads values only when expanded and preserves browser state across collapse and refresh', async () => {
    await renderSection(model(), vi.fn(), { expanded: false });
    const section = document.querySelector('.wildcard-section');
    const toggle = document.querySelector('[data-wildcard-section-toggle]');

    expect(section.classList.contains('is-collapsed')).toBe(true);
    expect(document.querySelector('[data-wildcard-browser]').hidden).toBe(true);
    expect(document.querySelectorAll('.wildcard-key-row')).toHaveLength(0);
    expect(apiMock.fetchEntryValues).not.toHaveBeenCalled();

    toggle.click();
    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('a\nb');
    });
    expect(apiMock.fetchEntryValues).toHaveBeenCalledTimes(1);

    const filter = document.querySelector('[data-wildcard-filter]');
    const collapseButton = document.querySelector('[data-wildcard-section-collapse]');
    expect(filter.nextElementSibling).toBe(collapseButton);
    expect(collapseButton.hidden).toBe(false);
    filter.value = 'cool';
    filter.dispatchEvent(new Event('input'));
    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('cool value');
    });
    expect(apiMock.fetchEntryValues).toHaveBeenCalledTimes(2);

    collapseButton.click();
    expect(section._wildcardViewState).toEqual({
      expanded: false,
      query: 'cool',
      selectedKey: 'anime/cool',
    });
    toggle.click();
    expect(document.querySelectorAll('.wildcard-key-row')).toHaveLength(1);
    expect(document.querySelector('.wildcard-key-row.is-selected').dataset.key).toBe('anime/cool');
    expect(apiMock.fetchEntryValues).toHaveBeenCalledTimes(2);

    await renderSection(model(), vi.fn(), {
      expanded: true,
      viewState: section._wildcardViewState,
    });
    expect(document.querySelector('[data-wildcard-filter]').value).toBe('cool');
    expect(document.querySelector('.wildcard-key-row.is-selected').dataset.key).toBe('anime/cool');
    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('cool value');
    });
  });

  it('selects the first key, filters results and copies the selected reference', async () => {
    await renderSection();

    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('a\nb');
    });
    expect(document.querySelector('.wildcard-key-row.is-selected').dataset.key).toBe('anime/warm');
    expect(document.querySelector('.wildcard-key-row.is-selected').getAttribute('aria-selected')).toBe('true');
    expect(document.querySelector('[data-wildcard-reference]').textContent).toBe('__anime/warm__');

    document.querySelector('[data-wildcard-filter]').value = 'cool';
    document.querySelector('[data-wildcard-filter]').dispatchEvent(new Event('input'));
    const rows = document.querySelectorAll('.wildcard-key-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].classList.contains('is-selected')).toBe(true);

    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toBe('cool value');
    });
    document.querySelector('[data-wildcard-copy]').click();
    await vi.waitFor(() => {
      expect(copyToClipboardMock).toHaveBeenCalledWith('__anime/cool__', 'Wildcard reference copied');
    });
  });

  it('keeps the values header and reference visible with a long value list', async () => {
    apiMock.fetchEntryValues.mockResolvedValue({
      values: Array.from({ length: 676 }, (_, index) => `value ${index + 1}`),
    });
    const style = document.createElement('style');
    style.textContent = readFileSync(
      path.resolve(__dirname, '../../../static/css/wildcards.css'),
      'utf8',
    );
    document.head.appendChild(style);
    await renderSection(model({
      entries: [{ key: 'poses', effective_key: 'poses', values_count: 676 }],
      entry_count: 1,
    }));

    await vi.waitFor(() => {
      expect(document.querySelector('[data-wildcard-preview]').textContent).toContain('value 676');
    });
    expect(getComputedStyle(document.querySelector('.wildcard-value-panel__header')).flexShrink).toBe('0');
    const reference = document.querySelector('[data-wildcard-reference]');
    expect(getComputedStyle(reference).flexShrink).toBe('0');
    expect(reference.textContent).toBe('__poses__');
    expect(getComputedStyle(document.querySelector('[data-wildcard-preview]')).overflow).toBe('auto');
  });

  it('supports keyboard navigation and uses effective keys while active', async () => {
    await renderSection(model({
      active: true,
      entries: [
        { key: 'anime/warm', effective_key: 'jp/anime/warm', values_count: 3 },
        { key: 'anime/cool', effective_key: 'jp/anime/cool', values_count: 2 },
      ],
    }));

    const list = document.querySelector('[data-wildcard-key-list]');
    list.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));

    expect(document.querySelector('.wildcard-key-row.is-selected').dataset.key).toBe('anime/cool');
    expect(document.querySelector('[data-wildcard-reference]').textContent).toBe('__jp/anime/cool__');
  });

  it('opens activation settings, previews the prefix and saves activation', async () => {
    const { onRefresh } = await renderSection();
    const { openWildcardActivationSettings } = await import(
      '../../../static/js/components/shared/WildcardSection.js'
    );
    openWildcardActivationSettings('modelModal');

    const dialog = document.querySelector('[data-wildcard-settings]');
    expect(dialog.hasAttribute('open')).toBe(true);
    const namespace = document.querySelector('[data-wildcard-field="namespace"]');
    namespace.value = 'Characters/Fantasy';
    namespace.dispatchEvent(new Event('input'));
    expect(document.querySelector('[data-wildcard-settings-example]').textContent)
      .toBe('__characters/fantasy/anime/warm__');

    namespace.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await vi.waitFor(() => {
      expect(apiMock.activate).toHaveBeenCalledWith('/models/wild.zip', 'Characters/Fantasy', {});
      expect(onRefresh).toHaveBeenCalled();
    });
    expect(showToastMock).toHaveBeenCalledWith(
      'wildcards.messages.activated',
      {},
      'success',
      'Resource activated.',
    );
  });

  it('saves an alias for a single-key resource and keeps conflicts in the dialog', async () => {
    const single = model({
      entries: [{ key: 'original', effective_key: 'original', values_count: 1 }],
    });
    await renderSection(single);
    const { openWildcardActivationSettings } = await import(
      '../../../static/js/components/shared/WildcardSection.js'
    );
    openWildcardActivationSettings('modelModal');

    const alias = document.querySelector('[data-wildcard-field="alias"]');
    alias.value = 'character';
    alias.dispatchEvent(new Event('input'));
    expect(document.querySelector('[data-wildcard-settings-example]').textContent).toBe('__character__');

    const conflict = new Error('Conflict');
    conflict.payload = { conflicts: [{ key: 'character', owners: [{ resource_id: 'other.zip' }] }] };
    apiMock.activate.mockRejectedValueOnce(conflict);
    document.querySelector('[data-wildcard-settings-save]').click();

    await vi.waitFor(() => {
      expect(apiMock.activate).toHaveBeenCalledWith('/models/wild.zip', '', { original: 'character' });
      expect(document.querySelector('[data-wildcard-settings-error]').textContent).toContain('other.zip');
    });
    expect(document.querySelector('[data-wildcard-settings]').hasAttribute('open')).toBe(true);
  });

  it('flags keys that cannot be referenced through __key__ syntax', async () => {
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
    await renderSection(broken);

    expect(document.querySelector('.wildcard-section__warning').textContent).toContain('Some keys (1)');
    const rows = document.querySelectorAll('.wildcard-key-row');
    expect(rows[0].classList.contains('is-unreferenceable')).toBe(false);
    expect(rows[1].classList.contains('is-unreferenceable')).toBe(true);
    expect(rows[1].querySelector('.wildcard-key-row__warning')).not.toBeNull();
    expect(rows[1].title).toContain('closes the token early');
  });
});
