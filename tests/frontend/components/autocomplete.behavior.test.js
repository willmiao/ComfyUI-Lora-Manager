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
  },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    canvas: {
      ds: { scale: 1 },
    },
  },
}));

vi.mock(CARET_HELPER_MODULE, () => ({
  TextAreaCaretHelper: vi.fn(() => caretHelperInstance),
}));

vi.mock(PREVIEW_COMPONENT_MODULE, () => ({
  PreviewTooltip: vi.fn(() => previewTooltipMock),
}));

describe('AutoComplete widget interactions', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.querySelectorAll('style').forEach((styleEl) => styleEl.remove());
    Element.prototype.scrollIntoView = vi.fn();
    fetchApiMock.mockReset();
    caretHelperInstance.getBeforeCursor.mockReset();
    caretHelperInstance.getCursorOffset.mockReset();
    caretHelperInstance.getBeforeCursor.mockReturnValue('');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 0, top: 0 });
    previewTooltipMock.show.mockReset();
    previewTooltipMock.hide.mockReset();
    previewTooltipMock.cleanup.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('fetches and renders search results when input exceeds the minimum characters', async () => {
    vi.useFakeTimers();

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, relative_paths: ['models/example.safetensors'] }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('example');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input, 'loras', { debounceDelay: 0, showPreview: false });

    input.value = 'example';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/loras/relative-paths?search=example&limit=20');
    const items = autoComplete.dropdown.querySelectorAll('.comfy-autocomplete-item');
    expect(items).toHaveLength(1);
    expect(autoComplete.dropdown.style.display).toBe('block');
    expect(autoComplete.isVisible).toBe(true);
    expect(caretHelperInstance.getCursorOffset).toHaveBeenCalled();
  });

  it('inserts the selected LoRA with usage tip strengths and restores focus', async () => {
    fetchApiMock.mockImplementation((url) => {
      if (url.includes('usage-tips-by-path')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            usage_tips: JSON.stringify({ strength: '1.5', clip_strength: '0.9' }),
          }),
        });
      }

      return Promise.resolve({
        json: () => Promise.resolve({ success: true, relative_paths: ['models/example.safetensors'] }),
      });
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('alpha, example');

    const input = document.createElement('textarea');
    input.value = 'alpha, example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input, 'loras', { debounceDelay: 0, showPreview: false });

    await autoComplete.insertSelection('models/example.safetensors');

    expect(fetchApiMock).toHaveBeenCalledWith(
      '/lm/loras/usage-tips-by-path?relative_path=models%2Fexample.safetensors',
    );
    expect(input.value).toContain('<lora:example:1.5:0.9>, ');
    expect(autoComplete.dropdown.style.display).toBe('none');
    expect(input.focus).toHaveBeenCalled();
    expect(input.setSelectionRange).toHaveBeenCalled();
  });
});
