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

  it('registers the recipe picker with its own stable command id and default', async () => {
    const { COMMAND_IDS, DEFAULT_KEYBINDINGS, getCommandShortcutLabel } = await loadShortcuts();

    expect(COMMAND_IDS.quickRecipePicker).toBe('LoraManager.ToggleRecipeQuickPanel');
    expect(DEFAULT_KEYBINDINGS[COMMAND_IDS.quickRecipePicker]).toEqual({ key: 'r', alt: true });
    expect(getCommandShortcutLabel(COMMAND_IDS.quickRecipePicker)).toBe('Alt+R');
  });

  it('leaves the wildcard picker unbound by default', async () => {
    const { COMMAND_IDS, DEFAULT_KEYBINDINGS, getCommandShortcutLabel } = await loadShortcuts();

    expect(COMMAND_IDS.quickWildcardPicker).toBe('LoraManager.ToggleWildcardQuickPanel');
    expect(DEFAULT_KEYBINDINGS[COMMAND_IDS.quickWildcardPicker]).toBeUndefined();
    expect(getCommandShortcutLabel(COMMAND_IDS.quickWildcardPicker)).toBe('');
  });

  it('returns an empty label for a command without a default shortcut', async () => {
    const { getCommandShortcutLabel } = await loadShortcuts();

    expect(getCommandShortcutLabel('LoraManager.Unknown')).toBe('');
  });
});
