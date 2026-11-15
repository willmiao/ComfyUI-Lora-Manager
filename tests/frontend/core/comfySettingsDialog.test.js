import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { APP_MODULE, appMock } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  appMock: { extensionManager: undefined },
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));

function createSettingsDialog(navId = 'LoRA Manager') {
  const dialog = document.createElement('div');
  dialog.setAttribute('data-testid', 'settings-dialog');

  const navItem = document.createElement('button');
  navItem.setAttribute('data-nav-id', navId);
  const click = vi.fn();
  navItem.addEventListener('click', click);

  dialog.appendChild(navItem);
  document.body.appendChild(dialog);
  return { dialog, click };
}

async function importOpener() {
  return import('../../../web/comfyui/comfy_settings_dialog.js');
}

describe('openComfyUISettingsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    appMock.extensionManager = undefined;
    appMock.ui = undefined;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('runs the settings command and selects the LoRA Manager category', async () => {
    const { click } = createSettingsDialog();
    const execute = vi.fn();
    appMock.extensionManager = { command: { commands: [], execute } };

    const { openComfyUISettingsDialog } = await importOpener();
    await openComfyUISettingsDialog();

    expect(execute).toHaveBeenCalledWith('Comfy.ShowSettingsDialog');
    expect(click).toHaveBeenCalledOnce();
  });

  it('matches a category nested under a nav group', async () => {
    // Custom categories may be rendered below a group, in which case the nav id
    // is a path rather than the bare category name.
    const { click } = createSettingsDialog('Other/LoRA Manager');
    appMock.extensionManager = { command: { commands: [], execute: vi.fn() } };

    const { openComfyUISettingsDialog } = await importOpener();
    await openComfyUISettingsDialog();

    expect(click).toHaveBeenCalledOnce();
  });

  it('falls back to app.ui.settings.show on older frontends', async () => {
    const show = vi.fn();
    appMock.ui = { settings: { show } };
    vi.useFakeTimers();

    const { openComfyUISettingsDialog } = await importOpener();
    const pending = openComfyUISettingsDialog();
    // Waits out the command-store probe, then the category poll.
    await vi.advanceTimersByTimeAsync(7200);
    await pending;

    expect(show).toHaveBeenCalledOnce();
  });

  it('still opens the dialog when the category entry is missing', async () => {
    const execute = vi.fn();
    appMock.extensionManager = { command: { commands: [], execute } };
    vi.useFakeTimers();

    const { openComfyUISettingsDialog } = await importOpener();
    const pending = openComfyUISettingsDialog();
    await vi.advanceTimersByTimeAsync(2100);
    await pending;

    expect(execute).toHaveBeenCalledWith('Comfy.ShowSettingsDialog');
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('LoRA Manager category was not found')
    );
  });
});
