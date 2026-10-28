import { describe, it, beforeEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const copyToClipboardMock = vi.fn();
const fetchWorkflowContentMock = vi.fn();
const sendToComfyMock = vi.fn();
const resetAndReloadMock = vi.fn();

const stateStub = {
  global: { settings: { standalone_mode: false } },
  currentPageType: 'workflows',
  pages: {},
};

vi.mock('../../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  copyToClipboard: copyToClipboardMock,
}));

vi.mock('../../../../static/js/state/index.js', () => ({
  state: stateStub,
}));

vi.mock('../../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(() => ({
    fetchWorkflowContent: fetchWorkflowContentMock,
    sendToComfy: sendToComfyMock,
  })),
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { showMoveModal: vi.fn() },
}));

vi.mock('../../../../static/js/utils/modalUtils.js', () => ({
  showDeleteModal: vi.fn(),
  showExcludeModal: vi.fn(),
}));

vi.mock('../../../../static/js/components/ContextMenu/ModelContextMenuMixin.js', () => ({
  ModelContextMenuMixin: {
    handleCommonMenuActions: vi.fn(() => false),
    updateExcludeMenuItem: vi.fn(),
    initNSFWSelector: vi.fn(),
  },
}));

const { WorkflowContextMenu } = await import(
  '../../../../static/js/components/ContextMenu/WorkflowContextMenu.js'
);

function setupDom() {
  document.body.innerHTML = `
    <div id="workflowContextMenu" class="context-menu" style="display: none;">
      <div class="context-menu-item" data-action="send-to-comfy"></div>
      <div class="context-menu-item" data-action="copy-workflow"></div>
    </div>
    <div class="model-card" data-filepath="/library/workflows/flow.json"></div>
    <select id="nsfwLevelSelector"></select>
  `;
}

describe('WorkflowContextMenu', () => {
  let menu;
  let card;

  beforeEach(() => {
    vi.clearAllMocks();
    stateStub.global.settings.standalone_mode = false;
    setupDom();
    menu = new WorkflowContextMenu();
    card = document.querySelector('.model-card');
    menu.currentCard = card;
  });

  it('copies the workflow document to the clipboard', async () => {
    const workflow = { 1: { class_type: 'CheckpointLoaderSimple', inputs: {} } };
    fetchWorkflowContentMock.mockResolvedValue(workflow);

    menu.handleMenuAction('copy-workflow');
    await vi.waitFor(() => expect(copyToClipboardMock).toHaveBeenCalled());

    expect(fetchWorkflowContentMock).toHaveBeenCalledWith('/library/workflows/flow.json');
    expect(copyToClipboardMock).toHaveBeenCalledWith(JSON.stringify(workflow));
    expect(showToastMock).not.toHaveBeenCalledWith(
      'workflows.copyWorkflow.failed',
      expect.anything(),
      'error'
    );
  });

  it('shows an error toast when the workflow content cannot be loaded', async () => {
    fetchWorkflowContentMock.mockRejectedValue(new Error('not_a_workflow'));

    menu.handleMenuAction('copy-workflow');
    await vi.waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        'workflows.copyWorkflow.failed',
        { message: 'not_a_workflow' },
        'error'
      )
    );
    expect(copyToClipboardMock).not.toHaveBeenCalled();
  });

  it('hides send-to-comfy in standalone mode', () => {
    stateStub.global.settings.standalone_mode = true;

    menu.showMenu(10, 10, card);

    const sendItem = document.querySelector('[data-action="send-to-comfy"]');
    expect(sendItem.style.display).toBe('none');
  });

  it('keeps send-to-comfy visible in plugin mode', () => {
    menu.showMenu(10, 10, card);

    const sendItem = document.querySelector('[data-action="send-to-comfy"]');
    expect(sendItem.style.display).toBe('');
  });
});
