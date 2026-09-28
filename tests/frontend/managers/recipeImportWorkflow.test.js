import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const { showToastMock, translateMock } = vi.hoisted(() => ({
  showToastMock: vi.fn(),
  translateMock: vi.fn((key, params, fallback) =>
    typeof fallback === 'string' ? fallback : key
  ),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => ({})),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  MODEL_TYPES: { LORA: 'loras', CHECKPOINT: 'checkpoints', EMBEDDING: 'embeddings' },
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  getStorageItem: vi.fn(() => null),
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: { virtualScroller: null },
}));

import { DownloadManager } from '../../../static/js/managers/import/DownloadManager.js';

function buildImportManager(recipeData) {
  return {
    recipeId: null,
    recipeName: 'Test Recipe',
    recipeImage: null,
    recipeTags: [],
    downloadableLoRAs: [],
    importMode: 'url',
    recipeData,
    loadingManager: { showSimpleLoading: vi.fn(), hide: vi.fn() },
  };
}

async function saveAndReadMetadata(recipeData) {
  let capturedBody = null;
  const fetchMock = vi.fn(async (url, options) => {
    capturedBody = options?.body ?? null;
    return { ok: true, json: async () => ({ success: true }) };
  });
  globalThis.fetch = fetchMock;
  window.fetch = fetchMock;

  const manager = new DownloadManager(buildImportManager(recipeData));
  await manager.saveRecipe(true);

  expect(fetchMock).toHaveBeenCalledWith('/api/lm/recipes/save', expect.anything());
  expect(capturedBody).toBeInstanceOf(FormData);
  return JSON.parse(capturedBody.get('metadata'));
}

describe('recipe import save payload', () => {
  beforeEach(() => {
    globalThis.modalManager = { closeModal: vi.fn() };
    globalThis.window.recipeManager = { loadRecipes: vi.fn() };
  });

  afterEach(() => {
    delete globalThis.modalManager;
    delete globalThis.window.recipeManager;
    vi.clearAllMocks();
  });

  it('forwards a workflow recovered from the original rendition', async () => {
    const workflow = '{"nodes": [{"id": 1}]}';
    const metadata = await saveAndReadMetadata({
      image_base64: 'AAAA',
      base_model: 'sd',
      loras: [],
      gen_params: {},
      workflow,
    });

    expect(metadata.workflow).toBe(workflow);
  });

  it('omits the workflow key when analysis recovered none', async () => {
    const metadata = await saveAndReadMetadata({
      image_base64: 'AAAA',
      base_model: 'sd',
      loras: [],
      gen_params: {},
    });

    expect('workflow' in metadata).toBe(false);
  });
});
