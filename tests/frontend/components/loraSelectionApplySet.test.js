import { describe, expect, it, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
    ui: { settings: { settingsById: {} } },
  },
}));

vi.mock(API_MODULE, () => ({
  api: { fetchApi: vi.fn(), addEventListener: vi.fn() },
}));

import { applyLoraSet } from '../../../web/comfyui/lora_selection.js';

const listed = (name, { active = true, strength = '0.80' } = {}) => ({
  name,
  strength,
  clipStrength: strength,
  active,
  expanded: false,
  selected: false,
  locked: false,
});

describe('applyLoraSet (recipe apply)', () => {
  it('appends available recipe LoRAs with their strengths and counts skipped ones', () => {
    const current = [listed('styles/keep', { strength: '0.90' })];
    const result = applyLoraSet(current, [
      { file_name: 'characters/astral.safetensors', strength: 0.7, inLibrary: true },
      { file_name: 'characters/missing.safetensors', strength: 0.5, inLibrary: false },
      { file_name: 'characters/deleted.safetensors', strength: 0.5, isDeleted: true },
      { file_name: 'characters/excluded.safetensors', strength: 0.5, exclude: true },
    ]);

    expect(result.changed).toBe(true);
    expect(result.applied).toBe(1);
    expect(result.skipped).toBe(3);
    expect(result.loras).toHaveLength(2);
    expect(result.loras[0]).toMatchObject({ name: 'styles/keep', strength: '0.90' });
    expect(result.loras[1]).toMatchObject({
      name: 'characters/astral',
      strength: '0.70',
      active: true,
    });
  });

  it('enables a listed LoRA in place and keeps its current strength on append', () => {
    const current = [listed('characters/astral', { active: false, strength: '0.40' })];
    const result = applyLoraSet(current, [
      { file_name: 'characters/astral.safetensors', strength: 0.9, inLibrary: true },
    ]);

    expect(result.changed).toBe(true);
    expect(result.applied).toBe(1);
    expect(result.loras).toHaveLength(1);
    expect(result.loras[0]).toMatchObject({ strength: '0.40', active: true });
  });

  it('reports no change when every recipe LoRA is already active', () => {
    const current = [listed('characters/astral')];
    const result = applyLoraSet(current, [
      { file_name: 'characters/astral.safetensors', strength: 0.3, inLibrary: true },
    ]);

    expect(result.changed).toBe(false);
    expect(result.applied).toBe(1);
    expect(result.skipped).toBe(0);
    expect(result.loras).toBe(current);
  });

  it('replaces the list with the available recipe entries and recipe strengths', () => {
    const current = [
      listed('old/one', { strength: '0.10' }),
      listed('old/two', { strength: '0.20' }),
    ];
    const result = applyLoraSet(current, [
      { file_name: 'characters/astral.safetensors', strength: 0.7, inLibrary: true },
      { file_name: 'styles/film.safetensors', strength: 0.35, inLibrary: true },
      { file_name: 'missing/gone.safetensors', strength: 0.5, inLibrary: false },
    ], { mode: 'replace' });

    expect(result.changed).toBe(true);
    expect(result.applied).toBe(2);
    expect(result.skipped).toBe(1);
    expect(result.loras.map((entry) => [entry.name, entry.strength, entry.active])).toEqual([
      ['characters/astral', '0.70', true],
      ['styles/film', '0.35', true],
    ]);
  });

  it('keeps the current list when no recipe entry is available', () => {
    const current = [listed('styles/keep')];
    const result = applyLoraSet(current, [
      { file_name: 'missing/one.safetensors', inLibrary: false },
      { file_name: 'missing/two.safetensors', isDeleted: true },
      { strength: 0.5, inLibrary: true },
    ], { mode: 'replace' });

    expect(result.changed).toBe(false);
    expect(result.applied).toBe(0);
    expect(result.skipped).toBe(3);
    expect(result.loras).toBe(current);
  });

  it('deduplicates repeated recipe names in replace mode', () => {
    const result = applyLoraSet([], [
      { file_name: 'characters/astral.safetensors', strength: 0.7, inLibrary: true },
      { file_name: 'characters/astral.safetensors', strength: 0.9, inLibrary: true },
    ], { mode: 'replace' });

    expect(result.applied).toBe(1);
    expect(result.loras).toHaveLength(1);
    expect(result.loras[0]).toMatchObject({ name: 'characters/astral', strength: '0.70' });
  });
});


describe('applyLoraSet block weights', () => {
  it('keeps recipes limited to LoRA names and strengths', () => {
    const lbw = { enabled: true, weights: { IN04: 0.25 } };
    const result = applyLoraSet([
      { name: 'characters/astral', strength: '0.70', clipStrength: '0.70', active: true, lbw },
    ], [
      { file_name: 'characters/astral.safetensors', strength: 0.7, inLibrary: true, lbw },
    ], { mode: 'replace' });

    expect(result.loras[0]).not.toHaveProperty('lbw');
    expect(result.changed).toBe(true);
  });
});
