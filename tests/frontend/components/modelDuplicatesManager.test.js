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

vi.mock('../../../static/js/utils/modalUtils.js', () => ({}));

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

describe('ModelDuplicatesManager card selection', () => {
  it('selects from the video preview without enabling native playback', async () => {
    const manager = await createManager();
    const group = createGroup();
    group.models[0].preview_url = '/previews/car.mp4';
    manager.duplicateGroups = [group];
    manager.renderDuplicateGroups();

    const card = document.querySelector(`[data-file-path="${carPath}"]`);
    const video = card.querySelector('video');
    const source = video.querySelector('source');

    expect(video.controls).toBe(false);
    expect(video.preload).toBe('metadata');
    expect(video.style.pointerEvents).toBe('none');
    expect(video.hasAttribute('autoplay')).toBe(false);
    expect(source.getAttribute('src')).toBe('/previews/car.mp4');

    video.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(manager.selectedForDeletion.has(carPath)).toBe(true);
    expect(card.classList.contains('duplicate-selected')).toBe(true);
    expect(card.querySelector('.selector-checkbox').checked).toBe(true);

    card.querySelector('.card-footer').dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(manager.selectedForDeletion.has(carPath)).toBe(false);
    expect(card.classList.contains('duplicate-selected')).toBe(false);
  });

  it('selects all but the newest model in every group', async () => {
    const manager = await createManager();
    const first = createGroup('first-hash');
    const second = createGroup('second-hash');
    first.models[0].file_path = '/models/first-old.safetensors';
    first.models[1].file_path = '/models/first-new.safetensors';
    second.models[0].file_path = '/models/second-old.safetensors';
    second.models[1].file_path = '/models/second-new.safetensors';
    first.models[0].modified = 1;
    first.models[1].modified = 2;
    second.models[0].modified = 3;
    second.models[1].modified = 4;
    manager.duplicateGroups = [first, second];

    manager.selectLatestDuplicates();

    expect(Array.from(manager.selectedForDeletion).sort()).toEqual([
      '/models/first-old.safetensors',
      '/models/second-old.safetensors',
    ]);
  });

  it('selects every item in a large group before all cards are rendered', async () => {
    const manager = await createManager();
    const models = Array.from({ length: 14 }, (_, index) => createModel(
      `/models/loras/model-${index}.safetensors`,
      'shared-hash'
    ));
    manager.duplicateGroups = [{ hash: 'shared-hash', models }];
    manager.renderDuplicateGroups();

    expect(document.querySelectorAll('.selector-checkbox')).toHaveLength(12);

    manager.toggleSelectAllInGroup('shared-hash');

    expect(manager.selectedForDeletion.size).toBe(14);
    document.querySelector('.group-toggle-btn').click();

    const checkboxes = Array.from(document.querySelectorAll('.selector-checkbox'));
    expect(checkboxes).toHaveLength(14);
    expect(checkboxes.every(checkbox => checkbox.checked)).toBe(true);
  });

  it('renders all groups when IntersectionObserver is unavailable', async () => {
    const manager = await createManager();
    const originalObserver = global.IntersectionObserver;
    delete global.IntersectionObserver;

    try {
      manager.duplicateGroups = Array.from({ length: 30 }, (_, index) => createGroup(`hash-${index}`));
      manager.renderDuplicateGroups();

      expect(document.querySelectorAll('.duplicate-group')).toHaveLength(30);
      expect(document.querySelector('.duplicates-group-sentinel')).toBeNull();
    } finally {
      if (originalObserver) {
        global.IntersectionObserver = originalObserver;
      }
    }
  });

  it('loads later duplicate groups when the sentinel intersects', async () => {
    const manager = await createManager();
    const originalObserver = global.IntersectionObserver;
    let observer;
    global.IntersectionObserver = class {
      constructor(callback) {
        this.callback = callback;
        observer = this;
      }
      observe() {}
      disconnect() {}
    };

    try {
      manager.duplicateGroups = Array.from({ length: 30 }, (_, index) => createGroup(`hash-${index}`));
      manager.renderDuplicateGroups();

      expect(document.querySelectorAll('.duplicate-group')).toHaveLength(25);
      expect(document.querySelector('.duplicates-group-sentinel')).not.toBeNull();

      observer.callback([{ isIntersecting: true }]);

      expect(document.querySelectorAll('.duplicate-group')).toHaveLength(30);
      expect(document.querySelector('.duplicates-group-sentinel')).toBeNull();
    } finally {
      if (originalObserver) {
        global.IntersectionObserver = originalObserver;
      } else {
        delete global.IntersectionObserver;
      }
    }
  });
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

    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(manager.inDuplicateMode).toBe(true);

    await lastActionToastOptions().onAction();

    expect(handleUndoDeleteMock).toHaveBeenCalledTimes(1);
    expect(handleUndoDeleteMock).toHaveBeenCalledWith('model-batch-1', expect.any(Function));
    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(manager.inDuplicateMode).toBe(true);

    const refreshFn = handleUndoDeleteMock.mock.calls[0][1];
    resetAndReloadMock.mockClear();
    await refreshFn();
    expect(resetAndReloadMock).toHaveBeenCalledTimes(1);
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
    expect(manager.inDuplicateMode).toBe(false);
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

  it('reports a failure instead of a success when nothing was deleted', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({
      success: false,
      error: 'Permission denied',
      total_deleted: 0,
      results: [{ file_path: carPath, success: false, error: 'Permission denied' }],
    });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);

    await manager.confirmDeleteDuplicates();

    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.deleteFailed',
      { type: 'loras', message: expect.stringContaining('Permission denied') },
      'error'
    );
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.duplicates.deleteSuccess',
      expect.anything(),
      expect.anything()
    );
    expect(showActionToastMock).not.toHaveBeenCalled();
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });

  it('surfaces per-file failures that arrive alongside a successful response', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({
      success: true,
      total_deleted: 1,
      batch_id: 'model-batch-1',
      results: [
        { file_path: carPath, success: true },
        { file_path: copyPath, success: false, error: 'The file is in use' },
      ],
    });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(copyPath);

    await manager.confirmDeleteDuplicates();

    expect(showActionToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.deletePartialFailed',
      { failed: 1, type: 'loras', message: 'The file is in use' },
      'error'
    );
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });

  it('warns when the files were deleted but the cache was not updated', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({
      success: true,
      total_deleted: 1,
      cache_updated: false,
    });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);

    await manager.confirmDeleteDuplicates();

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.duplicates.cacheUpdateFailed',
      {},
      'warning'
    );
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });

  it('removes only successful deletions and keeps failed items selected', async () => {
    const manager = await createManager();
    const thirdPath = '/models/loras/aspark-owl-third.safetensors';
    manager.duplicateGroups = [{
      hash: 'actual-hash',
      models: [
        createModel(carPath, 'actual-hash'),
        createModel(copyPath, 'actual-hash'),
        createModel(thirdPath, 'actual-hash'),
      ],
    }];
    const removeMultipleMock = vi.fn();
    state.virtualScroller.removeMultipleItemsByFilePath = removeMultipleMock;
    mockDeleteAndRecheck({
      success: true,
      total_deleted: 1,
      batch_id: 'model-batch-1',
      results: [
        { file_path: carPath, success: true },
        { file_path: copyPath, success: false, error: 'The file is in use' },
      ],
    });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);
    manager.selectedForDeletion.add(copyPath);

    await manager.confirmDeleteDuplicates();

    expect(manager.duplicateGroups[0].models.map(model => model.file_path)).toEqual([
      copyPath,
      thirdPath,
    ]);
    expect(Array.from(manager.selectedForDeletion)).toEqual([copyPath]);
    expect(removeMultipleMock).toHaveBeenCalledWith([carPath]);
    expect(resetAndReloadMock).not.toHaveBeenCalled();
  });

  it('does not reload the library or rescan duplicates after deletion', async () => {
    const manager = await createManager();
    mockDeleteAndRecheck({ success: true, total_deleted: 1, batch_id: 'model-batch-1' });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);

    await manager.confirmDeleteDuplicates();

    const requestedUrls = global.fetch.mock.calls.map(([url]) => String(url));
    expect(requestedUrls).toEqual(['/api/lm/loras/bulk-delete']);
    expect(resetAndReloadMock).not.toHaveBeenCalled();
    expect(manager._libraryNeedsRefresh).toBe(true);

    await manager.exitDuplicateMode();
    expect(resetAndReloadMock).toHaveBeenCalledWith(true);
  });

  it('blocks duplicate submissions and shows a busy state until deletion finishes', async () => {
    const manager = await createManager();
    let finishDelete;
    global.fetch = vi.fn((url) => {
      if (String(url).includes('bulk-delete')) {
        return new Promise(resolve => {
          finishDelete = () => resolve({
            ok: true,
            statusText: 'OK',
            json: async () => ({ success: true, total_deleted: 1, batch_id: 'model-batch-1' }),
          });
        });
      }
      return Promise.resolve({
        ok: true,
        statusText: 'OK',
        json: async () => ({ success: true, duplicates: [] }),
      });
    });

    manager.inDuplicateMode = true;
    manager.selectedForDeletion.add(carPath);
    const deleteButton = document.querySelector('.btn-delete-selected');

    const firstRequest = manager.confirmDeleteDuplicates();
    await Promise.resolve();

    expect(manager._isDeleting).toBe(true);
    expect(deleteButton.disabled).toBe(true);
    expect(state.loadingManager.showSimpleLoading).toHaveBeenCalledWith(
      'duplicates.deleting'
    );
    expect(await manager.confirmDeleteDuplicates()).toBe(false);
    expect(global.fetch.mock.calls.filter(([url]) => String(url).includes('bulk-delete'))).toHaveLength(1);

    finishDelete();
    await firstRequest;

    expect(manager._isDeleting).toBe(false);
    expect(state.loadingManager.hide).toHaveBeenCalled();
  });
});
