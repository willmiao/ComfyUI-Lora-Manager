import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  getModelApiClientMock,
  resetAndReloadMock,
  showToastMock,
  sidebarManagerMock,
  moveManagerMock,
  showDeleteModalMock,
  showExcludeModalMock,
} = vi.hoisted(() => ({
  getModelApiClientMock: vi.fn(),
  resetAndReloadMock: vi.fn(async () => {}),
  showToastMock: vi.fn(),
  sidebarManagerMock: {
    setHostPageControls: vi.fn(),
    initialize: vi.fn(async function () {
      sidebarManagerMock.isInitialized = true;
    }),
    refresh: vi.fn(async () => {}),
    cleanup: vi.fn(),
    isInitialized: false,
  },
  moveManagerMock: {
    showMoveModal: vi.fn(),
  },
  showDeleteModalMock: vi.fn(),
  showExcludeModalMock: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: getModelApiClientMock,
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  openCivitaiByMetadata: vi.fn(),
  isTypingContext: () => false,
  getNSFWLevelName: vi.fn(() => 'Unknown'),
  openExampleImagesFolder: vi.fn(),
}));

vi.mock('../../../static/js/managers/DownloadManager.js', () => ({
  downloadManager: { showDownloadModal: vi.fn() },
}));

vi.mock('../../../static/js/components/SidebarManager.js', () => ({
  sidebarManager: sidebarManagerMock,
}));

vi.mock('../../../static/js/managers/MoveManager.js', () => ({
  moveManager: moveManagerMock,
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  showDeleteModal: showDeleteModalMock,
  showExcludeModal: showExcludeModalMock,
}));

vi.mock('../../../static/js/components/alphabet/index.js', () => ({
  createAlphabetBar: vi.fn(() => ({ destroy: vi.fn() })),
}));

vi.mock('../../../static/js/utils/updateCheckHelpers.js', () => ({
  performModelUpdateCheck: vi.fn(async () => ({ status: 'success', displayName: 'Model', records: [] })),
}));

import { createPageControls } from '../../../static/js/components/controls/index.js';
import { OtherControls } from '../../../static/js/components/controls/OtherControls.js';
import { createPageContextMenu } from '../../../static/js/components/ContextMenu/index.js';
import { OtherContextMenu } from '../../../static/js/components/ContextMenu/OtherContextMenu.js';

describe('createPageControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    document.body.innerHTML = '';
    document.body.dataset.page = 'other';
    sidebarManagerMock.isInitialized = false;
  });

  afterEach(() => {
    delete window.pageControls;
    delete window.bulkManager;
  });

  it('creates OtherControls for the other page type', () => {
    const controls = createPageControls('other');

    expect(controls).toBeInstanceOf(OtherControls);
    expect(controls.pageType).toBe('other');
    // OtherControls registers its API with the base class
    expect(typeof controls.api.loadMoreModels).toBe('function');
    expect(typeof controls.api.refreshModels).toBe('function');
    expect(typeof controls.api.fetchFromCivitai).toBe('function');
    expect(typeof controls.api.toggleBulkMode).toBe('function');
  });

  it('returns null for an unknown page type', () => {
    expect(createPageControls('not-a-page')).toBeNull();
  });
});

describe('createPageContextMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = '<div id="otherContextMenu" class="context-menu" style="display: none;"></div>';
  });

  function createMenuWithCard() {
    const menu = createPageContextMenu('other');
    const card = document.createElement('div');
    card.className = 'model-card';
    card.dataset.filepath = '/models/vae/test.safetensors';
    document.body.appendChild(card);
    menu.currentCard = card;
    return { menu, card };
  }

  it('creates OtherContextMenu for the other page type', () => {
    const menu = createPageContextMenu('other');

    expect(menu).toBeInstanceOf(OtherContextMenu);
    expect(menu.modelType).toBe('other');
    expect(menu.menu).toBe(document.getElementById('otherContextMenu'));
  });

  it('returns null for an unknown page type', () => {
    expect(createPageContextMenu('not-a-page')).toBeNull();
  });

  it('delegates refresh-metadata to the model API client', () => {
    const refreshSingleModelMetadata = vi.fn();
    getModelApiClientMock.mockReturnValue({ refreshSingleModelMetadata });
    const { menu } = createMenuWithCard();

    menu.handleMenuAction('refresh-metadata');

    expect(refreshSingleModelMetadata).toHaveBeenCalledWith('/models/vae/test.safetensors');
  });

  it('opens the move modal for the move action', () => {
    const { menu } = createMenuWithCard();

    menu.handleMenuAction('move');

    expect(moveManagerMock.showMoveModal).toHaveBeenCalledWith('/models/vae/test.safetensors');
  });

  it('shows the exclude modal for the exclude action', () => {
    const { menu } = createMenuWithCard();

    menu.handleMenuAction('exclude');

    expect(showExcludeModalMock).toHaveBeenCalledWith('/models/vae/test.safetensors');
  });
});
