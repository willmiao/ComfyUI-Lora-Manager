import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const showActionToastMock = vi.fn();
const handleUndoDeleteMock = vi.fn();
const resetAndReloadMock = vi.fn();

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
  showActionToast: showActionToastMock,
}));

vi.mock('../../../static/js/utils/undoHelpers.js', () => ({
  handleUndoDelete: handleUndoDeleteMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  resetAndReload: resetAndReloadMock,
}));

vi.mock('../../../static/js/utils/modalUtils.js', () => ({
  armDeleteButton: (modalElement) => {
    if (!modalElement) return null;
    const buttons = modalElement.querySelectorAll('.delete-btn');
    buttons.forEach((button) => { button.disabled = true; });
    return setTimeout(() => {
      buttons.forEach((button) => { button.disabled = false; });
    }, 1500);
  },
}));

const { ModelDuplicatesManager } = await import('../../../static/js/components/ModelDuplicatesManager.js');
const { state } = await import('../../../static/js/state/index.js');

const carPath = '/models/loras/aspark-owl.safetensors';
const copyPath = '/models/loras/aspark-owl-copy.safetensors';
const stalePath = '/models/loras/old-mismatch.safetensors';

function createModel(filePath, sha256, modelName = 'Aspark Owl - 2019') {
  return {
    file_path: filePath,
    file_name: filePath.split('/').pop(),
    model_name: modelName,
    sha256,
    preview_url: '',
    preview_nsfw_level: 0,
    modified: Date.now(),
    civitai: { name: 'Version 1' },
  };
}

function createGroup(hash = 'actual-hash') {
  return {
    hash,
    models: [
      createModel(carPath, hash),
      createModel(copyPath, hash, 'Aspark Owl - 2019 Copy'),
    ],
  };
}

async function createManager() {
  document.body.innerHTML = `
    <div id="modelGrid"></div>
    <span id="duplicatesBadge"></span>
    <span id="duplicatesSelectedCount"></span>
    <button class="btn-delete-selected"></button>
  `;

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    statusText: 'OK',
    json: async () => ({ success: true, duplicates: [] }),
  });

  const manager = new ModelDuplicatesManager({}, 'loras');

  await Promise.resolve();
  await Promise.resolve();
  global.fetch.mockClear();

  return manager;
}

beforeEach(() => {
  vi.clearAllMocks();

  state.loadingManager = {
    showSimpleLoading: vi.fn(),
    hide: vi.fn(),
  };
});

afterEach(() => {
  vi.restoreAllMocks();
  state.loadingManager = null;
});

describe('ModelDuplicatesManager verification state', () => {
  it('clears stale Different Hash state when a later verification confirms the group is duplicate', async () => {
    const manager = await createManager();
    const group = createGroup();

    manager.duplicateGroups = [group];
    manager.mismatchedFiles.set(carPath, 'old-actual-hash');
    manager.renderDuplicateGroups();

    expect(document.querySelector(`[data-file-path="${carPath}"]`).classList.contains('hash-mismatch')).toBe(true);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      statusText: 'OK',
      json: async () => ({
        success: true,
        verified_as_duplicates: true,
        mismatched_files: [],
        new_hash_map: {},
      }),
    });

    await manager.handleVerifyHashes(group);

    const carCard = document.querySelector(`[data-file-path="${carPath}"]`);
    const carCheckbox = carCard.querySelector('.selector-checkbox');

    expect(manager.mismatchedFiles.has(carPath)).toBe(false);
    expect(carCard.classList.contains('hash-mismatch')).toBe(false);
    expect(carCard.querySelector('.mismatch-badge')).toBeNull();
    expect(carCheckbox.disabled).toBe(false);
  });

  it('keeps showing Different Hash for files returned as mismatched by the current verification', async () => {
    const manager = await createManager();
    const group = createGroup('metadata-hash');

    manager.duplicateGroups = [group];
    manager.selectedForDeletion.add(carPath);
    manager.selectedForDeletion.add(copyPath);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      statusText: 'OK',
      json: async () => ({
        success: true,
        verified_as_duplicates: false,
        mismatched_files: [carPath],
        new_hash_map: {
          [carPath]: 'actual-car-hash',
        },
      }),
    });

    await manager.handleVerifyHashes(group);

    const carCard = document.querySelector(`[data-file-path="${carPath}"]`);
    const carCheckbox = carCard.querySelector('.selector-checkbox');

    expect(manager.mismatchedFiles.get(carPath)).toBe('actual-car-hash');
    expect(manager.selectedForDeletion.has(carPath)).toBe(false);
    expect(manager.selectedForDeletion.has(copyPath)).toBe(true);
    expect(carCard.classList.contains('hash-mismatch')).toBe(true);
    expect(carCard.querySelector('.mismatch-badge')?.textContent).toContain('Different Hash');
    expect(carCheckbox.disabled).toBe(true);
  });

  it('refreshes selected count and delete button when selected files become mismatched', async () => {
    const manager = await createManager();
    const group = createGroup('metadata-hash');

    manager.duplicateGroups = [group];
    manager.selectedForDeletion.add(carPath);
    manager.updateSelectedCount();

    expect(document.getElementById('duplicatesSelectedCount').textContent).toBe('1');
    expect(document.querySelector('.btn-delete-selected').disabled).toBe(false);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      statusText: 'OK',
      json: async () => ({
        success: true,
        verified_as_duplicates: false,
        mismatched_files: [carPath],
        new_hash_map: {
          [carPath]: 'actual-car-hash',
        },
      }),
    });

    await manager.handleVerifyHashes(group);

    expect(manager.selectedForDeletion.size).toBe(0);
    expect(document.getElementById('duplicatesSelectedCount').textContent).toBe('0');
    expect(document.querySelector('.btn-delete-selected').disabled).toBe(true);
    expect(document.querySelector('.btn-delete-selected').classList.contains('disabled')).toBe(true);
  });

  it('preserves valid selected deletion candidates when verification succeeds', async () => {
    const manager = await createManager();
    const group = createGroup();

    manager.duplicateGroups = [group];
    manager.selectedForDeletion.add(carPath);
    manager.selectedForDeletion.add(copyPath);

    global.fetch.mockResolvedValueOnce({
      ok: true,
      statusText: 'OK',
      json: async () => ({
        success: true,
        verified_as_duplicates: true,
        mismatched_files: [],
        new_hash_map: {},
      }),
    });

    await manager.handleVerifyHashes(group);

    expect(manager.selectedForDeletion.has(carPath)).toBe(true);
    expect(manager.selectedForDeletion.has(copyPath)).toBe(true);
    expect(document.querySelector(`[data-file-path="${carPath}"] .selector-checkbox`).checked).toBe(true);
    expect(document.querySelector(`[data-file-path="${copyPath}"] .selector-checkbox`).checked).toBe(true);
  });

  it('prunes mismatch and verified state that no longer belongs to refreshed duplicate groups', async () => {
    const manager = await createManager();
    const visibleGroup = createGroup('visible-hash');

    manager.mismatchedFiles.set(stalePath, 'stale-hash');
    manager.mismatchedFiles.set(carPath, 'visible-mismatch');
    manager.verifiedGroups.add('stale-group-hash');
    manager.verifiedGroups.add('visible-hash');

    global.fetch.mockResolvedValueOnce({
      ok: true,
      statusText: 'OK',
      json: async () => ({
        success: true,
        duplicates: [visibleGroup],
      }),
    });

    await manager.findDuplicates();

    expect(manager.mismatchedFiles.has(stalePath)).toBe(false);
    expect(manager.mismatchedFiles.has(carPath)).toBe(true);
    expect(manager.verifiedGroups.has('stale-group-hash')).toBe(false);
    expect(manager.verifiedGroups.has('visible-hash')).toBe(true);
  });
});

describe('ModelDuplicatesManager confirmDeleteDuplicates undo flows', () => {
  function mockDeleteAndRecheck(deletePayload) {
    global.fetch = vi.fn((url) => {
      if (String(url).includes('bulk-delete')) {
        return Promise.resolve({
          ok: true,
          statusText: 'OK',
          json: async () => deletePayload,
        });
      }
      return Promise.resolve({
        ok: true,
        statusText: 'OK',
        json: async () => ({ success: true, duplicates: [] }),
      });
    });
  }

  function lastActionToastOptions() {
    const call = showActionToastMock.mock.calls[showActionToastMock.mock.calls.length - 1];
    return call[3];
  }

  beforeEach(() => {
    handleUndoDeleteMock.mockResolvedValue(true);
    state.virtualScroller = { enable: vi.fn(), disable: vi.fn() };
    globalThis.modalManager = { showModal: vi.fn(), closeModal: vi.fn() };
  });

  afterEach(() => {
    state.virtualScroller = null;
    delete globalThis.modalManager;
  });

  it('shows the undo action toast with the batch id and refreshes models on undo', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({ success: true, total_deleted: 1, batch_id: 'model-batch-1' });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showActionToastMock).toHaveBeenCalledWith(
      'toast.undo.deletedBulk',
      { count: 1 },
      'success',
      expect.objectContaining({
        actionText: 'toast.undo.action',
        onAction: expect.any(Function),
      })
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.duplicates.deleteSuccess',
      expect.anything(),
      expect.anything()
    );

    // The existing reset + find-duplicates re-check path still runs
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    // No remaining duplicates -> duplicate mode exited
    expect(manager.inDuplicateMode).toBe(false);

    lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    expect(handleUndoDeleteMock).toHaveBeenCalledWith('model-batch-1', expect.any(Function));

    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    resetAndReloadMock.mockClear();
    refreshFn();
    expect(resetAndReloadMock).toHaveBeenCalledTimes(1);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('undoes the batch_ids fallback sequentially with one final refresh and restored toast', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({ success: true, total_deleted: 2, batch_ids: ['mb-1', 'mb-2'] });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);
    manager.selectedForDeletion.add(copyPath);

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    resetAndReloadMock.mockClear();
    await lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(2);
    expect(handleUndoDeleteMock.mock.calls[0]).toEqual(['mb-1', null, { showToast: false, refresh: false }]);
    expect(handleUndoDeleteMock.mock.calls[1]).toEqual(['mb-2', null, { showToast: false, refresh: false }]);
    expect(resetAndReloadMock).toHaveBeenCalledTimes(1);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.restored', {}, 'success');
  });

  it('keeps the legacy success toast when the response carries no batch field', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({ success: true, total_deleted: 1 });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.deleteSuccess',
      { count: 1, type: 'loras' },
      'success'
    );
  });
});

describe('ModelDuplicatesManager deleteSelectedDuplicates delay-activate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.modalManager = { showModal: vi.fn(), closeModal: vi.fn() };
  });

  afterEach(() => {
    vi.useRealTimers();
    delete globalThis.modalManager;
  });

  it('opens with the delete button disabled and enables it after 1500ms', async () => {
    const manager = await createManager();
    document.body.insertAdjacentHTML('beforeend', `
      <div id="modelDuplicateDeleteModal" class="modal delete-modal">
        <div class="delete-model-info"><p><span id="modelDuplicateDeleteCount">0</span></p></div>
        <button class="cancel-btn">Cancel</button>
        <button class="delete-btn">Delete</button>
      </div>
    `);
    manager.selectedForDeletion.add(carPath);

    await manager.deleteSelectedDuplicates();

    expect(globalThis.modalManager.showModal).toHaveBeenCalledWith('modelDuplicateDeleteModal');
    const deleteBtn = document.querySelector('#modelDuplicateDeleteModal .delete-btn');
    expect(deleteBtn.disabled).toBe(true);

    vi.advanceTimersByTime(1500);
    expect(deleteBtn.disabled).toBe(false);
  });
});
