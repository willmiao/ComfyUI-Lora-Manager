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
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
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

/**
 * Tests for the active-filters search indicator (loras mode only).
 *
 * The small filter chip in the textarea corner mirrors the
 * loramanager.lora_active_filters_autocomplete setting: it reflects the
 * current state, can toggle it, and stays in sync with slash-command /
 * context-menu toggles via the lora-manager:setting-toggled window event.
 */

const settingsMocks = vi.hoisted(() => ({
  getPreference: vi.fn(),
  setValue: vi.fn(),
}))

vi.mock('../../../web/comfyui/settings.js', () => ({
  LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID:
    'loramanager.lora_active_filters_autocomplete',
  SETTING_TOGGLED_EVENT_NAME: 'lora-manager:setting-toggled',
  getLoraActiveFiltersAutocompletePreference: settingsMocks.getPreference,
  setLoraManagerSettingValue: settingsMocks.setValue,
}))

const getActiveFiltersPreferenceMock = settingsMocks.getPreference
const setSettingValueMock = settingsMocks.setValue

function mountLorasWidget() {
  const widget = createMockWidget()
  const node = { id: 1 }
  const wrapper = shallowMount(AutocompleteTextWidget, {
    props: { widget, node, modelType: 'loras' },
    attachTo: document.body,
  })
  return { wrapper, widget }
}

describe('AutocompleteTextWidget active-filters indicator', () => {
  beforeEach(() => {
    getActiveFiltersPreferenceMock.mockReset()
    getActiveFiltersPreferenceMock.mockReturnValue(false)
    setSettingValueMock.mockReset()
    setSettingValueMock.mockResolvedValue(true)
  })

  it('renders only in loras mode', () => {
    const loras = mountLorasWidget()
    expect(loras.wrapper.find('.active-filters-toggle').exists()).toBe(true)

    const widget = createMockWidget()
    const prompt = shallowMount(AutocompleteTextWidget, {
      props: { widget, node: { id: 2 }, modelType: 'prompt' },
      attachTo: document.body,
    })
    expect(prompt.find('.active-filters-toggle').exists()).toBe(false)
  })

  it('reflects the current setting state', async () => {
    const { wrapper } = mountLorasWidget()
    await nextTick()
    expect(wrapper.find('.active-filters-toggle').classes()).not.toContain('is-active')

    getActiveFiltersPreferenceMock.mockReturnValue(true)
    const wrapper2 = mountLorasWidget().wrapper
    await nextTick()
    expect(wrapper2.find('.active-filters-toggle').classes()).toContain('is-active')
  })

  it('toggles the setting when clicked', async () => {
    const { wrapper } = mountLorasWidget()
    await nextTick()

    await wrapper.find('.active-filters-toggle').trigger('click')
    expect(setSettingValueMock).toHaveBeenCalledWith(
      'loramanager.lora_active_filters_autocomplete',
      true
    )
    await nextTick()
    expect(wrapper.find('.active-filters-toggle').classes()).toContain('is-active')
  })

  it('stays in sync with setting-toggled window events', async () => {
    const { wrapper } = mountLorasWidget()
    await nextTick()
    expect(wrapper.find('.active-filters-toggle').classes()).not.toContain('is-active')

    window.dispatchEvent(
      new CustomEvent('lora-manager:setting-toggled', {
        detail: {
          settingId: 'loramanager.lora_active_filters_autocomplete',
          value: true,
        },
      })
    )
    await nextTick()
    expect(wrapper.find('.active-filters-toggle').classes()).toContain('is-active')

    window.dispatchEvent(
      new CustomEvent('lora-manager:setting-toggled', {
        detail: { settingId: 'loramanager.some_other_setting', value: true },
      })
    )
    await nextTick()
    // Unrelated settings must not flip the indicator
    expect(wrapper.find('.active-filters-toggle').classes()).toContain('is-active')
  })
})

/**
 * Tests for the vertical-scrollbar inset.
 *
 * When the textarea content overflows and a classic (non-overlay) scrollbar
 * is shown, the absolutely-positioned corner buttons (clear x, active-filters
 * filter chip) would sit on top of the scrollbar. The component measures the
 * scrollbar gutter and exposes it as the --lm-vscrollbar-width CSS var on
 * .input-wrapper so the buttons shift left of the scrollbar. jsdom does no
 * layout, so overflow is simulated by overriding the scroll/dimension props.
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
})
