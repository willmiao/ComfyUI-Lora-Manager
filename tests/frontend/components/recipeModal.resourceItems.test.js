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
    _lastDownloadError: '',
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

const hashInvalidLora = {
  name: 'invalid-hash-lora',
  modelName: 'Invalid Hash LoRA',
  inLibrary: false,
  hash: 'a2a12bfa01',
  hashInvalid: true,
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
    hashInvalidLora,
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

  it('shows reconnect failures inline in the panel instead of a toast', async () => {
    const recipeModal = await createRecipeModal();
    global.fetch = vi.fn(async (url) => {
      if (String(url).includes('/recipe/lora/reconnect')) {
        return { ok: true, json: async () => ({ success: false, error: 'LoRA not found locally' }) };
      }
      return { ok: true, json: async () => ({}) };
    });
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const deletedItem = document.querySelector('.recipe-lora-item.is-deleted');
    deletedItem.querySelector('.lora-reconnect').click();
    const container = deletedItem.querySelector('.lora-reconnect-container');
    const input = container.querySelector('.reconnect-input');
    const error = container.querySelector('.reconnect-error');
    expect(error).not.toBeNull();

    input.value = 'nonexistent-lora';
    container.querySelector('.reconnect-confirm-btn').click();

    await vi.waitFor(() => {
      expect(error.classList.contains('active')).toBe(true);
    });
    expect(error.textContent).toContain('LoRA not found locally');
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.reconnectFailed',
      expect.anything(),
      'error'
    );

    // Typing again clears the inline error
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(error.classList.contains('active')).toBe(false);
    expect(error.textContent).toBe('');
  });
  it('renders hash-invalid LoRAs with a dedicated badge and reconnect instead of download', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);
    await flushWiring();

    const invalidItem = document.querySelector('[data-lora-index="3"]');
    const badge = invalidItem.querySelector('.invalid-hash-badge');
    expect(badge).not.toBeNull();
    expect(badge.title).toContain('cannot be resolved on CivitAI');
    expect(badge.textContent).toContain('Unresolvable Hash');

    expect(invalidItem.querySelector('.lora-download')).toBeNull();
    const reconnectButton = invalidItem.querySelector('.lora-reconnect');
    expect(reconnectButton).not.toBeNull();

    reconnectButton.click();
    const container = invalidItem.querySelector('.lora-reconnect-container');
    expect(container).not.toBeNull();
    expect(container.classList.contains('active')).toBe(true);
  });

  it('marks the entry hash-invalid when hash resolution returns Model not found', async () => {
    const recipeModal = await createRecipeModal();
    const requests = [];
    // Deep copy so the mark step mutating loras[5].hashInvalid does not
    // leak into the shared fixture used by later tests.
    const isolatedRecipe = JSON.parse(JSON.stringify(recipeWithResources));
    fetchRecipeDetailsMock.mockResolvedValue(isolatedRecipe);
    global.fetch = vi.fn(async (url, options) => {
      requests.push({ url: String(url), options });
      const urlStr = String(url);
      if (urlStr.includes('/civitai/model/hash/')) {
        return { ok: false, json: async () => ({ success: false, error: 'Model not found' }) };
      }
      return { ok: true, json: async () => ({}) };
    });
    recipeModal.showRecipeDetails(isolatedRecipe);
    await flushWiring();

    const hashItem = document.querySelector('[data-lora-index="5"]');
    const downloadButton = hashItem.querySelector('.lora-download');
    downloadButton.click();

    await vi.waitFor(() => {
      expect(
        requests.some(r => r.url.includes('/recipe/lora/mark-hash-invalid'))
      ).toBe(true);
    });

    const markRequest = requests.find(r => r.url.includes('/mark-hash-invalid'));
    expect(JSON.parse(markRequest.options.body)).toEqual({
      recipe_id: 'recipe-resources',
      lora_index: 5,
    });
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.hashNotFoundOnCivitai',
      {},
      'error'
    );
    expect(downloadVersionWithDefaultsMock).not.toHaveBeenCalled();
  });

  it('renders no action row when neither identifiers nor hash are available', async () => {
    const recipeModal = await createRecipeModal();
    recipeModal.showRecipeDetails(recipeWithResources);

    const mysteryItem = document.querySelector('[data-lora-index="4"]');
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

    const hashItem = document.querySelector('[data-lora-index="5"]');
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

  describe('reconnect suggestions', () => {
    const suggestionsPayload = {
      success: true,
      suggestions: [
        {
          file_name: 'deleted-lora-v1.safetensors',
          file_path: '/models/loras/deleted-lora-v1.safetensors',
          model_name: 'Deleted LoRA v1',
          base_model: 'SD 1.5',
          preview_url: '/preview/deleted.png',
          hash: 'abc123',
          score: 0.95,
          match_reason: 'same_version',
          target_name: 'deleted-lora-v1',
        },
      ],
    };

    function mockSuggestionsFetch(payload) {
      const requests = [];
      global.fetch = vi.fn(async (url, options) => {
        requests.push({ url: String(url), options });
        if (String(url).includes('/reconnect-suggestions')) {
          return { ok: true, json: async () => payload };
        }
        if (String(url).includes('/recipe/lora/reconnect')) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              updated_lora: { name: 'deleted-lora-v1', modelName: 'Deleted LoRA v1', inLibrary: true },
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      });
      return requests;
    }

    async function openReconnectPanel(recipeModal, loraIndex) {
      recipeModal.showRecipeDetails(recipeWithResources);
      await flushWiring();
      const item = document.querySelector(`[data-lora-index="${loraIndex}"]`);
      item.querySelector('.lora-reconnect').click();
      return item.querySelector('.lora-reconnect-container');
    }

    it('fetches suggestions when the panel opens and renders them as rows', async () => {
      const recipeModal = await createRecipeModal();
      mockSuggestionsFetch(suggestionsPayload);

      const container = await openReconnectPanel(recipeModal, 2);

      // The loading state shows synchronously while the fetch is in flight
      expect(container.querySelector('.reconnect-suggestions-loading')).not.toBeNull();

      await vi.waitFor(() => {
        expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(1);
      });

      expect(global.fetch).toHaveBeenCalledWith(
        '/api/lm/recipe/recipe-resources/lora/2/reconnect-suggestions'
      );

      const row = container.querySelector('.reconnect-suggestion');
      // Primary label is the file stem (what the match scored on and what
      // gets submitted); the secondary line shows only the base model — the
      // model name is noise and intentionally omitted.
      expect(row.querySelector('.reconnect-suggestion-name').textContent).toBe('deleted-lora-v1');
      expect(row.querySelector('.reconnect-suggestion-secondary').textContent).toBe('SD 1.5');
      expect(row.querySelector('.reconnect-suggestion-reason').textContent).toBe('Same model version');
      expect(row.title).toBe('deleted-lora-v1');
      const preview = row.querySelector('.reconnect-suggestion-preview');
      expect(preview.getAttribute('src')).toBe('/preview/deleted.png');
    });

    it('reconnects with the suggestion target_name when a row is clicked', async () => {
      const recipeModal = await createRecipeModal();
      const requests = mockSuggestionsFetch(suggestionsPayload);

      const container = await openReconnectPanel(recipeModal, 2);
      await vi.waitFor(() => {
        expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(1);
      });

      container.querySelector('.reconnect-suggestion').click();

      await vi.waitFor(() => {
        expect(requests.some(r => r.url === '/api/lm/recipe/lora/reconnect')).toBe(true);
      });

      const reconnectRequest = requests.find(r => r.url === '/api/lm/recipe/lora/reconnect');
      expect(reconnectRequest.options.method).toBe('POST');
      // lora_index rides as the DOM attribute string, same as the manual form
      expect(JSON.parse(reconnectRequest.options.body)).toEqual({
        recipe_id: 'recipe-resources',
        lora_index: '2',
        target_name: 'deleted-lora-v1',
      });
    });

    it('warns when the reconnect crossed base-model families', async () => {
      const recipeModal = await createRecipeModal();
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes('/reconnect-suggestions')) {
          return { ok: true, json: async () => suggestionsPayload };
        }
        if (String(url).includes('/recipe/lora/reconnect')) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              updated_lora: { name: 'deleted-lora-v1', modelName: 'Deleted LoRA v1', inLibrary: true },
              base_model_mismatch: { recipe_base_model: 'Illustrious', lora_base_model: 'Pony' },
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      });

      const container = await openReconnectPanel(recipeModal, 2);
      await vi.waitFor(() => {
        expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(1);
      });

      container.querySelector('.reconnect-suggestion').click();

      await vi.waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith(
          'toast.recipes.reconnectBaseModelMismatch',
          { recipe: 'Illustrious', lora: 'Pony' },
          'warning'
        );
      });
    });

    it('shows an empty state when no suggestions are available', async () => {
      const recipeModal = await createRecipeModal();
      mockSuggestionsFetch({ success: true, suggestions: [] });

      const container = await openReconnectPanel(recipeModal, 3);

      await vi.waitFor(() => {
        expect(container.querySelector('.reconnect-suggestions-empty')).not.toBeNull();
      });
      expect(container.querySelector('.reconnect-suggestions-empty').textContent)
        .toBe('No matching LoRAs in your local library');
      expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(0);
    });

    it('submits free text via the combobox onCommit when Enter is pressed', async () => {
      const recipeModal = await createRecipeModal();
      const requests = mockSuggestionsFetch({ success: true, suggestions: [] });

      const container = await openReconnectPanel(recipeModal, 2);
      const input = container.querySelector('.reconnect-input');
      input.value = 'typed-lora-name';
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

      await vi.waitFor(() => {
        expect(requests.some(r => r.url === '/api/lm/recipe/lora/reconnect')).toBe(true);
      });
      const reconnectRequest = requests.find(r => r.url === '/api/lm/recipe/lora/reconnect');
      expect(JSON.parse(reconnectRequest.options.body)).toEqual({
        recipe_id: 'recipe-resources',
        lora_index: '2',
        target_name: 'typed-lora-name',
      });
    });

    it('keeps the panel open when the combobox dropdown is clicked', async () => {
      const recipeModal = await createRecipeModal();
      mockSuggestionsFetch({ success: true, suggestions: [] });

      recipeModal.showRecipeDetails(recipeWithResources);
      await flushWiring();
      // Open the panel directly — button wiring races the hydration re-render,
      // and this test is about the document click handler, not the button.
      recipeModal.showReconnectInput('2');
      const container = document.querySelector('.lora-reconnect-container[data-lora-index="2"]');
      expect(container.classList.contains('active')).toBe(true);

      // The dropdown panel lives on document.body; clicking an option there is
      // part of the reconnect interaction, not an outside click.
      const panel = document.createElement('div');
      panel.className = 'lm-combobox-panel';
      document.body.appendChild(panel);
      panel.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      expect(container.classList.contains('active')).toBe(true);
      panel.remove();

      // A genuine outside click still closes the panel
      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      expect(container.classList.contains('active')).toBe(false);
    });
  });

  it('offers undo for reconnected entries and restores via the API', async () => {
    const recipeModal = await createRecipeModal();
    const isolatedRecipe = JSON.parse(JSON.stringify(recipeWithResources));
    isolatedRecipe.loras[0].reconnectSnapshot = { file_name: 'gone', isDeleted: true };
    fetchRecipeDetailsMock.mockResolvedValue(isolatedRecipe);
    const requests = [];
    global.fetch = vi.fn(async (url, options) => {
      requests.push({ url: String(url), options });
      if (String(url).includes('/recipe/lora/restore')) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            updated_lora: { name: 'gone', modelName: 'Gone', inLibrary: false, isDeleted: true },
          }),
        };
      }
      return { ok: true, json: async () => ({}) };
    });
    recipeModal.showRecipeDetails(isolatedRecipe);
    await flushWiring();

    const item = document.querySelector('[data-lora-index="0"]');
    const undoButton = item.querySelector('.lora-undo-reconnect');
    expect(undoButton).not.toBeNull();

    undoButton.click();
    // Wait for the whole restore chain (fetch -> json -> toast), not just the
    // request itself.
    await vi.waitFor(() => {
      expect(showToastMock).toHaveBeenCalledWith('toast.recipes.loraRestored', {}, 'success');
    });
    const restoreRequest = requests.find(r => r.url === '/api/lm/recipe/lora/restore');
    expect(restoreRequest.options.method).toBe('POST');
    expect(JSON.parse(restoreRequest.options.body)).toEqual({
      recipe_id: 'recipe-resources',
      lora_index: '0',
    });
  });

  describe('checkpoint reconnect', () => {
    const brokenCheckpoint = {
      name: 'gone-checkpoint',
      file_name: 'gone',
      inLibrary: false,
      isDeleted: true,
      hash: 'a2a12bfa01',
    };
    const hashInvalidCheckpoint = {
      name: 'invalid-checkpoint',
      file_name: 'invalid',
      inLibrary: false,
      hashInvalid: true,
      hash: 'deadbeefcafe',
    };

    function recipeWithCheckpoint(checkpoint) {
      return {
        ...JSON.parse(JSON.stringify(recipeWithResources)),
        checkpoint: { ...checkpoint },
      };
    }

    // Hydration re-fetches the recipe right after render and re-renders the
    // modal, so the mock must resolve the SAME broken-checkpoint recipe —
    // otherwise the fetch wipes isDeleted/hashInvalid back to the fixture.
    async function renderBrokenCheckpoint(recipeModal, checkpoint) {
      const isolated = recipeWithCheckpoint(checkpoint);
      fetchRecipeDetailsMock.mockResolvedValue(isolated);
      recipeModal.showRecipeDetails(isolated);
      await flushWiring();
    }

    function mockCheckpointSuggestionsFetch(payload) {
      const requests = [];
      global.fetch = vi.fn(async (url, options) => {
        requests.push({ url: String(url), options });
        if (String(url).includes('/checkpoint/reconnect-suggestions')) {
          return { ok: true, json: async () => payload };
        }
        if (String(url).includes('/recipe/checkpoint/reconnect')) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              updated_checkpoint: {
                name: 'main-checkpoint',
                file_name: 'main',
                inLibrary: true,
              },
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      });
      return requests;
    }

    it('renders a deleted checkpoint with a badge and reconnect affordance', async () => {
      const recipeModal = await createRecipeModal();
      await renderBrokenCheckpoint(recipeModal, brokenCheckpoint);

      const item = document.querySelector('.checkpoint-item');
      expect(item.classList.contains('is-deleted')).toBe(true);
      expect(item.querySelector('.deleted-badge')).not.toBeNull();
      const reconnectButton = item.querySelector('.checkpoint-reconnect');
      expect(reconnectButton).not.toBeNull();
      // Deleted checkpoints lose the civitai link (their source page is gone)
      expect(item.querySelector('.recipe-lora-title a.recipe-civitai-link')).toBeNull();
      // The inline form is present but hidden until the button is pressed
      const container = item.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');
      expect(container).not.toBeNull();
      expect(container.classList.contains('active')).toBe(false);
    });

    it('renders a hash-invalid checkpoint with the unresolvable hash badge', async () => {
      const recipeModal = await createRecipeModal();
      await renderBrokenCheckpoint(recipeModal, hashInvalidCheckpoint);

      const item = document.querySelector('.checkpoint-item');
      expect(item.querySelector('.invalid-hash-badge')).not.toBeNull();
      expect(item.querySelector('.checkpoint-reconnect')).not.toBeNull();
    });

    it('renders reconnect for a name-only checkpoint with no download identifiers', async () => {
      // Importers can leave a checkpoint entry with nothing but a model name
      // (no hash / version id, so nothing was ever queryable on CivitAI).
      // It cannot be downloaded and is not marked deleted — reconnect is the
      // only remediation, so it must still surface.
      const recipeModal = await createRecipeModal();
      await renderBrokenCheckpoint(recipeModal, {
        type: 'checkpoint',
        modelName: 'meichidarkMix_meichidarkanimxlV1',
        inLibrary: false,
      });

      const item = document.querySelector('.checkpoint-item');
      expect(item.querySelector('.checkpoint-download')).toBeNull();
      const reconnectButton = item.querySelector('.checkpoint-reconnect');
      expect(reconnectButton).not.toBeNull();
      const container = item.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');
      expect(container).not.toBeNull();

      reconnectButton.click();
      expect(container.classList.contains('active')).toBe(true);
    });

    it('fetches checkpoint suggestions against the checkpoint endpoint', async () => {
      const recipeModal = await createRecipeModal();
      const suggestionsPayload = {
        success: true,
        suggestions: [
          {
            file_name: 'main-checkpoint.safetensors',
            base_model: 'SD 1.5',
            preview_url: '/preview/main.png',
            score: 0.95,
            match_reason: 'same_version',
            target_name: 'main-checkpoint',
          },
        ],
      };
      mockCheckpointSuggestionsFetch(suggestionsPayload);

      await renderBrokenCheckpoint(recipeModal, brokenCheckpoint);
      document.querySelector('.checkpoint-reconnect').click();
      const container = document.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');

      expect(container.classList.contains('active')).toBe(true);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/lm/recipe/recipe-resources/checkpoint/reconnect-suggestions'
      );

      await vi.waitFor(() => {
        expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(1);
      });
      expect(container.querySelector('.reconnect-suggestion-name').textContent)
        .toBe('main-checkpoint');
    });

    it('reconnects the checkpoint via its own endpoint when a suggestion is clicked', async () => {
      const recipeModal = await createRecipeModal();
      const requests = mockCheckpointSuggestionsFetch({
        success: true,
        suggestions: [
          {
            file_name: 'main-checkpoint.safetensors',
            target_name: 'main-checkpoint',
            match_reason: 'same_version',
            score: 0.95,
          },
        ],
      });

      await renderBrokenCheckpoint(recipeModal, brokenCheckpoint);
      document.querySelector('.checkpoint-reconnect').click();
      const container = document.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');

      await vi.waitFor(() => {
        expect(container.querySelectorAll('.reconnect-suggestion').length).toBe(1);
      });
      container.querySelector('.reconnect-suggestion').click();

      await vi.waitFor(() => {
        expect(requests.some(r => r.url === '/api/lm/recipe/checkpoint/reconnect')).toBe(true);
      });
      const reconnectRequest = requests.find(r => r.url === '/api/lm/recipe/checkpoint/reconnect');
      expect(reconnectRequest.options.method).toBe('POST');
      expect(JSON.parse(reconnectRequest.options.body)).toEqual({
        recipe_id: 'recipe-resources',
        target_name: 'main-checkpoint',
      });
      await vi.waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith(
          'toast.recipes.checkpointReconnectedSuccessfully',
          {},
          'success'
        );
      });
      expect(recipeModal.currentRecipe.checkpoint.inLibrary).toBe(true);
    });

    it('warns when the checkpoint reconnect crossed base-model families', async () => {
      const recipeModal = await createRecipeModal();
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes('/checkpoint/reconnect-suggestions')) {
          return { ok: true, json: async () => ({ success: true, suggestions: [] }) };
        }
        if (String(url).includes('/recipe/checkpoint/reconnect')) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              updated_checkpoint: { name: 'main', inLibrary: true },
              base_model_mismatch: { recipe_base_model: 'Illustrious', checkpoint_base_model: 'Pony' },
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      });

      await renderBrokenCheckpoint(recipeModal, brokenCheckpoint);
      document.querySelector('.checkpoint-reconnect').click();
      const container = document.querySelector('.lora-reconnect-container[data-lora-index="checkpoint"]');
      const input = container.querySelector('.reconnect-input');
      input.value = 'main';
      container.querySelector('.reconnect-confirm-btn').click();

      await vi.waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith(
          'toast.recipes.reconnectCheckpointBaseModelMismatch',
          { recipe: 'Illustrious', checkpoint: 'Pony' },
          'warning'
        );
      });
    });

    it('offers undo for a reconnected checkpoint and restores via the API', async () => {
      const recipeModal = await createRecipeModal();
      const isolatedRecipe = recipeWithCheckpoint(brokenCheckpoint);
      isolatedRecipe.checkpoint = {
        name: 'main-checkpoint',
        file_name: 'main',
        inLibrary: true,
        reconnectSnapshot: { name: 'gone-checkpoint', file_name: 'gone', isDeleted: true },
      };
      fetchRecipeDetailsMock.mockResolvedValue(isolatedRecipe);
      const requests = [];
      global.fetch = vi.fn(async (url, options) => {
        requests.push({ url: String(url), options });
        if (String(url).includes('/recipe/checkpoint/restore')) {
          return {
            ok: true,
            json: async () => ({
              success: true,
              updated_checkpoint: { name: 'gone', inLibrary: false, isDeleted: true },
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      });
      recipeModal.showRecipeDetails(isolatedRecipe);
      await flushWiring();

      const item = document.querySelector('.checkpoint-item');
      const undoButton = item.querySelector('.checkpoint-undo-reconnect');
      expect(undoButton).not.toBeNull();

      undoButton.click();
      await vi.waitFor(() => {
        expect(showToastMock).toHaveBeenCalledWith('toast.recipes.checkpointRestored', {}, 'success');
      });
      const restoreRequest = requests.find(r => r.url === '/api/lm/recipe/checkpoint/restore');
      expect(restoreRequest.options.method).toBe('POST');
      expect(JSON.parse(restoreRequest.options.body)).toEqual({
        recipe_id: 'recipe-resources',
      });
    });

    it('marks the checkpoint hash invalid only when the failure is unresolvable', async () => {
      const recipeModal = await createRecipeModal();
      const { downloadManager } = await import('../../../static/js/managers/DownloadManager.js');
      const requests = [];
      global.fetch = vi.fn(async (url, options) => {
        requests.push({ url: String(url), options });
        return { ok: true, json: async () => ({ success: true }) };
      });

      // Explicit "model removed" signal: the entry becomes a rematch/
      // reconnect candidate (same rule as the LoRA resolve "not found").
      // Use an isolated copy so the hashInvalid mutation does not leak into
      // the shared recipeWithResources fixture used by later tests.
      const isolatedRecipe = JSON.parse(JSON.stringify(recipeWithResources));
      fetchRecipeDetailsMock.mockResolvedValue(isolatedRecipe);
      downloadVersionWithDefaultsMock.mockResolvedValue(false);
      downloadManager._lastDownloadError = 'Model not found';
      recipeModal.showRecipeDetails(isolatedRecipe);
      await flushWiring();
      document.querySelector('.checkpoint-download').click();

      await vi.waitFor(() => {
        expect(requests.some(r => r.url === '/api/lm/recipe/checkpoint/mark-hash-invalid')).toBe(true);
      });
      const markRequest = requests.find(r => r.url === '/api/lm/recipe/checkpoint/mark-hash-invalid');
      expect(markRequest.options.method).toBe('POST');
      expect(JSON.parse(markRequest.options.body)).toEqual({ recipe_id: 'recipe-resources' });
      expect(recipeModal.currentRecipe.checkpoint.hashInvalid).toBe(true);
    });

    it('does not mark the checkpoint hash invalid on transient download failures', async () => {
      const recipeModal = await createRecipeModal();
      const { downloadManager } = await import('../../../static/js/managers/DownloadManager.js');
      const requests = [];
      global.fetch = vi.fn(async (url, options) => {
        requests.push({ url: String(url), options });
        return { ok: true, json: async () => ({ success: true }) };
      });

      // Transport/API exceptions must NOT enroll the entry in the
      // remediation flow — transient failures are not evidence the model is
      // unrecoverable (mirrors the LoRA path).
      downloadVersionWithDefaultsMock.mockRejectedValue(new Error('Network timeout'));
      recipeModal.showRecipeDetails(recipeWithResources);
      await flushWiring();
      document.querySelector('.checkpoint-download').click();

      await new Promise(resolve => setTimeout(resolve, 100));
      expect(requests.some(r => r.url === '/api/lm/recipe/checkpoint/mark-hash-invalid')).toBe(false);

      // Business failure without an unresolvable signal also stays untouched.
      downloadVersionWithDefaultsMock.mockResolvedValue(false);
      downloadManager._lastDownloadError = 'Connection refused';
      await recipeModal.downloadCheckpoint(recipeModal.currentRecipe.checkpoint);
      expect(requests.some(r => r.url === '/api/lm/recipe/checkpoint/mark-hash-invalid')).toBe(false);
    });
  });
});
