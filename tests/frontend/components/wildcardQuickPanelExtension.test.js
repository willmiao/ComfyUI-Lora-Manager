import { beforeAll, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  API_MODULE,
  QUICK_PANEL_MODULE,
  registered,
  toggleWildcardMock,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/wildcard_quick_panel.js', import.meta.url).pathname,
  registered: [],
  toggleWildcardMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: (extension) => registered.push(extension),
  },
}));
vi.mock(API_MODULE, () => ({
  api: { addEventListener: vi.fn() },
}));
vi.mock(QUICK_PANEL_MODULE, () => ({
  openWildcardQuickPanel: vi.fn(),
  reloadWildcardQuickPanel: vi.fn(),
  toggleWildcardQuickPanel: toggleWildcardMock,
}));

async function loadExtension() {
  await import('../../../web/comfyui/wildcard_quick_panel_extension.js');
  return registered.find((extension) => extension.name === 'LoraManager.WildcardQuickPanel');
}

describe('Wildcard quick panel extension', () => {
  let extension;

  beforeAll(async () => {
    extension = await loadExtension();
  });

  it('registers a remappable command without a default keybinding', () => {
    expect(extension.commands).toEqual([
      expect.objectContaining({
        id: 'LoraManager.ToggleWildcardQuickPanel',
        label: 'Global Wildcards',
      }),
    ]);
    expect(extension.keybindings).toBeUndefined();

    extension.commands[0].function();
    expect(toggleWildcardMock).toHaveBeenCalledOnce();
  });
});
