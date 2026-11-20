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
  WILDCARD_TAB_MODULE,
  setupWildcardTabMock,
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
  WILDCARD_TAB_MODULE: new URL('../../../static/js/components/shared/WildcardTab.js', import.meta.url).pathname,
  setupWildcardTabMock: vi.fn(),
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

vi.mock(WILDCARD_TAB_MODULE, () => ({
  renderWildcardTab: vi.fn(() => '<div class="wildcard-tab">Wildcard tab</div>'),
  setupWildcardTab: setupWildcardTabMock,
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

describe('Model modal wildcard tab placement', () => {
  let getModelApiClient;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    getModelApiClient.mockReset();
    getModelApiClient.mockReturnValue({
      fetchModelMetadataWithStatus: vi.fn().mockResolvedValue({
        metadata: {},
        partial: false,
        offline: false,
      }),
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: async () => ({ resources: [{ ...MODEL, active: true, entries: [] }] }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
  });

  it('keeps Wildcards last and leaves the first tab active for a card click', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(MODEL, 'wildcards');

    expect((await getTabs()).map((tab) => tab.tab)).toEqual([
      'showcase',
      'description',
      'versions',
      'wildcards',
    ]);
    expect((await getTabs())[0].active).toBe(true);
    expect((await getTabs())[3].active).toBe(false);
  });

  it('activates the last Wildcards tab when an explicit entry point requests it', async () => {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(MODEL, 'wildcards', { openWildcardsTab: true });

    const tabs = await getTabs();
    expect(tabs[3]).toEqual({ tab: 'wildcards', active: true });
    expect(tabs[0].active).toBe(false);
    expect(setupWildcardTabMock).toHaveBeenCalled();
  });
});
