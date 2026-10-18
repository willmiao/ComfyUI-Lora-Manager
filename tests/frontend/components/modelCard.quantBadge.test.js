import { describe, it, expect, vi, beforeEach } from 'vitest';

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
      checkpoints: {
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
  translate: vi.fn((key, params, fallback) => {
    if (typeof fallback === 'string' && params && 'count' in params) {
      return `${params.count} versions`;
    }
    return typeof fallback === 'string' ? fallback : key;
  }),
}));

vi.mock(API_CONFIG_MODULE, () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings', OTHER: 'other' },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({})),
}));

function createCheckpointModel(overrides = {}) {
  return {
    sha256: 'abc123',
    file_path: '/models/checkpoints/test_ckpt.safetensors',
    model_name: 'Test Checkpoint',
    file_name: 'test_ckpt',
    folder: '',
    modified: 1234567890,
    file_size: 1024,
    notes: '',
    base_model: 'SDXL 1.0',
    favorite: false,
    exclude: false,
    hf_url: '',
    update_available: false,
    skip_metadata_refresh: false,
    preview_url: '',
    preview_nsfw_level: 0,
    tags: [],
    civitai: { name: 'v2.0' },
    sub_type: 'checkpoint',
    ...overrides,
  };
}

describe('ModelCard quantization badge', () => {
  let createModelCard;
  let state;

  beforeEach(async () => {
    ({ createModelCard } = await import(MODEL_CARD_MODULE));
    ({ state } = await import(STATE_MODULE));
    state.global.settings.group_by_model = false;
  });

  it('renders the quant badge after the version name when quantization is set', () => {
    const card = createModelCard(createCheckpointModel({ quantization: 'Q4_K_M' }), 'checkpoints');

    const badge = card.querySelector('.quant-badge');
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe('Q4_K_M');

    const unit = card.querySelector('.badge-version-unit');
    const versionName = unit.querySelector('.version-name');
    expect(versionName).not.toBeNull();
    // Version name stays leftmost; the quant badge follows it
    expect(versionName.nextElementSibling).toBe(badge);
  });

  it('renders the quant badge even without a version name', () => {
    const card = createModelCard(createCheckpointModel({ quantization: 'FP8', civitai: {} }), 'checkpoints');

    const badge = card.querySelector('.quant-badge');
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe('FP8');
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['an empty string', ''],
    ['a non-string value', 8],
  ])('does not render the quant badge when quantization is %s', (_label, quantization) => {
    const card = createModelCard(createCheckpointModel({ quantization }), 'checkpoints');

    expect(card.querySelector('.quant-badge')).toBeNull();
    // Version name must still render on its own
    expect(card.querySelector('.version-name')).not.toBeNull();
  });

  it('suppresses the quant badge in grouped mode (version_count > 1)', () => {
    state.global.settings.group_by_model = true;
    const card = createModelCard(
      createCheckpointModel({ quantization: 'Q4_K_M', version_count: 3 }),
      'checkpoints',
    );

    expect(card.querySelector('.quant-badge')).toBeNull();
    expect(card.querySelector('.version-count-link')).not.toBeNull();
    expect(card.querySelector('.version-name')).toBeNull();
  });
});
