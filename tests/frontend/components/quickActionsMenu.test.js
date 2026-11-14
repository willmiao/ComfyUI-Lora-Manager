import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  STYLES_MODULE,
  CANVAS_API_MODULE,
  QUICK_PANEL_MODULE,
  appMock,
  toggleQuickPanelMock,
  openManagerMock,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  STYLES_MODULE: new URL('../../../web/comfyui/lm_styles_loader.js', import.meta.url).pathname,
  CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
  appMock: { extensionManager: undefined },
  toggleQuickPanelMock: vi.fn(),
  openManagerMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));
vi.mock(CANVAS_API_MODULE, () => ({ openLoraManagerHome: openManagerMock }));
vi.mock(QUICK_PANEL_MODULE, () => ({ toggleLoraQuickPanel: toggleQuickPanelMock }));

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
    expect(menu.querySelector('kbd').textContent).toBe('Alt+L');
    expect(anchor.getAttribute('aria-expanded')).toBe('true');

    menu.querySelector('[role="menuitem"]').click();
    expect(toggleQuickPanelMock).toHaveBeenCalledOnce();
    expect(document.querySelector('.lm-quick-actions-menu')).toBeNull();
    expect(anchor.getAttribute('aria-expanded')).toBe('false');
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

    expect(document.querySelector('.lm-quick-actions-menu kbd')).toBeNull();
  });

  it('keeps the full manager available from the same menu', async () => {
    const { toggleQuickActionsMenu } = await import('../../../web/comfyui/quick_actions_menu.js');
    const anchor = createAnchor();
    toggleQuickActionsMenu(anchor);

    const items = document.querySelectorAll('[role="menuitem"]');
    items[items.length - 1].click();

    expect(openManagerMock).toHaveBeenCalledWith();
    expect(toggleQuickPanelMock).not.toHaveBeenCalled();
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
