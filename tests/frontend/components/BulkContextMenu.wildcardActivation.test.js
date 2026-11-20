import { beforeEach, describe, expect, it, vi } from 'vitest';

const activateMock = vi.fn();
const deactivateMock = vi.fn();
const stateStub = {
  currentPageType: 'wildcards',
  selectedModels: new Set(['/models/a.txt']),
};
const bulkManagerStub = {
  actionConfig: {
    wildcards: { activateAll: true, deactivateAll: true },
    loras: {},
  },
  activateSelectedWildcards: activateMock,
  deactivateSelectedWildcards: deactivateMock,
};

vi.mock('../../../static/js/state/index.js', () => ({ state: stateStub }));
vi.mock('../../../static/js/managers/BulkManager.js', () => ({ bulkManager: bulkManagerStub }));
vi.mock('../../../static/js/managers/BulkMissingLoraDownloadManager.js', () => ({
  bulkMissingLoraDownloadManager: {},
}));
vi.mock('../../../static/js/utils/uiHelpers.js', () => ({ showToast: vi.fn() }));
vi.mock('../../../static/js/api/modelApiFactory.js', () => ({ getModelApiClient: vi.fn() }));
vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key) => key),
  updateElementText: vi.fn(),
}));

describe('BulkContextMenu wildcard activation actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.currentPageType = 'wildcards';
    document.body.innerHTML = `
      <div id="bulkContextMenu">
        <div class="bulk-context-header"></div>
        <div class="context-menu-section" data-section="activation">
          <div class="context-menu-item" data-action="activate-all"></div>
          <div class="context-menu-item" data-action="deactivate-all"></div>
        </div>
      </div>`;
  });

  it('shows activation actions only for wildcards', async () => {
    const { BulkContextMenu } = await import(
      '../../../static/js/components/ContextMenu/BulkContextMenu.js'
    );
    const menu = new BulkContextMenu();
    const section = document.querySelector('[data-section="activation"]');

    expect(document.querySelector('[data-action="activate-all"]').style.display).toBe('flex');
    expect(document.querySelector('[data-action="deactivate-all"]').style.display).toBe('flex');
    expect(section.style.display).not.toBe('none');

    stateStub.currentPageType = 'loras';
    menu.updateMenuItemsForModelType();

    expect(document.querySelector('[data-action="activate-all"]').style.display).toBe('none');
    expect(document.querySelector('[data-action="deactivate-all"]').style.display).toBe('none');
    expect(section.style.display).toBe('none');
  });

  it('delegates both actions to BulkManager', async () => {
    const { BulkContextMenu } = await import(
      '../../../static/js/components/ContextMenu/BulkContextMenu.js'
    );
    const menu = new BulkContextMenu();
    menu.currentCard = {};

    document.querySelector('[data-action="activate-all"]').click();
    menu.currentCard = {};
    document.querySelector('[data-action="deactivate-all"]').click();

    expect(activateMock).toHaveBeenCalledTimes(1);
    expect(deactivateMock).toHaveBeenCalledTimes(1);
  });
});
