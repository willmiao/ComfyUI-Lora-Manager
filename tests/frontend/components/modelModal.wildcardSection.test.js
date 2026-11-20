import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  MODAL_MODULE,
  API_FACTORY,
  UI_HELPERS_MODULE,
  MODAL_MANAGER_MODULE,
  SHOWCASE_MODULE,
  MODEL_TAGS_MODULE,
  UTILS_MODULE,
  TRIGGER_WORDS_MODULE,
  PRESET_TAGS_MODULE,
  MODEL_VERSIONS_MODULE,
  RECIPE_TAB_MODULE,
  I18N_HELPERS_MODULE,
  WILDCARD_SECTION_MODULE,
  renderWildcardSectionMock,
  setupWildcardSectionMock,
  openWildcardSettingsMock,
} = vi.hoisted(() => ({
  MODAL_MODULE: new URL('../../../static/js/components/shared/ModelModal.js', import.meta.url).pathname,
  API_FACTORY: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  SHOWCASE_MODULE: new URL('../../../static/js/components/shared/showcase/ShowcaseView.js', import.meta.url).pathname,
  MODEL_TAGS_MODULE: new URL('../../../static/js/components/shared/ModelTags.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../static/js/components/shared/utils.js', import.meta.url).pathname,
  TRIGGER_WORDS_MODULE: new URL('../../../static/js/components/shared/TriggerWords.js', import.meta.url).pathname,
  PRESET_TAGS_MODULE: new URL('../../../static/js/components/shared/PresetTags.js', import.meta.url).pathname,
  MODEL_VERSIONS_MODULE: new URL('../../../static/js/components/shared/ModelVersionsTab.js', import.meta.url).pathname,
  RECIPE_TAB_MODULE: new URL('../../../static/js/components/shared/RecipeTab.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  WILDCARD_SECTION_MODULE: new URL('../../../static/js/components/shared/WildcardSection.js', import.meta.url).pathname,
  renderWildcardSectionMock: vi.fn(() => '<div class="wildcard-section">Wildcard section</div>'),
  setupWildcardSectionMock: vi.fn(),
  openWildcardSettingsMock: vi.fn(),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  openCivitai: vi.fn(),
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn((id, html) => {
      document.body.innerHTML = `<div id="${id}">${html}</div>`;
    }),
    closeModal: vi.fn(),
  },
}));

vi.mock(SHOWCASE_MODULE, () => ({
  scrollToTop: vi.fn(),
  loadExampleImages: vi.fn(),
}));

vi.mock(MODEL_TAGS_MODULE, () => ({
  setupTagEditMode: vi.fn(),
}));

vi.mock(UTILS_MODULE, async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    renderCompactTags: vi.fn(() => ''),
    setupTagTooltip: vi.fn(),
    formatFileSize: vi.fn(() => '1 MB'),
  };
});

vi.mock(TRIGGER_WORDS_MODULE, () => ({
  renderTriggerWords: vi.fn(() => ''),
  setupTriggerWordsEditMode: vi.fn(),
}));

vi.mock(PRESET_TAGS_MODULE, () => ({
  parsePresets: vi.fn(() => ({})),
  renderPresetTags: vi.fn(() => ''),
}));

vi.mock(MODEL_VERSIONS_MODULE, () => ({
  initVersionsTab: vi.fn(() => ({
    load: vi.fn().mockResolvedValue(undefined),
  })),
}));

vi.mock(RECIPE_TAB_MODULE, () => ({
  loadRecipesForModel: vi.fn(),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback || ''),
}));

vi.mock(WILDCARD_SECTION_MODULE, () => ({
  renderWildcardSection: renderWildcardSectionMock,
  setupWildcardSection: setupWildcardSectionMock,
  openWildcardActivationSettings: openWildcardSettingsMock,
}));

vi.mock(API_FACTORY, () => ({
  getModelApiClient: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
    WILDCARD: 'wildcards',
  },
}));

const MODEL = {
  model_name: 'Wild',
  file_path: '/models/wild.zip',
  file_name: 'wild.zip',
  civitai: {},
};

async function getTabs() {
  return [...document.querySelectorAll('#modelModal .showcase-tabs .tab-btn')].map((button) => ({
    tab: button.dataset.tab,
    active: button.classList.contains('active'),
  }));
}

describe('Model modal wildcard section', () => {
  let getModelApiClient;
  let apiClient;

  beforeEach(async () => {
    document.body.innerHTML = '';
    renderWildcardSectionMock.mockClear();
    setupWildcardSectionMock.mockClear();
    openWildcardSettingsMock.mockClear();
    ({ getModelApiClient } = await import(API_FACTORY));
    getModelApiClient.mockReset();
    apiClient = {
      fetchModelMetadataWithStatus: vi.fn().mockResolvedValue({
        metadata: {},
        partial: false,
        offline: false,
      }),
      activate: vi.fn().mockResolvedValue({
        success: true,
        resource: { ...MODEL, active: true, activated_at: '2026-01-01T00:00:00Z', entries: [] },
      }),
      deactivate: vi.fn().mockResolvedValue({
        success: true,
        resource: { ...MODEL, active: false, activated_at: '2026-01-01T00:00:00Z', entries: [] },
      }),
    };
    getModelApiClient.mockReturnValue(apiClient);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ resources: [{ ...MODEL, active: true, entries: [] }] }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  it('renders the key browser in the main info grid and removes the Wildcards tab', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(MODEL, 'wildcards');

    expect((await getTabs()).map((tab) => tab.tab)).toEqual([
      'showcase',
      'description',
      'versions',
    ]);
    expect((await getTabs())[0].active).toBe(true);
    expect(document.querySelector('#modelModal .info-grid > .wildcard-section')).not.toBeNull();
    expect(document.querySelector('#wildcards-tab')).toBeNull();
    expect(setupWildcardSectionMock).toHaveBeenCalled();
  });

  it('auto-expands the section only for explicit wildcard entry points', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(MODEL, 'wildcards');
    expect(renderWildcardSectionMock).toHaveBeenLastCalledWith(expect.anything(), { expanded: false });

    await showModelModal(MODEL, 'wildcards', { openWildcardsSection: true });
    expect(renderWildcardSectionMock).toHaveBeenLastCalledWith(expect.anything(), { expanded: true });
  });

  it('keeps activation first and adds a separate settings action in the header', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal({ ...MODEL, active: false, entries: [] }, 'wildcards');

    const actions = document.querySelectorAll('#modelModal .modal-header-actions > button');
    expect(actions[0].dataset.action).toBe('toggle-wildcard');
    expect(actions[0].dataset.active).toBe('false');
    expect(actions[0].getAttribute('aria-label')).toBe('Activate');
    expect(actions[0].querySelectorAll('.wildcard-toggle-label > span')).toHaveLength(2);
    expect(actions[1].dataset.action).toBe('wildcard-settings');
    expect(actions[1].getAttribute('aria-label')).toBe('Activation settings');
  });

  it('opens settings for first-time activation instead of activating with unchecked defaults', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal({ ...MODEL, active: false, activated_at: null, entries: [] }, 'wildcards');

    document.querySelector('#modelModal [data-action="toggle-wildcard"]').click();

    expect(openWildcardSettingsMock).toHaveBeenCalledWith('modelModal');
    expect(apiClient.activate).not.toHaveBeenCalled();
  });

  it('reuses saved settings on later activation and refreshes the section in place', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal({
      ...MODEL,
      active: false,
      activated_at: '2026-01-01T00:00:00Z',
      entries: [],
    }, 'wildcards');
    const button = document.querySelector('#modelModal [data-action="toggle-wildcard"]');
    const setupCallsBefore = setupWildcardSectionMock.mock.calls.length;

    button.click();

    await vi.waitFor(() => {
      expect(apiClient.activate).toHaveBeenCalledWith('/models/wild.zip');
      expect(button.getAttribute('aria-label')).toBe('Deactivate');
    });
    expect(button.dataset.active).toBe('true');
    expect(button.classList.contains('is-active')).toBe(true);
    expect(setupWildcardSectionMock.mock.calls.length).toBe(setupCallsBefore + 1);
  });

  it('opens activation settings from the header action', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal({ ...MODEL, active: true, entries: [] }, 'wildcards');

    document.querySelector('#modelModal [data-action="wildcard-settings"]').click();

    expect(openWildcardSettingsMock).toHaveBeenCalledWith('modelModal');
    expect(apiClient.deactivate).not.toHaveBeenCalled();
  });
});
