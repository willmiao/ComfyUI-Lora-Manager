import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  API_MODULE,
  APP_MODULE,
  CARET_HELPER_MODULE,
  PREVIEW_COMPONENT_MODULE,
  AUTOCOMPLETE_MODULE,
} = vi.hoisted(() => ({
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  CARET_HELPER_MODULE: new URL('../../../web/comfyui/textarea_caret_helper.js', import.meta.url).pathname,
  PREVIEW_COMPONENT_MODULE: new URL('../../../web/comfyui/preview_tooltip.js', import.meta.url).pathname,
  AUTOCOMPLETE_MODULE: new URL('../../../web/comfyui/autocomplete.js', import.meta.url).pathname,
}));

const fetchApiMock = vi.fn();
const settingGetMock = vi.fn();
const settingSetMock = vi.fn();
const caretHelperInstance = {
  getBeforeCursor: vi.fn(() => ''),
  getCursorOffset: vi.fn(() => ({ left: 0, top: 0 })),
};
const previewTooltipMock = { show: vi.fn(), hide: vi.fn(), cleanup: vi.fn() };

vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock, addEventListener: vi.fn() },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    canvas: { ds: { scale: 1 } },
    extensionManager: { setting: { get: settingGetMock, set: settingSetMock } },
    registerExtension: vi.fn(),
  },
}));

vi.mock(CARET_HELPER_MODULE, () => ({
  TextAreaCaretHelper: vi.fn(() => caretHelperInstance),
}));

vi.mock(PREVIEW_COMPONENT_MODULE, () => ({
  PreviewTooltip: vi.fn(() => previewTooltipMock),
}));

const PATHS = ['portraits/example_entry.safetensors', 'styles/other_entry.safetensors'];

const respondWith = (paths = PATHS) => ({
  json: () => Promise.resolve({ success: true, relative_paths: paths }),
});

const flush = async () => {
  await vi.runAllTimersAsync();
  for (let i = 0; i < 6; i += 1) {
    await Promise.resolve();
  }
};

// The field's binding: a plain input whose picks go to the node's LoRA list and
// whose dropdown hangs off the field rather than the caret.
const mountField = async (options = {}) => {
  const input = document.createElement('input');
  document.body.append(input);

  const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
  const autoComplete = new AutoComplete(input, 'loras', {
    debounceDelay: 0,
    showPreview: false,
    pickIntoNode: true,
    anchorToElement: true,
    ...options,
  });

  return { input, autoComplete };
};

const loraWidget = (value = []) => ({
  value,
  callback: vi.fn(),
  selectLoraByName: vi.fn(),
});

const dropdownBox = (autoComplete) => ({
  left: autoComplete.dropdown.style.left,
  top: autoComplete.dropdown.style.top,
  width: parseInt(autoComplete.dropdown.style.width, 10),
});

describe('AutoComplete LoRA search field', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.querySelectorAll('style').forEach((styleEl) => styleEl.remove());
    Element.prototype.scrollIntoView = vi.fn();
    fetchApiMock.mockReset();
    settingGetMock.mockReset();
    settingSetMock.mockReset();
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') return true;
      if (key === 'loramanager.autocomplete_auto_format') return true;
      if (key === 'loramanager.autocomplete_accept_key') return 'both';
      if (key === 'loramanager.prompt_tag_autocomplete') return true;
      if (key === 'loramanager.tag_space_replacement') return false;
      if (key === 'loramanager.node_lora_name_display') return 'File Name';
      return undefined;
    });
    caretHelperInstance.getBeforeCursor.mockReset();
    caretHelperInstance.getCursorOffset.mockReset();
    caretHelperInstance.getBeforeCursor.mockReturnValue('');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 0, top: 0 });
    previewTooltipMock.show.mockReset();
    previewTooltipMock.hide.mockReset();
    previewTooltipMock.cleanup.mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('adds a picked LoRA to the node list instead of the field', async () => {
    const widget = loraWidget();
    const { input, autoComplete } = await mountField({ node: { lorasWidget: widget } });

    await autoComplete.insertSelection(PATHS[0]);

    expect(widget.value).toHaveLength(1);
    expect(widget.value[0]).toMatchObject({
      name: 'portraits/example_entry',
      active: true,
    });
    expect(widget.callback).toHaveBeenCalledTimes(1);
    // The pick is also located in the list, as if its row had been clicked.
    expect(widget.selectLoraByName).toHaveBeenCalledWith('portraits/example_entry');
    expect(input.value).toBe('');
    expect(autoComplete.dropdown.style.display).not.toBe('block');
  });

  it('enables a listed but disabled LoRA in place, keeping its strength', async () => {
    const widget = loraWidget([
      { name: 'portraits/example_entry', strength: '0.80', clipStrength: '0.80', active: false },
    ]);
    const { input, autoComplete } = await mountField({ node: { lorasWidget: widget } });

    await autoComplete.insertSelection(PATHS[0]);

    expect(widget.value).toHaveLength(1);
    expect(widget.value[0]).toMatchObject({ active: true, strength: '0.80' });
    expect(widget.callback).toHaveBeenCalledTimes(1);
    expect(widget.selectLoraByName).toHaveBeenCalledWith('portraits/example_entry');
    expect(input.value).toBe('');
  });

  it('leaves an already active LoRA alone and fires no callback', async () => {
    const widget = loraWidget([
      { name: 'portraits/example_entry', strength: '0.80', clipStrength: '0.80', active: true },
    ]);
    const { input, autoComplete } = await mountField({ node: { lorasWidget: widget } });

    await autoComplete.insertSelection(PATHS[0]);

    expect(widget.value).toHaveLength(1);
    expect(widget.callback).not.toHaveBeenCalled();
    // Still located in the list even when nothing changed.
    expect(widget.selectLoraByName).toHaveBeenCalledWith('portraits/example_entry');
    expect(input.value).toBe('');
  });

  it('anchors the dropdown to the field instead of the caret', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    const { input, autoComplete } = await mountField();
    input.getBoundingClientRect = () => ({
      left: 40, top: 100, right: 340, bottom: 118, width: 300, height: 18,
      x: 40, y: 100, toJSON: () => ({}),
    });

    await autoComplete.search('exa');
    await flush();

    expect(dropdownBox(autoComplete)).toMatchObject({ left: '40px', top: '122px' });
    expect(dropdownBox(autoComplete).width).toBeGreaterThanOrEqual(300);

    // Typing moves the caret; the dropdown must stay put and stay wide enough.
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');
    input.value = 'example';
    input.setSelectionRange(input.value.length, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flush();

    expect(dropdownBox(autoComplete)).toMatchObject({ left: '40px', top: '122px' });
    expect(dropdownBox(autoComplete).width).toBeGreaterThanOrEqual(300);
  });

  it('keeps caret anchoring when no anchor is requested', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    const { autoComplete } = await mountField({ anchorToElement: false });
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 12, top: 34 });

    await autoComplete.search('exa');
    await flush();

    expect(dropdownBox(autoComplete)).toMatchObject({ left: '12px', top: '34px' });
  });
});
