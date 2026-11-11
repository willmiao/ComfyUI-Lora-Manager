import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  COMFYUI_SETTINGS_AVAILABLE_MESSAGE,
  COMFYUI_SETTINGS_CHANNEL,
  DISCOVER_COMFYUI_SETTINGS_MESSAGE,
  OPEN_COMFYUI_SETTINGS_MESSAGE,
  OPEN_COMFYUI_SETTINGS_QUERY,
  openComfyUISettings,
} from '../../../static/js/utils/comfySettingsNavigation.js';

class BroadcastChannelMock {
  static instances = [];

  constructor(name) {
    this.name = name;
    this.onmessage = null;
    this.postMessage = vi.fn();
    this.close = vi.fn();
    BroadcastChannelMock.instances.push(this);
  }

  emit(data) {
    this.onmessage?.({ data });
  }
}

const setOpener = (opener) => {
  Object.defineProperty(window, 'opener', {
    configurable: true,
    writable: true,
    value: opener,
  });
};

const setBroadcastChannel = (value) => {
  Object.defineProperty(window, 'BroadcastChannel', {
    configurable: true,
    writable: true,
    value,
  });
};

describe('openComfyUISettings', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/loras');
    delete window.LM_BASE_PATH;
    setOpener(null);
    BroadcastChannelMock.instances = [];
    setBroadcastChannel(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    setOpener(null);
    setBroadcastChannel(undefined);
    delete window.LM_BASE_PATH;
  });

  it('messages and focuses the same-origin ComfyUI opener', async () => {
    const opener = {
      closed: false,
      location: { origin: window.location.origin },
      postMessage: vi.fn(),
      focus: vi.fn(),
    };
    const windowOpen = vi.spyOn(window, 'open').mockReturnValue({});
    setOpener(opener);

    expect(await openComfyUISettings()).toBe('opener');
    expect(opener.postMessage).toHaveBeenCalledWith(
      { type: OPEN_COMFYUI_SETTINGS_MESSAGE },
      window.location.origin,
    );
    expect(opener.focus).toHaveBeenCalledOnce();
    expect(windowOpen).not.toHaveBeenCalled();
  });

  it('reuses the most recently active existing ComfyUI tab', async () => {
    vi.useFakeTimers();
    setBroadcastChannel(BroadcastChannelMock);
    const windowOpen = vi.spyOn(window, 'open').mockReturnValue({});

    const resultPromise = openComfyUISettings();
    const channel = BroadcastChannelMock.instances[0];
    expect(channel.name).toBe(COMFYUI_SETTINGS_CHANNEL);
    const discovery = channel.postMessage.mock.calls[0][0];
    expect(discovery.type).toBe(DISCOVER_COMFYUI_SETTINGS_MESSAGE);

    channel.emit({
      type: COMFYUI_SETTINGS_AVAILABLE_MESSAGE,
      requestId: discovery.requestId,
      tabId: 'older-tab',
      lastActive: 10,
    });
    channel.emit({
      type: COMFYUI_SETTINGS_AVAILABLE_MESSAGE,
      requestId: discovery.requestId,
      tabId: 'recent-tab',
      lastActive: 20,
    });
    await vi.advanceTimersByTimeAsync(200);

    expect(await resultPromise).toBe('existing');
    expect(channel.postMessage).toHaveBeenLastCalledWith({
      type: OPEN_COMFYUI_SETTINGS_MESSAGE,
      targetTabId: 'recent-tab',
    });
    expect(channel.close).toHaveBeenCalledOnce();
    expect(windowOpen).not.toHaveBeenCalled();
  });

  it('opens ComfyUI with a startup request when no existing tab is available', async () => {
    window.LM_BASE_PATH = '/comfyui';
    const windowOpen = vi.spyOn(window, 'open').mockReturnValue({});

    expect(await openComfyUISettings()).toBe('new');
    expect(windowOpen).toHaveBeenCalledWith(
      `${window.location.origin}/comfyui/?${OPEN_COMFYUI_SETTINGS_QUERY}=1`,
      '_blank',
    );
  });

  it('opens a new page instead of messaging a cross-origin opener', async () => {
    const opener = {
      closed: false,
      location: { origin: 'https://example.com' },
      postMessage: vi.fn(),
      focus: vi.fn(),
    };
    setOpener(opener);
    const windowOpen = vi.spyOn(window, 'open').mockReturnValue({});

    expect(await openComfyUISettings()).toBe('new');
    expect(opener.postMessage).not.toHaveBeenCalled();
    expect(windowOpen).toHaveBeenCalledOnce();
  });

  it('reports a blocked new window', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);

    expect(await openComfyUISettings()).toBeNull();
  });
});
