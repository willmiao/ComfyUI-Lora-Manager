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
  parseNodeNameDisplayMode,
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

describe('parseNodeNameDisplayMode', () => {
  it('reads the file_name preference', () => {
    expect(parseNodeNameDisplayMode({ settings: { node_lora_name_display: 'file_name' } })).toBe(
      'file_name'
    );
  });

  it('reads the model_name preference', () => {
    expect(parseNodeNameDisplayMode({ settings: { node_lora_name_display: 'model_name' } })).toBe(
      'model_name'
    );
  });

  it('defaults to model_name for missing or unknown values', () => {
    expect(parseNodeNameDisplayMode({ settings: {} })).toBe('model_name');
    expect(parseNodeNameDisplayMode({ settings: { node_lora_name_display: 'nonsense' } })).toBe(
      'model_name'
    );
    expect(parseNodeNameDisplayMode(undefined)).toBe('model_name');
    expect(parseNodeNameDisplayMode({})).toBe('model_name');
  });

  it('ignores the model card preference', () => {
    // The cards' own setting must not leak into node rows: they answer
    // different questions (what you browse vs what a graph will load).
    expect(
      parseNodeNameDisplayMode({ settings: { model_name_display: 'file_name' } })
    ).toBe('model_name');
    expect(
      parseNodeNameDisplayMode({
        settings: { model_name_display: 'model_name', node_lora_name_display: 'file_name' },
      })
    ).toBe('file_name');
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
    respondWith({ loras, settings: { node_lora_name_display: 'model_name' } });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('Example title');
  });

  it('returns the stored name when the preference is the file name', async () => {
    respondWith({ loras, settings: { node_lora_name_display: 'file_name' } });
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

describe('buildModelNameMap duplicate titles', () => {
  const title = 'Ass and Thighs Slider - (Krea-2 + ZIT)';

  it('leaves a unique title alone', () => {
    const map = buildModelNameMap([
      { file_name: 'krea2/only', model_name: 'Only One', version_name: 'Krea-2_v1', folder: 'krea2' },
    ]);
    expect(map.get('krea2/only')).toBe('Only One');
    expect(map.get('only')).toBe('Only One');
  });

  it('trims the version prefix every member shares', () => {
    const map = buildModelNameMap([
      { file_name: 'krea2/ass_v1', model_name: title, version_name: 'Krea-2_v1', folder: 'krea2' },
      {
        file_name: 'krea2/ass_v2',
        model_name: title,
        version_name: 'Krea-2_v2 (ass only)',
        folder: 'krea2',
      },
    ]);
    expect(map.get('krea2/ass_v1')).toBe(`${title} (v1)`);
    expect(map.get('krea2/ass_v2')).toBe(`${title} (v2 (ass only))`);
    // basename alias carries the same label
    expect(map.get('ass_v2')).toBe(`${title} (v2 (ass only))`);
  });

  it('trims a shared tail as well as a shared head', () => {
    const map = buildModelNameMap([
      {
        file_name: 'wan/high',
        model_name: 'WAN General NSFW model',
        version_name: '2.2 HIGH v0.08a (nightly)',
        folder: 'wan',
      },
      {
        file_name: 'wan/low',
        model_name: 'WAN General NSFW model',
        version_name: '2.2 LOW v0.08a (nightly)',
        folder: 'wan',
      },
    ]);
    expect(map.get('wan/high')).toBe('WAN General NSFW model (HIGH)');
    expect(map.get('wan/low')).toBe('WAN General NSFW model (LOW)');
  });

  it('keeps the whole version name when trimming would empty one of them', () => {
    const map = buildModelNameMap([
      { file_name: 'krea2/oops', model_name: 'Oops', version_name: 'Krea 2', folder: 'krea2' },
      { file_name: 'krea2/oops2', model_name: 'Oops', version_name: 'Krea 2 Stripped', folder: 'krea2' },
    ]);
    expect(map.get('krea2/oops')).toBe('Oops (Krea 2)');
    expect(map.get('krea2/oops2')).toBe('Oops (Krea 2 Stripped)');
  });

  it('falls back to the folder when the version names are identical', () => {
    const map = buildModelNameMap([
      { file_name: 'FLUX/a', model_name: 'Areola Flux', version_name: 'v3.0 - Saggys Pancakes', folder: 'FLUX' },
      {
        file_name: 'FLUX2/bulk/b',
        model_name: 'Areola Flux',
        version_name: 'v3.0 - Saggys Pancakes',
        folder: 'FLUX2/bulk',
      },
    ]);
    expect(map.get('FLUX/a')).toBe('Areola Flux (FLUX)');
    expect(map.get('FLUX2/bulk/b')).toBe('Areola Flux (FLUX2/bulk)');
  });

  it('falls back to the file name when version names and folders both collide', () => {
    const map = buildModelNameMap([
      { file_name: 'FLUX/pancakes v3', model_name: 'Areola Flux', version_name: 'v3.0 - Saggys', folder: 'FLUX' },
      { file_name: 'FLUX/areola_v3', model_name: 'Areola Flux', version_name: 'v3.0 - Saggys', folder: 'FLUX' },
    ]);
    expect(map.get('FLUX/pancakes v3')).toBe('Areola Flux (pancakes v3)');
    expect(map.get('FLUX/areola_v3')).toBe('Areola Flux (areola_v3)');
  });

  it('ignores a missing version name and still disambiguates', () => {
    const map = buildModelNameMap([
      { file_name: 'krea2/x', model_name: 'No Metadata', folder: 'krea2' },
      { file_name: 'FLUX/y', model_name: 'No Metadata', folder: 'FLUX' },
    ]);
    expect(map.get('krea2/x')).toBe('No Metadata (krea2)');
    expect(map.get('FLUX/y')).toBe('No Metadata (FLUX)');
  });

  it('caps a long suffix when the difference survives the cut', () => {
    const pad = 'x'.repeat(40);
    const map = buildModelNameMap([
      { file_name: 'k/a', model_name: 'T', version_name: `A${pad}`, folder: 'k' },
      { file_name: 'k/b', model_name: 'T', version_name: `B${pad}`, folder: 'k' },
    ]);
    const label = map.get('k/a');
    const suffix = label.slice(label.indexOf('(') + 1, label.lastIndexOf(')'));
    expect(suffix.startsWith('A')).toBe(true);
    expect(suffix.endsWith('\u2026')).toBe(true);
    expect(suffix.length).toBe(32);
  });

  it('falls back to the file name when truncating would make labels identical', () => {
    // The only differing character sits past the cap, so a truncated suffix
    // would give two identical rows: prefer the file name instead.
    const pad = 'x'.repeat(40);
    const map = buildModelNameMap([
      { file_name: 'k/first', model_name: 'T', version_name: `${pad}A`, folder: 'k' },
      { file_name: 'k/second', model_name: 'T', version_name: `${pad}B`, folder: 'k' },
    ]);
    expect(map.get('k/first')).toBe('T (first)');
    expect(map.get('k/second')).toBe('T (second)');
  });
});
