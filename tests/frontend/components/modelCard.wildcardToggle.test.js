import { describe, it, expect, vi, beforeEach } from 'vitest';

import { state } from '../../../static/js/state/index.js';

const {
  MODEL_CARD_MODULE,
  STATE_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  API_CONFIG_MODULE,
  API_FACTORY_MODULE,
  WILDCARD_ACTIONS_MODULE,
  WILDCARD_ACTIONS,
  API_CLIENTS,
  showToastMock,
} = vi.hoisted(() => {
  const wildcardClient = { activate: vi.fn(), deactivate: vi.fn() };
  return {
    MODEL_CARD_MODULE: new URL('../../../static/js/components/shared/ModelCard.js', import.meta.url).pathname,
    STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
    UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
    I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
    API_CONFIG_MODULE: new URL('../../../static/js/api/apiConfig.js', import.meta.url).pathname,
    API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
    WILDCARD_ACTIONS_MODULE: new URL('../../../static/js/utils/wildcardActions.js', import.meta.url).pathname,
    WILDCARD_ACTIONS: { openWildcardModel: vi.fn(), deactivateWildcard: vi.fn() },
    API_CLIENTS: { wildcards: wildcardClient },
    showToastMock: vi.fn(),
  };
});

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
        autoplay_on_hover: false,
      },
    },
    pages: {
      wildcards: {
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
  showToast: showToastMock,
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
  MODEL_TYPES: {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings',
    OTHER: 'other',
    WILDCARD: 'wildcards',
    WORKFLOW: 'workflows',
  },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn((modelType) => API_CLIENTS[modelType] || {}),
}));

vi.mock(WILDCARD_ACTIONS_MODULE, () => WILDCARD_ACTIONS);

function wildcardModel(overrides = {}) {
  return {
    sha256: 'abc123',
    file_path: '/models/wildcards/pack.zip',
    model_name: 'Pack',
    file_name: 'pack',
    folder: '',
    modified: '2026-01-01T00:00:00',
    file_size: 1024,
    from_civitai: false,
    civitai: {},
    base_model: 'Illustrious',
    usage_count: 0,
    active: false,
    entries: [],
    entry_count: 0,
    errors: [],
    ...overrides,
  };
}

async function mountWildcardCard(overrides = {}) {
  const { createModelCard, setupModelCardEventDelegation } = await import(MODEL_CARD_MODULE);
  setupModelCardEventDelegation('wildcards');
  const card = createModelCard(wildcardModel(overrides), 'wildcards');
  document.getElementById('modelGrid').append(card);
  return card;
}

describe('wildcard card activation action', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '<div id="modelGrid"></div>';
    state.virtualScroller = null;
    API_CLIENTS.wildcards.activate.mockResolvedValue({ success: true });
    API_CLIENTS.wildcards.deactivate.mockResolvedValue({ success: true });
  });

  it('replaces the copy action with a toggle next to the Civitai globe', async () => {
    const { createModelCard } = await import(MODEL_CARD_MODULE);

    const inactive = createModelCard(wildcardModel(), 'wildcards');
    const inactiveToggle = inactive.querySelector('[data-wildcard-toggle]');
    expect(inactive.querySelector('.fa-copy')).toBeNull();
    expect(inactiveToggle).not.toBeNull();
    expect(inactiveToggle.closest('.card-actions')).not.toBeNull();
    expect(inactiveToggle.previousElementSibling.classList.contains('fa-globe')).toBe(true);
    expect(inactiveToggle.classList.contains('fa-toggle-off')).toBe(true);
    expect(inactiveToggle.title).toBe('Activate');
    expect(inactive.classList.contains('wildcard-active')).toBe(false);

    const active = createModelCard(wildcardModel({ active: true }), 'wildcards');
    const activeToggle = active.querySelector('[data-wildcard-toggle]');
    expect(active.querySelector('.fa-copy')).toBeNull();
    expect(activeToggle.classList.contains('fa-toggle-on')).toBe(true);
    expect(activeToggle.classList.contains('wildcard-toggle-active')).toBe(true);
    expect(activeToggle.title).toBe('Deactivate');
    expect(active.classList.contains('wildcard-active')).toBe(true);
  });

  it('activates from the toggle and updates the card in place', async () => {
    const card = await mountWildcardCard();
    state.virtualScroller = {
      items: [{ file_path: '/models/wildcards/pack.zip', active: false }],
    };

    card.querySelector('[data-wildcard-toggle]').click();

    await vi.waitFor(() => {
      expect(API_CLIENTS.wildcards.activate).toHaveBeenCalledWith('/models/wildcards/pack.zip');
    });
    await vi.waitFor(() => {
      expect(card.querySelector('[data-wildcard-toggle]').classList.contains('fa-toggle-on')).toBe(true);
    });
    expect(card.dataset.active).toBe('true');
    expect(card.classList.contains('wildcard-active')).toBe(true);
    expect(card.querySelector('[data-wildcard-toggle]').title).toBe('Deactivate');
    expect(state.virtualScroller.items[0].active).toBe(true);
    expect(showToastMock).toHaveBeenCalledWith('wildcards.messages.activated', {}, 'success');
    expect(WILDCARD_ACTIONS.openWildcardModel).not.toHaveBeenCalled();
  });

  it('deactivates an active card from the toggle', async () => {
    const card = await mountWildcardCard({ active: true });

    card.querySelector('[data-wildcard-toggle]').click();

    await vi.waitFor(() => {
      expect(API_CLIENTS.wildcards.deactivate).toHaveBeenCalledWith('/models/wildcards/pack.zip');
    });
    await vi.waitFor(() => {
      expect(card.querySelector('[data-wildcard-toggle]').classList.contains('fa-toggle-off')).toBe(true);
    });
    expect(card.dataset.active).toBe('false');
    expect(card.classList.contains('wildcard-active')).toBe(false);
    expect(card.querySelector('[data-wildcard-toggle]').title).toBe('Activate');
    expect(showToastMock).toHaveBeenCalledWith('wildcards.messages.deactivated', {}, 'success');
  });

  it('keeps the card inactive and opens the manager on a key conflict', async () => {
    const conflict = Object.assign(
      new Error('Activation would replace an existing wildcard key'),
      { payload: { success: false, conflicts: [{ key: 'anime/bang_dream' }] } },
    );
    API_CLIENTS.wildcards.activate.mockRejectedValueOnce(conflict);
    const card = await mountWildcardCard();

    card.querySelector('[data-wildcard-toggle]').click();

    await vi.waitFor(() => {
      expect(WILDCARD_ACTIONS.openWildcardModel).toHaveBeenCalledWith(
        '/models/wildcards/pack.zip',
        { openWildcardsTab: true },
      );
    });
    expect(card.dataset.active).toBe('false');
    expect(card.querySelector('[data-wildcard-toggle]').classList.contains('fa-toggle-off')).toBe(true);
    expect(showToastMock).toHaveBeenCalledWith(
      expect.stringContaining('key conflict'),
      {},
      'error',
    );
  });
});
