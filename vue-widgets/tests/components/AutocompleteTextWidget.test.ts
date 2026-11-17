/**
 * Tests for AutocompleteTextWidget — clear button behavior.
 *
 * The clear button must clear the textarea through a trusted editing command
 * (execCommand) so the browser records an undo entry and Ctrl+Z (with focus
 * in the textarea) can restore the cleared content. jsdom's execCommand is a
 * no-op that returns false, so the fallback manual-clear path is exercised by
 * default; the execCommand path is covered by emulating the browser edit.
 */

import { nextTick } from 'vue'
import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, afterEach } from 'vitest'
import AutocompleteTextWidget from '@/components/AutocompleteTextWidget.vue'

function createMockWidget() {
  return {
    callback: vi.fn(),
    onSetValue: undefined as ((v: string) => void) | undefined,
    inputEl: undefined,
    metadataWidget: undefined,
    name: 'text',
  }
}

function mountWidget() {
  const widget = createMockWidget()
  const node = { id: 1 }
  const wrapper = shallowMount(AutocompleteTextWidget, {
    props: { widget, node, modelType: 'prompt' },
    // Attach to the document so jsdom implements real focus behavior
    attachTo: document.body,
  })
  return { wrapper, widget }
}

afterEach(() => {
  document.body.innerHTML = ''
  delete (document as unknown as { execCommand?: unknown }).execCommand
})

describe('AutocompleteTextWidget clear button', () => {
  it('is hidden when the textarea is empty and appears once text is entered', async () => {
    const { wrapper } = mountWidget()

    expect(wrapper.find('.clear-button').exists()).toBe(false)

    await wrapper.find('textarea').setValue('hello <lora:foo:1>')

    expect(wrapper.find('.clear-button').exists()).toBe(true)
  })

  it('clears the textarea via the fallback path when execCommand is unavailable', async () => {
    const { wrapper, widget } = mountWidget()
    const textarea = wrapper.find('textarea')

    await textarea.setValue('hello <lora:foo:1>')
    expect(widget.callback).toHaveBeenLastCalledWith('hello <lora:foo:1>')

    // jsdom does not define document.execCommand at all, so the availability
    // guard fails and the fallback manual clear runs: value reset + synthetic
    // input event.
    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.find('.clear-button').exists()).toBe(false)
    expect(widget.callback).toHaveBeenLastCalledWith('')
    // Focus returns to the textarea so Ctrl+Z can trigger native undo
    expect(document.activeElement).toBe(textarea.element)
  })

  it('clears through a trusted execCommand edit so the browser records an undo entry', async () => {
    const { wrapper, widget } = mountWidget()
    const textarea = wrapper.find('textarea')

    await textarea.setValue('hello world')
    widget.callback.mockClear()

    // Emulate Chromium: replace the selection with the given text, then fire
    // a trusted input event that Vue and the autocomplete listeners observe.
    // jsdom has no document.execCommand, so define it for this test.
    const execMock = vi.fn((_cmd: string, _showUI: boolean, value: string) => {
      const ta = document.activeElement as HTMLTextAreaElement | null
      if (!ta || ta.tagName !== 'TEXTAREA') return false
      ta.value = String(value ?? '')
      ta.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    })
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execMock })

    await wrapper.find('.clear-button').trigger('click')

    expect(execMock).toHaveBeenCalledWith('insertText', false, '')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
    // Callback is driven by the trusted input event (exactly once, no double call)
    expect(widget.callback).toHaveBeenCalledTimes(1)
    expect(widget.callback).toHaveBeenCalledWith('')
    expect(wrapper.find('.clear-button').exists()).toBe(false)
  })

  it('collapses the selection when Ctrl+Z restores the cleared text', async () => {
    const { wrapper, widget } = mountWidget()
    const textarea = wrapper.find('textarea')
    const ta = textarea.element as HTMLTextAreaElement

    await textarea.setValue('hello world')
    widget.callback.mockClear()

    // Clear via the trusted edit path (emulated Chromium)
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: vi.fn(() => {
        ta.value = ''
        ta.dispatchEvent(new Event('input', { bubbles: true }))
        return true
      }),
    })
    await wrapper.find('.clear-button').trigger('click')

    // Simulate the browser's undo: restore the text and the captured
    // full-text selection, then fire the historyUndo input event
    ta.value = 'hello world'
    ta.setSelectionRange(0, ta.value.length)
    ta.dispatchEvent(
      Object.assign(new Event('input', { bubbles: true }), { inputType: 'historyUndo' })
    )
    await nextTick()

    expect(ta.value).toBe('hello world')
    // The restored text must not remain selected — caret collapsed to the end
    expect(ta.selectionStart).toBe(ta.value.length)
    expect(ta.selectionEnd).toBe(ta.value.length)
    expect(wrapper.find('.clear-button').exists()).toBe(true)
    expect(widget.callback).toHaveBeenLastCalledWith('hello world')
  })
})

/**
 * Tests for the LoRA widget's clear.
 *
 * On a LoRA widget the box holds the node's LoRA list in tag form, so a clear
 * keeps the tags of the LoRAs that are enabled and drops everything else:
 * disabled entries and any prompt text around them. Prompt widgets have no
 * list, so they still clear outright.
 */

interface MockLoraEntry {
  name: string
  strength?: string
  active?: boolean
}

function mountLoraWidget(loras: MockLoraEntry[] | undefined, modelType: 'loras' | 'prompt' = 'loras') {
  const widget = createMockWidget()
  const node: { id: number; lorasWidget?: { value: MockLoraEntry[] } } = { id: 1 }
  if (loras !== undefined) {
    node.lorasWidget = { value: loras }
  }
  const wrapper = shallowMount(AutocompleteTextWidget, {
    props: { widget, node, modelType },
    attachTo: document.body,
  })
  return { wrapper, widget, node }
}

describe('AutocompleteTextWidget clear on a LoRA widget', () => {
  it('keeps the enabled LoRAs, dropping disabled entries and prompt text', async () => {
    const { wrapper, widget } = mountLoraWidget([
      { name: 'style/enabled_one', strength: '0.80', active: true },
      { name: 'style/off_two', strength: '1.20', active: false },
    ])
    const textarea = wrapper.find('textarea')

    await textarea.setValue(
      'masterpiece, <lora:style/enabled_one:0.80>, <lora:style/off_two:1.20>, best quality'
    )
    widget.callback.mockClear()

    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('<lora:style/enabled_one:0.80>')
    expect(widget.callback).toHaveBeenCalledTimes(1)
    expect(widget.callback).toHaveBeenCalledWith('<lora:style/enabled_one:0.80>')
    // Something is still in the box, so the button stays available
    expect(wrapper.find('.clear-button').exists()).toBe(true)
  })

  it('keeps clip strengths and tag order as they are in the box', async () => {
    const { wrapper } = mountLoraWidget([
      { name: 'a', active: true },
      { name: 'b', active: true },
    ])
    const textarea = wrapper.find('textarea')

    await textarea.setValue('<lora:b:0.50:0.70> <lora:a:1.00>')
    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('<lora:b:0.50:0.70> <lora:a:1.00>')
  })

  it('clears the box when no listed LoRA is enabled', async () => {
    const { wrapper, widget } = mountLoraWidget([
      { name: 'a', active: false },
      { name: 'b', active: false },
    ])
    const textarea = wrapper.find('textarea')

    await textarea.setValue('<lora:a:1.00> and some prompt text <lora:b:1.00>')
    widget.callback.mockClear()

    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
    expect(widget.callback).toHaveBeenCalledWith('')
    expect(wrapper.find('.clear-button').exists()).toBe(false)
  })

  it('clears the box when the node has no LoRA list', async () => {
    const { wrapper } = mountLoraWidget(undefined)
    const textarea = wrapper.find('textarea')

    await textarea.setValue('<lora:a:1.00>')
    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('counts a listed LoRA without an active flag as enabled', async () => {
    const { wrapper } = mountLoraWidget([{ name: 'legacy_entry' }])
    const textarea = wrapper.find('textarea')

    await textarea.setValue('<lora:legacy_entry:1.00> prompt words')
    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('<lora:legacy_entry:1.00>')
  })

  it('leaves the box untouched when it already holds only enabled LoRAs', async () => {
    const { wrapper, widget } = mountLoraWidget([{ name: 'a', active: true }])
    const textarea = wrapper.find('textarea')

    await textarea.setValue('<lora:a:1.00>')
    widget.callback.mockClear()

    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('<lora:a:1.00>')
    // Nothing was cleared, so no edit is reported to the node
    expect(widget.callback).not.toHaveBeenCalled()
    expect(document.activeElement).toBe(textarea.element)
  })

  it('records the retained text as the trusted edit so undo restores the clear', async () => {
    const { wrapper, widget } = mountLoraWidget([
      { name: 'a', active: true },
      { name: 'b', active: false },
    ])
    const textarea = wrapper.find('textarea')

    await textarea.setValue('words <lora:a:1.00> <lora:b:1.00>')
    widget.callback.mockClear()

    const execMock = vi.fn((_cmd: string, _showUI: boolean, value: string) => {
      const ta = document.activeElement as HTMLTextAreaElement | null
      if (!ta || ta.tagName !== 'TEXTAREA') return false
      ta.value = String(value ?? '')
      ta.dispatchEvent(new Event('input', { bubbles: true }))
      return true
    })
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execMock })

    await wrapper.find('.clear-button').trigger('click')

    expect(execMock).toHaveBeenCalledWith('insertText', false, '<lora:a:1.00>')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('<lora:a:1.00>')
    expect(widget.callback).toHaveBeenCalledTimes(1)
    expect(widget.callback).toHaveBeenCalledWith('<lora:a:1.00>')
  })

  it('still clears everything on a prompt widget that has a LoRA list', async () => {
    const { wrapper } = mountLoraWidget([{ name: 'a', active: true }], 'prompt')
    const textarea = wrapper.find('textarea')

    await textarea.setValue('words <lora:a:1.00>')
    await wrapper.find('.clear-button').trigger('click')

    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('titles the button for the behaviour it has', async () => {
    const lora = mountLoraWidget([{ name: 'a', active: true }])
    await lora.wrapper.find('textarea').setValue('<lora:a:1.00>')
    expect(lora.wrapper.find('.clear-button').attributes('title')).toBe(
      'Clear text, keeping enabled LoRAs'
    )

    const prompt = mountLoraWidget([{ name: 'a', active: true }], 'prompt')
    await prompt.wrapper.find('textarea').setValue('words')
    expect(prompt.wrapper.find('.clear-button').attributes('title')).toBe('Clear text')
  })
})

/**
 * Tests for the vertical-scrollbar inset.
 *
 * When the textarea content overflows and a classic (non-overlay) scrollbar
 * is shown, the absolutely-positioned corner clear (x) button would sit on
 * top of the scrollbar. The component measures the scrollbar gutter and
 * exposes it as the --lm-vscrollbar-width CSS var on .input-wrapper so the
 * button shifts left of the scrollbar. jsdom does no layout, so overflow is
 * simulated by overriding the scroll/dimension props.
 */
describe('AutocompleteTextWidget vertical scrollbar inset', () => {
  function overrideTextareaMetrics(
    ta: HTMLTextAreaElement,
    metrics: { scrollHeight: number; clientHeight: number; offsetWidth: number; clientWidth: number }
  ) {
    Object.defineProperty(ta, 'scrollHeight', { configurable: true, value: metrics.scrollHeight })
    Object.defineProperty(ta, 'clientHeight', { configurable: true, value: metrics.clientHeight })
    Object.defineProperty(ta, 'offsetWidth', { configurable: true, value: metrics.offsetWidth })
    Object.defineProperty(ta, 'clientWidth', { configurable: true, value: metrics.clientWidth })
  }

  it('exposes the scrollbar width as a CSS var when the content overflows', async () => {
    const { wrapper } = mountWidget()
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    overrideTextareaMetrics(textarea, {
      scrollHeight: 200,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 305, // 15px scrollbar gutter
    })
    textarea.dispatchEvent(new Event('input'))
    await nextTick()

    const wrapperEl = wrapper.find('.input-wrapper').element as HTMLElement
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('15px')
  })

  it('keeps the CSS var at 0px when there is no vertical scrollbar', async () => {
    const { wrapper } = mountWidget()
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    overrideTextareaMetrics(textarea, {
      scrollHeight: 100,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 320,
    })
    textarea.dispatchEvent(new Event('input'))
    await nextTick()

    const wrapperEl = wrapper.find('.input-wrapper').element as HTMLElement
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('0px')
  })

  it('clears the inset once overflowing content is removed', async () => {
    const { wrapper } = mountWidget()
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    overrideTextareaMetrics(textarea, {
      scrollHeight: 200,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 305,
    })
    textarea.dispatchEvent(new Event('input'))
    await nextTick()
    const wrapperEl = wrapper.find('.input-wrapper').element as HTMLElement
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('15px')

    // Content now fits: no scrollbar → inset cleared
    overrideTextareaMetrics(textarea, {
      scrollHeight: 100,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 320,
    })
    textarea.dispatchEvent(new Event('input'))
    await nextTick()
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('0px')
  })

  it('re-measures the inset when the value is set programmatically via onSetValue', async () => {
    const { wrapper, widget } = mountWidget()
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    // Start with no overflow
    overrideTextareaMetrics(textarea, {
      scrollHeight: 100,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 320,
    })
    await nextTick()

    // Simulate an external setValue (e.g. "send lora to workflow"): the DOM
    // value is set by the caller and widget.onSetValue fires without an
    // input event. Content now overflows → inset must be re-measured.
    overrideTextareaMetrics(textarea, {
      scrollHeight: 200,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 305, // 15px scrollbar gutter
    })
    if (!widget.onSetValue) throw new Error('onSetValue not installed by component')
    widget.onSetValue('long content')
    await nextTick()

    const wrapperEl = wrapper.find('.input-wrapper').element as HTMLElement
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('15px')
  })

  it('re-measures the inset on external value-change events', async () => {
    const { wrapper } = mountWidget()
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    // Start with no overflow
    overrideTextareaMetrics(textarea, {
      scrollHeight: 100,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 320,
    })
    await nextTick()

    // The lora-manager:autocomplete-value-changed event fires when the
    // widget value is set externally; content now overflows → re-measure.
    overrideTextareaMetrics(textarea, {
      scrollHeight: 200,
      clientHeight: 100,
      offsetWidth: 320,
      clientWidth: 305, // 15px scrollbar gutter
    })
    textarea.dispatchEvent(
      new CustomEvent('lora-manager:autocomplete-value-changed', {
        detail: { value: 'long content' },
      })
    )
    await nextTick()

    const wrapperEl = wrapper.find('.input-wrapper').element as HTMLElement
    expect(wrapperEl.style.getPropertyValue('--lm-vscrollbar-width')).toBe('15px')
  })
})
