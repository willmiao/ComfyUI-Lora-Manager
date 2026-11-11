import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';

const { APP_MODULE, mocks } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  mocks: {
    executeCommand: vi.fn(),
    legacyShow: vi.fn(),
    registerExtension: vi.fn(),
    selectCategory: vi.fn(),
    setSetting: vi.fn(),
  },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: mocks.registerExtension,
    extensionManager: {
      setting: {
        get: vi.fn(),
        set: mocks.setSetting,
      },
      command: {
        commands: [],
        execute: mocks.executeCommand,
      },
    },
    ui: {
      settings: {
        settingsById: {},
        show: mocks.legacyShow,
      },
    },
  },
}));

import {
  COMFYUI_SETTINGS_AVAILABLE_MESSAGE,
  DISCOVER_COMFYUI_SETTINGS_MESSAGE,
  OPEN_COMFYUI_SETTINGS_MESSAGE,
  OPEN_COMFYUI_SETTINGS_QUERY,
} from '../../../web/comfyui/settings.js';

class BroadcastChannelMock {
  static instances = [];

  constructor(name) {
    this.name = name;
    this.listeners = [];
    this.postMessage = vi.fn();
    BroadcastChannelMock.instances.push(this);
  }

  addEventListener(type, listener) {
    if (type === 'message') this.listeners.push(listener);
  }

  emit(data) {
    this.listeners.forEach((listener) => listener({ data }));
  }
}

describe('ComfyUI settings navigation', () => {
  beforeAll(async () => {
    Object.defineProperty(window, 'BroadcastChannel', {
      configurable: true,
      writable: true,
      value: BroadcastChannelMock,
    });
    vi.spyOn(window, 'focus').mockImplementation(() => {});
    mocks.executeCommand.mockImplementation(async () => {
      let dialog = document.querySelector('[data-testid="settings-dialog"]');
      if (!dialog) {
        dialog = document.createElement('div');
        dialog.dataset.testid = 'settings-dialog';
        const navItem = document.createElement('button');
        navItem.dataset.navId = 'root/LoRA Manager';
        navItem.addEventListener('click', mocks.selectCategory);
        dialog.appendChild(navItem);
        document.body.appendChild(dialog);
      }
    });

    window.history.replaceState({}, '', `/?${OPEN_COMFYUI_SETTINGS_QUERY}=1&keep=yes`);
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, workflows: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ settings: {} }),
      });

    const extension = mocks.registerExtension.mock.calls
      .map(([registered]) => registered)
      .find((registered) => registered?.name === 'LoraManager.Settings');
    await extension.setup();
  });

  afterAll(() => {
    window.history.replaceState({}, '', '/');
    document.body.innerHTML = '';
    delete window.BroadcastChannel;
    delete global.fetch;
  });

  it('opens the LM category and reuses a targeted existing tab', async () => {
    await vi.waitFor(() => {
      expect(mocks.executeCommand).toHaveBeenCalledWith('Comfy.ShowSettingsDialog');
      expect(mocks.selectCategory).toHaveBeenCalled();
    });
    expect(window.location.search).toBe('?keep=yes');

    mocks.executeCommand.mockClear();
    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      data: { type: OPEN_COMFYUI_SETTINGS_MESSAGE },
    }));
    await vi.waitFor(() => {
      expect(mocks.executeCommand).toHaveBeenCalledWith('Comfy.ShowSettingsDialog');
    });

    mocks.executeCommand.mockClear();
    window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://example.com',
      data: { type: OPEN_COMFYUI_SETTINGS_MESSAGE },
    }));
    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      data: { type: 'unrelated-message' },
    }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mocks.executeCommand).not.toHaveBeenCalled();

    const channel = BroadcastChannelMock.instances[0];
    channel.emit({ type: DISCOVER_COMFYUI_SETTINGS_MESSAGE, requestId: 'request-1' });
    const availability = channel.postMessage.mock.calls[0][0];
    expect(availability).toMatchObject({
      type: COMFYUI_SETTINGS_AVAILABLE_MESSAGE,
      requestId: 'request-1',
    });

    channel.emit({ type: OPEN_COMFYUI_SETTINGS_MESSAGE, targetTabId: 'another-tab' });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mocks.executeCommand).not.toHaveBeenCalled();

    channel.emit({ type: OPEN_COMFYUI_SETTINGS_MESSAGE, targetTabId: availability.tabId });
    await vi.waitFor(() => {
      expect(mocks.executeCommand).toHaveBeenCalledWith('Comfy.ShowSettingsDialog');
    });
    expect(window.focus).toHaveBeenCalled();
  });
});
