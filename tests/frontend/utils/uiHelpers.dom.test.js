import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  I18N_MODULE,
  STATE_MODULE,
  STORAGE_MODULE,
  CONSTANTS_MODULE,
  EVENT_MANAGER_MODULE,
  UI_HELPERS_MODULE,
} = vi.hoisted(() => ({
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  CONSTANTS_MODULE: new URL('../../../static/js/utils/constants.js', import.meta.url).pathname,
  EVENT_MANAGER_MODULE: new URL('../../../static/js/utils/EventManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
}));

const translateMock = vi.fn((key, _params, fallback) => fallback || key);
const getStorageItemMock = vi.fn();
const setStorageItemMock = vi.fn();

vi.mock(I18N_MODULE, () => ({
  translate: translateMock,
}));

vi.mock(STATE_MODULE, () => ({
  state: {},
  getCurrentPageState: vi.fn(),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: getStorageItemMock,
  setStorageItem: setStorageItemMock,
}));

vi.mock(CONSTANTS_MODULE, () => ({
  NODE_TYPE_ICONS: {},
  DEFAULT_NODE_COLOR: '#ffffff',
}));

vi.mock(EVENT_MANAGER_MODULE, () => ({
  eventManager: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    addHandler: vi.fn(),
    removeHandler: vi.fn(),
    setState: vi.fn(),
  },
}));

describe('UI helper DOM utilities', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-theme');
    getStorageItemMock.mockReset();
    setStorageItemMock.mockReset();
    translateMock.mockReset();
    globalThis.requestAnimationFrame = (cb) => cb();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete global.fetch;
  });

  it('creates toast elements and cleans them up after timeout', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Toast message');

    const { showToast } = await import(UI_HELPERS_MODULE);

    showToast('uiHelpers.clipboard.copied', {}, 'success');

    const container = document.querySelector('.toast-container');
    expect(container).not.toBeNull();
    expect(container.querySelectorAll('.toast')).toHaveLength(1);

    await Promise.resolve();
    vi.advanceTimersByTime(2000);

    const toast = container.querySelector('.toast');
    toast.dispatchEvent(new Event('transitionend', { bubbles: true }));
    await Promise.resolve();

    expect(toast.classList.contains('show')).toBe(false);
  });

  it('toggles the persisted theme and updates DOM attributes', async () => {
    getStorageItemMock.mockReturnValue('light');
    document.body.innerHTML = '<button class="theme-toggle"></button>';
    globalThis.matchMedia = vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    const { toggleTheme } = await import(UI_HELPERS_MODULE);

    const nextTheme = toggleTheme();

    expect(nextTheme).toBe('dark');
    expect(setStorageItemMock).toHaveBeenCalledWith('theme', 'dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(document.body.dataset.theme).toBe('dark');
    expect(document.querySelector('.theme-toggle').classList.contains('theme-dark')).toBe(true);
  });

  it('renders subgraph names in the node selector list', async () => {
    const registryResponse = {
      success: true,
      data: {
        node_count: 2,
        nodes: {
          'root:1': {
            id: 1,
            graph_id: 'root',
            graph_name: null,
            title: 'Root Loader',
            type: 1,
            bgcolor: '#123456',
          },
          'subgraph-uuid:2': {
            id: 2,
            graph_id: 'subgraph-uuid',
            graph_name: 'Character Subgraph',
            title: 'Nested Loader',
            type: 1,
            bgcolor: '#654321',
          },
        },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      json: async () => registryResponse,
    });

    document.body.innerHTML = '<div id="nodeSelector"></div>';

    const { sendLoraToWorkflow } = await import(UI_HELPERS_MODULE);

    const result = await sendLoraToWorkflow('<lora:test:1>');

    expect(result).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/get-registry');

    const nodeLabels = Array.from(
      document.querySelectorAll('#nodeSelector .node-item[data-node-id] span')
    ).map((span) => span.textContent.trim());

    expect(nodeLabels).toEqual([
      '#1 Root Loader',
      '#2 (Character Subgraph) Nested Loader',
    ]);
  });
});
