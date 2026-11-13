/**
 * Tests for the text widget's LoRA search field.
 *
 * The field is the place to click and type when adding a LoRA: it must exist
 * only on LoRA text widgets, must stay quiet until something is typed, and must
 * bind the autocomplete with `pickIntoNode` so a pick lands on the node's LoRA
 * list instead of being written into the field itself.
 */

import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

const { useAutocompleteMock } = vi.hoisted(() => ({
  useAutocompleteMock: vi.fn(),
}))

// The composable loads web/comfyui/autocomplete.js through a runtime dynamic
// import that does not resolve inside the Vue test build, so the instance is
// supplied directly.
vi.mock('@/composables/useAutocomplete', () => ({
  useAutocomplete: useAutocompleteMock,
}))

import AutocompleteTextWidget from '@/components/AutocompleteTextWidget.vue'

function mountWidget(modelType: 'loras' | 'prompt' = 'loras') {
  const widget = {
    callback: vi.fn(),
    onSetValue: undefined as ((v: string) => void) | undefined,
    inputEl: undefined,
    metadataWidget: undefined,
    name: 'text',
  }
  const wrapper = shallowMount(AutocompleteTextWidget, {
    props: { widget, node: { id: 1 }, modelType, placeholder: 'Search LoRAs to add...' },
    attachTo: document.body,
  })
  return { wrapper, widget }
}

beforeEach(() => {
  useAutocompleteMock.mockReset()
  useAutocompleteMock.mockImplementation(() => ({
    autocompleteInstance: { value: null },
    isInitialized: { value: true },
    initAutocomplete: vi.fn(),
    destroyAutocomplete: vi.fn(),
    refreshCaretHelper: vi.fn(),
  }))
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('AutocompleteTextWidget search field', () => {
  it('renders on LoRA text widgets and not on prompt text widgets', () => {
    const { wrapper: loraWidget } = mountWidget('loras')
    expect(loraWidget.find('.lora-search-row').exists()).toBe(true)
    expect(loraWidget.find('.lora-search-input').exists()).toBe(true)
    // The field is text only: the magnifier was dropped on request.
    expect(loraWidget.find('.lora-search-icon').exists()).toBe(false)

    const { wrapper: promptWidget } = mountWidget('prompt')
    expect(promptWidget.find('.lora-search-row').exists()).toBe(false)
  })

  it('drops the prompt placeholder when the dedicated field exists', () => {
    const { wrapper: loraWidget } = mountWidget('loras')
    expect(loraWidget.find('textarea').attributes('placeholder')).toBe('')

    const { wrapper: promptWidget } = mountWidget('prompt')
    expect(promptWidget.find('textarea').attributes('placeholder')).toBe('Search LoRAs to add...')
  })

  it('binds the field to the same autocomplete class with pickIntoNode', () => {
    mountWidget('loras')

    const promptOptions = useAutocompleteMock.mock.calls[0][2]
    expect(promptOptions.pickIntoNode).toBeUndefined()

    const fieldOptions = useAutocompleteMock.mock.calls[1][2]
    expect(fieldOptions.pickIntoNode).toBe(true)
    expect(fieldOptions.anchorToElement).toBe(true)
    expect(useAutocompleteMock.mock.calls[1][1]).toBe('loras')
    // Thumbnails: the field must show the same preview tooltip the text-area
    // search does, so the preview must not be disabled here.
    expect(fieldOptions.showPreview).not.toBe(false)
  })

  it('keeps the field text out of the prompt while typing', async () => {
    const { wrapper, widget } = mountWidget('loras')
    widget.callback.mockClear()

    await wrapper.find('.lora-search-input').setValue('example')

    // The field is not the prompt: typing in it must not call the widget
    // callback that syncs the textarea's value.
    expect(widget.callback).not.toHaveBeenCalled()
  })

  it('forwards the wheel over the field to the canvas so the node still zooms', async () => {
    const processMouseWheel = vi.fn()
    ;(window as any).app = { canvas: { processMouseWheel } }
    const { wrapper } = mountWidget('loras')

    const event = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true })
    wrapper.find('.lora-search-input').element.dispatchEvent(event)
    await wrapper.vm.$nextTick()

    expect(processMouseWheel).toHaveBeenCalledTimes(1)
    expect(processMouseWheel.mock.calls[0][0]).toBe(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('leaves the wheel alone when there is no canvas to forward to', async () => {
    ;(window as any).app = undefined
    const { wrapper } = mountWidget('loras')

    const event = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true })
    expect(() => wrapper.find('.lora-search-input').element.dispatchEvent(event)).not.toThrow()
    expect(event.defaultPrevented).toBe(false)
  })

  it('clears the query when the field loses focus', async () => {
    const { wrapper } = mountWidget('loras')
    const input = wrapper.find('.lora-search-input')

    await input.setValue('kre')
    const inputEvents = vi.fn()
    input.element.addEventListener('input', inputEvents)
    await input.trigger('blur')

    expect((input.element as HTMLInputElement).value).toBe('')
    // The input event is what cancels a pending keystroke search in the engine.
    expect(inputEvents).toHaveBeenCalledTimes(1)
  })

  it('leaves the prompt text alone when the field blurs', async () => {
    const { wrapper, widget } = mountWidget('loras')
    widget.callback.mockClear()

    await wrapper.find('.lora-search-input').setValue('kre')
    await wrapper.find('.lora-search-input').trigger('blur')

    expect(widget.callback).not.toHaveBeenCalled()
  })

  it('forwards the wheel from the prompt too, but leaves it when the prompt scrolls', async () => {
    const processMouseWheel = vi.fn()
    ;(window as any).app = { canvas: { processMouseWheel } }
    const { wrapper } = mountWidget('loras')
    const textarea = wrapper.find('textarea').element as HTMLTextAreaElement

    Object.defineProperty(textarea, 'scrollHeight', { value: 100, configurable: true })
    Object.defineProperty(textarea, 'clientHeight', { value: 100, configurable: true })
    const forwarded = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true })
    textarea.dispatchEvent(forwarded)

    expect(processMouseWheel).toHaveBeenCalledTimes(1)
    expect(forwarded.defaultPrevented).toBe(true)

    // A scrollable prompt keeps the wheel: only the canvas zoom is suppressed.
    Object.defineProperty(textarea, 'scrollHeight', { value: 400, configurable: true })
    const kept = new WheelEvent('wheel', { deltaY: 100, bubbles: true, cancelable: true })
    textarea.dispatchEvent(kept)

    expect(processMouseWheel).toHaveBeenCalledTimes(1)
    expect(kept.defaultPrevented).toBe(false)
  })
})
