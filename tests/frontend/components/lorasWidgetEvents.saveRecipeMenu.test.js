import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const { EVENTS_MODULE, API_MODULE, APP_MODULE, COMPONENTS_MODULE, UTILS_MODULE } =
  vi.hoisted(() => ({
    EVENTS_MODULE: new URL('../../../web/comfyui/loras_widget_events.js', import.meta.url)
      .pathname,
    API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
    APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
    COMPONENTS_MODULE: new URL('../../../web/comfyui/loras_widget_components.js', import.meta.url)
      .pathname,
    UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url)
      .pathname,
  }));

const saveRecipeDirectly = vi.fn();

vi.mock(API_MODULE, () => ({ api: {} }));
vi.mock(APP_MODULE, () => ({ app: {} }));

vi.mock(COMPONENTS_MODULE, () => ({
  createMenuItem: (text, icon, onClick) => {
    const el = document.createElement('div');
    el.className = 'lm-lora-menu-item';
    el.textContent = text;
    if (onClick) el.addEventListener('click', onClick);
    return el;
  },
  createDropIndicator: vi.fn(),
}));

vi.mock(UTILS_MODULE, () => ({
  parseLoraValue: vi.fn(() => []),
  formatLoraValue: vi.fn((value) => value),
  syncClipStrengthIfCollapsed: vi.fn(),
  saveRecipeDirectly,
  copyToClipboard: vi.fn(),
  showToast: vi.fn(),
  moveLoraByDirection: vi.fn(),
  getDropTargetIndex: vi.fn(),
  getLoraStrengthRange: vi.fn(),
  applyStrengthRangeCue: vi.fn(),
}));

function findMenuItem(label) {
  return Array.from(document.querySelectorAll('.lm-lora-menu-item')).find(
    (item) => item.textContent === label
  );
}

describe('LoRA widget context menu save options', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
  });

  it('offers workflow embedding as a separate, opt-in action', async () => {
    const { createContextMenu } = await import(EVENTS_MODULE);
    const widget = { value: [], callback: vi.fn() };

    createContextMenu(10, 10, 'lora-a', widget, null, vi.fn());

    const plain = findMenuItem('Save Recipe');
    const withWorkflow = findMenuItem('Save Recipe with Workflow');
    expect(plain).toBeTruthy();
    expect(withWorkflow).toBeTruthy();

    plain.click();
    expect(saveRecipeDirectly).toHaveBeenLastCalledWith();

    // Re-open: the first click removed the menu.
    createContextMenu(10, 10, 'lora-a', widget, null, vi.fn());
    findMenuItem('Save Recipe with Workflow').click();
    expect(saveRecipeDirectly).toHaveBeenLastCalledWith({ embedWorkflow: true });
  });
});
