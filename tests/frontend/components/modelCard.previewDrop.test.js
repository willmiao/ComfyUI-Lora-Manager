import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MODEL_CARD_DRAG_MIME_TYPE } from '../../../static/js/utils/constants.js';

const {
  MODEL_CARD_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  API_CONFIG_MODULE,
  API_FACTORY_MODULE,
} = vi.hoisted(() => ({
  MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();
const uploadPreviewMock = vi.fn();

vi.mock(STATE_MODULE, () => ({
  state: {
    settings: {
      blur_mature_content: false,
      model_name_display: 'model_name',
    },
    global: {
      settings: {
        model_name_display: 'model_name',
        group_by_model: false,
        display_density: 'default',
        model_card_footer_action: 'replace_preview',
      },
    },
    pages: {
      loras: {
        previewVersions: new Map(),
        sortBy: 'name',
      },
    },
    bulkMode: false,
    selectedLoras: new Set(),
  },
  getCurrentPageState: vi.fn(() => ({
    sortBy: 'name',
    previewVersions: new Map(),
  })),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
  openCivitai: vi.fn(),
  openHuggingFace: vi.fn(),
  copyToClipboard: vi.fn(),
  copyLoraSyntax: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
  sendEmbeddingToWorkflow: vi.fn(),
  openExampleImagesFolder: vi.fn(),
  buildLoraSyntax: vi.fn(),
  sendModelPathToWorkflow: vi.fn(),
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key) => key),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({ uploadPreview: uploadPreviewMock })),
}));

describe('ModelCard drag & drop preview upload', () => {
  let createModelCard;

  beforeEach(async () => {
    showToastMock.mockReset();
    uploadPreviewMock.mockReset();
    ({ createModelCard } = await import(MODEL_CARD_MODULE));
  });

  function createCard() {
    const model = {
      sha256: 'abc123',
      file_path: '/models/test_lora.safetensors',
      model_name: 'Test LoRA',
      file_name: 'test_lora',
      folder: 'models',
      modified: 1234567890,
      file_size: 1024,
      usage_count: 0,
      notes: '',
      base_model: 'SD1.5',
      favorite: false,
      exclude: false,
      hf_url: '',
      update_available: false,
      skip_metadata_refresh: false,
      preview_url: '',
      preview_nsfw_level: 0,
      tags: [],
      civitai: {},
      sub_type: 'lora',
    };
    return createModelCard(model, 'loras');
  }

  function dispatchDrop(card, files, types = []) {
    const event = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'dataTransfer', { value: { files, types } });
    card.dispatchEvent(event);
    return event;
  }

  it('uploads the dropped image as the model preview', () => {
    const card = createCard();
    const file = new File(['data'], 'preview.png', { type: 'image/png' });

    dispatchDrop(card, [file]);

    expect(uploadPreviewMock).toHaveBeenCalledTimes(1);
    expect(uploadPreviewMock).toHaveBeenCalledWith('/models/test_lora.safetensors', file);
  });

  it('supports MP4 video files', () => {
    const card = createCard();
    const file = new File(['data'], 'preview.mp4', { type: 'video/mp4' });

    dispatchDrop(card, [file]);

    expect(uploadPreviewMock).toHaveBeenCalledTimes(1);
  });

  it('rejects unsupported file types with a toast', () => {
    const card = createCard();
    const file = new File(['data'], 'notes.txt', { type: 'text/plain' });

    dispatchDrop(card, [file]);

    expect(uploadPreviewMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.previewDropInvalid',
      { name: 'notes.txt' },
      'error'
    );
  });

  it('ignores drops without files', () => {
    const card = createCard();

    dispatchDrop(card, []);

    expect(uploadPreviewMock).not.toHaveBeenCalled();
  });

  it('prevents browser default and highlights the card while dragging over', () => {
    const card = createCard();

    const dragOverEvent = new Event('dragover', { bubbles: true, cancelable: true });
    card.dispatchEvent(dragOverEvent);
    expect(dragOverEvent.defaultPrevented).toBe(true);
    expect(card.classList.contains('drag-over')).toBe(true);

    const dragLeaveEvent = new Event('dragleave', { bubbles: true, cancelable: true });
    card.dispatchEvent(dragLeaveEvent);
    expect(dragLeaveEvent.defaultPrevented).toBe(true);
    expect(card.classList.contains('drag-over')).toBe(false);
  });

  it('clears the highlight when the drop completes', () => {
    const card = createCard();
    const file = new File(['data'], 'preview.png', { type: 'image/png' });

    const event = dispatchDrop(card, [file]);

    expect(event.defaultPrevented).toBe(true);
    expect(card.classList.contains('drag-over')).toBe(false);
  });

  it('ignores drops tagged as internal card drags (move-to-folder)', () => {
    const card = createCard();
    const file = new File(['data'], 'preview.png', { type: 'image/png' });

    const event = dispatchDrop(card, [file], [MODEL_CARD_DRAG_MIME_TYPE]);

    expect(uploadPreviewMock).not.toHaveBeenCalled();
    expect(showToastMock).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
    expect(card.classList.contains('drag-over')).toBe(false);
  });

  it('does not highlight or intercept internal card drags during dragover', () => {
    const card = createCard();

    const dragOverEvent = new Event('dragover', { bubbles: true, cancelable: true });
    Object.defineProperty(dragOverEvent, 'dataTransfer', {
      value: { types: [MODEL_CARD_DRAG_MIME_TYPE] },
    });
    card.dispatchEvent(dragOverEvent);

    expect(dragOverEvent.defaultPrevented).toBe(false);
    expect(card.classList.contains('drag-over')).toBe(false);
  });

  it('keeps the card draggable (move-to-folder) but the preview image non-draggable', () => {
    const card = createCard();

    // The card itself must stay draggable for sidebar move-to-folder drags.
    expect(card.draggable).toBe(true);
    // The preview image must not start a native image drag: the browser would
    // synthesize a File payload from it, which the drop handler would mistake
    // for an external preview replacement.
    const img = card.querySelector('.card-preview img');
    expect(img.getAttribute('draggable')).toBe('false');
  });
});
