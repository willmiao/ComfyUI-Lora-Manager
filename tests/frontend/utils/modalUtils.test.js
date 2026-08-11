import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  MODAL_UTILS_MODULE,
  MODAL_MANAGER_MODULE,
  API_FACTORY_MODULE,
  UI_HELPERS_MODULE,
  I18N_MODULE,
  UNDO_HELPERS_MODULE,
  STATE_MODULE,
} = vi.hoisted(() => ({
  MODAL_UTILS_MODULE: new URL('../../../static/js/utils/modalUtils.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
}));

const deleteModelMock = vi.fn();
const resetAndReloadMock = vi.fn();
const showActionToastMock = vi.fn();
const handleUndoDeleteMock = vi.fn();
const translateMock = vi.fn((key) => key);
const closeModalMock = vi.fn();
const showModalMock = vi.fn();

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    getModal: vi.fn((id) => ({ element: document.getElementById(id) })),
    showModal: showModalMock,
    closeModal: closeModalMock,
  },
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({ deleteModel: deleteModelMock })),
  resetAndReload: resetAndReloadMock,
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showActionToast: showActionToastMock,
}));

vi.mock(I18N_MODULE, () => ({
  translate: translateMock,
}));

vi.mock(UNDO_HELPERS_MODULE, () => ({
  handleUndoDelete: handleUndoDeleteMock,
}));

describe('modalUtils confirmDelete undo flow', () => {
  beforeEach(() => {
    deleteModelMock.mockReset();
    resetAndReloadMock.mockReset();
    showActionToastMock.mockReset();
    handleUndoDeleteMock.mockReset();
    translateMock.mockClear();
    closeModalMock.mockReset();
    showModalMock.mockReset();
    document.body.innerHTML = `
      <div class="model-card" data-filepath="/models/foo.safetensors" data-name="Foo Model"></div>
      <div id="deleteModal"><div class="delete-model-info"></div></div>
    `;
    window.modelDuplicatesManager = undefined;
  });

  it('shows the undo action toast and wires undo to handleUndoDelete + resetAndReload', async () => {
    deleteModelMock.mockResolvedValue({ success: true, batch_id: 'batch-9' });

    const { showDeleteModal, confirmDelete } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');
    await confirmDelete();

    expect(deleteModelMock).toHaveBeenCalledWith('/models/foo.safetensors');
    expect(closeModalMock).toHaveBeenCalledWith('deleteModal');
    expect(showActionToastMock).toHaveBeenCalledTimes(1);

    const [key, params, type, options] = showActionToastMock.mock.calls[0];
    expect(key).toBe('toast.undo.deleted');
    expect(params).toEqual({ name: 'Foo Model' });
    expect(type).toBe('success');
    expect(options.actionText).toBe('toast.undo.action');
    expect(translateMock).toHaveBeenCalledWith('toast.undo.action');

    // Clicking Undo posts the batch and refreshes the model list
    options.onAction();
    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    const [batchId, refreshFn] = handleUndoDeleteMock.mock.calls[0];
    expect(batchId).toBe('batch-9');
    expect(typeof refreshFn).toBe('function');

    refreshFn();
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('does not show the action toast when the delete was not staged', async () => {
    deleteModelMock.mockResolvedValue({ success: true, batch_id: null });

    const { showDeleteModal, confirmDelete } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');
    await confirmDelete();

    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(closeModalMock).toHaveBeenCalledWith('deleteModal');
  });

  it('falls back to the file name when no card is present', async () => {
    deleteModelMock.mockResolvedValue({ success: true, batch_id: 'batch-10' });
    document.querySelector('.model-card').remove();

    const { showDeleteModal, confirmDelete } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/bar.safetensors');
    await confirmDelete();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock.mock.calls[0][1]).toEqual({ name: 'bar.safetensors' });
  });

  it('refreshes the duplicates badge when the manager is available', async () => {
    deleteModelMock.mockResolvedValue({ success: true, batch_id: 'batch-11' });
    const updateBadge = vi.fn();
    window.modelDuplicatesManager = { updateDuplicatesBadgeAfterRefresh: updateBadge };

    const { showDeleteModal, confirmDelete } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');
    await confirmDelete();

    expect(updateBadge).toHaveBeenCalledTimes(1);
  });
});

describe('modalUtils armDeleteButton delay-activate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    deleteModelMock.mockReset();
    showModalMock.mockReset();
    closeModalMock.mockReset();
    document.body.innerHTML = `
      <div class="model-card" data-filepath="/models/foo.safetensors" data-name="Foo Model"></div>
      <div id="deleteModal">
        <div class="delete-model-info"></div>
        <button class="cancel-btn">Cancel</button>
        <button class="delete-btn">Delete</button>
      </div>
    `;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens with the delete button disabled and enables it after exactly 1500ms', async () => {
    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');

    const deleteBtn = document.querySelector('#deleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1499);
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1);
    expect(deleteBtn.disabled).toBe(false);
  });

  it('clicking the disabled delete button fires nothing', async () => {
    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');

    const deleteBtn = document.querySelector('#deleteModal .delete-btn');
    deleteBtn.click();

    expect(deleteBtn.disabled).toBe(true);
    expect(deleteModelMock).not.toHaveBeenCalled();
  });

  it('closing during the countdown clears the timer and reopening re-arms a full 1500ms', async () => {
    const { showDeleteModal, closeDeleteModal } = await import(MODAL_UTILS_MODULE);

    showDeleteModal('/models/foo.safetensors');
    const deleteBtn = document.querySelector('#deleteModal .delete-btn');

    vi.advanceTimersByTime(1400);
    closeDeleteModal();
    expect(closeModalMock).toHaveBeenCalledWith('deleteModal');

    // Reopen — the stale timer must not enable the button early
    showDeleteModal('/models/foo.safetensors');
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1499);
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1);
    expect(deleteBtn.disabled).toBe(false);
  });
});

describe('modalUtils showDeleteModal warning copy and size line', () => {
  beforeEach(() => {
    showModalMock.mockReset();
    closeModalMock.mockReset();
    translateMock.mockClear();
    translateMock.mockImplementation((key) => key);
    document.body.innerHTML = `
      <div class="model-card" data-filepath="/models/foo.safetensors" data-name="Foo Model" data-file_size="2147483648"></div>
      <div id="deleteModal">
        <div class="delete-model-info"></div>
        <button class="delete-btn">Delete</button>
      </div>
    `;
  });

  afterEach(async () => {
    const { state } = await import(STATE_MODULE);
    state.global.settings.delete_undo_enabled = true;
  });

  function modelInfoHtml() {
    return document.querySelector('#deleteModal .delete-model-info').innerHTML;
  }

  it('shows the recoverable warning when delete_undo_enabled is truthy', async () => {
    const { state } = await import(STATE_MODULE);
    state.global.settings.delete_undo_enabled = true;

    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);
    showDeleteModal('/models/foo.safetensors');

    expect(modelInfoHtml()).toContain('modals.deleteModel.recoverableWarning');
    expect(modelInfoHtml()).not.toContain('modals.deleteModel.permanentWarning');
  });

  it('shows the permanent warning when delete_undo_enabled is falsy', async () => {
    const { state } = await import(STATE_MODULE);
    state.global.settings.delete_undo_enabled = false;

    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);
    showDeleteModal('/models/foo.safetensors');

    expect(modelInfoHtml()).toContain('modals.deleteModel.permanentWarning');
    expect(modelInfoHtml()).not.toContain('modals.deleteModel.recoverableWarning');
  });

  it('falls back to the neutral permanent warning when the setting is unavailable', async () => {
    const { state } = await import(STATE_MODULE);
    delete state.global.settings.delete_undo_enabled;

    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);
    showDeleteModal('/models/foo.safetensors');

    expect(modelInfoHtml()).toContain('modals.deleteModel.permanentWarning');
  });

  it('appends a formatted "Frees {size}" line when the card carries a file size', async () => {
    translateMock.mockImplementation((key, params) =>
      params && params.size ? `${key} ${params.size}` : key
    );

    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);
    showDeleteModal('/models/foo.safetensors');

    expect(modelInfoHtml()).toContain('modals.deleteModel.freesSpace 2.0 GB');
  });

  it('omits the size line when the card has no file size dataset', async () => {
    document.querySelector('.model-card').removeAttribute('data-file_size');

    const { showDeleteModal } = await import(MODAL_UTILS_MODULE);
    showDeleteModal('/models/foo.safetensors');

    expect(modelInfoHtml()).not.toContain('modals.deleteModel.freesSpace');
  });
});
