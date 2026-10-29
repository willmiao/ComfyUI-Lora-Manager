import { describe, it, beforeEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const copyToClipboardMock = vi.fn();
const fetchWorkflowContentMock = vi.fn();
const sendToComfyMock = vi.fn();
const fetchComfyuiStateMock = vi.fn();
const updateFromComfyMock = vi.fn();
const restoreMock = vi.fn();
const resetAndReloadMock = vi.fn();
const updateSingleItemMock = vi.fn();
const showConfirmationModalMock = vi.fn();

const showSimpleLoadingMock = vi.fn();
const hideLoadingMock = vi.fn();

const stateStub = {
  global: { settings: { standalone_mode: false } },
  currentPageType: 'workflows',
  pages: {},
  virtualScroller: { updateSingleItem: updateSingleItemMock, items: [] },
  loadingManager: { showSimpleLoading: showSimpleLoadingMock, hide: hideLoadingMock },
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
    fetchComfyuiState: fetchComfyuiStateMock,
    updateFromComfy: updateFromComfyMock,
    restore: restoreMock,
  })),
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (key) => key,
}));

vi.mock('../../../../static/js/managers/MoveManager.js', () => ({
  moveManager: { showMoveModal: vi.fn() },
}));

vi.mock('../../../../static/js/utils/modalUtils.js', () => ({
  showDeleteModal: vi.fn(),
  showExcludeModal: vi.fn(),
  showConfirmationModal: showConfirmationModalMock,
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
      <div class="context-menu-item disabled" data-action="update-from-comfy"></div>
      <div class="context-menu-item" data-action="copy-workflow"></div>
      <div class="context-menu-item" data-action="restore-download"></div>
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
    stateStub.virtualScroller.items = [];
    fetchComfyuiStateMock.mockResolvedValue([]);
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

  it('hides update-from-comfy in standalone mode', () => {
    stateStub.global.settings.standalone_mode = true;

    menu.showMenu(10, 10, card);

    const updateItem = document.querySelector('[data-action="update-from-comfy"]');
    expect(updateItem.style.display).toBe('none');
  });

  it('keeps update-from-comfy disabled when the workflow is not open in ComfyUI', async () => {
    fetchComfyuiStateMock.mockResolvedValue([]);

    menu.showMenu(10, 10, card);
    await vi.waitFor(() => expect(fetchComfyuiStateMock).toHaveBeenCalled());

    const updateItem = document.querySelector('[data-action="update-from-comfy"]');
    expect(updateItem.classList.contains('disabled')).toBe(true);
  });

  it('keeps update-from-comfy disabled when the open workflow has no edits', async () => {
    fetchComfyuiStateMock.mockResolvedValue([
      { client_id: 'c1', file_path: '/library/workflows/flow.json', dirty: false },
    ]);

    menu.showMenu(10, 10, card);
    await vi.waitFor(() => expect(fetchComfyuiStateMock).toHaveBeenCalled());

    const updateItem = document.querySelector('[data-action="update-from-comfy"]');
    expect(updateItem.classList.contains('disabled')).toBe(true);
  });

  it('enables update-from-comfy when the workflow is open in ComfyUI with edits', async () => {
    fetchComfyuiStateMock.mockResolvedValue([
      { client_id: 'c1', file_path: '/library/workflows/flow.json', dirty: true },
    ]);

    menu.showMenu(10, 10, card);
    await vi.waitFor(() => {
      const updateItem = document.querySelector('[data-action="update-from-comfy"]');
      expect(updateItem.classList.contains('disabled')).toBe(false);
    });
  });

  it('triggers the write-back flow on update-from-comfy', async () => {
    updateFromComfyMock.mockResolvedValue({ success: true, sha256: 'newhash123' });

    menu.handleMenuAction('update-from-comfy');
    await vi.waitFor(() =>
      expect(updateFromComfyMock).toHaveBeenCalledWith('/library/workflows/flow.json')
    );
    await vi.waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        'workflows.updateFromComfy.success',
        {},
        'success'
      )
    );
    // The card is refreshed in place so it shows the "Updated" cue.
    expect(updateSingleItemMock).toHaveBeenCalledWith('/library/workflows/flow.json', {
      sha256: 'newhash123',
    });
  });

  it('surfaces no_changes as an info toast', async () => {
    const error = new Error('no_changes');
    error.kind = 'no_changes';
    updateFromComfyMock.mockRejectedValue(error);

    menu.handleMenuAction('update-from-comfy');
    await vi.waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        'workflows.updateFromComfy.noChanges',
        {},
        'info'
      )
    );
  });

  it('disables restore-download for local-only .json workflows', () => {
    stateStub.virtualScroller.items = [
      { file_path: '/library/workflows/flow.json', from_civitai: false },
    ];

    menu.showMenu(10, 10, card);

    const restoreItem = document.querySelector('[data-action="restore-download"]');
    expect(restoreItem.classList.contains('disabled')).toBe(true);
  });

  it('enables restore-download for CivitAI-sourced .json workflows', () => {
    stateStub.virtualScroller.items = [
      { file_path: '/library/workflows/flow.json', from_civitai: true },
    ];

    menu.showMenu(10, 10, card);

    const restoreItem = document.querySelector('[data-action="restore-download"]');
    expect(restoreItem.classList.contains('disabled')).toBe(false);
  });

  it('enables restore-download for container artifacts without CivitAI data', () => {
    card.dataset.filepath = '/library/workflows/pack.zip';

    menu.showMenu(10, 10, card);

    const restoreItem = document.querySelector('[data-action="restore-download"]');
    expect(restoreItem.classList.contains('disabled')).toBe(false);
  });

  it('restores the workflow on restore-download after confirmation', async () => {
    showConfirmationModalMock.mockResolvedValue(true);
    restoreMock.mockResolvedValue({ success: true, restored: 'downloaded', sha256: 'restoredsha' });

    menu.handleMenuAction('restore-download');
    await vi.waitFor(() =>
      expect(restoreMock).toHaveBeenCalledWith('/library/workflows/flow.json')
    );
    await vi.waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        'workflows.restoreDownloaded.success',
        {},
        'success'
      )
    );
    // The confirmation goes through the app's modal, not the browser dialog.
    expect(showConfirmationModalMock).toHaveBeenCalledWith(
      expect.objectContaining({ danger: true })
    );
    // A blocking indicator covers the (potentially slow) re-download.
    expect(showSimpleLoadingMock).toHaveBeenCalled();
    expect(hideLoadingMock).toHaveBeenCalled();
    // The card is refreshed in place so it shows the "Updated" cue.
    expect(updateSingleItemMock).toHaveBeenCalledWith('/library/workflows/flow.json', {
      sha256: 'restoredsha',
    });
  });

  it('does not call restore when the confirmation is declined', async () => {
    showConfirmationModalMock.mockResolvedValue(false);

    menu.handleMenuAction('restore-download');
    await vi.waitFor(() => expect(showConfirmationModalMock).toHaveBeenCalled());

    expect(restoreMock).not.toHaveBeenCalled();
    expect(showSimpleLoadingMock).not.toHaveBeenCalled();
  });

  it('shows an error toast when restore fails and still hides the loading', async () => {
    showConfirmationModalMock.mockResolvedValue(true);
    const error = new Error('Workflow has no recorded CivitAI source to restore from');
    error.kind = 'no_source';
    restoreMock.mockRejectedValue(error);

    menu.handleMenuAction('restore-download');
    await vi.waitFor(() =>
      expect(showToastMock).toHaveBeenCalledWith(
        'workflows.restoreDownloaded.failed',
        { message: 'Workflow has no recorded CivitAI source to restore from' },
        'error'
      )
    );
    expect(hideLoadingMock).toHaveBeenCalled();
  });
});
