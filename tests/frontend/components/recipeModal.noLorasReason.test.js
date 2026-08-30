import { describe, it, beforeEach, expect, vi } from 'vitest';

const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

const loadingManagerStub = {
  showSimpleLoading: vi.fn(),
  hide: vi.fn(),
  show: vi.fn(),
  restoreProgressBar: vi.fn(),
};

const virtualScrollerStub = {
  updateSingleItem: vi.fn(),
  getNavigationState: vi.fn(() => ({
    index: 0,
    hasPrev: false,
    hasNext: false,
    loadedItems: 1,
    totalItems: 1,
  })),
  getAdjacentItemByFilePath: vi.fn(async () => null),
};

const stateStub = {
  global: { settings: {}, loadingManager: loadingManagerStub },
  loadingManager: loadingManagerStub,
  virtualScroller: virtualScrollerStub,
};

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
  sendModelPathToWorkflow: vi.fn(),
  openCivitaiByMetadata: vi.fn(),
  stripLoraTags: vi.fn((text) => text),
  sendPromptToWorkflow: vi.fn(),
  sendGenParamsToWorkflow: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  setSessionItem: vi.fn(),
  removeSessionItem: vi.fn(),
  getStorageItem: vi.fn(() => null),
  setStorageItem: vi.fn(),
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  fetchRecipeDetails: vi.fn(),
  updateRecipeMetadata: vi.fn(() => Promise.resolve({ success: true })),
  sendRecipeWorkflow: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

function recipeModalFixture() {
  return `
    <div id="recipeModal" class="modal">
      <div class="modal-content">
        <header class="recipe-modal-header">
          <h2 id="recipeModalTitle">Recipe Details</h2>
          <div id="recipeTagsContainer"></div>
        </header>
        <div class="modal-body">
          <div class="recipe-media-column">
            <div class="recipe-preview-container" id="recipePreviewContainer">
              <img id="recipeModalImage" src="" alt="Recipe Preview" class="recipe-preview-media">
            </div>
          </div>
          <div class="info-section recipe-bottom-section">
            <div class="recipe-section-actions">
              <span id="recipeLorasCount"></span>
              <button class="action-btn view-loras-btn" id="viewRecipeLorasBtn"></button>
            </div>
            <div class="recipe-loras-list" id="recipeLorasList"></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

describe('RecipeModal no-LoRA reason panel', () => {
  let recipeModal;

  beforeEach(async () => {
    vi.clearAllMocks();
    document.body.innerHTML = recipeModalFixture();
    const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
    recipeModal = new RecipeModal();
  });

  function sync(recipe) {
    recipeModal.syncResourcesSection(recipe);
    return document.getElementById('recipeLorasList');
  }

  it('shows the base message only when generation genuinely used no LoRAs', () => {
    const list = sync({
      id: 'r1',
      loras: [],
      import_info: { channel: 'url', reason: 'no_loras_used' },
    });

    expect(list.querySelector('.no-loras')).not.toBeNull();
    expect(list.textContent).toContain('No LoRAs associated with this recipe');
    expect(list.querySelector('details.no-loras-reason')).toBeNull();
  });

  it('renders a collapsed reason panel from recorded import_info', () => {
    const list = sync({
      id: 'r2',
      loras: [],
      import_info: {
        channel: 'batch_import_url',
        reason: 'api_meta_no_lora_resources',
        details: {
          api_meta_keys: ['prompt'],
          api_model_version_ids: 0,
          exif_present: false,
        },
      },
    });

    const details = list.querySelector('details.no-loras-reason');
    expect(details).not.toBeNull();
    // Collapsed by default (no `open` attribute).
    expect(details.hasAttribute('open')).toBe(false);
    expect(details.querySelector('summary').textContent).toContain('Why no LoRAs?');

    const body = details.querySelector('.no-loras-reason-body');
    expect(body.textContent).toContain('Batch import (image URL)');
    expect(body.textContent).toContain('The source API returned no LoRA resource data');
    expect(body.textContent).toContain('API metadata fields');
    expect(body.textContent).toContain('prompt');
    expect(body.textContent).toContain('Model version IDs reported');
    expect(body.textContent).toContain('Embedded metadata');
    // Recorded diagnostics are not labeled as inferred.
    expect(body.querySelector('.no-loras-inferred-note')).toBeNull();
  });

  it('infers a possible reason for legacy URL recipes without import_info', () => {
    const list = sync({
      id: 'r3',
      loras: [],
      source_path: 'https://civitai.red/images/139995974',
      gen_params: { prompt: 'a castle' },
    });

    const details = list.querySelector('details.no-loras-reason');
    expect(details).not.toBeNull();
    const body = details.querySelector('.no-loras-reason-body');
    expect(body.textContent).toContain('The source API returned no LoRA resource data');
    // Heuristic results must be labeled as inferred.
    expect(body.querySelector('.no-loras-inferred-note')).not.toBeNull();
  });

  it('reports missing embedded metadata for legacy local recipes with no params', () => {
    const list = sync({
      id: 'r4',
      loras: [],
      source_path: '/data/images/photo.png',
      gen_params: {},
    });

    const details = list.querySelector('details.no-loras-reason');
    expect(details).not.toBeNull();
    expect(details.querySelector('.no-loras-reason-body').textContent).toContain(
      'The image has no embedded generation metadata'
    );
  });

  it('does not show the panel for legacy local recipes with complete params', () => {
    const list = sync({
      id: 'r5',
      loras: [],
      source_path: '/data/images/photo.png',
      gen_params: { prompt: 'a castle', steps: 20, seed: 42 },
    });

    expect(list.querySelector('details.no-loras-reason')).toBeNull();
  });

  it('flags ComfyUI workflow sources via has_workflow', () => {
    const list = sync({
      id: 'r6',
      loras: [],
      has_workflow: true,
    });

    const details = list.querySelector('details.no-loras-reason');
    expect(details).not.toBeNull();
    expect(details.querySelector('.no-loras-reason-body').textContent).toContain(
      'ComfyUI workflow'
    );
  });

  it('escapes HTML in recorded diagnostic values', () => {
    const list = sync({
      id: 'r7',
      loras: [],
      import_info: {
        channel: 'url',
        reason: 'api_meta_no_lora_resources',
        details: { api_meta_keys: ['<img src=x onerror=alert(1)>'] },
      },
    });

    const details = list.querySelector('details.no-loras-reason');
    expect(details).not.toBeNull();
    expect(details.innerHTML).not.toContain('<img src=x');
    expect(details.textContent).toContain('<img src=x onerror=alert(1)>');
  });
});
