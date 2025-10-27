import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  EVENTS_MODULE,
  API_MODULE,
  APP_MODULE,
  COMPONENTS_MODULE,
} = vi.hoisted(() => ({
  EVENTS_MODULE: new URL('../../../web/comfyui/loras_widget_events.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  COMPONENTS_MODULE: new URL('../../../web/comfyui/loras_widget_components.js', import.meta.url).pathname,
}));

vi.mock(API_MODULE, () => ({
  api: {},
}));

vi.mock(APP_MODULE, () => ({
  app: {},
}));

vi.mock(COMPONENTS_MODULE, () => ({
  createMenuItem: vi.fn(),
  createDropIndicator: vi.fn(),
}));

describe('LoRA widget drag interactions', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    const dragStyle = document.getElementById('lm-lora-shared-styles');
    if (dragStyle) {
      dragStyle.remove();
    }
  });

  afterEach(() => {
    document.body.classList.remove('lm-lora-strength-dragging');
  });

  it('adjusts a single LoRA strength while syncing collapsed clip strength', async () => {
    const { handleStrengthDrag } = await import(EVENTS_MODULE);

    const widget = {
      value: [
        { name: 'Test', strength: 0.5, clipStrength: 0.25, expanded: false },
      ],
      callback: vi.fn(),
    };

    handleStrengthDrag('Test', 0.5, 100, { clientX: 140 }, widget, false);

    expect(widget.value[0].strength).toBeCloseTo(0.54, 2);
    expect(widget.value[0].clipStrength).toBeCloseTo(0.54, 2);
    expect(widget.callback).toHaveBeenCalledWith(widget.value);
  });

  it('applies proportional drag updates to all LoRAs', async () => {
    const { handleAllStrengthsDrag } = await import(EVENTS_MODULE);

    const widget = {
      value: [
        { name: 'A', strength: 0.4, clipStrength: 0.4 },
        { name: 'B', strength: 0.6, clipStrength: 0.6 },
      ],
      callback: vi.fn(),
    };

    const initialStrengths = [
      { modelStrength: 0.4, clipStrength: 0.4 },
      { modelStrength: 0.6, clipStrength: 0.6 },
    ];

    handleAllStrengthsDrag(initialStrengths, 100, { clientX: 160 }, widget);

    expect(widget.value[0].strength).toBeCloseTo(0.41, 2);
    expect(widget.value[1].strength).toBeCloseTo(0.62, 2);
    expect(widget.callback).toHaveBeenCalledWith(widget.value);
  });

  it('initiates drag gestures, updates strength, and clears cursor state on mouseup', async () => {
    const module = await import(EVENTS_MODULE);
    const renderSpy = vi.fn();
    const previewSpy = { hide: vi.fn() };

    const dragEl = document.createElement('div');
    dragEl.className = 'lm-lora-entry';
    document.body.append(dragEl);

    const widget = {
      value: [{ name: 'Test', strength: 0.5, clipStrength: 0.5 }],
      callback: vi.fn(),
    };

    module.initDrag(dragEl, 'Test', widget, false, previewSpy, renderSpy);

    dragEl.dispatchEvent(new MouseEvent('mousedown', { clientX: 50, bubbles: true }));
    expect(document.body.classList.contains('lm-lora-strength-dragging')).toBe(true);

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 70, bubbles: true }));
    expect(renderSpy).toHaveBeenCalledWith(widget.value, widget);
    expect(previewSpy.hide).toHaveBeenCalled();
    expect(widget.value[0].strength).not.toBe(0.5);

    document.dispatchEvent(new MouseEvent('mouseup'));
    expect(document.body.classList.contains('lm-lora-strength-dragging')).toBe(false);
  });

  it('deletes the selected LoRA when backspace is pressed outside of strength inputs', async () => {
    const { handleKeyboardNavigation } = await import(EVENTS_MODULE);
    const widget = {
      value: [{ name: 'Test', strength: 0.5, clipStrength: 0.5 }],
      callback: vi.fn(),
    };
    const preventDefault = vi.fn();
    const renderSpy = vi.fn();
    const selectLora = vi.fn();
    const event = {
      key: 'Backspace',
      preventDefault,
      ctrlKey: false,
      metaKey: false,
      target: document.createElement('div'),
    };

    const handled = handleKeyboardNavigation(event, 'Test', widget, renderSpy, selectLora);

    expect(handled).toBe(true);
    expect(preventDefault).toHaveBeenCalled();
    expect(widget.value).toEqual([]);
    expect(widget.callback).toHaveBeenCalledWith([]);
    expect(renderSpy).toHaveBeenCalledWith([], widget);
    expect(selectLora).toHaveBeenCalledWith(null);
  });

  it('keeps the LoRA entry when editing strength input and pressing backspace', async () => {
    const { handleKeyboardNavigation } = await import(EVENTS_MODULE);
    const strengthInput = document.createElement('input');
    strengthInput.classList.add('lm-lora-strength-input');

    const widget = {
      value: [{ name: 'Test', strength: 0.5, clipStrength: 0.5 }],
      callback: vi.fn(),
    };
    const preventDefault = vi.fn();
    const renderSpy = vi.fn();
    const selectLora = vi.fn();

    const event = {
      key: 'Backspace',
      preventDefault,
      ctrlKey: false,
      metaKey: false,
      target: strengthInput,
    };

    const handled = handleKeyboardNavigation(event, 'Test', widget, renderSpy, selectLora);

    expect(handled).toBe(false);
    expect(preventDefault).not.toHaveBeenCalled();
    expect(widget.value).toHaveLength(1);
    expect(widget.callback).not.toHaveBeenCalled();
    expect(renderSpy).not.toHaveBeenCalled();
    expect(selectLora).not.toHaveBeenCalled();
  });
});
