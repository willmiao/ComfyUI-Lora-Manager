import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  I18N_MODULE,
  STATE_MODULE,
  STORAGE_MODULE,
  CONSTANTS_MODULE,
  EVENT_MANAGER_MODULE,
  BANNER_SERVICE_MODULE,
  MODAL_MANAGER_MODULE,
  UI_HELPERS_MODULE,
} = vi.hoisted(() => ({
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  STORAGE_MODULE: new URL('../../../static/js/utils/storageHelpers.js', import.meta.url).pathname,
  CONSTANTS_MODULE: new URL('../../../static/js/utils/constants.js', import.meta.url).pathname,
  EVENT_MANAGER_MODULE: new URL('../../../static/js/utils/EventManager.js', import.meta.url).pathname,
  BANNER_SERVICE_MODULE: new URL('../../../static/js/managers/BannerService.js', import.meta.url).pathname,
  MODAL_MANAGER_MODULE: new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
}));

const translateMock = vi.fn((key, _params, fallback) => fallback || key);
const getStorageItemMock = vi.fn();
const setStorageItemMock = vi.fn();
const registerBannerMock = vi.fn();
const showModalMock = vi.fn();

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

vi.mock(BANNER_SERVICE_MODULE, () => ({
  bannerService: {
    registerBanner: registerBannerMock,
  },
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: showModalMock,
  },
}));

describe('UI helper DOM utilities', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.body.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-theme');
    getStorageItemMock.mockReset();
    setStorageItemMock.mockReset();
    registerBannerMock.mockReset();
    showModalMock.mockReset();
    translateMock.mockReset();
    globalThis.requestAnimationFrame = (cb) => cb();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete global.fetch;
    delete navigator.clipboard;
    delete window.open;
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

  it('renders an action button and countdown span for action toasts', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Deleted Demo Model');

    const { showActionToast } = await import(UI_HELPERS_MODULE);

    const onAction = vi.fn();
    showActionToast('toast.undo.deleted', { name: 'Demo Model' }, 'success', {
      actionText: 'Undo',
      onAction,
    });

    const toast = document.querySelector('.toast-container .toast');
    expect(toast).not.toBeNull();
    expect(toast.classList.contains('toast-success')).toBe(true);
    expect(translateMock).toHaveBeenCalledWith('toast.undo.deleted', { name: 'Demo Model' });

    const button = toast.querySelector('.toast-action-btn');
    expect(button).not.toBeNull();
    expect(button.textContent).toBe('Undo');

    const countdown = toast.querySelector('.toast-countdown');
    expect(countdown).not.toBeNull();
    expect(countdown.textContent).toBe('(30s)');

    // Ticking one second updates the countdown text
    vi.advanceTimersByTime(1000);
    expect(countdown.textContent).toBe('(29s)');

    // Drain remaining timers so no state leaks into other tests
    vi.advanceTimersByTime(30000);
  });

  it('invokes onAction once and dismisses immediately when the button is clicked', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Deleted Demo Model');

    const { showActionToast } = await import(UI_HELPERS_MODULE);

    const onAction = vi.fn();
    showActionToast('toast.undo.deleted', {}, 'success', {
      actionText: 'Undo',
      onAction,
    });

    const toast = document.querySelector('.toast-container .toast');
    toast.querySelector('.toast-action-btn').click();

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(toast.classList.contains('show')).toBe(false);

    // Dismissal removes the element after the transition ends
    toast.dispatchEvent(new Event('transitionend', { bubbles: true }));
    expect(document.querySelector('.toast-container .toast')).toBeNull();
    expect(document.querySelector('.toast-container')).toBeNull();
  });

  it('calls onAction exactly once when the button is double-clicked', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Deleted Demo Model');

    const { showActionToast } = await import(UI_HELPERS_MODULE);

    const onAction = vi.fn();
    showActionToast('toast.undo.deleted', {}, 'success', {
      actionText: 'Undo',
      onAction,
    });

    const button = document.querySelector('.toast-action-btn');
    button.click();
    button.click();

    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('dismisses the toast when the countdown reaches zero', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Deleted Demo Model');
    // Async RAF mirrors production ordering: the countdown interval is
    // registered before the dismiss timeout, so the final tick displays (0s)
    globalThis.requestAnimationFrame = (cb) => setTimeout(cb, 0);

    const { showActionToast } = await import(UI_HELPERS_MODULE);

    showActionToast('toast.undo.deleted', {}, 'success', {
      actionText: 'Undo',
      onAction: vi.fn(),
      durationMs: 3000,
    });

    vi.advanceTimersByTime(0); // Flush the RAF callback
    const toast = document.querySelector('.toast-container .toast');
    const countdown = toast.querySelector('.toast-countdown');
    expect(countdown.textContent).toBe('(3s)');

    vi.advanceTimersByTime(2000);
    expect(countdown.textContent).toBe('(1s)');
    expect(toast.classList.contains('show')).toBe(true);

    vi.advanceTimersByTime(1000);
    expect(countdown.textContent).toBe('(0s)');
    expect(toast.classList.contains('show')).toBe(false);

    toast.dispatchEvent(new Event('transitionend', { bubbles: true }));
    expect(document.querySelector('.toast-container .toast')).toBeNull();
  });

  it('clears the countdown interval when dismissed via the action button', async () => {
    vi.useFakeTimers();
    translateMock.mockReturnValue('Deleted Demo Model');

    const { showActionToast } = await import(UI_HELPERS_MODULE);

    const onAction = vi.fn();
    showActionToast('toast.undo.deleted', {}, 'success', {
      actionText: 'Undo',
      onAction,
      durationMs: 30000,
    });

    const toast = document.querySelector('.toast-container .toast');
    const countdown = toast.querySelector('.toast-countdown');
    toast.querySelector('.toast-action-btn').click();

    // Advancing past the full duration must not tick the countdown further,
    // throw, or re-dismiss the already-dismissed toast
    vi.advanceTimersByTime(60000);
    expect(countdown.textContent).toBe('(30s)');
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(toast.classList.contains('show')).toBe(false);

    toast.dispatchEvent(new Event('transitionend', { bubbles: true }));
    expect(document.querySelector('.toast-container')).toBeNull();
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

  it('excludes prompt targets whose text widget is connected to an input', async () => {
    const registryResponse = {
      success: true,
      data: {
        node_count: 4,
        nodes: {
          'root:1': {
            id: 1,
            graph_id: 'root',
            graph_name: null,
            title: 'Free Text',
            type: 'CLIPTextEncode',
            mode: 0,
            marker_role: null,
            capabilities: {
              has_text_widget: true,
              text_widget_connected: false,
              widget_names: ['text', 'clip'],
            },
          },
          'root:2': {
            id: 2,
            graph_id: 'root',
            graph_name: null,
            title: 'Wired Text',
            type: 'CLIPTextEncode',
            mode: 0,
            marker_role: null,
            capabilities: {
              has_text_widget: true,
              text_widget_connected: true,
              widget_names: ['text', 'clip'],
            },
          },
          'root:3': {
            id: 3,
            graph_id: 'root',
            graph_name: null,
            title: 'Marked But Wired',
            type: 'KSampler',
            mode: 0,
            marker_role: 'send_prompt_target',
            capabilities: {
              has_text_widget: false,
              text_widget_connected: true,
              widget_names: ['seed'],
            },
          },
          'root:4': {
            id: 4,
            graph_id: 'root',
            graph_name: null,
            title: 'Free Text 2',
            type: 'CLIPTextEncode',
            mode: 0,
            marker_role: null,
            capabilities: {
              has_text_widget: true,
              text_widget_connected: false,
              widget_names: ['text', 'clip'],
            },
          },
        },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      json: async () => registryResponse,
    });

    document.body.innerHTML = '<div id="nodeSelector"></div>';

    const { sendPromptToWorkflow } = await import(UI_HELPERS_MODULE);

    const result = await sendPromptToWorkflow('a cat');

    expect(result).toBe(true);

    const nodeLabels = Array.from(
      document.querySelectorAll('#nodeSelector .node-item[data-node-id] span')
    ).map((span) => span.textContent.trim());

    expect(nodeLabels).toEqual(['#1 Free Text', '#4 Free Text 2']);
  });

  it('returns false when the only prompt target has its text widget connected', async () => {
    const registryResponse = {
      success: true,
      data: {
        node_count: 1,
        nodes: {
          'root:1': {
            id: 1,
            graph_id: 'root',
            graph_name: null,
            title: 'Wired Text',
            type: 'CLIPTextEncode',
            mode: 0,
            marker_role: null,
            capabilities: {
              has_text_widget: true,
              text_widget_connected: true,
              widget_names: ['text', 'clip'],
            },
          },
        },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      json: async () => registryResponse,
    });

    document.body.innerHTML = '<div id="nodeSelector"></div>';
    translateMock.mockReturnValue(
      'No compatible prompt targets in the workflow.\nRight-click a node in ComfyUI → Mark as → Send Prompt Target'
    );

    const { sendPromptToWorkflow } = await import(UI_HELPERS_MODULE);

    const result = await sendPromptToWorkflow('a cat');

    expect(result).toBe(false);
    expect(document.querySelectorAll('#nodeSelector .node-item').length).toBe(0);

    const toast = document.querySelector('.toast-container .toast');
    expect(toast).not.toBeNull();
    expect(toast.textContent).toContain('Mark as');
    expect(toast.textContent).toContain('Send Prompt Target');
  });

  it('shows the mark-as hint when no embedding target is available', async () => {
    const registryResponse = {
      success: true,
      data: {
        node_count: 1,
        nodes: {
          'root:1': {
            id: 1,
            graph_id: 'root',
            graph_name: null,
            title: 'Wired Text',
            type: 'CLIPTextEncode',
            mode: 0,
            marker_role: null,
            capabilities: {
              has_text_widget: true,
              text_widget_connected: true,
              widget_names: ['text', 'clip'],
            },
          },
        },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      json: async () => registryResponse,
    });

    document.body.innerHTML = '<div id="nodeSelector"></div>';
    translateMock.mockReturnValue(
      'No compatible prompt targets in the workflow.\nRight-click a node in ComfyUI → Mark as → Send Prompt Target'
    );

    const { sendEmbeddingToWorkflow } = await import(UI_HELPERS_MODULE);

    const result = await sendEmbeddingToWorkflow('embeddingcode');

    expect(result).toBe(false);

    const toast = document.querySelector('.toast-container .toast');
    expect(toast).not.toBeNull();
    expect(toast.textContent).toContain('Send Prompt Target');
  });

  it('keeps unconnected marker targets in the prompt candidate list', async () => {
    const registryResponse = {
      success: true,
      data: {
        node_count: 2,
        nodes: {
          'root:1': {
            id: 1,
            graph_id: 'root',
            graph_name: null,
            title: 'Marked Target',
            type: 'KSampler',
            mode: 0,
            marker_role: 'send_prompt_target',
            capabilities: {
              has_text_widget: false,
              text_widget_connected: false,
              widget_names: ['seed'],
            },
          },
          'root:2': {
            id: 2,
            graph_id: 'root',
            graph_name: null,
            title: 'Marked Target 2',
            type: 'KSampler',
            mode: 0,
            marker_role: 'send_prompt_target',
            capabilities: {
              has_text_widget: false,
              text_widget_connected: false,
              widget_names: ['seed'],
            },
          },
        },
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      json: async () => registryResponse,
    });

    document.body.innerHTML = '<div id="nodeSelector"></div>';

    const { sendPromptToWorkflow } = await import(UI_HELPERS_MODULE);

    const result = await sendPromptToWorkflow('a cat');

    expect(result).toBe(true);

    const nodeLabels = Array.from(
      document.querySelectorAll('#nodeSelector .node-item[data-node-id] span')
    ).map((span) => span.textContent.trim());

    expect(nodeLabels).toEqual(['#1 Marked Target', '#2 Marked Target 2']);
  });

  it('opens Civitai links using the preferred host and registers the first-use banner once', async () => {
    const openSpy = vi.fn();
    globalThis.window.open = openSpy;

    getStorageItemMock.mockImplementation((key, defaultValue) => {
      if (key === 'civitai_host_info_banner_seen') {
        return false;
      }
      return defaultValue;
    });

    const { openCivitaiByMetadata } = await import(UI_HELPERS_MODULE);

    openCivitaiByMetadata(123, 456, 'Demo Model');

    expect(setStorageItemMock).toHaveBeenCalledWith('civitai_host_info_banner_seen', true);
    expect(registerBannerMock).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledWith(
      'https://civitai.com/models/123?modelVersionId=456',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('uses the configured red host for fallback searches', async () => {
    const openSpy = vi.fn();
    globalThis.window.open = openSpy;

    getStorageItemMock.mockImplementation((key, defaultValue) => {
      if (key === 'civitai_host_info_banner_seen') {
        return true;
      }
      return defaultValue;
    });

    const stateModule = await import(STATE_MODULE);
    stateModule.state.global = {
      settings: {
        civitai_host: 'civitai.red',
      },
    };

    const { openCivitaiByMetadata } = await import(UI_HELPERS_MODULE);

    openCivitaiByMetadata(null, null, 'Demo Model');

    expect(registerBannerMock).not.toHaveBeenCalled();
    expect(openSpy).toHaveBeenCalledWith(
      'https://civitai.red/models?query=Demo%20Model',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('copies mapped local example-image paths when the backend requests clipboard mode', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: async () => ({
        success: true,
        mode: 'clipboard',
        path: '/Volumes/ComfyUI/examples/demo',
      }),
    });
    navigator.clipboard = {
      writeText: vi.fn().mockResolvedValue(),
    };

    const { openExampleImagesFolder } = await import(UI_HELPERS_MODULE);

    const result = await openExampleImagesFolder('abc123');

    expect(result).toBe(true);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('/Volumes/ComfyUI/examples/demo');
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/open-example-images-folder', expect.objectContaining({
      method: 'POST',
    }));
  });

  it('opens custom URIs for example-image folders when requested by the backend', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      json: async () => ({
        success: true,
        mode: 'uri',
        uri: 'shortcuts://run-shortcut?name=OpenFinder',
      }),
    });
    window.open = vi.fn(() => ({}));

    const { openExampleImagesFolder } = await import(UI_HELPERS_MODULE);

    const result = await openExampleImagesFolder('abc123');

    expect(result).toBe(true);
    expect(window.open).toHaveBeenCalledWith(
      'shortcuts://run-shortcut?name=OpenFinder',
      '_blank',
      'noopener,noreferrer'
    );
  });
});
