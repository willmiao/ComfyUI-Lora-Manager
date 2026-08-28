import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => {
  if (typeof fallback !== 'string') {
    return key;
  }
  return fallback.replace(/\{(\w+)\}/g, (match, name) =>
    params && params[name] != null ? String(params[name]) : match
  );
});

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

const modalManagerMock = {
  showModal: vi.fn(),
  closeModal: vi.fn(),
};

const downloadVersionWithDefaultsMock = vi.fn(() => Promise.resolve());

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
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
  getSessionItem: vi.fn(() => null),
  getStorageItem: vi.fn(() => null),
  setStorageItem: vi.fn(),
  removeStorageItem: vi.fn(),
}));

const fetchRecipeDetailsMock = vi.fn(() => Promise.resolve({}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  fetchRecipeDetails: fetchRecipeDetailsMock,
  updateRecipeMetadata: vi.fn(() => Promise.resolve({ success: true })),
  sendRecipeWorkflow: vi.fn(),
  extractRecipeId: (filePath) => {
    if (!filePath) return null;
    const basename = filePath.split('/').pop().split('\\').pop();
    const dotIndex = basename.lastIndexOf('.');
    return dotIndex > 0 ? basename.substring(0, dotIndex) : basename;
  },
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
  },
}));

vi.mock('../../../static/js/managers/DownloadManager.js', () => ({
  downloadManager: {
    downloadVersionWithDefaults: downloadVersionWithDefaultsMock,
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
            <div id="recipeCheckpoint"></div>
            <div id="recipeResourceDivider"></div>
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

const missingLora = {
  name: 'gone-lora',
  modelName: 'Gone LoRA',
  inLibrary: false,
  modelId: 123,
  id: 456,
};

const hashOnlyLora = {
  name: 'hash-lora',
  modelName: 'Hash LoRA',
  inLibrary: false,
  hash: 'deadbeefcafe',
};

const recipeWithResources = {
  id: 'recipe-resources',
  file_path: '/recipes/resources.json',
  title: 'Resource Recipe',
  tags: [],
  checkpoint: {
    name: 'gone-checkpoint',
    inLibrary: false,
    modelId: 900,
    id: 901,
  },
  loras: [
    { name: 'present-lora', modelName: 'Present LoRA', inLibrary: true, hash: 'ABC123' },
    missingLora,
    { name: 'deleted-lora', modelName: 'Deleted LoRA', inLibrary: false, isDeleted: true },
    { name: 'mystery-lora', modelName: 'Mystery LoRA', inLibrary: false },
    hashOnlyLora,
  ],
};

const createdModals = [];

async function createRecipeModal() {
  const { RecipeModal } = await import('../../../static/js/components/RecipeModal.js');
  const recipeModal = new RecipeModal();
  createdModals.push(recipeModal);
  return recipeModal;
}

function flushWiring() {
  // Item action/navigation wiring happens in a setTimeout after rendering
  return new Promise(resolve => setTimeout(resolve, 150));
}

describe('RecipeModal resource item interactions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // clearAllMocks keeps one-off mockResolvedValue implementations; reset
    // the shared mocks to their defaults explicitly.
    downloadVersionWithDefaultsMock.mockReset();
    downloadVersionWithDefaultsMock.mockResolvedValue(undefined);
    fetchRecipeDetailsMock.mockReset();
    // Hydration re-fetches the recipe right after render; resolving an empty
    // object would delete currentRecipe.loras and wipe the list, so resolve
    // the full recipe by default (individual tests can override afterwards).
    fetchRecipeDetailsMock.mockResolvedValue(recipeWithResources);
    document.body.innerHTML = recipeModalFixture();
    global.modalManager = modalManagerMock;
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({}),
    }));
  });

  afterEach(() => {
    createdModals.forEach(recipeModal => recipeModal.cleanupNavigationShortcuts());
    createdModals.length = 0;
    document.body.innerHTML = '';
    delete global.modalManager;
    delete global.fetch;
  });

  it('renders the missing badge as a pure status indicator with a tooltip', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);

    const badge = document.querySelector('.recipe-lora-item.missing-locally .missing-badge');
    expect(badge).not.toBeNull();
    expect(badge.tagName).toBe('DIV');
    expect(badge.title).toBe('This model is not in your library');
    expect(badge.classList.contains('reconnectable')).toBe(false);
    expect(badge.textContent).toContain('Not in Library');
  });

  it('renders an explicit download action and an inline title link for a missing LoRA', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);

    const item = document.querySelector('.recipe-lora-item.missing-locally:not(.checkpoint-item)');

    // The Civitai link belongs to the title, not the action row
    const link = item.querySelector('.recipe-lora-title a.recipe-civitai-link');
    expect(link).not.toBeNull();
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
    expect(link.href).toBe('https://civitai.com/models/123?modelVersionId=456');
    expect(link.title).toBe('View on Civitai');

    const actions = item.querySelector('.recipe-lora-actions');
    expect(actions).not.toBeNull();

    const downloadButton = actions.querySelector('.lora-download');
    expect(downloadButton).not.toBeNull();
    expect(downloadButton.tagName).toBe('BUTTON');
    expect(downloadButton.type).toBe('button');
    expect(downloadButton.classList.contains('resource-action')).toBe(true);
    expect(downloadButton.classList.contains('primary')).toBe(true);
    expect(downloadButton.title).toBe('Download this LoRA');

    // The action row holds only real actions; no link icon in it
    expect(actions.querySelector('.recipe-civitai-link')).toBeNull();
  });

  it('downloads only the clicked LoRA via the download manager', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const downloadButton = document.querySelector('.lora-download');
    downloadButton.click();
    await vi.waitFor(() => {
        expect(downloadVersionWithDefaultsMock).toHaveBeenCalledTimes(1);
    });

    expect(downloadVersionWithDefaultsMock).toHaveBeenCalledWith(
      'loras',
      123,
      456,
      expect.objectContaining({ source: 'recipe-modal' })
    );
  });

  it('does not navigate when a missing LoRA row is clicked', async () => {
    const recipeModal = await createRecipeModal();
    const navigateSpy = vi
      .spyOn(recipeModal, 'navigateToLorasPage')
      .mockImplementation(() => {});
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const missingItem = document.querySelector('.recipe-lora-item.missing-locally');
    expect(missingItem.getAttribute('role')).toBeNull();
    expect(missingItem.getAttribute('tabindex')).toBeNull();

    missingItem.click();
    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('keeps in-library rows navigable and keyboard accessible', async () => {
    const recipeModal = await createRecipeModal();
    const navigateSpy = vi
      .spyOn(recipeModal, 'navigateToLorasPage')
      .mockImplementation(() => {});
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const localItem = document.querySelector('.recipe-lora-item.exists-locally:not(.checkpoint-item)');
    expect(localItem.getAttribute('role')).toBe('button');
    expect(localItem.getAttribute('tabindex')).toBe('0');

    localItem.click();
    expect(navigateSpy).toHaveBeenCalledWith(0);

    navigateSpy.mockClear();
    localItem.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(navigateSpy).toHaveBeenCalledWith(0);
  });

  it('renders deleted LoRAs with a status badge and an explicit reconnect button', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const deletedItem = document.querySelector('.recipe-lora-item.is-deleted');
    const badge = deletedItem.querySelector('.deleted-badge');
    expect(badge).not.toBeNull();
    expect(badge.classList.contains('reconnectable')).toBe(false);
    expect(badge.title).toContain('deleted from the source');

    const reconnectButton = deletedItem.querySelector('.lora-reconnect');
    expect(reconnectButton).not.toBeNull();
    expect(reconnectButton.tagName).toBe('BUTTON');
    expect(reconnectButton.classList.contains('ghost')).toBe(true);

    reconnectButton.click();
    const container = deletedItem.querySelector('.lora-reconnect-container');
    expect(container.classList.contains('active')).toBe(true);
  });

  it('renders no action row when neither identifiers nor hash are available', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);

    const mysteryItem = document.querySelector('[data-lora-index="3"]');
    expect(mysteryItem.querySelector('.lora-download')).toBeNull();
    // No actions at all -> no empty action row taking vertical space
    expect(mysteryItem.querySelector('.recipe-lora-actions')).toBeNull();

    // The name-fallback search link still sits inline in the title
    const link = mysteryItem.querySelector('.recipe-lora-title a.recipe-civitai-link');
    expect(link).not.toBeNull();
    expect(link.href).toContain('query=Mystery%20LoRA');
  });

  it('offers download for hash-only LoRAs and resolves identifiers on demand', async () => {
    const recipeModal = await createRecipeModal();
    global.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        typeof url === 'string' && url.includes('/civitai/model/hash/')
          ? { id: 789, modelId: 777, name: 'Hash LoRA v1' }
          : {},
    }));
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const hashItem = document.querySelector('[data-lora-index="4"]');
    const downloadButton = hashItem.querySelector('.lora-download');
    expect(downloadButton).not.toBeNull();

    downloadButton.click();
    await vi.waitFor(() => {
      expect(downloadVersionWithDefaultsMock).toHaveBeenCalledTimes(1);
    });

    // Hash resolution needs a network round trip; immediate feedback must
    // appear while the user waits for the progress UI
    expect(loadingManagerStub.showSimpleLoading).toHaveBeenCalledWith('Preparing download...');
    expect(loadingManagerStub.hide).toHaveBeenCalled();

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/lm/loras/civitai/model/hash/deadbeefcafe'
    );
    expect(downloadVersionWithDefaultsMock).toHaveBeenCalledWith(
      'loras',
      777,
      789,
      expect.objectContaining({ source: 'recipe-modal', versionName: 'Hash LoRA v1' })
    );
  });

  it('refreshes the resources section and the recipe card after a successful download', async () => {
    const recipeModal = await createRecipeModal();
    downloadVersionWithDefaultsMock.mockResolvedValue(true);
    const updatedRecipe = {
      ...recipeWithResources,
      loras: recipeWithResources.loras.map((lora, index) =>
        index === 1 ? { ...lora, inLibrary: true } : lora
      ),
    };
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();
    fetchRecipeDetailsMock.mockResolvedValue(updatedRecipe);

    const downloadButton = document.querySelector('.lora-download');
    downloadButton.click();

    await vi.waitFor(() => {
      expect(fetchRecipeDetailsMock).toHaveBeenCalledWith('recipe-resources');
    });

    // The recipe card on the listing page receives the fresh recipe data
    await vi.waitFor(() => {
      expect(virtualScrollerStub.updateSingleItem).toHaveBeenCalledWith(
        '/recipes/resources.json',
        updatedRecipe
      );
    });

    // The modal's resources section re-renders with the flipped status
    await vi.waitFor(() => {
      const item = document.querySelector('[data-lora-index="1"]');
      expect(item.classList.contains('exists-locally')).toBe(true);
      expect(item.querySelector('.local-badge')).not.toBeNull();
      expect(item.querySelector('.missing-badge')).toBeNull();
    });
  });

  it('shows a status badge, download action and Civitai link for a missing checkpoint without row navigation', async () => {
    const recipeModal = await createRecipeModal();
    const navigateSpy = vi
      .spyOn(recipeModal, 'navigateToCheckpointPage')
      .mockImplementation(() => {});
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const checkpointItem = document.querySelector('.checkpoint-item');
    expect(checkpointItem.classList.contains('missing-locally')).toBe(true);
    expect(checkpointItem.getAttribute('role')).toBeNull();

    expect(checkpointItem.querySelector('.missing-badge')).not.toBeNull();
    expect(checkpointItem.querySelector('.checkpoint-download')).not.toBeNull();

    const link = checkpointItem.querySelector('.recipe-lora-title a.recipe-civitai-link');
    expect(link).not.toBeNull();
    expect(link.href).toBe('https://civitai.com/models/900?modelVersionId=901');

    checkpointItem.click();
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
