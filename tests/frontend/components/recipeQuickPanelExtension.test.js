import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  QUICK_PANEL_MODULE,
  registered,
  openRecipeMock,
  toggleRecipeMock,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
  registered: [],
  openRecipeMock: vi.fn(),
  toggleRecipeMock: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: (extension) => registered.push(extension),
  },
}));
vi.mock(QUICK_PANEL_MODULE, () => ({
  openRecipeQuickPanel: openRecipeMock,
  toggleRecipeQuickPanel: toggleRecipeMock,
}));

async function loadExtension() {
  await import('../../../web/comfyui/recipe_quick_panel.js');
  return registered.find((extension) => extension.name === 'LoraManager.RecipeQuickPanel');
}

describe('Recipe quick picker extension', () => {
  let extension;

  beforeAll(async () => {
    extension = await loadExtension();
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('registers a remappable command with the Alt+R default', async () => {
    expect(extension.commands).toEqual([
      expect.objectContaining({
        id: 'LoraManager.ToggleRecipeQuickPanel',
        label: 'Quick Recipe Picker',
      }),
    ]);
    expect(extension.keybindings).toEqual([{
      combo: { key: 'r', alt: true },
      commandId: 'LoraManager.ToggleRecipeQuickPanel',
    }]);

    extension.commands[0].function();
    expect(toggleRecipeMock).toHaveBeenCalledOnce();
  });

  it('does not add a node context-menu item', async () => {
    expect(extension.getNodeMenuItems).toBeUndefined();
    expect(openRecipeMock).not.toHaveBeenCalled();
  });
});
