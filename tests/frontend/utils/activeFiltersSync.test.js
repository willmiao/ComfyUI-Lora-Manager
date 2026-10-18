import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { setStorageItem, removeStorageItem, setActiveFiltersListener } from '../../../static/js/utils/storageHelpers.js';
import { initActiveFiltersSync, pushActiveFilters } from '../../../static/js/utils/activeFiltersSync.js';

const okResponse = () => ({ ok: true, status: 200 });

describe('activeFiltersSync', () => {
  let fetchMock;

  beforeEach(() => {
    fetchMock = vi.fn(() => Promise.resolve(okResponse()));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('pushes current state immediately on init', async () => {
    setStorageItem('loras_activeFolder', 'SD_XL');
    setStorageItem('loras_recursiveSearch', false);
    setStorageItem('loras_filters', { baseModel: ['SDXL 1.0'], tags: { anime: 'include' } });

    initActiveFiltersSync('loras');
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/lm/loras/active-filters');
    expect(options.method).toBe('PUT');
    expect(JSON.parse(options.body)).toEqual({
      activeFolder: 'SD_XL',
      recursiveSearch: false,
      filters: { baseModel: ['SDXL 1.0'], tags: { anime: 'include' } },
    });
  });

  it('syncs with debounce when a filter key changes', async () => {
    vi.useFakeTimers();
    initActiveFiltersSync('loras');
    fetchMock.mockClear();

    setStorageItem('loras_activeFolder', 'anime');
    setStorageItem('loras_activeFolder', 'anime/sub');

    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(400);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.activeFolder).toBe('anime/sub');
  });

  it('does not sync for unrelated storage keys', async () => {
    vi.useFakeTimers();
    initActiveFiltersSync('loras');
    fetchMock.mockClear();

    setStorageItem('loras_sort', 'name');
    setStorageItem('theme', 'dark');

    await vi.advanceTimersByTimeAsync(1000);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('pushes null filters after the filters key is removed', async () => {
    vi.useFakeTimers();
    setStorageItem('loras_filters', { baseModel: ['Pony'] });
    initActiveFiltersSync('loras');
    fetchMock.mockClear();

    removeStorageItem('loras_filters');
    await vi.advanceTimersByTimeAsync(400);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.filters).toBeNull();
  });

  it('normalizes the legacy "null" folder string to null', async () => {
    localStorage.setItem('lora_manager_loras_activeFolder', 'null');

    await pushActiveFilters('loras');

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.activeFolder).toBeNull();
    expect(body.recursiveSearch).toBe(true);
  });

  it('warns instead of throwing when the request fails', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(pushActiveFilters('loras')).resolves.toBeUndefined();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});

describe('storageHelpers active-filter listener', () => {
  afterEach(() => {
    setActiveFiltersListener(null);
  });

  it('notifies with the page type for filter keys', () => {
    const listener = vi.fn();
    setActiveFiltersListener(listener);

    setStorageItem('loras_activeFolder', 'a');
    setStorageItem('checkpoints_recursiveSearch', true);
    removeStorageItem('embeddings_filters');

    expect(listener.mock.calls.map((call) => call[0])).toEqual([
      'loras',
      'checkpoints',
      'embeddings',
    ]);
  });

  it('ignores non-filter keys', () => {
    const listener = vi.fn();
    setActiveFiltersListener(listener);

    setStorageItem('loras_sort', 'name');
    removeStorageItem('version_info');

    expect(listener).not.toHaveBeenCalled();
  });
});
