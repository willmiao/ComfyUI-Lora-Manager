/**
 * Tests for the LoRA list header's sweep button.
 *
 * The header carries three actions beside the toggle-all: the strength drag
 * handle, the sweep button and the quick-picker add button. Sweep drops the
 * rows that are switched off and leaves everything else — strengths, order,
 * selection — alone. The clear (x) in a node's text box is deliberately not
 * touched: it keeps clearing the text, LoRAs included.
 *
 * The widget mount mirrors ComfyUI's real addDOMWidget: `value` is wired to
 * options.getValue/setValue, and setValue() re-renders the list. The header is
 * therefore rebuilt after every toggle, which is what keeps the sweep button's
 * count and disabled state current.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const { APP_MODULE, API_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
}));

const canvasMocks = vi.hoisted(() => ({
  emitBeforeChange: vi.fn(),
  emitAfterChange: vi.fn(),
}));

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: vi.fn(),
    graph: {},
    canvas: { ds: { scale: 1 }, ...canvasMocks },
    ui: { settings: { settingsById: {} } },
    extensionManager: {
      setting: { get: () => undefined, set: vi.fn() },
    },
  },
}));

const { fetchApiMock } = vi.hoisted(() => ({ fetchApiMock: vi.fn() }));
vi.mock(API_MODULE, () => ({
  api: { fetchApi: fetchApiMock, addEventListener: vi.fn() },
}));

// The styles loader fetches the stylesheet over a relative URL, which jsdom's
// fetch cannot resolve; styles are irrelevant to the list contents under test.
vi.mock('../../../web/comfyui/lm_styles_loader.js', () => ({
  ensureLmStyles: () => {},
}));

import { addLorasWidget } from '../../../web/comfyui/loras_widget.js';
import {
  getAvailableLoras,
  resetAvailableLorasCache,
} from '../../../web/comfyui/loras_widget_utils.js';

const respondWith = ({ loras = [] } = {}) => {
  fetchApiMock.mockImplementation(async (url) => {
    if (url === '/lm/loras/cycler-list') {
      return { ok: true, json: async () => ({ success: true, loras }) };
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
};

const mountWidget = async (entries) => {
  const node = {
    id: 1,
    comfyClass: 'Lora Stacker (LoraManager)',
    addDOMWidget(name, type, container, options) {
      const widget = {
        get value() {
          return options.getValue();
        },
        set value(nextValue) {
          options.setValue(nextValue);
        },
      };
      node.container = container;
      node.widget = widget;
      return widget;
    },
  };
  addLorasWidget(node, 'loras', { defaultVal: entries });
  document.body.appendChild(node.container);
  await getAvailableLoras();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return node;
};

const entry = (name, active, strength = '1.00', extra = {}) => ({
  name,
  strength,
  active,
  ...extra,
});
const rows = (node) => [...node.container.querySelectorAll('.lm-lora-entry')];
const rowNames = (node) => rows(node).map((row) => row.dataset.loraName);
const sweepButton = (node) => node.container.querySelector('.lm-lora-sweep-button');
const addButton = (node) => node.container.querySelector('.lm-lora-add-button');
const headerLabel = (node) => node.container.querySelector('.lm-toggle-label');
const selectedNames = (node) =>
  rows(node)
    .filter((row) => row.dataset.selected === 'true')
    .map((row) => row.dataset.loraName);

describe('addLorasWidget sweep button', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApiMock.mockReset();
    canvasMocks.emitBeforeChange.mockReset();
    canvasMocks.emitAfterChange.mockReset();
    resetAvailableLorasCache();
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('sits in the header actions beside the drag handle and the add button', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', false)]);

    const actions = node.container.querySelector('.lm-loras-header-actions');
    const order = [...actions.children].map((el) => el.className.split(' ')[0]);
    expect(order).toEqual([
      'lm-lora-strength-drag-handle',
      'lm-lora-sweep-button',
      'lm-lora-add-button',
    ]);
    expect(sweepButton(node)).toBeTruthy();
    expect(addButton(node)).toBeTruthy();
  });

  it('removes the turned-off rows and keeps the enabled ones', async () => {
    respondWith();
    const node = await mountWidget([
      entry('keep_one', true, '0.80', { clipStrength: '0.70', expanded: true }),
      entry('drop_one', false, '1.20'),
      entry('keep_two', true, '1.00'),
      entry('drop_two', false, '0.50'),
    ]);
    const callback = vi.fn();
    node.widget.callback = callback;

    expect(rowNames(node)).toEqual(['keep_one', 'drop_one', 'keep_two', 'drop_two']);

    sweepButton(node).click();

    expect(node.widget.value.map((lora) => lora.name)).toEqual(['keep_one', 'keep_two']);
    // The enabled rows keep their strengths, clip strength, expansion and order
    expect(node.widget.value.map((lora) => lora.strength)).toEqual(['0.80', '1.00']);
    expect(node.widget.value[0]).toMatchObject({
      clipStrength: '0.70',
      expanded: true,
    });
    // The list callback runs once, with the swept value
    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback.mock.calls[0][0].map((lora) => lora.name)).toEqual(['keep_one', 'keep_two']);
    // Rows are re-rendered from the new value
    expect(rowNames(node)).toEqual(['keep_one', 'keep_two']);
  });

  it('names the number of rows it would remove', async () => {
    respondWith();
    const node = await mountWidget([
      entry('a', true),
      entry('b', false),
      entry('c', false),
    ]);

    expect(sweepButton(node).title).toBe('Remove 2 turned-off LoRAs');
    expect(sweepButton(node).getAttribute('aria-label')).toBe('Remove 2 turned-off LoRAs');
    expect(sweepButton(node).disabled).toBe(false);

    sweepButton(node).click();

    // One row left, nothing off: the button is rebuilt in its disabled state
    expect(rowNames(node)).toEqual(['a']);
    expect(sweepButton(node).disabled).toBe(true);
    expect(sweepButton(node).title).toBe('No turned-off LoRAs to remove');
  });

  it('uses the singular for one row', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', false)]);

    expect(sweepButton(node).title).toBe('Remove 1 turned-off LoRA');
  });

  it('records the sweep as one undo transaction', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', false)]);

    sweepButton(node).click();

    expect(canvasMocks.emitBeforeChange).toHaveBeenCalledTimes(1);
    expect(canvasMocks.emitAfterChange).toHaveBeenCalledTimes(1);
    expect(
      canvasMocks.emitBeforeChange.mock.invocationCallOrder[0]
    ).toBeLessThan(canvasMocks.emitAfterChange.mock.invocationCallOrder[0]);
    expect(rowNames(node)).toEqual(['a']);
  });

  it('is disabled and inert when nothing is turned off', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', true)]);
    const callback = vi.fn();
    node.widget.callback = callback;
    const before = JSON.stringify(node.widget.value);

    expect(sweepButton(node).disabled).toBe(true);
    sweepButton(node).click();

    expect(JSON.stringify(node.widget.value)).toBe(before);
    expect(callback).not.toHaveBeenCalled();
    expect(canvasMocks.emitBeforeChange).not.toHaveBeenCalled();
    expect(canvasMocks.emitAfterChange).not.toHaveBeenCalled();
    expect(rowNames(node)).toEqual(['a', 'b']);
  });

  it('treats a row with no active flag as off, like the row and the node do', async () => {
    respondWith();
    const node = await mountWidget([
      { name: 'legacy_entry', strength: '1.00' },
      entry('off_one', false),
    ]);

    // The row toggle and the header counter already treat it as off, and the
    // Python nodes skip it because active is missing.
    expect(node.widget.value.find((lora) => lora.name === 'legacy_entry').active).toBeUndefined();
    expect(headerLabel(node).textContent).toBe('0/2 on');
    expect(sweepButton(node).title).toBe('Remove 2 turned-off LoRAs');

    sweepButton(node).click();

    expect(node.widget.value).toEqual([]);
    expect(node.container.querySelector('.lm-lora-empty-state')).toBeTruthy();
  });

  it('leaves the row selection on a surviving row', async () => {
    respondWith();
    const node = await mountWidget([entry('keep', true), entry('drop', false)]);

    rows(node).find((row) => row.dataset.loraName === 'keep').click();
    expect(selectedNames(node)).toEqual(['keep']);

    sweepButton(node).click();

    expect(selectedNames(node)).toEqual(['keep']);
  });

  it('clears the selection when the selected row is removed', async () => {
    respondWith();
    const node = await mountWidget([entry('keep', true), entry('drop', false)]);

    rows(node).find((row) => row.dataset.loraName === 'drop').click();
    expect(selectedNames(node)).toEqual(['drop']);

    sweepButton(node).click();

    expect(rowNames(node)).toEqual(['keep']);
    expect(selectedNames(node)).toEqual([]);
  });

  it('updates after a row toggle without any hover', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', true), entry('c', true)]);
    expect(headerLabel(node).textContent).toBe('3/3 on');
    expect(sweepButton(node).disabled).toBe(true);

    // Switching a row off goes through widget.value -> setValue -> render, so
    // this header is rebuilt and the sweep state is fresh.
    rows(node)
      .find((row) => row.dataset.loraName === 'b')
      .querySelector('.lm-lora-toggle')
      .click();

    expect(node.widget.value.find((lora) => lora.name === 'b').active).toBe(false);
    expect(headerLabel(node).textContent).toBe('2/3 on');
    expect(sweepButton(node).disabled).toBe(false);
    expect(sweepButton(node).title).toBe('Remove 1 turned-off LoRA');

    sweepButton(node).click();

    expect(rowNames(node)).toEqual(['a', 'c']);
    expect(headerLabel(node).textContent).toBe('2/2 on');
    expect(sweepButton(node).disabled).toBe(true);
  });

  it('updates after toggle-all off and empties the list in one click', async () => {
    respondWith();
    const node = await mountWidget([entry('a', true), entry('b', true)]);
    expect(sweepButton(node).disabled).toBe(true);

    node.container.querySelector('.lm-toggle-container .lm-lora-toggle').click();

    expect(node.widget.value.every((lora) => !lora.active)).toBe(true);
    expect(headerLabel(node).textContent).toBe('0/2 on');
    expect(sweepButton(node).disabled).toBe(false);
    expect(sweepButton(node).title).toBe('Remove 2 turned-off LoRAs');

    sweepButton(node).click();

    expect(node.widget.value).toEqual([]);
    expect(node.container.querySelector('.lm-lora-empty-state')).toBeTruthy();
  });

  it('stays available but disabled in the empty state', async () => {
    respondWith();
    const node = await mountWidget([]);

    expect(sweepButton(node)).toBeTruthy();
    expect(sweepButton(node).disabled).toBe(true);
    expect(sweepButton(node).title).toBe('No turned-off LoRAs to remove');
    expect(addButton(node)).toBeTruthy();
    expect(node.container.querySelector('.lm-lora-strength-drag-handle')).toBeNull();
  });
});
