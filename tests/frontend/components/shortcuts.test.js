import { beforeEach, describe, expect, it, vi } from 'vitest';

const { APP_MODULE, appMock } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  appMock: { extensionManager: undefined },
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));

const loadShortcuts = () => import('../../../web/comfyui/shortcuts.js');

const quickPickerCommand = (keybinding) => ({
  id: 'LoraManager.ToggleQuickPanel',
  keybinding,
});

describe('command shortcut labels', () => {
  beforeEach(() => {
    appMock.extensionManager = undefined;
  });

  it('formats the effective keybinding with ComfyUI key sequences', async () => {
    appMock.extensionManager = {
      command: {
        commands: [quickPickerCommand({
          combo: { key: 'k', ctrl: true, getKeySequences: () => ['Ctrl', 'K'] },
        })],
      },
    };
    const { COMMAND_IDS, getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker)).toBe('Ctrl+K');
  });

  it('formats a plain key combo when the frontend exposes no key sequences', async () => {
    appMock.extensionManager = {
      command: {
        commands: [quickPickerCommand({ combo: { key: 'l', alt: true } })],
      },
    };
    const { COMMAND_IDS, getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker)).toBe('Alt+L');
  });

  it('returns an empty label when the shortcut is unbound', async () => {
    appMock.extensionManager = {
      command: { commands: [quickPickerCommand(null)] },
    };
    const { COMMAND_IDS, getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker)).toBe('');
  });

  it('falls back to the registered default when the command is not available', async () => {
    const { COMMAND_IDS, getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker)).toBe('Alt+L');
  });

  it('falls back to the registered default on frontends without a keybinding getter', async () => {
    appMock.extensionManager = {
      command: { commands: [{ id: 'LoraManager.ToggleQuickPanel' }] },
    };
    const { COMMAND_IDS, getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel(COMMAND_IDS.quickLoraPicker)).toBe('Alt+L');
  });

  it('returns an empty label for a command without a default shortcut', async () => {
    const { getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel('LoraManager.Unknown')).toBe('');
  });
});
