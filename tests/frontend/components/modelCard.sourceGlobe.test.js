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

function makeModel(overrides = {}) {
  return {
    sha256: 'abc123',
    file_path: '/models/loras/linked.safetensors',
    model_name: 'Linked LoRA',
    file_name: 'linked',
    folder: '',
    modified: 1234567890,
    file_size: 1024,
    notes: '',
    base_model: '',
    favorite: false,
    exclude: false,
    from_civitai: true,
    hf_url: '',
    update_available: false,
    skip_metadata_refresh: false,
    preview_url: '',
    preview_nsfw_level: 0,
    tags: [],
    civitai: {},
    ...overrides,
  };
}

function mountCard(createModelCard, model) {
  document.body.innerHTML = '<div id="modelGrid"></div>';
  const card = createModelCard(model, 'loras');
  document.getElementById('modelGrid').appendChild(card);
  return card;
}

describe('ModelCard source globe (#1094)', () => {
  let createModelCard;
  let setupModelCardEventDelegation;
  let openCivitai;
  let openHuggingFace;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ createModelCard, setupModelCardEventDelegation } = await import(MODEL_CARD_MODULE));
    ({ openCivitai, openHuggingFace } = await import(UI_HELPERS_MODULE));
    openCivitai.mockReset();
    openHuggingFace.mockReset();
  });

  it('points the globe at CivitAI when CivitAI data is present alongside an HF link', () => {
    const card = mountCard(
      createModelCard,
      makeModel({
        civitai: { id: 111, modelId: 222, name: 'v1' },
        hf_url: 'https://huggingface.co/user/repo',
      })
    );

    expect(card.dataset.has_civitai).toBe('true');
    expect(card.querySelector('.fa-globe').getAttribute('title')).toBe('View on Civitai');
  });

  it('keeps the CivitAI globe target when from_civitai is false but CivitAI data exists', () => {
    // Regression for case 1: linking HF no longer hides CivitAI.
    const card = mountCard(
      createModelCard,
      makeModel({
        from_civitai: false,
        civitai: { id: 111, modelId: 222 },
        hf_url: 'https://huggingface.co/user/repo',
      })
    );

    expect(card.dataset.has_civitai).toBe('true');
    expect(card.querySelector('.fa-globe').getAttribute('title')).toBe('View on Civitai');
  });

  it('points the globe at HuggingFace for an HF-only model', () => {
    const card = mountCard(
      createModelCard,
      makeModel({ from_civitai: false, civitai: {}, hf_url: 'https://huggingface.co/user/repo' })
    );

    expect(card.dataset.has_civitai).toBe('false');
    expect(card.querySelector('.fa-globe').getAttribute('title')).toBe('View on Hugging Face');
  });

  it('disables the globe when there is no CivitAI data and no HF link', () => {
    const card = mountCard(createModelCard, makeModel({ civitai: {} }));
    const globe = card.querySelector('.fa-globe');

    expect(card.dataset.has_civitai).toBe('false');
    expect(globe.getAttribute('style')).toContain('cursor: not-allowed');
  });

  it('opens CivitAI when the globe is clicked on a dual-source model', () => {
    const model = makeModel({
      civitai: { id: 111, modelId: 222 },
      hf_url: 'https://huggingface.co/user/repo',
    });
    const card = mountCard(createModelCard, model);
    setupModelCardEventDelegation('loras');

    card.querySelector('.fa-globe').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(openCivitai).toHaveBeenCalledWith(model.file_path);
    expect(openHuggingFace).not.toHaveBeenCalled();
  });

  it('opens HuggingFace when the globe is clicked on an HF-only model', () => {
    const model = makeModel({
      from_civitai: false,
      civitai: {},
      hf_url: 'https://huggingface.co/user/repo',
    });
    const card = mountCard(createModelCard, model);
    setupModelCardEventDelegation('loras');

    card.querySelector('.fa-globe').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(openHuggingFace).toHaveBeenCalledWith('https://huggingface.co/user/repo');
    expect(openCivitai).not.toHaveBeenCalled();
  });

  it('points the globe at ModelScope for a ModelScope-linked model', () => {
    const card = mountCard(
      createModelCard,
      makeModel({
        from_civitai: false,
        civitai: {},
        source_platform: 'modelscope',
        source_url: 'https://modelscope.cn/models/user/repo',
      })
    );

    expect(card.dataset.has_civitai).toBe('false');
    expect(card.dataset.source_platform).toBe('modelscope');
    expect(card.dataset.hf_url).toBe('');
    expect(card.querySelector('.fa-globe').getAttribute('title')).toBe('View on ModelScope');
  });

  it('opens the ModelScope page when the globe is clicked', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => {});
    const card = mountCard(
      createModelCard,
      makeModel({
        from_civitai: false,
        civitai: {},
        source_platform: 'modelscope',
        source_url: 'https://modelscope.cn/models/user/repo',
      })
    );
    setupModelCardEventDelegation('loras');

    card.querySelector('.fa-globe').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(openSpy).toHaveBeenCalledWith(
      'https://modelscope.cn/models/user/repo',
      '_blank',
      'noopener,noreferrer'
    );
    expect(openCivitai).not.toHaveBeenCalled();
    expect(openHuggingFace).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it('points the globe at TensorArt for a TensorArt-linked model', () => {
    const card = mountCard(
      createModelCard,
      makeModel({
        from_civitai: false,
        civitai: {},
        source_platform: 'tensorart',
        source_url: 'https://tensor.art/models/827823520299086029',
      })
    );

    expect(card.querySelector('.fa-globe').getAttribute('title')).toBe('View on TensorArt');
  });
});
