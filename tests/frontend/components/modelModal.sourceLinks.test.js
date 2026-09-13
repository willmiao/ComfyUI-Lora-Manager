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
  copyToClipboard: vi.fn(),
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

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

vi.mock(API_FACTORY, () => ({
  getModelApiClient: vi.fn(),
}));

function makeModel(overrides = {}) {
  return {
    model_name: 'Linked Model',
    file_path: 'models/linked.safetensors',
    file_name: 'linked.safetensors',
    sha256: 'a'.repeat(64),
    from_civitai: true,
    civitai: {},
    ...overrides,
  };
}

describe('Model modal source links (#1094)', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    const { getModelApiClient } = await import(API_FACTORY);
    getModelApiClient.mockReset();
    getModelApiClient.mockReturnValue({
      fetchModelMetadata: vi.fn().mockResolvedValue(null),
      saveModelMetadata: vi.fn(),
    });
  });

  async function renderModal(model) {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(model, 'loras');
  }

  const civitaiLink = () => document.querySelector('[data-action="view-civitai"]');
  const hfLink = () => document.querySelector('[data-action="view-huggingface"]');

  it('renders both links when the model has CivitAI data and an HF link', async () => {
    await renderModal(
      makeModel({
        civitai: { id: 111, modelId: 222, name: 'v1' },
        hf_url: 'https://huggingface.co/user/repo',
      })
    );

    expect(civitaiLink()).not.toBeNull();
    expect(hfLink()).not.toBeNull();
    expect(hfLink().dataset.hfUrl).toBe('https://huggingface.co/user/repo');
  });

  it('keeps the CivitAI link after linking HF even when from_civitai is false', async () => {
    // Regression for case 1: set_hf_url used to flip from_civitai to false,
    // which hid the CivitAI link despite the model still having CivitAI data.
    await renderModal(
      makeModel({
        from_civitai: false,
        civitai: { id: 111, modelId: 222, name: 'v1' },
        hf_url: 'https://huggingface.co/user/repo',
      })
    );

    expect(civitaiLink()).not.toBeNull();
    expect(hfLink()).not.toBeNull();
  });

  it('renders only the HF link for an HF-only model', async () => {
    await renderModal(
      makeModel({
        from_civitai: false,
        civitai: {},
        hf_url: 'https://huggingface.co/user/repo',
      })
    );

    expect(civitaiLink()).toBeNull();
    expect(hfLink()).not.toBeNull();
  });

  it('renders the CivitAI link from civitai.model_id when modelId is absent', async () => {
    await renderModal(
      makeModel({
        from_civitai: false,
        civitai: { id: 111, model_id: 222 },
      })
    );

    expect(civitaiLink()).not.toBeNull();
    expect(hfLink()).toBeNull();
  });

  it('renders neither link when there is no CivitAI data and no HF link', async () => {
    await renderModal(makeModel({ civitai: {} }));

    expect(civitaiLink()).toBeNull();
    expect(hfLink()).toBeNull();
  });
});
