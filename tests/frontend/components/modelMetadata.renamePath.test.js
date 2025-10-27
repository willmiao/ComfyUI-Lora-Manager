import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  METADATA_MODULE,
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
  METADATA_MODULE: new URL('../../../static/js/components/shared/ModelMetadata.js', import.meta.url).pathname,
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

describe('Model metadata interactions keep file path in sync', () => {
  let getModelApiClient;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ getModelApiClient } = await import(API_FACTORY));
    getModelApiClient.mockReset();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('updates modal references after renaming the model file', async () => {
    const renameModelFile = vi.fn().mockResolvedValue({
      success: true,
      new_file_path: 'new/models/Qwen.testing.safetensors',
    });

    getModelApiClient.mockReturnValue({
      renameModelFile,
      saveModelMetadata: vi.fn(),
    });

    document.body.innerHTML = `
      <div id="modelModal" data-file-path="models/Qwen.safetensors"></div>
      <div class="model-name-header">
        <h2 class="model-name-content" data-file-path="models/Qwen.safetensors">Qwen</h2>
        <button class="edit-model-name-btn"></button>
      </div>
      <div class="base-model-display">
        <span class="base-model-content" data-file-path="models/Qwen.safetensors">SDXL</span>
        <button class="edit-base-model-btn"></button>
      </div>
      <div class="file-name-wrapper">
        <span class="file-name-content" data-file-path="models/Qwen.safetensors">Qwen</span>
        <button class="edit-file-name-btn"></button>
      </div>
      <div class="model-tags-container">
        <div class="model-tags-compact"></div>
        <div class="tooltip-content"></div>
        <button class="edit-tags-btn" data-file-path="models/Qwen.safetensors"></button>
      </div>
      <button class="edit-trigger-words-btn" data-file-path="models/Qwen.safetensors"></button>
      <div data-action="open-file-location" data-filepath="models/Qwen.safetensors"></div>
    `;

    const { setupFileNameEditing } = await import(METADATA_MODULE);

    setupFileNameEditing('models/Qwen.safetensors');

    const fileNameContent = document.querySelector('.file-name-content');
    fileNameContent.setAttribute('contenteditable', 'true');
    fileNameContent.dataset.originalValue = 'Qwen';
    fileNameContent.textContent = 'Qwen.testing';

    fileNameContent.dispatchEvent(new FocusEvent('blur'));

    await vi.waitFor(() => {
      expect(renameModelFile).toHaveBeenCalledWith('models/Qwen.safetensors', 'Qwen.testing');
    });
    await Promise.resolve();
    await renameModelFile.mock.results[0].value;
    expect(document.getElementById('modelModal').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('.model-name-content').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('.base-model-content').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('.file-name-content').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('.edit-tags-btn').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('.edit-trigger-words-btn').dataset.filePath).toBe('new/models/Qwen.testing.safetensors');
    expect(document.querySelector('[data-action="open-file-location"]').dataset.filepath).toBe('new/models/Qwen.testing.safetensors');
  });

  it('uses the latest file path when saving notes', async () => {
    const saveModelMetadata = vi.fn().mockResolvedValue({ success: true });
    const fetchModelMetadata = vi.fn().mockResolvedValue(null);

    getModelApiClient.mockReturnValue({
      fetchModelMetadata,
      saveModelMetadata,
    });

    const { showModelModal } = await import(MODAL_MODULE);

    await showModelModal(
      {
        model_name: 'Qwen',
        file_path: 'models/Qwen.safetensors',
        file_name: 'Qwen.safetensors',
        civitai: {},
      },
      'loras',
    );

    const modalElement = document.getElementById('modelModal');
    modalElement.dataset.filePath = 'models/Qwen.testing.safetensors';

    const notesContent = document.querySelector('.notes-content');
    notesContent.textContent = 'Updated notes';
    notesContent.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    await vi.waitFor(() => {
      expect(saveModelMetadata).toHaveBeenCalledWith('models/Qwen.testing.safetensors', { notes: 'Updated notes' });
    });
  });
});
