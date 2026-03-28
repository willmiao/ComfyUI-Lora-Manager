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

describe('AutoComplete widget interactions', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.querySelectorAll('style').forEach((styleEl) => styleEl.remove());
    Element.prototype.scrollIntoView = vi.fn();
    fetchApiMock.mockReset();
    settingGetMock.mockReset();
    settingSetMock.mockReset();
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return true;
      }
      if (key === 'loramanager.autocomplete_accept_key') {
        return 'both';
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });
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
    const autoComplete = new AutoComplete(input,'loras', { debounceDelay: 0, showPreview: false });

    input.value = 'example';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/loras/relative-paths?search=example&limit=100');
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
    const autoComplete = new AutoComplete(input,'loras', { debounceDelay: 0, showPreview: false });

    await autoComplete.insertSelection('models/example.safetensors');

    expect(fetchApiMock).toHaveBeenCalledWith(
      '/lm/loras/usage-tips-by-path?relative_path=models%2Fexample.safetensors',
    );
    expect(input.value).toContain('<lora:example:1.5:0.9>,');
    expect(autoComplete.dropdown.style.display).toBe('none');
    expect(input.focus).toHaveBeenCalled();
    expect(input.setSelectionRange).toHaveBeenCalled();
  });

  it('accepts the selected suggestion with Tab', async () => {
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['example_completion'];
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(true);
    expect(insertSelectionSpy).toHaveBeenCalledWith('example_completion');
  });

  it('accepts the selected suggestion with Enter', async () => {
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['example_completion'];
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    input.dispatchEvent(enterEvent);

    expect(enterEvent.defaultPrevented).toBe(true);
    expect(insertSelectionSpy).toHaveBeenCalledWith('example_completion');
  });

  it('prefers the latest best match when Tab is pressed before debounced suggestions fully refresh', async () => {
    caretHelperInstance.getBeforeCursor.mockReturnValue('loop');

    const input = document.createElement('textarea');
    input.value = 'loop';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', { showPreview: false, minChars: 1 });

    autoComplete.searchType = 'custom_words';
    autoComplete.items = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1000 },
      { tag_name: 'loop', category: 0, post_count: 500 },
    ];
    autoComplete.currentSearchTerm = 'loo';
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(true);
    expect(autoComplete.selectedIndex).toBe(1);
    expect(insertSelectionSpy).toHaveBeenCalledWith('loop');
  });

  it('accepts the first available suggestion with Tab even if delayed auto-selection has not happened yet', async () => {
    caretHelperInstance.getBeforeCursor.mockReturnValue('loop');

    const input = document.createElement('textarea');
    input.value = 'loop';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['loop'];
    autoComplete.selectedIndex = -1;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(true);
    expect(autoComplete.selectedIndex).toBe(0);
    expect(insertSelectionSpy).toHaveBeenCalledWith('loop');
  });

  it('only accepts with Tab when autocomplete accept key is set to tab_only', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return true;
      }
      if (key === 'loramanager.autocomplete_accept_key') {
        return 'tab_only';
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['example_completion'];
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    input.dispatchEvent(enterEvent);

    expect(enterEvent.defaultPrevented).toBe(false);
    expect(insertSelectionSpy).not.toHaveBeenCalled();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(true);
    expect(insertSelectionSpy).toHaveBeenCalledWith('example_completion');
  });

  it('only accepts with Enter when autocomplete accept key is set to enter_only', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return true;
      }
      if (key === 'loramanager.autocomplete_accept_key') {
        return 'enter_only';
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['example_completion'];
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = true;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(false);
    expect(insertSelectionSpy).not.toHaveBeenCalled();

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    input.dispatchEvent(enterEvent);

    expect(enterEvent.defaultPrevented).toBe(true);
    expect(insertSelectionSpy).toHaveBeenCalledWith('example_completion');
  });

  it('does not intercept Tab when the dropdown is not visible', async () => {
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'custom_words', { showPreview: false });

    autoComplete.items = ['example_completion'];
    autoComplete.selectedIndex = 0;
    autoComplete.isVisible = false;
    const insertSelectionSpy = vi.spyOn(autoComplete,'insertSelection').mockResolvedValue();

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    input.dispatchEvent(tabEvent);

    expect(tabEvent.defaultPrevented).toBe(false);
    expect(insertSelectionSpy).not.toHaveBeenCalled();
  });

  it('highlights multiple include tokens while ignoring excluded ones', async () => {
    const input = document.createElement('textarea');
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'loras', { showPreview: false });

    const highlighted = autoComplete.highlightMatch(
      'models/flux/beta-detail.safetensors',
      'flux detail -beta',
    );

    const highlightCount = (highlighted.match(/<span/g) || []).length;
    expect(highlightCount).toBe(2);
    expect(highlighted).toContain('flux');
    expect(highlighted).toContain('detail');
    expect(highlighted).not.toMatch(/beta<\/span>/i);
  });

  it('handles arrow key navigation with virtual scrolling', async () => {
    vi.useFakeTimers();

    const mockItems = Array.from({ length: 50 }, (_, i) => `model_${i.toString().padStart(2,'0')}.safetensors`);

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, relative_paths: mockItems }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('model');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'loras', {
      debounceDelay: 0,
      showPreview: false,
      enableVirtualScroll: true,
      itemHeight: 40,
      visibleItems: 15,
      pageSize: 20,
    });

    input.value = 'model';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(autoComplete.items.length).toBeGreaterThan(0);
    expect(autoComplete.selectedIndex).toBe(0);

    const initialSelectedEl = autoComplete.contentContainer?.querySelector('.comfy-autocomplete-item-selected');
    expect(initialSelectedEl).toBeDefined();

    const arrowDownEvent = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true });
    input.dispatchEvent(arrowDownEvent);

    expect(autoComplete.selectedIndex).toBe(1);

    const secondSelectedEl = autoComplete.contentContainer?.querySelector('.comfy-autocomplete-item-selected');
    expect(secondSelectedEl).toBeDefined();
    expect(secondSelectedEl?.dataset.index).toBe('1');

    const arrowUpEvent = new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true });
    input.dispatchEvent(arrowUpEvent);

    expect(autoComplete.selectedIndex).toBe(0);

    const firstSelectedElAgain = autoComplete.contentContainer?.querySelector('.comfy-autocomplete-item-selected');
    expect(firstSelectedElAgain).toBeDefined();
    expect(firstSelectedElAgain?.dataset.index).toBe('0');
  });

  it('maintains selection when scrolling to invisible items', async () => {
    vi.useFakeTimers();

    const mockItems = Array.from({ length: 100 }, (_, i) => `item_${i.toString().padStart(3,'0')}.safetensors`);

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, relative_paths: mockItems }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('item');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.style.width = '400px';
    input.style.height = '200px';
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'loras', {
      debounceDelay: 0,
      showPreview: false,
      enableVirtualScroll: true,
      itemHeight: 40,
      visibleItems: 15,
      pageSize: 20,
    });

    input.value = 'item';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(autoComplete.items.length).toBeGreaterThan(0);

    autoComplete.selectedIndex = 14;

    const scrollTopBefore = autoComplete.scrollContainer?.scrollTop || 0;

    const arrowDownEvent = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true });
    input.dispatchEvent(arrowDownEvent);

    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(autoComplete.selectedIndex).toBe(15);

    const selectedEl = autoComplete.contentContainer?.querySelector('.comfy-autocomplete-item-selected');
    expect(selectedEl).toBeDefined();
    expect(selectedEl?.dataset.index).toBe('15');

    const scrollTopAfter = autoComplete.scrollContainer?.scrollTop || 0;
    expect(scrollTopAfter).toBeGreaterThanOrEqual(scrollTopBefore);
  });

  it('replaces entire multi-word phrase when it matches selected tag (Danbooru convention)', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1234 },
      { tag_name: 'looking_away', category: 0, post_count: 5678 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('looking to the side');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'looking to the side';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;

    await autoComplete.insertSelection('looking_to_the_side');

    expect(input.value).toBe('looking_to_the_side,');
    expect(autoComplete.dropdown.style.display).toBe('none');
    expect(input.focus).toHaveBeenCalled();
  });

  it('replaces only last token when typing partial match (e.g., "hello 1gi" -> "1girl")', async () => {
    const mockTags = [
      { tag_name: '1girl', category: 4, post_count: 500000 },
      { tag_name: '1boy', category: 4, post_count: 300000 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('hello 1gi');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'hello 1gi';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'hello 1gi';

    await autoComplete.insertSelection('1girl');

    expect(input.value).toBe('hello 1girl,');
  });

  it('replaces entire phrase for underscore tag match (e.g., "blue hair" -> "blue_hair")', async () => {
    const mockTags = [
      { tag_name: 'blue_hair', category: 0, post_count: 45000 },
      { tag_name: 'blue_eyes', category: 0, post_count: 80000 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('blue hair');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'blue hair';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'blue hair';

    await autoComplete.insertSelection('blue_hair');

    expect(input.value).toBe('blue_hair,');
  });

  it('handles multi-word phrase with preceding text correctly', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1234 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('1girl, looking to the side');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = '1girl, looking to the side';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'looking to the side';

    await autoComplete.insertSelection('looking_to_the_side');

    expect(input.value).toBe('1girl, looking_to_the_side,');
  });

  it('replaces entire command and search term when using command mode with multi-word phrase', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 4, post_count: 1234 },
      { tag_name: 'looking_away', category: 4, post_count: 5678 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // Simulate "/char looking to the side" input
    caretHelperInstance.getBeforeCursor.mockReturnValue('/char looking to the side');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = '/char looking to the side';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    // Set up command mode state
    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = { categories: [4, 11], label: 'Character' };
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = '/char looking to the side';

    await autoComplete.insertSelection('looking_to_the_side');

    // Command part should be replaced along with search term
    expect(input.value).toBe('looking_to_the_side,');
  });

  it('replaces only last token when multi-word query does not exactly match selected tag', async () => {
    const mockTags = [
      { tag_name: 'blue_hair', category: 0, post_count: 45000 },
      { tag_name: 'blue_eyes', category: 0, post_count: 80000 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // User types "looking to the blue" but selects "blue_hair" (doesn't match entire phrase)
    caretHelperInstance.getBeforeCursor.mockReturnValue('looking to the blue');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'looking to the blue';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'looking to the blue';

    await autoComplete.insertSelection('blue_hair');

    // Only "blue" should be replaced, not the entire phrase
    expect(input.value).toBe('looking to the blue_hair,');
  });

  it('handles multiple consecutive spaces in multi-word phrase correctly', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1234 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // Input with multiple spaces between words
    caretHelperInstance.getBeforeCursor.mockReturnValue('looking  to   the side');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'looking  to   the side';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'looking  to   the side';

    await autoComplete.insertSelection('looking_to_the_side');

    // Multiple spaces should be normalized to single underscores for matching
    expect(input.value).toBe('looking_to_the_side,');
  });

  it('handles command mode with partial match replacing only last token', async () => {
    const mockTags = [
      { tag_name: 'blue_hair', category: 0, post_count: 45000 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // Command mode but selected tag doesn't match entire search phrase
    caretHelperInstance.getBeforeCursor.mockReturnValue('/general looking to the blue');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = '/general looking to the blue';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    // Command mode with activeCommand
    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = { categories: [0, 7], label: 'General' };
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = '/general looking to the blue';

    await autoComplete.insertSelection('blue_hair');

    // In command mode, the entire command + search term should be replaced
    expect(input.value).toBe('blue_hair,');
  });

  it('replaces entire phrase when selected tag starts with underscore version of search term (prefix match)', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1234 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // User types partial phrase "looking to the" and selects "looking_to_the_side"
    caretHelperInstance.getBeforeCursor.mockReturnValue('looking to the');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'looking to the';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'looking to the';

    await autoComplete.insertSelection('looking_to_the_side');

    // Entire phrase should be replaced with selected tag (with underscores)
    expect(input.value).toBe('looking_to_the_side,');
  });

  it('inserts tag with underscores regardless of space replacement setting', async () => {
    const mockTags = [
      { tag_name: 'blue_hair', category: 0, post_count: 45000 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('blue');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'blue';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;

    await autoComplete.insertSelection('blue_hair');

    // Tag should be inserted with underscores, not spaces
    expect(input.value).toBe('blue_hair,');
  });

  it('omits the trailing comma when the append comma setting is disabled', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return false;
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    const mockTags = [
      { tag_name: 'blue_hair', category: 0, post_count: 45000 },
    ];

    caretHelperInstance.getBeforeCursor.mockReturnValue('blue hair');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'blue hair';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'blue hair';

    await autoComplete.insertSelection('blue_hair');

    expect(input.value).toBe('blue_hair ');
  });

  it('uses persisted autocomplete metadata as the next search start when comma append is disabled', async () => {
    vi.useFakeTimers();

    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return false;
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: [{ tag_name: 'cat_ears', category: 0, post_count: 1234 }] }),
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('1girl cat');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = '1girl cat';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    input._autocompleteMetadataWidget = {
      value: {
        version: 1,
        textWidgetName: 'text',
        lastAccepted: {
          start: 0,
          end: 6,
          insertedText: '1girl ',
          textSnapshot: '1girl ',
        },
      },
    };
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    expect(autoComplete.getSearchTerm(input.value)).toBe('cat');

    input.dispatchEvent(new Event('input', { bubbles: true }));
    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/custom-words/search?enriched=true&search=cat&limit=100');
  });

  it('invalidates stale autocomplete metadata and falls back to delimiter-based matching', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return false;
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('1boy cat');

    const metadataWidget = {
      value: {
        version: 1,
        textWidgetName: 'text',
        lastAccepted: {
          start: 0,
          end: 6,
          insertedText: '1girl ',
          textSnapshot: '1girl ',
        },
      },
    };

    const input = document.createElement('textarea');
    input.value = '1boy cat';
    input.selectionStart = input.value.length;
    input._autocompleteMetadataWidget = metadataWidget;
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    expect(autoComplete.getSearchTerm(input.value)).toBe('1boy cat');
    expect(metadataWidget.value.lastAccepted).toBeUndefined();
  });

  it('does not duplicate the first character when accepting a suggestion after a trailing space', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return false;
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    const mockTags = [
      { tag_name: '1girl', category: 4, post_count: 500000 },
    ];

    caretHelperInstance.getBeforeCursor.mockReturnValue('1girl ');

    const input = document.createElement('textarea');
    input.value = '1girl ';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;

    await autoComplete.insertSelection('1girl');

    expect(input.value).toBe('1girl ');
  });

  it('treats a newline as a hard boundary after dismissing autocomplete', async () => {
    vi.useFakeTimers();

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: [{ tag_name: '1girl', category: 4, post_count: 500000 }] }),
    });

    const input = document.createElement('textarea');
    input.value = '1gi\n';
    input.selectionStart = input.value.length;
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    caretHelperInstance.getBeforeCursor.mockReturnValue('1gi');
    autoComplete.handleInput('1gi');
    await vi.runAllTimersAsync();
    await Promise.resolve();
    expect(fetchApiMock).toHaveBeenCalled();

    fetchApiMock.mockClear();
    autoComplete.hide();

    caretHelperInstance.getBeforeCursor.mockReturnValue('1gi\n');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await vi.runAllTimersAsync();
    await Promise.resolve();

    expect(autoComplete.getSearchTerm(input.value)).toBe('');
    expect(fetchApiMock).not.toHaveBeenCalled();
    expect(autoComplete.isVisible).toBe(false);
  });

  it('omits the trailing comma for LoRA insertions when the setting is disabled', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.autocomplete_append_comma') {
        return false;
      }
      if (key === 'loramanager.prompt_tag_autocomplete') {
        return true;
      }
      if (key === 'loramanager.tag_space_replacement') {
        return false;
      }
      return undefined;
    });

    fetchApiMock.mockImplementation((url) => {
      if (url.includes('usage-tips-by-path')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            success: true,
            usage_tips: JSON.stringify({ strength: '1.2' }),
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
    const autoComplete = new AutoComplete(input,'loras', { debounceDelay: 0, showPreview: false });

    await autoComplete.insertSelection('models/example.safetensors');

    expect(input.value).toContain('<lora:example:1.2>');
    expect(input.value).not.toContain('<lora:example:1.2>,');
  });

  it('replaces entire phrase when selected tag ends with underscore version of search term (suffix match)', async () => {
    const mockTags = [
      { tag_name: 'looking_to_the_side', category: 0, post_count: 1234 },
    ];

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: mockTags }),
    });

    // User types suffix "to the side" and selects "looking_to_the_side"
    caretHelperInstance.getBeforeCursor.mockReturnValue('to the side');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 15, top: 25 });

    const input = document.createElement('textarea');
    input.value = 'to the side';
    input.selectionStart = input.value.length;
    input.focus = vi.fn();
    input.setSelectionRange = vi.fn();
    document.body.append(input);

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input,'prompt', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    autoComplete.searchType = 'custom_words';
    autoComplete.activeCommand = null;
    autoComplete.items = mockTags;
    autoComplete.selectedIndex = 0;
    autoComplete.currentSearchTerm = 'to the side';

    await autoComplete.insertSelection('looking_to_the_side');

    // Entire phrase should be replaced with selected tag
    expect(input.value).toBe('looking_to_the_side,');
  });
});
