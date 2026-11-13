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
    model_name: 'Offline Model',
    file_path: 'models/offline.safetensors',
    file_name: 'offline.safetensors',
    civitai: {
      modelId: 7,
      name: 'v1.0',
      creator: { username: 'artist' },
    },
    ...overrides,
  };
}

describe('Model modal metadata fallback', () => {
  let getModelApiClient;
  let fetchModelMetadataWithStatus;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    getModelApiClient.mockReset();
    fetchModelMetadataWithStatus = vi.fn();
    getModelApiClient.mockReturnValue({
      fetchModelMetadataWithStatus,
      saveModelMetadata: vi.fn(),
    });
  });

  async function renderModal(model) {
    const { showModelModal } = await import(MODAL_MODULE);
    await showModelModal(model, 'loras');
    return document.getElementById('modelModal');
  }

  it('merges the cached payload into the list-level civitai data', async () => {
    fetchModelMetadataWithStatus.mockResolvedValue({
      metadata: {
        name: 'v2.0',
        creator: { username: 'artist' },
      },
      partial: true,
      offline: true,
    });

    const modal = await renderModal(makeModel());

    expect(modal.querySelector('.version-name-content').textContent).toBe('v2.0');
    expect(modal.querySelector('.creator-username').textContent).toBe('artist');
    // The list payload's model id must survive a partial response.
    expect(modal.querySelector('.civitai-id-entry .model-hash-value').textContent).toBe('7');
  });

  it('shows the offline notice and flags the modal for the description tab', async () => {
    fetchModelMetadataWithStatus.mockResolvedValue({
      metadata: { name: 'v2.0' },
      partial: true,
      offline: true,
    });

    const modal = await renderModal(makeModel());

    const notice = modal.querySelector('.modal-metadata-notice');
    expect(notice).not.toBeNull();
    expect(notice.classList.contains('modal-metadata-notice--offline')).toBe(true);
    expect(notice.textContent).toContain('offline');
    expect(modal.dataset.metadataOffline).toBe('true');
    expect(modal.dataset.metadataPartial).toBe('true');
  });

  it('shows the partial notice when the sidecar is unreadable but the disk is online', async () => {
    fetchModelMetadataWithStatus.mockResolvedValue({
      metadata: {},
      partial: true,
      offline: false,
    });

    const modal = await renderModal(makeModel());

    const notice = modal.querySelector('.modal-metadata-notice');
    expect(notice).not.toBeNull();
    expect(notice.classList.contains('modal-metadata-notice--offline')).toBe(false);
    expect(notice.textContent).toContain('could not be read');
    expect(modal.dataset.metadataOffline).toBe('false');
  });

  it('renders no notice for complete metadata', async () => {
    fetchModelMetadataWithStatus.mockResolvedValue({
      metadata: { name: 'v1.0', description: 'About' },
      partial: false,
      offline: false,
    });

    const modal = await renderModal(makeModel());

    expect(modal.querySelector('.modal-metadata-notice')).toBeNull();
    expect(modal.dataset.metadataOffline).toBe('false');
  });

  it('keeps the list data when the metadata request fails outright', async () => {
    fetchModelMetadataWithStatus.mockRejectedValue(new Error('boom'));

    const modal = await renderModal(makeModel());

    expect(modal.querySelector('.creator-username').textContent).toBe('artist');
    expect(modal.querySelector('.modal-metadata-notice')).toBeNull();
  });
});
