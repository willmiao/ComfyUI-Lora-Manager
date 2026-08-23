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
    EMBEDDING: 'embeddings'
  }
}));

vi.mock(API_FACTORY, () => ({
  getModelApiClient: vi.fn(),
}));

const SHA256 = 'abcdef1234567890' + 'f'.repeat(48);
const AUTOV3 = '0123456789ab';

function makeModel(overrides = {}) {
  return {
    model_name: 'Hash Model',
    file_path: 'models/hash.safetensors',
    file_name: 'hash.safetensors',
    sha256: SHA256,
    autov3: AUTOV3,
    civitai: {},
    ...overrides,
  };
}

describe('Model modal hash rendering', () => {
  let getModelApiClient;
  let copyToClipboard;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    ({ copyToClipboard } = await import(UI_HELPERS_MODULE));
    getModelApiClient.mockReset();
    copyToClipboard.mockReset();
    getModelApiClient.mockReturnValue({
      fetchModelMetadata: vi.fn().mockResolvedValue(null),
      saveModelMetadata: vi.fn(),
    });
  });

  async function renderModal(model) {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(model, 'loras');
  }

  it('renders sha256 middle-truncated with the full hash in title and copy button', async () => {
    await renderModal(makeModel());

    const hashItem = document.querySelector('.hash-footnote');
    expect(hashItem).not.toBeNull();

    const value = hashItem.querySelector('.model-hash-value');
    expect(value.textContent).toBe(`${SHA256.slice(0, 10)}\u2026${SHA256.slice(-6)}`);
    expect(value.getAttribute('title')).toBe(SHA256);

    const copyBtn = hashItem.querySelector('[data-action="copy-hash"]');
    expect(copyBtn.dataset.hash).toBe(SHA256);
  });

  it('renders autov3 in full', async () => {
    await renderModal(makeModel());

    const rows = document.querySelectorAll('.hash-footnote .hash-entry');
    expect(rows).toHaveLength(2);
    expect(rows[1].querySelector('.model-hash-value').textContent).toBe(AUTOV3);
    expect(rows[1].querySelector('[data-action="copy-hash"]').dataset.hash).toBe(AUTOV3);
  });

  it.each([null, undefined, ''])('hides the autov3 row when autov3 is %s', async (autov3) => {
    await renderModal(makeModel({ autov3 }));

    const rows = document.querySelectorAll('.hash-footnote .hash-entry');
    expect(rows).toHaveLength(1);
    expect(rows[0].querySelector('.hash-kind').textContent).toBe('SHA256');
  });

  it('hides the hashes item entirely when sha256 is empty', async () => {
    await renderModal(makeModel({ sha256: '', autov3: AUTOV3 }));

    expect(document.querySelector('.hash-footnote')).toBeNull();
  });

  it('copies the full hash when the copy button is clicked', async () => {
    await renderModal(makeModel());

    const copyBtn = document.querySelector('.hash-footnote [data-action="copy-hash"]');
    copyBtn.click();

    expect(copyToClipboard).toHaveBeenCalledWith(SHA256, expect.any(String));
  });
});
