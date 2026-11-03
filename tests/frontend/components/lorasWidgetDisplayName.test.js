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
  getLoraDisplayName,
  getAvailableLoras,
  resetAvailableLorasCache,
  handleLibraryChangeMessage,
} from '../../../web/comfyui/loras_widget_utils.js';

// The availability refresh is the only request left: the node label preference
// lives in ComfyUI's settings, so the cycler list must not be paired with a
// /lm/settings fetch. Throwing on any other URL proves that.
const respondWith = ({ loras = [] } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

describe('buildModelNameMap', () => {
  it('keys titles by normalized path and basename', () => {
    const map = buildModelNameMap([
      { file_name: 'set/abc123def', model_name: 'Example model title' },
    ]);
    expect(map.get('set/abc123def')).toBe('Example model title');
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

describe('getLoraDisplayName', () => {
  const loras = [
    { file_name: 'set/abc123def', model_name: 'Example model title' },
    { file_name: 'sub/plain.safetensors' },
  ];

  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('returns the stored name while the cache is not loaded', () => {
    expect(getLoraDisplayName('abc123def', 'model_name')).toBe('abc123def');
  });

  it('returns the model name when the node preference asks for model names', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def', 'model_name')).toBe('Example model title');
  });

  it('returns the stored name when the node preference asks for file names', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def', 'file_name')).toBe('abc123def');
  });

  it('defaults to the stored name when no preference is passed', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def')).toBe('abc123def');
  });

  it('resolves folder-qualified and extension-carrying entry names', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('set/abc123def', 'model_name')).toBe('Example model title');
    expect(getLoraDisplayName('set/abc123def.safetensors', 'model_name')).toBe(
      'Example model title'
    );
    expect(getLoraDisplayName('sub/plain', 'model_name')).toBe('sub/plain');
  });

  it('falls back to the stored name for unknown and absolute paths', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('unknown', 'model_name')).toBe('unknown');
    expect(getLoraDisplayName('/abs/path/abc123def', 'model_name')).toBe('/abs/path/abc123def');
    expect(getLoraDisplayName('C:/abs/abc123def', 'model_name')).toBe('C:/abs/abc123def');
  });

  it('fetches the cycler list only, never the LoRA Manager settings', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(fetchApiMock.mock.calls.map(([url]) => url)).toEqual(['/lm/loras/cycler-list']);
  });

  it('keeps cached labels after the availability cache TTL expires', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def', 'model_name')).toBe('Example model title');

    vi.useFakeTimers();
    try {
      vi.setSystemTime(Date.now() + 61_000);
      // Labels are display-only, so a stale map beats flashing file names
      // while the availability refresh is in flight.
      expect(getLoraDisplayName('abc123def', 'model_name')).toBe('Example model title');
    } finally {
      vi.useRealTimers();
    }
  });

  it('falls back to the stored name once the cache is invalidated', async () => {
    respondWith({ loras });
    await getAvailableLoras();
    expect(getLoraDisplayName('abc123def', 'model_name')).toBe('Example model title');

    handleLibraryChangeMessage({ type: 'models_changed' });
    expect(getLoraDisplayName('abc123def', 'model_name')).toBe('abc123def');
  });
});

describe('buildModelNameMap duplicate titles', () => {
  const title = 'Example model title';

  it('leaves a unique title alone', () => {
    const map = buildModelNameMap([
      { file_name: 'set/only', model_name: 'Example sole title', version_name: 'Example_v1', folder: 'set' },
    ]);
    expect(map.get('set/only')).toBe('Example sole title');
    expect(map.get('only')).toBe('Example sole title');
  });

  it('puts the trimmed version suffix first so a narrow row cannot clip it', () => {
    const map = buildModelNameMap([
      { file_name: 'set/abc_v1', model_name: title, version_name: 'Example_v1', folder: 'set' },
      {
        file_name: 'set/abc_v2',
        model_name: title,
        version_name: 'Example_v2 (variant)',
        folder: 'set',
      },
    ]);
    expect(map.get('set/abc_v1')).toBe(`[v1] ${title}`);
    expect(map.get('set/abc_v2')).toBe(`[v2 (variant)] ${title}`);
    // basename alias carries the same label
    expect(map.get('abc_v2')).toBe(`[v2 (variant)] ${title}`);
  });

  it('trims a shared tail as well as a shared head', () => {
    const map = buildModelNameMap([
      {
        file_name: 'wan/high',
        model_name: title,
        version_name: '2.2 HIGH r12 (nightly)',
        folder: 'wan',
      },
      {
        file_name: 'wan/low',
        model_name: title,
        version_name: '2.2 LOW r12 (nightly)',
        folder: 'wan',
      },
    ]);
    expect(map.get('wan/high')).toBe(`[HIGH] ${title}`);
    expect(map.get('wan/low')).toBe(`[LOW] ${title}`);
  });

  it('keeps the whole version name when trimming would empty one of them', () => {
    const map = buildModelNameMap([
      { file_name: 'set/oops', model_name: 'Oops', version_name: 'Example', folder: 'set' },
      { file_name: 'set/oops2', model_name: 'Oops', version_name: 'Example Stripped', folder: 'set' },
    ]);
    expect(map.get('set/oops')).toBe('[Example] Oops');
    expect(map.get('set/oops2')).toBe('[Example Stripped] Oops');
  });

  it('falls back to the folder when the version names are identical', () => {
    const map = buildModelNameMap([
      { file_name: 'set/a', model_name: 'Shared title', version_name: 'v3.0 - release', folder: 'set' },
      {
        file_name: 'archive/bulk/b',
        model_name: 'Shared title',
        version_name: 'v3.0 - release',
        folder: 'archive/bulk',
      },
    ]);
    expect(map.get('set/a')).toBe('[set] Shared title');
    expect(map.get('archive/bulk/b')).toBe('[archive/bulk] Shared title');
  });

  it('falls back to the file name when version names and folders both collide', () => {
    const map = buildModelNameMap([
      { file_name: 'set/altname v3', model_name: 'Shared title', version_name: 'v3.0 - release', folder: 'set' },
      { file_name: 'set/abc_v3', model_name: 'Shared title', version_name: 'v3.0 - release', folder: 'set' },
    ]);
    expect(map.get('set/altname v3')).toBe('[altname v3] Shared title');
    expect(map.get('set/abc_v3')).toBe('[abc_v3] Shared title');
  });

  it('ignores a missing version name and still disambiguates', () => {
    const map = buildModelNameMap([
      { file_name: 'set/x', model_name: 'No Metadata', folder: 'set' },
      { file_name: 'archive/y', model_name: 'No Metadata', folder: 'archive' },
    ]);
    expect(map.get('set/x')).toBe('[set] No Metadata');
    expect(map.get('archive/y')).toBe('[archive] No Metadata');
  });

  it('caps a long suffix when the difference survives the cut', () => {
    const pad = 'x'.repeat(40);
    const map = buildModelNameMap([
      { file_name: 'k/a', model_name: 'T', version_name: `A${pad}`, folder: 'k' },
      { file_name: 'k/b', model_name: 'T', version_name: `B${pad}`, folder: 'k' },
    ]);
    const label = map.get('k/a');
    const suffix = label.slice(label.indexOf('[') + 1, label.indexOf(']'));
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
    expect(map.get('k/first')).toBe('[first] T');
    expect(map.get('k/second')).toBe('[second] T');
  });
});
