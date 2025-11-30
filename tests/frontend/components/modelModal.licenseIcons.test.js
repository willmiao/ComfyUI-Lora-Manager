import { describe, it, beforeEach, expect, vi } from 'vitest';

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
  toggleShowcase: vi.fn(),
  setupShowcaseScroll: vi.fn(),
  scrollToTop: vi.fn(),
  loadExampleImages: vi.fn(),
}));

vi.mock(MODEL_TAGS_MODULE, () => ({
  setupTagEditMode: vi.fn(),
}));

vi.mock(UTILS_MODULE, () => ({
  renderCompactTags: vi.fn(() => ''),
  setupTagTooltip: vi.fn(),
  formatFileSize: vi.fn(() => '1 MB'),
}));

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
  loadRecipesForLora: vi.fn(),
}));

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_, __, fallback) => fallback || ''),
}));

vi.mock(API_FACTORY, () => ({
  getModelApiClient: vi.fn(),
}));

describe('Model modal license rendering', () => {
  let getModelApiClient;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    getModelApiClient.mockReset();
  });

  it('handles aggregated commercial strings without extra restrictions', async () => {
    const fetchModelMetadata = vi.fn().mockResolvedValue(null);
    getModelApiClient.mockReturnValue({
      fetchModelMetadata,
      saveModelMetadata: vi.fn(),
    });

    const { showModelModal } = await import(MODAL_MODULE);

    await showModelModal(
      {
        model_name: 'Aggregated',
        file_path: 'models/agg.safetensors',
        file_name: 'agg.safetensors',
        civitai: {
          model: {
            allowNoCredit: true,
            allowCommercialUse: '{Image,RentCivit,Rent}',
            allowDerivatives: true,
            allowDifferentLicense: false,
          },
        },
      },
      'loras',
    );

    const iconTitles = Array.from(document.querySelectorAll('.license-restrictions .license-icon')).map(icon => icon.getAttribute('title'));

    expect(iconTitles).toEqual(['No selling models', 'Same permissions required']);
  });
});
