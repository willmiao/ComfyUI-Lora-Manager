import { describe, it, expect, beforeEach, vi } from 'vitest';

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: { graph: {} },
}));

const { fetchApiMock } = vi.hoisted(() => ({ fetchApiMock: vi.fn() }));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock },
}));

import {
  normalizeLoraNameKey,
  buildAvailableLoraSet,
  isLoraNameAvailable,
  getAvailableLoras,
  getAvailableLorasSync,
  resetAvailableLorasCache,
  onLibraryChanged,
  handleLibraryChangeMessage,
} from '../../../web/comfyui/loras_widget_utils.js';

describe('normalizeLoraNameKey', () => {
  it('normalizes backslashes to forward slashes', () => {
    expect(normalizeLoraNameKey('sub\\folder\\lora.safetensors')).toBe(
      'sub/folder/lora'
    );
  });

  it('strips known model extensions case-insensitively', () => {
    expect(normalizeLoraNameKey('lora.safetensors')).toBe('lora');
    expect(normalizeLoraNameKey('lora.CKPT')).toBe('lora');
    expect(normalizeLoraNameKey('lora.pt')).toBe('lora');
    expect(normalizeLoraNameKey('lora.bin')).toBe('lora');
  });

  it('keeps extensions the backend does not strip', () => {
    // Matches backend _strip_lora_extension: .gguf is not a LoRA extension.
    expect(normalizeLoraNameKey('lora.gguf')).toBe('lora.gguf');
  });

  it('leaves extension-less names unchanged', () => {
    expect(normalizeLoraNameKey('lora')).toBe('lora');
  });
});

describe('buildAvailableLoraSet', () => {
  it('registers both path and basename forms without extension', () => {
    const set = buildAvailableLoraSet(['sub/a.safetensors', 'b.ckpt']);
    expect(set.has('sub/a')).toBe(true);
    expect(set.has('a')).toBe(true);
    expect(set.has('b')).toBe(true);
  });

  it('ignores empty entries', () => {
    const set = buildAvailableLoraSet([null, '', 'sub/c.safetensors']);
    expect(set.has('sub/c')).toBe(true);
    expect(set.has('')).toBe(false);
  });
});

describe('isLoraNameAvailable', () => {
  const set = buildAvailableLoraSet(['sub/a.safetensors', 'b.ckpt']);

  it('treats everything as available while the set is not loaded', () => {
    expect(isLoraNameAvailable('anything.safetensors', null)).toBe(true);
  });

  it('matches by basename with or without extension', () => {
    expect(isLoraNameAvailable('a', set)).toBe(true);
    expect(isLoraNameAvailable('a.safetensors', set)).toBe(true);
    expect(isLoraNameAvailable('b.ckpt', set)).toBe(true);
  });

  it('matches by full folder path', () => {
    expect(isLoraNameAvailable('sub/a.safetensors', set)).toBe(true);
  });

  it('reports names not in the library', () => {
    expect(isLoraNameAvailable('missing.safetensors', set)).toBe(false);
  });

  it('falls back to the basename for folder-qualified names', () => {
    // Mirror of the backend basename fallback: a folder prefix that does not
    // match a stored path still resolves when the basename exists.
    expect(isLoraNameAvailable('sub/b.ckpt', set)).toBe(true);
    expect(isLoraNameAvailable('any/folder/a.safetensors', set)).toBe(true);
    expect(isLoraNameAvailable('sub/missing.safetensors', set)).toBe(false);
  });

  it('treats absolute paths as available without verification', () => {
    expect(isLoraNameAvailable('/abs/path/x.safetensors', set)).toBe(true);
    expect(isLoraNameAvailable('C:/abs/path/x.safetensors', set)).toBe(true);
  });
});

describe('getAvailableLoras caching', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('fetches the cycler list and builds the availability set', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [{ file_name: 'sub/a.safetensors' }, { file_name: 'b.ckpt' }],
      }),
    });

    const set = await getAvailableLoras();
    expect(fetchApiMock).toHaveBeenCalledWith('/lm/loras/cycler-list', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    expect(set.has('sub/a')).toBe(true);
    expect(set.has('b')).toBe(true);
    expect(getAvailableLorasSync().has('sub/a')).toBe(true);
  });

  it('shares a single in-flight request between concurrent callers', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, loras: [] }),
    });

    await Promise.all([getAvailableLoras(), getAvailableLoras()]);
    expect(fetchApiMock).toHaveBeenCalledTimes(1);
  });

  it('does not refetch while the cache is fresh', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, loras: [] }),
    });

    await getAvailableLoras();
    await getAvailableLoras();
    expect(fetchApiMock).toHaveBeenCalledTimes(1);
  });

  it('resolves to null and does not cache on fetch failure', async () => {
    fetchApiMock.mockRejectedValue(new Error('network down'));

    const result = await getAvailableLoras();
    expect(result).toBeNull();
    expect(getAvailableLorasSync()).toBeNull();
  });

  it('resolves to null on non-ok response', async () => {
    fetchApiMock.mockResolvedValue({ ok: false });

    const result = await getAvailableLoras();
    expect(result).toBeNull();
  });
});

describe('library change invalidation', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('invalidates the availability cache and notifies listeners on models_changed', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [{ file_name: 'old.safetensors' }],
      }),
    });

    const listener = vi.fn();
    const unsubscribe = onLibraryChanged(listener);
    try {
      await getAvailableLoras();
      expect(getAvailableLorasSync().has('old')).toBe(true);

      // Simulate a deletion in the Lora Manager UI: the cache is dropped and
      // listeners are notified so widgets re-render with fresh data.
      handleLibraryChangeMessage({ type: 'models_changed' });
      expect(listener).toHaveBeenCalledTimes(1);
      expect(getAvailableLorasSync()).toBeNull();

      fetchApiMock.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, loras: [] }),
      });
      await getAvailableLoras();
      expect(getAvailableLorasSync().has('old')).toBe(false);
    } finally {
      unsubscribe();
    }
  });

  it('ignores unrelated messages', () => {
    const listener = vi.fn();
    const unsubscribe = onLibraryChanged(listener);
    try {
      handleLibraryChangeMessage({ type: 'download_progress' });
      handleLibraryChangeMessage({ type: 'init_progress' });
      handleLibraryChangeMessage(null);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it('unsubscribes listeners', () => {
    const listener = vi.fn();
    const unsubscribe = onLibraryChanged(listener);
    unsubscribe();
    handleLibraryChangeMessage({ type: 'models_changed' });
    expect(listener).not.toHaveBeenCalled();
  });
});
