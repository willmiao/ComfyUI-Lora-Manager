import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

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
        model_card_footer_action: 'example_images',
      },
    },
    pages: {
      other: {
        previewVersions: new Map(),
        sortBy: 'name',
      },
    },
    bulkMode: false,
    selectedModels: new Set(),
    selectedLoras: new Set(),
  },
  getCurrentPageState: vi.fn(() => ({
    sortBy: 'name',
    previewVersions: new Map(),
  })),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
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
  translate: vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key)),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings', OTHER: 'other' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({})),
}));

class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function createModel(overrides = {}) {
  return {
    sha256: 'abc123',
    file_path: '/models/vae/test_vae.safetensors',
    model_name: 'Test VAE',
    file_name: 'test_vae',
    folder: 'vae',
    modified: 1234567890,
    file_size: 1024,
    notes: '',
    base_model: '',
    favorite: false,
    exclude: false,
    hf_url: '',
    update_available: false,
    skip_metadata_refresh: false,
    preview_url: '',
    preview_nsfw_level: 0,
    tags: [],
    civitai: {},
    sub_type: 'vae',
    ...overrides,
  };
}

describe('ModelCard preview media type', () => {
  let createModelCard;
  let pauseSpy;

  beforeEach(async () => {
    global.IntersectionObserver = MockIntersectionObserver;
    pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    ({ createModelCard } = await import(MODEL_CARD_MODULE));
  });

  afterEach(() => {
    pauseSpy.mockRestore();
    delete global.IntersectionObserver;
  });

  it('renders a video element for a versioned mp4 preview URL', () => {
    const previewUrl = '/api/lm/previews?path=%2Fhome%2Fmodels%2Fvae%2Ftest_vae.mp4&v=1781613851611650515';
    const card = createModelCard(createModel({ preview_url: previewUrl }), 'other');

    const video = card.querySelector('.card-preview video');
    expect(video).not.toBeNull();
    expect(video.dataset.src).toBe(previewUrl);
    expect(card.querySelector('.card-preview img')).toBeNull();
  });

  it('renders a video element for a versioned webm preview URL', () => {
    const previewUrl = '/api/lm/previews?path=%2Fhome%2Fmodels%2Fvae%2Ftest_vae.webm&v=1781613851611650515';
    const card = createModelCard(createModel({ preview_url: previewUrl }), 'other');

    expect(card.querySelector('.card-preview video')).not.toBeNull();
  });

  it('keeps rendering an image for a versioned image preview URL', () => {
    const previewUrl = '/api/lm/previews?path=%2Fhome%2Fmodels%2Fvae%2Ftest_vae.jpeg&v=1781613851611650515';
    const card = createModelCard(createModel({ preview_url: previewUrl }), 'other');

    const img = card.querySelector('.card-preview img');
    expect(img).not.toBeNull();
    expect(img.getAttribute('src')).toBe(previewUrl);
    expect(card.querySelector('.card-preview video')).toBeNull();
  });

  it('renders a video element for a plain mp4 preview path', () => {
    const card = createModelCard(createModel({ preview_url: '/models/vae/test_vae.mp4' }), 'other');

    expect(card.querySelector('.card-preview video')).not.toBeNull();
  });
});
