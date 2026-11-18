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

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, _params, fallback) => fallback || key),
}));

vi.mock(STATE_MODULE, () => ({
  state: {
    global: {
      settings: {
        standalone_mode: false,
        send_to_workflow_exclusions: {
          node_classes: [],
          title_patterns: [],
        },
      },
    },
  },
  getCurrentPageState: vi.fn(),
}));

vi.mock(STORAGE_MODULE, () => ({
  getStorageItem: vi.fn(),
  setStorageItem: vi.fn(),
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
    registerBanner: vi.fn(),
  },
}));

vi.mock(MODAL_MANAGER_MODULE, () => ({
  modalManager: {
    showModal: vi.fn(),
  },
}));

function makeImageNode(id, overrides = {}) {
  return {
    id,
    graph_id: 'root',
    title: `LoadImage ${id}`,
    type: 0,
    type_name: 'LoadImage',
    comfy_class: 'LoadImage',
    mode: 0,
    marker_role: null,
    exclude_send: false,
    capabilities: {
      has_image_widget: true,
      image_input_name: 'image',
      image_folder: 'input',
      image_widget_connected: false,
    },
    ...overrides,
  };
}

async function loadHelper() {
  return import(UI_HELPERS_MODULE);
}

describe('sendImageToWorkflow', () => {
  let fetchMock;

  beforeEach(() => {
    document.body.innerHTML = '';
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends directly to the marked image target when one exists', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: {
            nodes: {
              'root:1': makeImageNode(1),
              'root:2': makeImageNode(2, { marker_role: 'send_image_target' }),
            },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

    const { sendImageToWorkflow } = await loadHelper();
    const result = await sendImageToWorkflow({
      url: '/example_images_static/model/image_0.png',
    });

    expect(result).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/lm/send-image-to-workflow');

    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.node_ids).toEqual([{ node_id: 2, graph_id: 'root' }]);
    expect(body.source).toEqual({
      url: '/example_images_static/model/image_0.png',
    });
  });

  it('falls back to the only auto-detected image node', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: { nodes: { 'root:4': makeImageNode(4) } },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

    const { sendImageToWorkflow } = await loadHelper();
    const result = await sendImageToWorkflow({ path: '/tmp/recipe.png' });

    expect(result).toBe(true);
    const body = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(body.node_ids).toEqual([{ node_id: 4, graph_id: 'root' }]);
    expect(body.source).toEqual({ path: '/tmp/recipe.png' });
  });

  it('does not POST when no image target is available', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          nodes: {
            'root:1': makeImageNode(1, {
              capabilities: { has_image_widget: false },
            }),
            'root:2': makeImageNode(2, {
              capabilities: {
                has_image_widget: true,
                image_widget_connected: true,
              },
            }),
            'root:3': makeImageNode(3, {
              capabilities: {
                has_image_widget: true,
                image_folder: 'output',
                image_widget_connected: false,
              },
            }),
          },
        },
      }),
    });

    const { sendImageToWorkflow } = await loadHelper();
    const result = await sendImageToWorkflow({
      url: '/example_images_static/model/image_0.png',
    });

    expect(result).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not fall back when the marked target is unusable', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          nodes: {
            'root:1': makeImageNode(1),
            'root:2': makeImageNode(2, {
              marker_role: 'send_image_target',
              capabilities: {
                has_image_widget: true,
                image_input_name: 'image',
                image_folder: 'input',
                image_widget_connected: true,
              },
            }),
          },
        },
      }),
    });

    const { sendImageToWorkflow } = await loadHelper();
    const result = await sendImageToWorkflow({
      url: '/example_images_static/model/image_0.png',
    });

    expect(result).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('shows a persistent loading toast while a remote image downloads', async () => {
    let resolveSend;
    const pendingSend = new Promise((resolve) => {
      resolveSend = resolve;
    });

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: { nodes: { 'root:1': makeImageNode(1) } },
        }),
      })
      .mockReturnValueOnce(pendingSend);

    const { sendImageToWorkflow } = await loadHelper();
    const sendPromise = sendImageToWorkflow({
      url: 'https://image.civitai.com/x/image.png',
    });

    for (let attempt = 0; attempt < 20; attempt += 1) {
      if (document.querySelector('.toast.toast-loading')) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }

    const loadingToast = document.querySelector('.toast.toast-loading');
    expect(loadingToast).not.toBeNull();
    expect(loadingToast.textContent).toContain('Downloading image');

    resolveSend({
      ok: true,
      json: async () => ({ success: true }),
    });
    await expect(sendPromise).resolves.toBe(true);
  });

  it('ignores duplicate sends while one is in flight', async () => {
    let resolveSend;
    const pendingSend = new Promise((resolve) => {
      resolveSend = resolve;
    });

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: { nodes: { 'root:1': makeImageNode(1) } },
        }),
      })
      .mockReturnValueOnce(pendingSend)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          data: { nodes: { 'root:1': makeImageNode(1) } },
        }),
      });

    const { sendImageToWorkflow } = await loadHelper();
    const first = sendImageToWorkflow({
      url: 'https://image.civitai.com/x/image.png',
    });

    for (let attempt = 0; attempt < 20; attempt += 1) {
      if (document.querySelector('.toast.toast-loading')) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
    }

    const second = await sendImageToWorkflow({
      url: 'https://image.civitai.com/x/image.png',
    });
    expect(second).toBe(false);

    const sendCalls = fetchMock.mock.calls.filter(
      ([url]) => url === '/api/lm/send-image-to-workflow',
    );
    expect(sendCalls).toHaveLength(1);

    resolveSend({
      ok: true,
      json: async () => ({ success: true }),
    });
    await expect(first).resolves.toBe(true);
  });

  it('rejects an empty source before contacting the registry', async () => {
    const { sendImageToWorkflow } = await loadHelper();
    const result = await sendImageToWorkflow({});

    expect(result).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
