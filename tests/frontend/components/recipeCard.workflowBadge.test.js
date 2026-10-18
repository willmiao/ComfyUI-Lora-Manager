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

function buildRecipe(overrides = {}) {
  return {
    id: 'recipe-1',
    file_path: '/recipes/r1.json',
    title: 'Badge Recipe',
    file_url: '/preview.png',
    preview_nsfw_level: 0,
    created_date: '2024-01-01',
    base_model: 'SDXL',
    loras: [],
    ...overrides,
  };
}

async function createCard(overrides) {
  const { RecipeCard } = await import(RECIPE_CARD_MODULE);
  return new RecipeCard(buildRecipe(overrides), vi.fn());
}

describe('RecipeCard workflow badge', () => {
  beforeEach(() => {
    translateMock.mockClear();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders the badge next to the base model label when the recipe embeds a workflow', async () => {
    const card = await createCard({ has_workflow: true });

    const badge = card.element.querySelector('.card-header-info .workflow-badge');
    expect(badge).not.toBeNull();
    expect(badge.querySelector('.fa-diagram-project')).not.toBeNull();
    expect(badge.title).toBe('Contains a ComfyUI workflow');
    expect(badge.previousElementSibling.classList.contains('base-model-label')).toBe(true);
  });

  it('omits the badge when has_workflow is false or missing', async () => {
    const withoutFlag = await createCard({ has_workflow: false });
    expect(withoutFlag.element.querySelector('.workflow-badge')).toBeNull();

    const missingFlag = await createCard({});
    expect(missingFlag.element.querySelector('.workflow-badge')).toBeNull();
  });

  it('asks i18n for the recipes.workflow.hasWorkflow tooltip', async () => {
    await createCard({ has_workflow: true });

    expect(translateMock).toHaveBeenCalledWith(
      'recipes.workflow.hasWorkflow',
      {},
      'Contains a ComfyUI workflow'
    );
  });
});
