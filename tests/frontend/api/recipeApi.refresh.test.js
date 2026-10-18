import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.hoisted(() => vi.fn());
const loadingManagerMock = vi.hoisted(() => ({
  show: vi.fn(),
  hide: vi.fn(),
  restoreProgressBar: vi.fn(),
  setProgress: vi.fn(),
  setStatus: vi.fn(),
}));
const virtualScrollerMock = vi.hoisted(() => ({
  refreshWithData: vi.fn(),
}));
const getCurrentPageStateMock = vi.hoisted(() => vi.fn());
const etaUpdateMock = vi.hoisted(() => vi.fn(() => 'ETA soon'));

vi.mock('../../../static/js/components/RecipeCard.js', () => ({
  RecipeCard: vi.fn(() => ({ element: document.createElement('div') })),
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: {
    loadingManager: loadingManagerMock,
    virtualScroller: virtualScrollerMock,
  },
  getCurrentPageState: getCurrentPageStateMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, params, fallback) => {
    if (fallback) {
      return Object.entries(params || {}).reduce(
        (text, [name, value]) => text.replaceAll(`{${name}}`, value),
        fallback
      );
    }
    return key;
  }),
}));

vi.mock('../../../static/js/utils/infiniteScroll.js', () => ({
  captureScrollPosition: vi.fn(),
  restoreScrollPosition: vi.fn(),
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  WS_ENDPOINTS: { fetchProgress: '/ws/fetch-progress' },
}));

vi.mock('../../../static/js/utils/scanEtaUtils.js', () => ({
  createScanEtaTracker: () => ({ update: etaUpdateMock }),
}));

import { refreshRecipes } from '../../../static/js/api/recipeApi.js';

class FakeWebSocket {
  static instances = [];
  static failNextConnection = false;

  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onerror = null;
    this.onmessage = null;
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
    const shouldFail = FakeWebSocket.failNextConnection;
    FakeWebSocket.failNextConnection = false;
    queueMicrotask(() => {
      if (shouldFail) {
        this.onerror?.(new Error('connection refused'));
      } else {
        this.onopen?.();
      }
    });
  }

  emit(data) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

async function flushMicrotasks() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('refreshRecipes scan progress', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCurrentPageStateMock.mockReturnValue({
      pageSize: 50,
      currentPage: 1,
      hasMore: true,
      isLoading: false,
      sortBy: 'date:desc',
      showFavoritesOnly: false,
      activeFolder: null,
      searchOptions: { recursive: true },
      customFilter: { active: false },
      filters: {},
    });
    FakeWebSocket.instances = [];
    FakeWebSocket.failNextConnection = false;
    vi.stubGlobal('WebSocket', FakeWebSocket);
  });

  afterEach(() => {
    delete global.fetch;
    vi.unstubAllGlobals();
  });

  function mockFetchPendingScan() {
    let resolveScan;
    global.fetch = vi.fn((input) => {
      const url = String(input);
      if (url.includes('/scan')) {
        return new Promise((resolve) => { resolveScan = resolve; });
      }
      // Recipe list reload after the scan completes
      return Promise.resolve({
        ok: true,
        json: async () => ({ items: [], total: 0, total_pages: 0 }),
      });
    });
    return {
      resolveOk: (payload = { status: 'success' }) =>
        resolveScan({ ok: true, json: async () => payload }),
      resolveNotOk: () =>
        resolveScan({ ok: false, status: 500, statusText: 'Server Error' }),
    };
  }

  async function startRefresh(fullRebuild = true) {
    const promise = refreshRecipes(fullRebuild);
    await vi.waitFor(() => {
      expect(FakeWebSocket.instances.length).toBe(1);
    });
    await flushMicrotasks();
    const socket = FakeWebSocket.instances[0];
    await vi.waitFor(() => {
      expect(socket.onmessage).toBeTruthy();
    });
    return { promise, socket };
  }

  it('shows scan progress updates from the WebSocket channel', async () => {
    const fetchControl = mockFetchPendingScan();
    const { promise, socket } = await startRefresh();

    expect(socket.url).toBe(`ws://${window.location.host}/ws/fetch-progress`);

    socket.emit({
      type: 'scan_progress',
      status: 'started',
      stage: 'scan_folders',
      model_type: 'recipe',
      pageType: 'recipes',
      full_rebuild: true,
      progress: 0,
    });
    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'process_models',
      model_type: 'recipe',
      pageType: 'recipes',
      full_rebuild: true,
      progress: 50,
      processed: 5,
      total: 10,
      current_name: 'style.recipe.json',
    });

    expect(loadingManagerMock.setProgress).toHaveBeenCalledWith(0);
    expect(loadingManagerMock.setProgress).toHaveBeenCalledWith(50);
    const lastStatus = loadingManagerMock.setStatus.mock.calls.at(-1)[0];
    expect(lastStatus).toContain('(5/10)');
    expect(lastStatus).toContain('style.recipe.json');
    expect(lastStatus).toContain('ETA soon');
    expect(etaUpdateMock).toHaveBeenCalledWith(5, 10);

    fetchControl.resolveOk();
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      { action: 'Full rebuild' },
      'success'
    );
    expect(socket.close).toHaveBeenCalled();
    expect(loadingManagerMock.hide).toHaveBeenCalled();
  });

  it('ignores messages for other types or other model types', async () => {
    const fetchControl = mockFetchPendingScan();
    const { promise, socket } = await startRefresh();

    socket.emit({
      type: 'scan_progress',
      status: 'processing',
      stage: 'process_models',
      model_type: 'lora',
      progress: 33,
      processed: 1,
      total: 3,
    });
    socket.emit({
      type: 'example_images_progress',
      status: 'running',
      model_type: 'recipe',
      progress: 66,
      processed: 2,
      total: 3,
    });

    expect(loadingManagerMock.setProgress).not.toHaveBeenCalled();
    expect(loadingManagerMock.setStatus).not.toHaveBeenCalled();

    fetchControl.resolveOk();
    await promise;
  });

  it('falls back to plain loading when the WebSocket connection fails', async () => {
    FakeWebSocket.failNextConnection = true;
    global.fetch = vi.fn((input) => {
      const url = String(input);
      if (url.includes('/scan')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'success' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ items: [], total: 0, total_pages: 0 }),
      });
    });

    await refreshRecipes(false);

    expect(global.fetch).toHaveBeenCalled();
    const [url] = global.fetch.mock.calls[0];
    expect(url.searchParams.get('full_rebuild')).toBe('false');
    expect(loadingManagerMock.show).toHaveBeenCalledWith('Refreshing Recipes...', 0);
    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      { action: 'Refresh' },
      'success'
    );
  });

  it('shows the cancelled toast when the server reports cancellation', async () => {
    const fetchControl = mockFetchPendingScan();
    const { promise } = await startRefresh();

    fetchControl.resolveOk({ status: 'cancelled' });
    await promise;

    expect(showToastMock).toHaveBeenCalledWith('toast.api.operationCancelled', {}, 'info');
    expect(showToastMock).not.toHaveBeenCalledWith(
      'toast.api.refreshComplete',
      expect.anything(),
      expect.anything()
    );
  });

  it('reports refresh failures through the error toast', async () => {
    const fetchControl = mockFetchPendingScan();
    const { promise } = await startRefresh();

    fetchControl.resolveNotOk();
    await promise;

    expect(showToastMock).toHaveBeenCalledWith(
      'toast.api.refreshFailed',
      { action: 'rebuild', type: 'recipe' },
      'error'
    );
    expect(loadingManagerMock.hide).toHaveBeenCalled();
  });
});
