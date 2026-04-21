import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const resetAndReloadMock = vi.fn();

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  resetAndReload: resetAndReloadMock,
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
