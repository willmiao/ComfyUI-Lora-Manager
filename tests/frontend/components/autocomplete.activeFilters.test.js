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
const caretHelperInstance = {
  getBeforeCursor: vi.fn(() => ''),
  getCursorOffset: vi.fn(() => ({ left: 0, top: 0 })),
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
        set: vi.fn(),
      },
    },
    registerExtension: vi.fn(),
  },
}));

vi.mock(CARET_HELPER_MODULE, () => ({
  TextAreaCaretHelper: vi.fn(() => caretHelperInstance),
}));

vi.mock(PREVIEW_COMPONENT_MODULE, () => ({
  PreviewTooltip: vi.fn(() => ({ show: vi.fn(), hide: vi.fn(), cleanup: vi.fn() })),
}));

async function createAutoComplete(modelType, activeFiltersEnabled) {
  settingGetMock.mockImplementation((key) => {
    if (key === 'loramanager.lora_active_filters_autocomplete') {
      return activeFiltersEnabled;
    }
    if (key === 'loramanager.autocomplete_append_comma') return false;
    if (key === 'loramanager.autocomplete_auto_format') return false;
    if (key === 'loramanager.autocomplete_accept_key') return 'both';
    return undefined;
  });

  fetchApiMock.mockResolvedValue({
    json: () => Promise.resolve({ success: true, relative_paths: [] }),
  });

  const input = document.createElement('textarea');
  document.body.append(input);

  const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
  const autoComplete = new AutoComplete(input, modelType, { debounceDelay: 0, showPreview: false });

  input.value = 'example';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await vi.runAllTimersAsync();
  await Promise.resolve();

  return autoComplete;
}

describe('AutoComplete active-filters flag', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '';
    document.head.querySelectorAll('style').forEach((styleEl) => styleEl.remove());
    Element.prototype.scrollIntoView = vi.fn();
    fetchApiMock.mockReset();
    settingGetMock.mockReset();
    caretHelperInstance.getBeforeCursor.mockReset();
    caretHelperInstance.getCursorOffset.mockReset();
    caretHelperInstance.getBeforeCursor.mockReturnValue('example');
    caretHelperInstance.getCursorOffset.mockReturnValue({ left: 0, top: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends use_active_filters for loras when the setting is enabled', async () => {
    await createAutoComplete('loras', true);

    expect(fetchApiMock).toHaveBeenCalledWith(
      '/lm/loras/relative-paths?search=example&limit=100&use_active_filters=true'
    );
  });

  it('omits the flag when the setting is disabled', async () => {
    await createAutoComplete('loras', false);

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/loras/relative-paths?search=example&limit=100');
  });

  it('omits the flag for non-lora model types even when enabled', async () => {
    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({ success: true, words: [] }),
    });
    await createAutoComplete('prompt', true);

    for (const call of fetchApiMock.mock.calls) {
      expect(call[0]).not.toContain('use_active_filters');
    }
  });

  it('does not read filter state from localStorage anymore', async () => {
    localStorage.setItem('lora_manager_loras_activeFolder', 'SD_XL');
    localStorage.setItem('lora_manager_loras_filters', JSON.stringify({ baseModel: ['SDXL 1.0'] }));

    await createAutoComplete('loras', true);

    for (const call of fetchApiMock.mock.calls) {
      expect(call[0]).not.toContain('folder=');
      expect(call[0]).not.toContain('base_model=');
    }
  });

  const typeLorasSlashCommand = async () => {
    const input = document.createElement('textarea');
    input.value = '/';
    input.selectionStart = 1;
    document.body.append(input);

    caretHelperInstance.getBeforeCursor.mockReturnValue('/');

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input, 'loras', { showPreview: false, minChars: 1 });

    input.dispatchEvent(new Event('input', { bubbles: true }));
    return autoComplete;
  };

  it('shows the active-filters state below the loras slash command list', async () => {
    await typeLorasSlashCommand();

    const footer = document.querySelector('.lm-autocomplete-command-footer');
    expect(footer).not.toBeNull();
    expect(footer.textContent).toContain('Active Filters Search: OFF');
    expect(footer.textContent).toContain('/activefilters to enable');
  });

  it('shows how to disable active-filters search in the footer when it is on', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.lora_active_filters_autocomplete') {
        return true;
      }
      return undefined;
    });

    await typeLorasSlashCommand();

    const footer = document.querySelector('.lm-autocomplete-command-footer');
    expect(footer).not.toBeNull();
    expect(footer.textContent).toContain('Active Filters Search: ON');
    expect(footer.textContent).toContain('/noactivefilters to disable');
  });

  it('shows a dismissible first-run hint on loras suggestions and remembers dismissal', async () => {
    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({
        success: true,
        relative_paths: ['models/example.safetensors'],
      }),
    });

    const triggerSearch = async () => {
      const input = document.createElement('textarea');
      input.value = 'example';
      input.selectionStart = 7;
      document.body.append(input);

      caretHelperInstance.getBeforeCursor.mockReturnValue('example');

      const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
      const autoComplete = new AutoComplete(input, 'loras', {
        debounceDelay: 0,
        showPreview: false,
        minChars: 1,
      });

      input.dispatchEvent(new Event('input', { bubbles: true }));
      await vi.runOnlyPendingTimersAsync();
      await vi.runOnlyPendingTimersAsync();
      await Promise.resolve();
      return autoComplete;
    };

    const autoComplete = await triggerSearch();
    const hint = autoComplete.dropdown.querySelector('.lm-autocomplete-first-run-hint');
    expect(hint).not.toBeNull();
    expect(hint.textContent).toContain('/activefilters');

    hint.querySelector('button').click();
    expect(autoComplete.dropdown.querySelector('.lm-autocomplete-first-run-hint')).toBeNull();
    expect(localStorage.getItem('lm:activefilters-tip-dismissed')).toBe('1');
    // A fresh instance no longer shows the hint once dismissed
    const autoComplete2 = await triggerSearch();
    expect(autoComplete2.dropdown.querySelector('.lm-autocomplete-first-run-hint')).toBeNull();
  });

  it('does not show the loras first-run hint when active-filters search is already on', async () => {
    settingGetMock.mockImplementation((key) => {
      if (key === 'loramanager.lora_active_filters_autocomplete') {
        return true;
      }
      return undefined;
    });

    fetchApiMock.mockResolvedValue({
      json: () => Promise.resolve({
        success: true,
        relative_paths: ['models/example.safetensors'],
      }),
    });

    const input = document.createElement('textarea');
    input.value = 'example';
    input.selectionStart = 7;
    document.body.append(input);

    caretHelperInstance.getBeforeCursor.mockReturnValue('example');

    const { AutoComplete } = await import(AUTOCOMPLETE_MODULE);
    const autoComplete = new AutoComplete(input, 'loras', {
      debounceDelay: 0,
      showPreview: false,
      minChars: 1,
    });

    input.dispatchEvent(new Event('input', { bubbles: true }));
    await vi.runOnlyPendingTimersAsync();
    await vi.runOnlyPendingTimersAsync();
    await Promise.resolve();

    expect(autoComplete.dropdown.querySelector('.lm-autocomplete-first-run-hint')).toBeNull();
  });
});
