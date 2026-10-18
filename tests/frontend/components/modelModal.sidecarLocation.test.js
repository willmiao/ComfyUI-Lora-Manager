import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

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
  STATE_MODULE,
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
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
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
    EMBEDDING: 'embeddings'
  }
}));

vi.mock(API_FACTORY, () => ({
  getModelApiClient: vi.fn(),
}));

const MODEL_PATH = '/data/loras/flux/model.safetensors';

function makeModel(overrides = {}) {
  return {
    model_name: 'Sidecar Model',
    file_path: MODEL_PATH,
    file_name: 'model.safetensors',
    civitai: {},
    ...overrides,
  };
}

describe('Model modal sidecar location entry', () => {
  let getModelApiClient;
  let showToast;
  let state;
  let originalMode;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    ({ showToast } = await import(UI_HELPERS_MODULE));
    ({ state } = await import(STATE_MODULE));
    getModelApiClient.mockReset();
    showToast.mockReset();
    getModelApiClient.mockReturnValue({
      fetchModelMetadata: vi.fn().mockResolvedValue(null),
      saveModelMetadata: vi.fn(),
    });
    originalMode = state.global.settings.sidecar_storage_mode;
    global.fetch = vi.fn();
  });

  afterEach(() => {
    state.global.settings.sidecar_storage_mode = originalMode;
    vi.restoreAllMocks();
  });

  async function renderModal(model) {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(model, 'loras');
  }

  it('renders the metadata location button only in centralized sidecar mode', async () => {
    state.global.settings.sidecar_storage_mode = 'centralized';
    await renderModal(makeModel());

    const button = document.querySelector('[data-action="open-sidecar-location"]');
    expect(button).not.toBeNull();
    expect(button.dataset.filepath).toBe(MODEL_PATH);
  });

  it.each(['alongside', '', undefined])('hides the button when sidecar mode is %s', async (mode) => {
    state.global.settings.sidecar_storage_mode = mode;
    await renderModal(makeModel());

    expect(document.querySelector('[data-action="open-sidecar-location"]')).toBeNull();
  });

  it('posts the model file path to the sidecar endpoint on click', async () => {
    state.global.settings.sidecar_storage_mode = 'centralized';
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
    await renderModal(makeModel());

    document.querySelector('[data-action="open-sidecar-location"]').click();
    await vi.waitFor(() => expect(showToast).toHaveBeenCalled());

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/models/open-sidecar-location',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ file_path: MODEL_PATH }),
      })
    );
    expect(showToast).toHaveBeenCalledWith('modals.model.openSidecarLocation.success', {}, 'success');
  });

  it('copies the resolved sidecar path in clipboard mode', async () => {
    state.global.settings.sidecar_storage_mode = 'centralized';
    const sidecarPath = '/sidecars/loras-abcd1234/flux/model.metadata.json';
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, mode: 'clipboard', path: sidecarPath }),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await renderModal(makeModel());

    document.querySelector('[data-action="open-sidecar-location"]').click();
    await vi.waitFor(() => expect(showToast).toHaveBeenCalled());

    expect(writeText).toHaveBeenCalledWith(sidecarPath);
    expect(showToast).toHaveBeenCalledWith(
      'modals.model.openSidecarLocation.copied',
      { path: sidecarPath },
      'success'
    );
  });

  it('shows an error toast when the endpoint fails', async () => {
    state.global.settings.sidecar_storage_mode = 'centralized';
    global.fetch.mockResolvedValue({ ok: false, status: 404 });
    await renderModal(makeModel());

    document.querySelector('[data-action="open-sidecar-location"]').click();
    await vi.waitFor(() => expect(showToast).toHaveBeenCalled());

    expect(showToast).toHaveBeenCalledWith('modals.model.openSidecarLocation.failed', {}, 'error');
  });
});
