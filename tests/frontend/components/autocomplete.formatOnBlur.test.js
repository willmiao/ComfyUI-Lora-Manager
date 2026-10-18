import { describe, it, expect, vi } from 'vitest';

const {
  API_MODULE,
  APP_MODULE,
  AUTOCOMPLETE_MODULE,
} = vi.hoisted(() => ({
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  AUTOCOMPLETE_MODULE: new URL('../../../web/comfyui/autocomplete.js', import.meta.url).pathname,
}));

vi.mock(API_MODULE, () => ({
  api: {
    fetchApi: vi.fn(),
  },
}));

vi.mock(APP_MODULE, () => ({
  app: {
    canvas: {
      ds: { scale: 1 },
    },
    extensionManager: {
      setting: {
        get: vi.fn(),
        set: vi.fn(),
      },
    },
    registerExtension: vi.fn(),
  },
}));

describe('formatAutocompleteTextOnBlur', () => {
  it('preserves repeated spaces inside LoRA names', async () => {
    const { formatAutocompleteTextOnBlur } = await import(AUTOCOMPLETE_MODULE);

    expect(formatAutocompleteTextOnBlur('<lora:test -  0021:1.00>')).toBe(
      '<lora:test -  0021:1.00>'
    );
  });

  it('preserves repeated spaces across multiple LoRA entries', async () => {
    const { formatAutocompleteTextOnBlur } = await import(AUTOCOMPLETE_MODULE);

    expect(
      formatAutocompleteTextOnBlur('<lora:test -  0021:1.00>,<lora:a  b:0.50>')
    ).toBe('<lora:test -  0021:1.00>, <lora:a  b:0.50>');
  });

  it('still normalizes whitespace outside LoRA tags', async () => {
    const { formatAutocompleteTextOnBlur } = await import(AUTOCOMPLETE_MODULE);

    expect(formatAutocompleteTextOnBlur('masterpiece,   best   quality')).toBe(
      'masterpiece, best quality'
    );
  });
});
