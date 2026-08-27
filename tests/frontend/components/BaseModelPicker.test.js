import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key)),
}));

import {
  createBaseModelPicker,
  inferBaseModelsFromFilename,
  inferBaseModelsFromFilepaths,
} from '../../../static/js/components/shared/BaseModelPicker.js';
import {
  setDynamicBaseModels,
  clearDynamicBaseModels,
  BASE_MODELS_UPDATED_EVENT,
} from '../../../static/js/utils/constants.js';

// jsdom does not implement scrollIntoView
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn();

const flushDebounce = () => new Promise((resolve) => setTimeout(resolve, 70));

function mountPicker(options = {}) {
  const picker = createBaseModelPicker(options);
  document.body.appendChild(picker.element);
  return picker;
}

function getInput(picker) {
  return picker.element.querySelector('.base-model-search-input');
}

function getDropdown(picker) {
  return picker.element.querySelector('.base-model-dropdown');
}

function getItemValues(picker) {
  return Array.from(picker.element.querySelectorAll('.base-model-dropdown-item'))
    .map((el) => el.dataset.value);
}

describe('inferBaseModelsFromFilepaths', () => {
  it('returns an empty array for empty or invalid input', () => {
    expect(inferBaseModelsFromFilepaths([])).toEqual([]);
    expect(inferBaseModelsFromFilepaths(null)).toEqual([]);
    expect(inferBaseModelsFromFilepaths(['/models/zzz_unknown.safetensors'])).toEqual([]);
  });

  it('deduplicates and sorts by hit count across selected paths', () => {
    const result = inferBaseModelsFromFilepaths([
      '/loras/flux1_dev_alpha.safetensors',
      '/loras/another_flux_model.safetensors',
      'C:\\models\\sdxl_style.safetensors',
    ]);

    // Flux.1 D matched two paths, so it ranks first; entries are deduplicated
    expect(result[0]).toBe('Flux.1 D');
    expect(new Set(result).size).toBe(result.length);
    expect(result).toContain('SDXL 1.0');
  });

  it('infers base models from a single filename', () => {
    expect(inferBaseModelsFromFilename('my_pony_lora.safetensors')).toContain('Pony');
    expect(inferBaseModelsFromFilename('')).toEqual([]);
  });
});

describe('createBaseModelPicker', () => {
  beforeEach(() => {
    clearDynamicBaseModels();
  });

  afterEach(() => {
    clearDynamicBaseModels();
  });

  it('groups uncategorized dynamic models under "Other (API)"', () => {
    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    const picker = mountPicker();

    const headers = Array.from(picker.element.querySelectorAll('.base-model-dropdown-header'));
    const otherHeader = headers.find((el) => el.textContent === 'Other (API)');
    expect(otherHeader).toBeTruthy();

    const section = otherHeader.closest('.base-model-dropdown-section');
    const values = Array.from(section.querySelectorAll('.base-model-dropdown-item'))
      .map((el) => el.dataset.value);
    expect(values).toContain('MiniMax H3');

    picker.destroy();
  });

  it('filters options case-insensitively after the debounce', async () => {
    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    const picker = mountPicker();

    const input = getInput(picker);
    input.value = 'MINIMAX';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushDebounce();

    expect(getItemValues(picker)).toEqual(['MiniMax H3']);

    picker.destroy();
  });

  it('shows the empty state when nothing matches', async () => {
    const picker = mountPicker();

    const input = getInput(picker);
    input.value = 'no-such-model-xyz';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushDebounce();

    expect(getItemValues(picker)).toEqual([]);
    expect(getDropdown(picker).querySelector('.base-model-dropdown-empty')).toBeTruthy();

    picker.destroy();
  });

  it('commits immediately on item click in commit mode', () => {
    const onCommit = vi.fn();
    const picker = mountPicker({ onCommit });

    const item = Array.from(picker.element.querySelectorAll('.base-model-dropdown-item'))
      .find((el) => el.dataset.value === 'SDXL 1.0');
    item.click();

    expect(onCommit).toHaveBeenCalledWith('SDXL 1.0');

    picker.destroy();
  });

  it('supports keyboard navigation and Enter to commit the active item', () => {
    const onCommit = vi.fn();
    const picker = mountPicker({ onCommit });
    const input = getInput(picker);

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));

    const active = picker.element.querySelector('.base-model-dropdown-item.active');
    expect(active).toBeTruthy();

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(onCommit).toHaveBeenCalledWith(active.dataset.value);

    picker.destroy();
  });

  it('commits a custom typed value on Enter', () => {
    const onCommit = vi.fn();
    const picker = mountPicker({ onCommit });
    const input = getInput(picker);

    input.value = 'My Custom Model';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(onCommit).toHaveBeenCalledWith('My Custom Model');
    expect(picker.getValue()).toBe('My Custom Model');

    picker.destroy();
  });

  it('keeps typed text search-only on Enter when allowCustomValue is false', () => {
    const onCommit = vi.fn();
    const picker = mountPicker({ onCommit, allowCustomValue: false });
    const input = getInput(picker);

    input.value = 'My Custom Model';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(onCommit).not.toHaveBeenCalled();
    expect(picker.getValue()).toBe('');

    picker.destroy();
  });

  it('commits the typed custom value on outside click', async () => {
    const onCommit = vi.fn();
    const onDismiss = vi.fn();
    const picker = mountPicker({ onCommit, onDismiss, initialValue: 'SD 1.5' });
    const input = getInput(picker);

    input.value = 'My Custom Model';
    await new Promise((resolve) => setTimeout(resolve, 0));
    document.body.click();

    expect(onCommit).toHaveBeenCalledWith('My Custom Model');
    expect(onDismiss).not.toHaveBeenCalled();
    expect(picker.getValue()).toBe('My Custom Model');

    picker.destroy();
  });

  it('dismisses without committing typed search text on outside click when allowCustomValue is false', async () => {
    const onCommit = vi.fn();
    const onDismiss = vi.fn();
    const picker = mountPicker({ onCommit, onDismiss, initialValue: 'SD 1.5', allowCustomValue: false });
    const input = getInput(picker);

    input.value = 'My Custom Model';
    await new Promise((resolve) => setTimeout(resolve, 0));
    document.body.click();

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onCommit).not.toHaveBeenCalled();
    expect(picker.getValue()).toBe('SD 1.5');

    picker.destroy();
  });

  it('dismisses without committing on Escape', () => {
    const onCommit = vi.fn();
    const onDismiss = vi.fn();
    const picker = mountPicker({ onCommit, onDismiss, initialValue: 'SD 1.5' });
    const input = getInput(picker);

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(onCommit).not.toHaveBeenCalled();

    picker.destroy();
  });

  it('refreshes options when dynamic models arrive late and keeps the search text', async () => {
    const picker = mountPicker();
    const input = getInput(picker);

    input.value = 'minimax';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushDebounce();
    expect(getItemValues(picker)).toEqual([]);

    // Dynamic models arrive after the picker is already open
    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    window.dispatchEvent(new CustomEvent(BASE_MODELS_UPDATED_EVENT));

    expect(input.value).toBe('minimax');
    expect(getItemValues(picker)).toEqual(['MiniMax H3']);

    picker.destroy();
  });

  it('stops reacting to updates after destroy', () => {
    const picker = mountPicker();
    picker.destroy();

    setDynamicBaseModels(['MiniMax H3'], new Date().toISOString());
    window.dispatchEvent(new CustomEvent(BASE_MODELS_UPDATED_EVENT));

    expect(getItemValues(picker)).not.toContain('MiniMax H3');
  });

  it('renders filename-based suggestions in a Suggested section', () => {
    const suggestions = inferBaseModelsFromFilename('flux1_dev_model.safetensors');
    const picker = mountPicker({ suggestions });

    const suggestedHeader = picker.element.querySelector('.base-model-dropdown-header.suggested-header');
    expect(suggestedHeader).toBeTruthy();

    const section = suggestedHeader.closest('.base-model-dropdown-section');
    const values = Array.from(section.querySelectorAll('.base-model-dropdown-item'))
      .map((el) => el.dataset.value);
    expect(values).toContain('Flux.1 D');

    // Suggested entries are deduplicated out of the categorized sections
    expect(getItemValues(picker).filter((v) => v === 'Flux.1 D')).toHaveLength(1);

    picker.destroy();
  });

  it('change mode only notifies via onChange and tracks the value', () => {
    const onCommit = vi.fn();
    const onChange = vi.fn();
    const picker = mountPicker({ mode: 'change', onCommit, onChange });

    const item = Array.from(picker.element.querySelectorAll('.base-model-dropdown-item'))
      .find((el) => el.dataset.value === 'SDXL 1.0');
    item.click();

    expect(onCommit).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledWith('SDXL 1.0');
    expect(picker.getValue()).toBe('SDXL 1.0');

    // The list collapses to the selected item instead of resetting to the
    // full list (avoids a scroll jump in the bulk modal's inline list)
    expect(getItemValues(picker)).toEqual(['SDXL 1.0']);

    picker.destroy();
  });

  it('treats typed text as the live value in change mode', async () => {
    const onChange = vi.fn();
    const picker = mountPicker({ mode: 'change', onChange });
    const input = getInput(picker);

    input.value = 'Typed Custom';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushDebounce();

    expect(onChange).toHaveBeenCalledWith('Typed Custom');
    expect(picker.getValue()).toBe('Typed Custom');

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(picker.getValue()).toBe('Typed Custom');
    // Custom values are not in the option list — the full list stays visible
    expect(getItemValues(picker).length).toBeGreaterThan(1);

    picker.destroy();
  });

  it('keeps typed text as search-only in change mode when allowCustomValue is false', async () => {
    const onChange = vi.fn();
    const picker = mountPicker({ mode: 'change', onChange, allowCustomValue: false });
    const input = getInput(picker);

    input.value = 'Typed Custom';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await flushDebounce();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(onChange).not.toHaveBeenCalled();
    expect(picker.getValue()).toBe('');
    expect(getDropdown(picker).querySelector('.base-model-dropdown-empty')).toBeTruthy();

    picker.destroy();
  });

  it('setValue updates the input and selected marker', () => {
    const picker = mountPicker({ mode: 'change' });

    picker.setValue('SD 3.5');

    expect(picker.getValue()).toBe('SD 3.5');
    const selected = picker.element.querySelector('.base-model-dropdown-item.selected');
    expect(selected?.dataset.value).toBe('SD 3.5');

    picker.destroy();
  });
});
