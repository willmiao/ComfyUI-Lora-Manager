import { beforeEach, describe, expect, it, vi } from 'vitest';

// Covers the two contracts the top menu extension has with ComfyUI's frontend:
// which button API it advertises for a given version, and how it keeps the
// LoRA Manager icon on a button that Vue re-renders behind its back.

const {
  APP_MODULE,
  CANVAS_API_MODULE,
  QUICK_MENU_MODULE,
  appMock,
  openManagerMock,
  toggleQuickActionsMock,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  QUICK_MENU_MODULE: new URL('../../../web/comfyui/quick_actions_menu.js', import.meta.url).pathname,
  appMock: {
    registerExtension: vi.fn(),
    menu: undefined,
  },
  openManagerMock: vi.fn(),
  toggleQuickActionsMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(CANVAS_API_MODULE, () => ({ openLoraManagerHome: openManagerMock }));
vi.mock(QUICK_MENU_MODULE, () => ({ toggleQuickActionsMenu: toggleQuickActionsMock }));

const BUTTON_TOOLTIP = 'Open LoRA Manager (Shift+Click opens in a new window)';
const QUICK_ACTIONS_TOOLTIP = 'LoRA Manager quick actions';
const STYLE_ID = 'lm-top-menu-button-styles';
const QUICK_ACTIONS_BUTTON_CLASS = 'lm-quick-actions-button';

// The classes ComfyUI puts on an action bar button (variant="muted-textonly",
// size="sm", class="h-7 rounded-full"); the extension has to work from this
// starting point and survive repeated passes over it.
const NATIVE_ACTION_BAR_CLASSES = [
  'bg-transparent',
  'text-muted-foreground',
  'h-7',
  'rounded-full',
  'px-2',
  'py-1',
];

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));

// The extension decorates the button from a requestAnimationFrame poll and
// from a MutationObserver, so a repair lands a couple of turns later.
async function settleDecoration() {
  await Promise.resolve();
  await nextFrame();
  await nextFrame();
}

function renderActionBar() {
  const main = document.createElement('button');
  main.type = 'button';
  main.setAttribute('aria-label', BUTTON_TOOLTIP);
  main.classList.add(...NATIVE_ACTION_BAR_CLASSES);
  main.innerHTML = '<i class="icon-[lucide--layers] size-4"></i>';

  const quick = document.createElement('button');
  quick.type = 'button';
  quick.setAttribute('aria-label', QUICK_ACTIONS_TOOLTIP);
  quick.classList.add(QUICK_ACTIONS_BUTTON_CLASS, ...NATIVE_ACTION_BAR_CLASSES);
  quick.innerHTML = '<i class="icon-[lucide--chevron-down] size-4"></i>';

  const actionBar = document.createElement('div');
  actionBar.setAttribute('data-testid', 'action-bar-buttons');
  actionBar.append(main, quick);
  document.body.appendChild(actionBar);

  return { actionBar, main, quick };
}

async function loadExtension(version = '1.50.0') {
  window.__COMFYUI_FRONTEND_VERSION__ = version;
  vi.resetModules();
  await import('../../../web/comfyui/top_menu_extension.js');
  await vi.waitFor(() => expect(appMock.registerExtension).toHaveBeenCalled());
  return appMock.registerExtension.mock.calls.at(-1)[0];
}

describe('LoRA Manager top menu extension', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.__lmIconObserver;
    delete window.__COMFYUI_FRONTEND_VERSION__;
    appMock.registerExtension.mockClear();
    appMock.menu = undefined;
    openManagerMock.mockClear();
    toggleQuickActionsMock.mockClear();
    // fetchVersionInfo() asks the backend for the extension version.
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ success: true, version: '9.9.9' }),
    })));
  });

  it('advertises the action bar buttons on frontends that support them', async () => {
    const extension = await loadExtension('1.50.0');

    expect(extension.name).toBe('LoraManager.TopMenu');
    expect(extension.actionBarButtons).toHaveLength(2);
    expect(extension.actionBarButtons[0]).toMatchObject({
      tooltip: BUTTON_TOOLTIP,
      onClick: expect.any(Function),
    });
    expect(extension.actionBarButtons[1]).toMatchObject({
      tooltip: QUICK_ACTIONS_TOOLTIP,
      class: QUICK_ACTIONS_BUTTON_CLASS,
      onClick: expect.any(Function),
    });
  });

  it('falls back to the legacy menu bar on older frontends', async () => {
    const settingsGroupParent = document.createElement('div');
    const settingsGroup = document.createElement('button');
    settingsGroupParent.appendChild(settingsGroup);
    document.body.appendChild(settingsGroupParent);
    appMock.menu = { settingsGroup: { element: settingsGroup, parentElement: settingsGroupParent } };

    const extension = await loadExtension('1.33.8');

    // Attaching through menu.settingsGroup is the pre-1.33.9 path: advertising
    // actionBarButtons as well would render the buttons twice.
    expect(extension.actionBarButtons).toBeUndefined();

    await extension.setup();

    const group = document.querySelector('.lora-manager-top-menu-group');
    expect(group).not.toBeNull();
    expect(group.parentElement).toBe(settingsGroupParent);
    const [mainButton, quickButton] = group.querySelectorAll('button');
    expect(mainButton).not.toBeUndefined();
    expect(quickButton).not.toBeUndefined();

    mainButton.dispatchEvent(new MouseEvent('click', { bubbles: true, shiftKey: true }));
    expect(openManagerMock).toHaveBeenCalledWith(true);

    quickButton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(toggleQuickActionsMock).toHaveBeenCalledWith(quickButton);
  });

  it('routes the action bar clicks to the manager and the quick actions menu', async () => {
    const { main, quick } = renderActionBar();
    const extension = await loadExtension('1.50.0');

    extension.actionBarButtons[0].onClick({ shiftKey: true, currentTarget: main });
    expect(openManagerMock).toHaveBeenCalledWith(true);

    extension.actionBarButtons[1].onClick({ shiftKey: false, currentTarget: quick });
    expect(toggleQuickActionsMock).toHaveBeenCalledWith(quick);
  });

  it('decorates the action bar button once, keeping the icon stable', async () => {
    const { main } = renderActionBar();
    const extension = await loadExtension('1.50.0');

    await extension.setup();
    await settleDecoration();

    const icon = main.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(main.classList.contains('lm-top-menu-button')).toBe(true);
    // The placeholder <i> is replaced, not kept next to the brand SVG.
    expect(main.querySelector('i')).toBeNull();
    expect(main.querySelectorAll('svg')).toHaveLength(1);

    // setup() runs again on extension reload; the existing icon must survive
    // instead of being rebuilt or duplicated.
    await extension.setup();
    await settleDecoration();

    expect(main.querySelectorAll('svg')).toHaveLength(1);
    expect(main.querySelector('svg')).toBe(icon);
  });

  it('puts the icon back when Vue re-renders the button contents', async () => {
    const { main } = renderActionBar();
    const extension = await loadExtension('1.50.0');

    await extension.setup();
    await settleDecoration();
    expect(main.querySelector('svg')).not.toBeNull();

    // Vue resets the button to its declared slot content.
    main.innerHTML = '<i class="icon-[lucide--layers] size-4"></i>';

    await vi.waitFor(() => expect(main.querySelector('svg')).not.toBeNull());
    expect(main.querySelectorAll('svg')).toHaveLength(1);
  });

  it('injects the button stylesheet once, no matter how often setup runs', async () => {
    renderActionBar();
    const extension = await loadExtension('1.50.0');

    await extension.setup();
    await extension.setup();

    expect(document.querySelectorAll(`#${STYLE_ID}`)).toHaveLength(1);
  });
});
