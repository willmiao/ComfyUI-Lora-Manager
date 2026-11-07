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

const previewTooltipMock = {
  show: vi.fn(),
  hide: vi.fn(),
  cleanup: vi.fn(),
};

vi.mock(API_MODULE, () => ({
  api: {
    fetchApi: fetchApiMock,
    addEventListener: vi.fn(),
  },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    canvas: {
      ds: { scale: 1 },
    },
    extensionManager: {
      setting: {
        get: settingGetMock,
        set: settingSetMock,
      },
    },
    registerExtension: vi.fn(),
  },
}));

vi.mock(CARET_HELPER_MODULE, () => ({
  TextAreaCaretHelper: vi.fn(() => caretHelperInstance),
}));

vi.mock(PREVIEW_COMPONENT_MODULE, () => ({
  PreviewTooltip: vi.fn(() => previewTooltipMock),
}));

const PATH = 'portraits/example_entry.safetensors';
const TITLE = 'Golden Hour Portrait';

const respondWith = ({ paths = [PATH], items = null } = {}) => {
  const payload = { success: true, relative_paths: paths };
  if (items) {
    payload.items = items;
  }
  return {
    json: () => Promise.resolve(payload),
  };
};

const mountAutocomplete = async ({ node } = {}) => {
  const input = document.createElement('textarea');
  document.body.append(input);

  const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
  const autoComplete = new AutoComplete(input, 'loras', {
    debounceDelay: 0,
    showPreview: false,
    node,
  });

  input.value = 'example';
  input.dispatchEvent(new Event('input', { bubbles: true }));

  await vi.runAllTimersAsync();
  await Promise.resolve();

  return { input, autoComplete };
};

const itemEls = (autoComplete) =>
  Array.from(autoComplete.dropdown.querySelectorAll('.comfy-autocomplete-item'));

describe('AutoComplete LoRA title matching and added cue', () => {
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

  it('keeps the legacy request and rendering in File Name mode', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const { autoComplete } = await mountAutocomplete();

    expect(fetchApiMock).toHaveBeenCalledWith(
      '/lm/loras/relative-paths?search=example&limit=100',
    );
    const [item] = itemEls(autoComplete);
    expect(item).toBeTruthy();
    expect(item.querySelector('.lm-autocomplete-name').textContent).toBe(
      'portraits/example_entry',
    );
    expect(item.querySelector('.lm-autocomplete-subtitle')).toBeNull();
    expect(item.querySelector('.lm-autocomplete-added')).toBeNull();
  });

  it('requests and shows library titles in Model Name mode', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.node_lora_name_display') return 'Model Name';
      return undefined;
    });
    fetchApiMock.mockResolvedValue(
      respondWith({
        items: [{ relative_path: PATH, model_name: TITLE }],
      }),
    );
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const { autoComplete } = await mountAutocomplete();

    expect(fetchApiMock).toHaveBeenCalledWith(
      '/lm/loras/relative-paths?search=example&limit=100&match_model_name=true&include_model_name=true',
    );
    const [item] = itemEls(autoComplete);
    expect(item.querySelector('.lm-autocomplete-name').textContent).toBe(TITLE);
    expect(item.querySelector('.lm-autocomplete-subtitle').textContent).toBe(
      'portraits/example_entry',
    );
  });

  it('falls back to the file name when the entry has no title', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.node_lora_name_display') return 'Model Name';
      return undefined;
    });
    fetchApiMock.mockResolvedValue(
      respondWith({
        items: [{ relative_path: PATH, model_name: '' }],
      }),
    );
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const { autoComplete } = await mountAutocomplete();

    const [item] = itemEls(autoComplete);
    expect(item.querySelector('.lm-autocomplete-name').textContent).toBe(
      'portraits/example_entry',
    );
    expect(item.querySelector('.lm-autocomplete-subtitle')).toBeNull();
  });

  it('marks a LoRA that is already on the node list', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const node = {
      lorasWidget: {
        value: [{ name: 'portraits/example_entry.safetensors', active: false }],
      },
    };
    const { autoComplete } = await mountAutocomplete({ node });

    const [item] = itemEls(autoComplete);
    const cue = item.querySelector('.lm-autocomplete-added');
    expect(cue).toBeTruthy();
    expect(cue.textContent).toBe('✓');
    expect(cue.getAttribute('aria-label')).toBe('Already added');
  });

  it('matches legacy bare-name list entries by file name', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const node = { lorasWidget: { value: [{ name: 'example_entry' }] } };
    const { autoComplete } = await mountAutocomplete({ node });

    const [item] = itemEls(autoComplete);
    expect(item.querySelector('.lm-autocomplete-added')).toBeTruthy();
  });

  it('does not mark a LoRA that is not on the node list', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const node = {
      lorasWidget: { value: [{ name: 'styles/other_entry' }] },
    };
    const { autoComplete } = await mountAutocomplete({ node });

    const [item] = itemEls(autoComplete);
    expect(item.querySelector('.lm-autocomplete-added')).toBeNull();
  });

  it('falls back to parsing the textarea when the node has no LoRA list', async () => {
    fetchApiMock.mockResolvedValue(respondWith());
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const node = {};
    const { autoComplete, input } = await mountAutocomplete({ node });
    input.value = 'masterpiece, <lora:portraits/example_entry:0.8>';

    autoComplete.render();

    const [item] = itemEls(autoComplete);
    expect(item.querySelector('.lm-autocomplete-added')).toBeTruthy();
  });

  it('does not request titles for non-LoRA autocompletes', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.node_lora_name_display') return 'Model Name';
      return undefined;
    });
    fetchApiMock.mockResolvedValue({ json: () => Promise.resolve({ success: true, words: [] }) });

    const input = document.createElement('textarea');
    document.body.append(input);
    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    new AutoComplete(input, 'prompt', { debounceDelay: 0, showPreview: false });

    input.value = 'example';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await vi.runAllTimersAsync();
    await Promise.resolve();

    const requestedUrl = fetchApiMock.mock.calls[0]?.[0] || '';
    expect(requestedUrl).not.toContain('match_model_name');
    expect(requestedUrl).not.toContain('include_model_name');
  });
});
