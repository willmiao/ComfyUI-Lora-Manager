import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  RECIPE_CARD_MODULE,
  UI_HELPERS_MODULE,
  RECIPE_API_MODULE,
  MODEL_CARD_MODULE,
  MODAL_MANAGER_MODULE,
  STATE_MODULE,
  BULK_MANAGER_MODULE,
  CONSTANTS_MODULE,
  I18N_MODULE,
  UNDO_HELPERS_MODULE,
} = vi.hoisted(() => ({
  RECIPE_CARD_MODULE: new URL('../../../static/js/components/RecipeCard.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  RECIPE_API_MODULE: new URL('../../../static/js/api/recipeApi.js', import.meta.url).pathname,
  MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  BULK_MANAGER_MODULE: new URL('../../../static/js/managers/BulkManager.js', import.meta.url).pathname,
  CONSTANTS_MODULE: new URL('../../../static/js/utils/constants.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
}));

const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
  showActionToast: vi.fn(),
  copyToClipboard: vi.fn(),
  sendLoraToWorkflow: vi.fn(),
}));

vi.mock(RECIPE_API_MODULE, () => ({
  updateRecipeMetadata: vi.fn(),
}));

vi.mock(MODEL_CARD_MODULE, () => ({
  configureModelCardVideo: vi.fn(),
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
    closeModal: vi.fn(),
  },
}));

vi.mock(STATE_MODULE, () => ({
  state: {
    global: { settings: {} },
    settings: {},
    virtualScroller: { removeItemByFilePath: vi.fn() },
  },
  getCurrentPageState: vi.fn(() => ({})),
}));

vi.mock(BULK_MANAGER_MODULE, () => ({
  bulkManager: {},
}));

vi.mock(CONSTANTS_MODULE, () => ({
  NSFW_LEVELS: {},
  getBaseModelAbbreviation: vi.fn((label) => label),
  getMatureBlurThreshold: vi.fn(() => 10),
}));

vi.mock(I18N_MODULE, () => ({
  translate: translateMock,
}));

vi.mock(UNDO_HELPERS_MODULE, () => ({
  handleUndoDelete: vi.fn(),
}));

function buildRecipe(loras) {
  return {
    id: 'recipe-1',
    file_path: '/recipes/r1.json',
    title: 'Badge Recipe',
    file_url: '/preview.png',
    preview_nsfw_level: 0,
    created_date: '2024-01-01',
    base_model: 'SDXL',
    loras,
  };
}

async function createCard(loras) {
  const { RecipeCard } = await import(RECIPE_CARD_MODULE);
  return new RecipeCard(buildRecipe(loras), vi.fn());
}

describe('RecipeCard LoRA status pill', () => {
  beforeEach(() => {
    translateMock.mockClear();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('shows available/total with a warning icon when LoRAs are missing', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: true },
      { name: 'b', inLibrary: false },
      { name: 'c', inLibrary: true },
    ]);

    const pill = card.element.querySelector('.lora-count.missing');
    expect(pill).not.toBeNull();
    expect(pill.querySelector('.fa-exclamation-triangle')).not.toBeNull();
    expect(pill.textContent).toContain('2/3');
    expect(pill.title).toBe('1 of 3 LoRAs missing');
  });

  it('shows a green check with n/n when every LoRA is available', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: true },
      { name: 'b', inLibrary: true },
    ]);

    const pill = card.element.querySelector('.lora-count.ready');
    expect(pill).not.toBeNull();
    expect(pill.querySelector('.fa-check')).not.toBeNull();
    expect(pill.textContent).toContain('2/2');
    expect(pill.title).toBe('All LoRAs available - Ready to use');
    expect(card.element.querySelector('.lora-count.missing')).toBeNull();
  });

  it('marks deleted-from-source LoRAs as partial instead of ready', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: true },
      { name: 'b', inLibrary: false, isDeleted: true },
    ]);

    expect(card.element.querySelector('.lora-count.missing')).toBeNull();
    expect(card.element.querySelector('.lora-count.ready')).toBeNull();

    const pill = card.element.querySelector('.lora-count.partial');
    expect(pill).not.toBeNull();
    expect(pill.querySelector('.fa-circle-minus')).not.toBeNull();
    expect(pill.textContent).toContain('1/2');
    expect(pill.title).toBe('1 of 2 LoRAs unavailable (deleted from source or unresolvable hash) - skipped when recipe is used');
  });

  it('treats an unresolvable hash as unobtainable, not missing', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: true },
      { name: 'b', inLibrary: false, hashInvalid: true },
    ]);

    expect(card.element.querySelector('.lora-count.missing')).toBeNull();

    const pill = card.element.querySelector('.lora-count.partial');
    expect(pill).not.toBeNull();
    expect(pill.textContent).toContain('1/2');
  });

  it('shows 0/n unavailable when every LoRA is deleted and none is in the library', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: false, isDeleted: true },
      { name: 'b', inLibrary: false, isDeleted: true },
    ]);

    const pill = card.element.querySelector('.lora-count.unavailable');
    expect(pill).not.toBeNull();
    expect(pill.querySelector('.fa-ban')).not.toBeNull();
    expect(pill.textContent).toContain('0/2');
    expect(pill.title).toBe('No usable LoRAs - 2 of 2 deleted from source or unresolvable hash');
    expect(card.element.querySelector('.lora-count.ready')).toBeNull();
  });

  it('keeps the actionable missing state when LoRAs are both missing and deleted', async () => {
    const card = await createCard([
      { name: 'a', inLibrary: true },
      { name: 'b', inLibrary: false },
      { name: 'c', inLibrary: false, isDeleted: true },
    ]);

    const pill = card.element.querySelector('.lora-count.missing');
    expect(pill).not.toBeNull();
    expect(pill.textContent).toContain('1/3');
    expect(pill.title).toBe('1 of 3 LoRAs missing, 1 unavailable (deleted from source or unresolvable hash)');
    expect(card.element.querySelector('.lora-count.partial')).toBeNull();
  });

  it('shows a neutral layers icon with a bare 0 when the recipe has no LoRAs', async () => {
    const card = await createCard([]);

    const pill = card.element.querySelector('.lora-count');
    expect(pill).not.toBeNull();
    expect(pill.classList.contains('missing')).toBe(false);
    expect(pill.classList.contains('ready')).toBe(false);
    expect(pill.querySelector('.fa-layer-group')).not.toBeNull();
    expect(pill.textContent).toContain('0');
    expect(pill.textContent).not.toContain('/');
    expect(pill.title).toBe('No LoRAs in this recipe');
  });
});
