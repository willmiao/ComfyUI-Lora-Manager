import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  STYLES_MODULE,
  CANVAS_API_MODULE,
  QUICK_PANEL_MODULE,
  WILDCARD_PANEL_MODULE,
  SETTINGS_DIALOG_MODULE,
  appMock,
  toggleQuickPanelMock,
  toggleRecipePanelMock,
  toggleWildcardPanelMock,
  openManagerMock,
  openComfyUISettingsMock,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  STYLES_MODULE: new URL('../../../web/comfyui/lm_styles_loader.js', import.meta.url).pathname,
  CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
  WILDCARD_PANEL_MODULE: new URL('../../../web/comfyui/wildcard_quick_panel.js', import.meta.url).pathname,
  SETTINGS_DIALOG_MODULE: new URL('../../../web/comfyui/comfy_settings_dialog.js', import.meta.url).pathname,
  appMock: { extensionManager: undefined },
  toggleQuickPanelMock: vi.fn(),
  toggleRecipePanelMock: vi.fn(),
  toggleWildcardPanelMock: vi.fn(),
  openManagerMock: vi.fn(),
  openComfyUISettingsMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));
vi.mock(CANVAS_API_MODULE, () => ({ openLoraManagerHome: openManagerMock }));
vi.mock(QUICK_PANEL_MODULE, () => ({
  toggleLoraQuickPanel: toggleQuickPanelMock,
  toggleRecipeQuickPanel: toggleRecipePanelMock,
}));
vi.mock(WILDCARD_PANEL_MODULE, () => ({
  toggleWildcardQuickPanel: toggleWildcardPanelMock,
}));
vi.mock(SETTINGS_DIALOG_MODULE, () => ({
  openComfyUISettingsDialog: openComfyUISettingsMock,
}));

function createAnchor() {
  const anchor = document.createElement('button');
  anchor.setAttribute('aria-expanded', 'false');
  anchor.getBoundingClientRect = () => ({
    left: 700,
    right: 730,
    top: 10,
    bottom: 38,
    width: 30,
    height: 28,
  });
  document.body.appendChild(anchor);
  return anchor;
}

describe('LoRA Manager Quick Actions menu', () => {
  beforeEach(() => {
    // The menu module keeps a module-level `activeMenu`; close any menu left
    // open by the previous test before resetting the DOM.
    document.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    }));
    document.body.innerHTML = '';
    vi.clearAllMocks();
    appMock.extensionManager = undefined;
  });

  it('shows the picker name and ComfyUI-style shortcut badge', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();

    toggleQuickActionsMenu(anchor);

    const menu = document.querySelector('.lm-quick-actions-menu');
    expect(menu).not.toBeNull();
    expect(menu.textContent).toContain('Quick LoRA Picker');
    expect(menu.textContent).toContain('Quick Recipe Picker');
    expect([...menu.querySelectorAll('kbd')].map((badge) => badge.textContent)).toEqual([
      'Alt+L',
      'Alt+R',
    ]);
    expect(anchor.getAttribute('aria-expanded')).toBe('true');

    menu.querySelector('[role="menuitem"]').click();
    expect(toggleQuickPanelMock).toHaveBeenCalledOnce();
    expect(document.querySelector('.lm-quick-actions-menu')).toBeNull();
    expect(anchor.getAttribute('aria-expanded')).toBe('false');
  });

  it('opens the recipe picker from its own menu item', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();
    toggleQuickActionsMenu(anchor);

    const items = document.querySelectorAll('[role="menuitem"]');
    items[1].click();

    expect(toggleRecipePanelMock).toHaveBeenCalledOnce();
    expect(toggleQuickPanelMock).not.toHaveBeenCalled();
  });

  it('opens the global wildcards panel from its own menu item', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    toggleQuickActionsMenu(createAnchor());

    document.querySelectorAll('[role="menuitem"]')[2].click();

    expect(toggleWildcardPanelMock).toHaveBeenCalledOnce();
    expect(toggleQuickPanelMock).not.toHaveBeenCalled();
    expect(toggleRecipePanelMock).not.toHaveBeenCalled();
  });

  it('shows the user-remapped shortcut instead of the default', async () => {
    appMock.extensionManager = {
      command: {
        commands: [{
          id: 'LoraManager.ToggleQuickPanel',
          keybinding: {
            combo: { key: 'k', ctrl: true, getKeySequences: () => ['Ctrl', 'K'] },
          },
        }],
      },
    };
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');

    toggleQuickActionsMenu(createAnchor());

    expect(document.querySelector('.lm-quick-actions-menu kbd').textContent).toBe('Ctrl+K');
  });

  it('omits the shortcut badge when the user unbinds the shortcut', async () => {
    appMock.extensionManager = {
      command: {
        commands: [{ id: 'LoraManager.ToggleQuickPanel', keybinding: null }],
      },
    };
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');

    toggleQuickActionsMenu(createAnchor());

    const items = document.querySelectorAll('[role="menuitem"]');
    expect(items[0].querySelector('kbd')).toBeNull();
    expect(items[1].querySelector('kbd').textContent).toBe('Alt+R');
  });

  it('keeps the full manager available from the same menu', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();
    toggleQuickActionsMenu(anchor);

    const items = [...document.querySelectorAll('[role="menuitem"]')];
    items.find((item) => item.textContent.includes('Open LoRA Manager')).click();

    expect(openManagerMock).toHaveBeenCalledWith();
    expect(toggleQuickPanelMock).not.toHaveBeenCalled();
    expect(openComfyUISettingsMock).not.toHaveBeenCalled();
  });

  it('opens ComfyUI settings from the last menu item, after its own divider', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();
    toggleQuickActionsMenu(anchor);

    const menu = document.querySelector('.lm-quick-actions-menu');
    const items = [...menu.querySelectorAll('[role="menuitem"]')];
    const settingsItem = items.find((item) => item.textContent === 'Settings');
    expect(settingsItem).toBeDefined();

    // Two dividers: quick tools | manager | settings.
    expect(menu.querySelectorAll('.lm-quick-actions-menu__divider')).toHaveLength(2);
    expect(items.indexOf(settingsItem)).toBe(items.length - 1);

    settingsItem.click();
    expect(openComfyUISettingsMock).toHaveBeenCalledOnce();
    expect(openManagerMock).not.toHaveBeenCalled();
    expect(document.querySelector('.lm-quick-actions-menu')).toBeNull();
  });

  it('closes on Escape and restores focus to the chevron', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();
    toggleQuickActionsMenu(anchor);

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));

    expect(document.querySelector('.lm-quick-actions-menu')).toBeNull();
    expect(document.activeElement).toBe(anchor);
  });
});
