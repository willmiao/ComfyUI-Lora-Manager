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
    onSetValue: undefined,
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
