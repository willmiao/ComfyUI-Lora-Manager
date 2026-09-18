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
  parseStrengthRange,
  describeStrengthRangeViolation,
  applyStrengthRangeCue,
  buildStrengthRangeMap,
  getLoraStrengthRange,
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

describe('parseStrengthRange', () => {
  it('parses explicit strength_min/strength_max keys', () => {
    expect(parseStrengthRange('{"strength_min": 0.4, "strength_max": 0.8}')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: null,
    });
  });

  it('parses the strength_range shorthand', () => {
    expect(parseStrengthRange('{"strength_range": "0.4-0.8"}')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: null,
    });
  });

  it('accepts camelCase variants', () => {
    expect(parseStrengthRange('{"strengthMin": 0.2, "strengthMax": 1.5}')).toEqual({
      min: 0.2,
      max: 1.5,
      recommended: null,
    });
  });

  it('prefers explicit min/max over the range string per side', () => {
    expect(
      parseStrengthRange('{"strength_min": 0.1, "strength_range": "0.4-0.8"}')
    ).toEqual({ min: 0.1, max: 0.8, recommended: null });
  });

  it('supports open-ended ranges', () => {
    expect(parseStrengthRange('{"strength_max": 1.0}')).toEqual({
      min: null,
      max: 1.0,
      recommended: null,
    });
  });

  it('captures the recommended strength when present', () => {
    expect(
      parseStrengthRange('{"strength": 0.6, "strength_min": 0.4, "strength_max": 0.8}')
    ).toEqual({ min: 0.4, max: 0.8, recommended: 0.6 });
  });

  it('accepts numeric strings for bounds', () => {
    expect(parseStrengthRange('{"strength_min": "0.4", "strength_max": "0.8"}')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: null,
    });
  });

  it('parses negative bounds in range strings', () => {
    expect(parseStrengthRange('{"strength_range": "-0.5-0.8"}')).toEqual({
      min: -0.5,
      max: 0.8,
      recommended: null,
    });
  });

  it('returns null when no range is configured', () => {
    expect(parseStrengthRange('{"strength": 0.6}')).toBeNull();
    expect(parseStrengthRange('{}')).toBeNull();
    expect(parseStrengthRange('')).toBeNull();
    expect(parseStrengthRange(null)).toBeNull();
    expect(parseStrengthRange(undefined)).toBeNull();
  });

  it('returns null for malformed JSON', () => {
    expect(parseStrengthRange('{invalid')).toBeNull();
  });

  it('returns null for inverted ranges', () => {
    expect(parseStrengthRange('{"strength_min": 0.9, "strength_max": 0.2}')).toBeNull();
  });

  it('accepts already-parsed objects', () => {
    expect(parseStrengthRange({ strength_min: 0.3 })).toEqual({
      min: 0.3,
      max: null,
      recommended: null,
    });
  });
});

describe('describeStrengthRangeViolation', () => {
  const range = { min: 0.4, max: 0.8, recommended: 0.6 };

  it('returns null when the value is inside the range', () => {
    expect(describeStrengthRangeViolation(0.6, range)).toBeNull();
    expect(describeStrengthRangeViolation(0.4, range)).toBeNull();
    expect(describeStrengthRangeViolation(0.8, range)).toBeNull();
  });

  it('describes values below the range', () => {
    expect(describeStrengthRangeViolation(0.2, range)).toBe(
      'Below recommended strength range (0.40\u20130.80); recommended: 0.60'
    );
  });

  it('describes values above the range', () => {
    expect(describeStrengthRangeViolation('1.0', range)).toBe(
      'Above recommended strength range (0.40\u20130.80); recommended: 0.60'
    );
  });

  it('omits the recommended part when not configured', () => {
    expect(describeStrengthRangeViolation(0.1, { min: 0.4, max: null, recommended: null })).toBe(
      'Below recommended strength range (\u2265 0.40)'
    );
    expect(describeStrengthRangeViolation(1.5, { min: null, max: 1.0, recommended: null })).toBe(
      'Above recommended strength range (\u2264 1.00)'
    );
  });

  it('returns null without a range or with a non-numeric value', () => {
    expect(describeStrengthRangeViolation(0.1, null)).toBeNull();
    expect(describeStrengthRangeViolation('abc', range)).toBeNull();
  });
});

describe('applyStrengthRangeCue', () => {
  const range = { min: 0.4, max: 0.8, recommended: 0.6 };

  it('adds the cue class and tooltip for out-of-range values', () => {
    const input = document.createElement('input');
    applyStrengthRangeCue(input, 1.5, range);
    expect(input.classList.contains('lm-strength-out-of-range')).toBe(true);
    expect(input.title).toContain('Above recommended strength range');
  });

  it('clears the cue for in-range values', () => {
    const input = document.createElement('input');
    applyStrengthRangeCue(input, 1.5, range);
    applyStrengthRangeCue(input, 0.6, range);
    expect(input.classList.contains('lm-strength-out-of-range')).toBe(false);
    expect(input.hasAttribute('title')).toBe(false);
  });

  it('clears the cue when no range is configured', () => {
    const input = document.createElement('input');
    input.classList.add('lm-strength-out-of-range');
    input.title = 'stale';
    applyStrengthRangeCue(input, 99, null);
    expect(input.classList.contains('lm-strength-out-of-range')).toBe(false);
    expect(input.hasAttribute('title')).toBe(false);
  });
});

describe('buildStrengthRangeMap', () => {
  it('keys ranges by normalized path and basename', () => {
    const map = buildStrengthRangeMap([
      { file_name: 'sub/a', usage_tips: '{"strength_min": 0.4, "strength_max": 0.8}' },
    ]);
    expect(map.get('sub/a')).toEqual({ min: 0.4, max: 0.8, recommended: null });
    expect(map.get('a')).toEqual({ min: 0.4, max: 0.8, recommended: null });
  });

  it('strips extensions from keys', () => {
    const map = buildStrengthRangeMap([
      { file_name: 'sub/a.safetensors', usage_tips: '{"strength_max": 1.0}' },
    ]);
    expect(map.get('sub/a')).toBeTruthy();
  });

  it('skips entries without a valid range', () => {
    const map = buildStrengthRangeMap([
      { file_name: 'a', usage_tips: '' },
      { file_name: 'b' },
      { file_name: 'c', usage_tips: '{"strength": 0.6}' },
      null,
    ]);
    expect(map.size).toBe(0);
  });
});

describe('getLoraStrengthRange', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    resetAvailableLorasCache();
  });

  it('returns null while the cache is not loaded', () => {
    expect(getLoraStrengthRange('a')).toBeNull();
  });

  it('resolves ranges from the cached cycler list', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [
          {
            file_name: 'sub/a.safetensors',
            usage_tips: '{"strength": 0.6, "strength_min": 0.4, "strength_max": 0.8}',
          },
          { file_name: 'b.safetensors' },
        ],
      }),
    });

    await getAvailableLoras();
    expect(getLoraStrengthRange('sub/a.safetensors')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: 0.6,
    });
    // Extension-free and basename forms resolve to the same entry.
    expect(getLoraStrengthRange('sub/a')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: 0.6,
    });
    expect(getLoraStrengthRange('a')).toEqual({
      min: 0.4,
      max: 0.8,
      recommended: 0.6,
    });
  });

  it('falls back to the basename for folder-qualified names', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [
          { file_name: 'sub/a.safetensors', usage_tips: '{"strength_max": 1.0}' },
        ],
      }),
    });

    await getAvailableLoras();
    expect(getLoraStrengthRange('any/folder/a.safetensors')).toEqual({
      min: null,
      max: 1.0,
      recommended: null,
    });
  });

  it('returns null for loras without a configured range', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [{ file_name: 'b.safetensors' }],
      }),
    });

    await getAvailableLoras();
    expect(getLoraStrengthRange('b')).toBeNull();
    expect(getLoraStrengthRange('missing')).toBeNull();
  });

  it('returns null for absolute paths', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        loras: [
          { file_name: 'a.safetensors', usage_tips: '{"strength_max": 1.0}' },
        ],
      }),
    });

    await getAvailableLoras();
    expect(getLoraStrengthRange('/abs/path/a.safetensors')).toBeNull();
    expect(getLoraStrengthRange('C:/abs/path/a.safetensors')).toBeNull();
  });
});
