import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const MODULE = '../../../static/js/managers/BulkMissingLoraDownloadManager.js';

const showToastMock = vi.fn();
const updateProgressMock = vi.fn();
const updateSingleItemMock = vi.fn();

const mockApiClient = {
  downloadModel: vi.fn(),
  cancelDownload: vi.fn(),
  fetchModelRoots: vi.fn(() => Promise.resolve({ roots: ['/models/loras'] })),
};

const loadingManagerStub = {
  showDownloadProgress: vi.fn(() => updateProgressMock),
  setStatus: vi.fn(),
  showCancelButton: vi.fn(),
  hide: vi.fn(),
};

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  // Keep the real predicate: these tests assert on its classification.
  isUnresolvableDownloadError: (message) =>
    !!message && /(not found|no longer available|deleted|removed|404|410|gone)/.test(String(message).toLowerCase()),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((_, __, fallback) => fallback ?? ''),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => mockApiClient),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings' },
}));

vi.mock('../../../static/js/api/recipeApi.js', () => ({
  extractRecipeId: (filePath) => {
    if (!filePath) return null;
    const basename = filePath.split('/').pop().split('\\').pop();
    const dotIndex = basename.lastIndexOf('.');
    return dotIndex > 0 ? basename.substring(0, dotIndex) : basename;
  },
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: {
    loadingManager: loadingManagerStub,
    virtualScroller: { updateSingleItem: updateSingleItemMock },
    global: { settings: {} },
  },
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: { showModal: vi.fn(), closeModal: vi.fn() },
}));

/** Mirrors the FakeWebSocket pattern from downloadManager.batchSummary.test.js. */
class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      if (this.onopen) this.onopen();
    });
  }
}

const makeRecipe = (filePath, loras) => ({ file_path: filePath, loras });

describe('BulkMissingLoraDownloadManager unresolvable-failure write-back', () => {
  let manager;
  let fetchMock;
  let requests;

  beforeEach(async () => {
    FakeWebSocket.instances = [];
    vi.clearAllMocks();
    loadingManagerStub.showDownloadProgress.mockReturnValue(updateProgressMock);

    requests = [];
    fetchMock = vi.fn((url, options) => {
      requests.push({ url, options });
      if (url === '/api/lm/recipe/lora/mark-hash-invalid') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      // Recipe detail refresh after the download loop
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 'refreshed' }) });
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('WebSocket', FakeWebSocket);

    vi.resetModules();
    ({ bulkMissingLoraDownloadManager: manager } = await import(MODULE));
    manager.pendingLoras = [];
    manager.pendingRecipes = [];
    manager.pendingMissingByRecipe = null;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const primePending = (recipes) => {
    const stats = manager.collectMissingLoras(recipes);
    manager.pendingRecipes = recipes;
    manager.pendingMissingByRecipe = stats.missingLorasByRecipe;
    return stats.uniqueLoras;
  };

  it('marks every recipe occurrence hash-invalid when the failure is unresolvable', async () => {
    const entryA = { hash: 'abc123', file_name: 'a.safetensors', inLibrary: false, modelId: 1, id: 10 };
    const entryB = { hash: 'abc123', file_name: 'a.safetensors', inLibrary: false, modelId: 1, id: 10 };
    const recipe1 = makeRecipe('/recipes/r1.json', [entryA]);
    const recipe2 = makeRecipe('/recipes/r2.json', [{ hash: 'x', file_name: 'keep.safetensors', inLibrary: true }, entryB]);
    const uniqueLoras = primePending([recipe1, recipe2]);

    mockApiClient.downloadModel.mockResolvedValue({ success: false, error: 'Model not found' });

    await manager.executeDownload(uniqueLoras);

    const markCalls = requests.filter(r => r.url === '/api/lm/recipe/lora/mark-hash-invalid');
    expect(markCalls).toHaveLength(2);
    const payloads = markCalls.map(r => JSON.parse(r.options.body));
    expect(payloads).toContainEqual({ recipe_id: 'r1', lora_index: 0 });
    expect(payloads).toContainEqual({ recipe_id: 'r2', lora_index: 1 });
    expect(entryA.hashInvalid).toBe(true);
    expect(entryB.hashInvalid).toBe(true);

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.recipes.unresolvableMarkedForReconnect',
      { count: 2 },
      'info',
      expect.any(String),
    );
  });

  it('leaves entries untouched when the failure is transient', async () => {
    const entry = { hash: 'abc123', file_name: 'a.safetensors', inLibrary: false, modelId: 1, id: 10 };
    const recipe = makeRecipe('/recipes/r1.json', [entry]);
    const uniqueLoras = primePending([recipe]);

    mockApiClient.downloadModel.mockResolvedValue({ success: false, error: 'Connection timed out' });

    await manager.executeDownload(uniqueLoras);

    expect(requests.some(r => r.url === '/api/lm/recipe/lora/mark-hash-invalid')).toBe(false);
    expect(entry.hashInvalid).toBeUndefined();
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.recipes.unresolvableMarkedForReconnect',
      expect.anything(),
      expect.anything(),
      expect.anything(),
    );
  });

  it('marks hash-invalid when the download request itself throws an unresolvable error', async () => {
    const entry = { hash: 'abc123', file_name: 'a.safetensors', inLibrary: false, modelId: 1, id: 10 };
    const recipe = makeRecipe('/recipes/r1.json', [entry]);
    const uniqueLoras = primePending([recipe]);

    mockApiClient.downloadModel.mockRejectedValue(new Error('410 Gone'));

    await manager.executeDownload(uniqueLoras);

    const markCalls = requests.filter(r => r.url === '/api/lm/recipe/lora/mark-hash-invalid');
    expect(markCalls).toHaveLength(1);
    expect(entry.hashInvalid).toBe(true);
  });

  it('does not mark entries whose download succeeds', async () => {
    const entry = { hash: 'abc123', file_name: 'a.safetensors', inLibrary: false, modelId: 1, id: 10 };
    const recipe = makeRecipe('/recipes/r1.json', [entry]);
    const uniqueLoras = primePending([recipe]);

    mockApiClient.downloadModel.mockResolvedValue({ success: true });

    await manager.executeDownload(uniqueLoras);

    expect(requests.some(r => r.url === '/api/lm/recipe/lora/mark-hash-invalid')).toBe(false);
  });
});
