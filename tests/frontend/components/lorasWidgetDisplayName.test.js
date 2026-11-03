import { describe, it, expect, beforeEach, vi } from 'vitest';

const {
  APP_MODULE,
  API_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: { graph: {} },
}));

const { fetchApiMock } = vi.hoisted(() => ({ fetchApiMock: vi.fn() }));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock },
}));

import {
  buildModelNameMap,
  parseModelNameDisplayMode,
  getLoraDisplayName,
  getAvailableLoras,
  resetAvailableLorasCache,
  handleLibraryChangeMessage,
} from '../../../web/comfyui/loras_widget_utils.js';

// Route the mocked ComfyUI API per endpoint: the availability refresh asks for
// the cycler list AND the LoRA Manager settings, and the two carry different
// payload shapes.
const respondWith = ({ loras = [], settings = {}, settingsOk = true } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    if (url === '/lm/settings') {
      if (!settingsOk) {
        return { ok: false, status: 500, json: async () => ({}) };
      }
      return { ok: true, json: async () => ({ success: true, settings }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

describe('buildModelNameMap', () => {
  it('keys titles by normalized path and basename', () => {
    const map = buildModelNameMap([
      { file_name: 'krea2/abc123def', model_name: 'Example model title' },
    ]);
    expect(map.get('krea2/abc123def')).toBe('Example model title');
    expect(map.get('abc123def')).toBe('Example model title');
  });

  it('strips file extensions from keys', () => {
    const map = buildModelNameMap([{ file_name: 'sub/a.safetensors', model_name: 'Title A' }]);
    expect(map.get('sub/a')).toBe('Title A');
    expect(map.get('a')).toBe('Title A');
  });

  it('trims titles and skips entries without one', () => {
    const map = buildModelNameMap([
      { file_name: 'a', model_name: '  Spaced Title  ' },
      { file_name: 'b' },
      { file_name: 'c', model_name: '   ' },
      { file_name: 'd', model_name: 42 },
    ]);
    expect(map.get('a')).toBe('Spaced Title');
    expect(map.has('b')).toBe(false);
    expect(map.has('c')).toBe(false);
    expect(map.has('d')).toBe(false);
  });

  it('skips entries without a file name', () => {
    const map = buildModelNameMap([{ model_name: 'Orphan' }]);
    expect(map.size).toBe(0);
  });

  it('tolerates missing input', () => {
    expect(buildModelNameMap(undefined).size).toBe(0);
    expect(buildModelNameMap([]).size).toBe(0);
  });
});

describe('parseModelNameDisplayMode', () => {
  it('reads the file_name preference', () => {
    expect(parseModelNameDisplayMode({ settings: { model_name_display: 'file_name' } })).toBe(
      'file_name'
    );
  });

  it('reads the model_name preference', () => {
    expect(parseModelNameDisplayMode({ settings: { model_name_display: 'model_name' } })).toBe(
      'model_name'
    );
  });

  it('defaults to model_name for missing or unknown values', () => {
    expect(parseModelNameDisplayMode({ settings: {} })).toBe('model_name');
    expect(parseModelNameDisplayMode({ settings: { model_name_display: 'nonsense' } })).toBe(
      'model_name'
    );
    expect(parseModelNameDisplayMode(undefined)).toBe('model_name');
    expect(parseModelNameDisplayMode({})).toBe('model_name');
  });
});

describe('getLoraDisplayName', () => {
  const loras = [
    { file_name: 'krea2/abc123def', model_name: 'Example title' },
    { file_name: 'sub/plain.safetensors' },
  ];

  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('returns the stored name while the cache is not loaded', () => {
    expect(getLoraDisplayName('abc123def')).toBe('abc123def');
  });

  it('returns the model name for the default display preference', async () => {
    respondWith({ loras, settings: { model_name_display: 'model_name' } });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('Example title');
  });

  it('returns the stored name when the preference is the file name', async () => {
    respondWith({ loras, settings: { model_name_display: 'file_name' } });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('abc123def');
  });

  it('resolves folder-qualified and extension-carrying entry names', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('krea2/abc123def')).toBe('Example title');
    expect(getLoraDisplayName('krea2/abc123def.safetensors')).toBe('Example title');
    expect(getLoraDisplayName('sub/plain')).toBe('sub/plain');
  });

  it('falls back to the stored name for unknown and absolute paths', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('unknown')).toBe('unknown');
    expect(getLoraDisplayName('/abs/path/abc123def')).toBe('/abs/path/abc123def');
    expect(getLoraDisplayName('C:/abs/abc123def')).toBe('C:/abs/abc123def');
  });

  it('keeps model names when the settings request fails', async () => {
    respondWith({ loras, settingsOk: false });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('Example title');
  });

  it('falls back to the stored name once the cache is invalidated', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('Example title');

    handleLibraryChangeMessage({ type: 'models_changed' });
    expect(getLoraDisplayName('abc123def')).toBe('abc123def');
  });
});
