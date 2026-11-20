import { describe, it, expect, vi, beforeEach } from 'vitest';

const {
  MODEL_CARD_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  API_FACTORY_MODULE,
} = vi.hoisted(() => ({
  MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
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

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({})),
}));

function createModel(overrides = {}) {
  return {
    sha256: 'abc123',
    file_path: '/models/vae/test_vae.safetensors',
    model_name: 'Test Model',
    file_name: 'test_model',
    folder: 'vae',
    modified: 1234567890,
    file_size: 1024,
    notes: '',
    base_model: '',
    favorite: false,
    exclude: false,
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

describe('ModelCard sub-type badges on pages that mix sub-types', () => {
  let createModelCard;

  beforeEach(async () => {
    ({ createModelCard } = await import(MODEL_CARD_MODULE));
  });

  it.each([
    ['vae', 'VAE', 'VAE'],
    ['upscaler', 'UPS', 'Upscaler'],
    ['text_encoder', 'TE', 'Text Encoder'],
    ['clip_vision', 'CV', 'CLIP Vision'],
    ['controlnet', 'CN', 'ControlNet'],
  ])('renders the %s badge abbreviation and tooltip', (subType, abbreviation, displayName) => {
    const card = createModelCard(createModel({ sub_type: subType }), 'other');

    const badge = card.querySelector('.model-sub-type');
    expect(badge).not.toBeNull();
    expect(badge.textContent).toBe(abbreviation);

    const label = card.querySelector('.base-model-label');
    expect(label.getAttribute('title')).toContain(displayName);
  });

  it('keeps the sub-type token on the LoRAs page, where sub-types vary', () => {
    const card = createModelCard(
      createModel({ sub_type: 'locon', base_model: 'SDXL 1.0' }),
      'loras',
    );

    expect(card.querySelector('.model-sub-type').textContent).toBe('LyCO');
    expect(card.querySelector('.model-base-type').textContent).toBe('XL');
    expect(card.querySelector('.model-separator')).not.toBeNull();
    expect(card.querySelector('.base-model-label').getAttribute('title')).toBe('LyCORIS | SDXL 1.0');
  });

  it('keeps the sub-type token on the checkpoints page, where sub-types vary', () => {
    const card = createModelCard(
      createModel({ sub_type: 'diffusion_model', base_model: 'Flux.1 D' }),
      'checkpoints',
    );

    expect(card.querySelector('.model-sub-type').textContent).toBe('DM');
    expect(card.querySelector('.base-model-label').getAttribute('title')).toBe('Diffusion Model | Flux.1 D');
  });

  it('keeps the token for page types that are not registered in MODEL_CONFIG', () => {
    const card = createModelCard(createModel({ sub_type: 'vae' }), 'unregistered-page');

    expect(card.querySelector('.model-sub-type')).not.toBeNull();
  });

  it('stores sub_type on the card dataset', () => {
    const card = createModelCard(createModel({ sub_type: 'text_encoder' }), 'other');

    expect(card.dataset.sub_type).toBe('text_encoder');
  });
});

describe('ModelCard sub-type badges on single-sub-type pages', () => {
  let createModelCard;

  beforeEach(async () => {
    ({ createModelCard } = await import(MODEL_CARD_MODULE));
  });

  it.each([
    ['embeddings', 'embedding', 'SDXL 1.0', 'XL'],
    ['workflows', 'workflow', 'Flux.1 D', 'F1D'],
    ['wildcards', 'wildcard', 'Illustrious', 'IL'],
  ])('drops the redundant token on %s cards', (pageType, subType, baseModel, baseAbbreviation) => {
    const card = createModelCard(createModel({ sub_type: subType, base_model: baseModel }), pageType);

    expect(card.querySelector('.model-sub-type')).toBeNull();
    expect(card.querySelector('.model-separator')).toBeNull();
    expect(card.querySelector('.model-base-type').textContent).toBe(baseAbbreviation);

    // The tooltip still names the full base model, without repeating the page type.
    const label = card.querySelector('.base-model-label');
    expect(label.getAttribute('title')).toBe(baseModel);
  });

  it('keeps the wildcard sub-type available on the card dataset for other consumers', () => {
    const card = createModelCard(
      createModel({ sub_type: 'wildcard', base_model: 'Illustrious' }),
      'wildcards',
    );

    expect(card.dataset.sub_type).toBe('wildcard');
  });
});
