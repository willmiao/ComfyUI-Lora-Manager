import { describe, expect, it } from 'vitest';

import {
  buildAddedLoraStateMap,
  createAddedLoraCue,
  resolveAddedLoraState,
} from '../../../web/comfyui/lora_added_state.js';

describe('LoRA added-state cues', () => {
  it('maps normalized names to their enabled state', () => {
    const states = buildAddedLoraStateMap([
      { name: 'characters\\astral.safetensors', active: true },
      { name: 'styles/dormant.pt', active: false },
      { name: 'legacy' },
      { name: '' },
    ]);

    expect(states.get('characters/astral')).toBe(true);
    expect(states.get('styles/dormant')).toBe(false);
    expect(states.get('legacy')).toBe(true);
    expect(states.size).toBe(3);
  });

  it('resolves active, inactive, and missing entries', () => {
    const states = buildAddedLoraStateMap([
      { name: 'characters/astral.safetensors', active: true },
      { name: 'characters/dormant', active: false },
    ]);

    expect(resolveAddedLoraState(states, 'characters/astral.safetensors')).toBe('active');
    expect(resolveAddedLoraState(states, 'characters/dormant.safetensors')).toBe('inactive');
    expect(resolveAddedLoraState(states, 'characters/unknown.safetensors')).toBeNull();
    expect(resolveAddedLoraState(null, 'characters/astral')).toBeNull();
    expect(resolveAddedLoraState(new Map(), 'characters/astral')).toBeNull();
  });

  it('accepts legacy bare-name entries', () => {
    const states = buildAddedLoraStateMap([{ name: 'astral' }]);

    expect(resolveAddedLoraState(states, 'characters/astral.safetensors')).toBe('active');
  });

  it('does not match a different folder with the same file name', () => {
    const states = buildAddedLoraStateMap([{ name: 'styles/astral' }]);

    expect(resolveAddedLoraState(states, 'characters/astral.safetensors')).toBeNull();
  });

  it('builds the shared badge markup for each state', () => {
    const active = createAddedLoraCue('active');
    expect(active.className).toBe('lm-lora-added is-active');
    expect(active.textContent).toBe('✓Added');
    expect(active.title).toBe('Added to this node');
    expect(active.getAttribute('aria-label')).toBe('Added to this node');

    const inactive = createAddedLoraCue('inactive');
    expect(inactive.className).toBe('lm-lora-added is-inactive');
    expect(inactive.textContent).toBe('○Off');
    expect(inactive.title).toBe('Added but turned off — select to enable');
  });
});
