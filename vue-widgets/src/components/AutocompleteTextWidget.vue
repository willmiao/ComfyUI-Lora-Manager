<template>
  <div class="autocomplete-text-widget">
    <div v-if="showSearchField" class="lora-search-row">
      <input
        ref="searchInputRef"
        class="lora-search-input"
        type="text"
        placeholder="Search LoRAs"
        aria-label="Search LoRAs"
        spellcheck="false"
        autocomplete="off"
        @blur="clearSearchField"
        @keydown.stop
      />
    </div>
    <div
      ref="inputWrapperRef"
      class="input-wrapper"
      :style="{ '--lm-vscrollbar-width': vScrollbarWidth + 'px' }"
    >
      <textarea
        ref="textareaRef"
        :placeholder="showSearchField ? '' : placeholder"
        :spellcheck="spellcheck ?? false"
        :class="['text-input', { 'vue-dom-mode': isVueDomMode, 'lm-wheel-scrollable': isVueDomMode }]"
        :style="maxHeight && isVueDomMode ? { maxHeight: maxHeight + 'px' } : undefined"
        data-capture-wheel="true"
        @input="onInput"
      />
      <button
        v-if="showClearButton"
        type="button"
        class="clear-button"
        title="Clear text"
        @click="clearText"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useAutocomplete } from '@/composables/useAutocomplete'
// @ts-ignore - ComfyUI external module
import { forwardWheelToCanvas } from '../../../web/comfyui/utils.js'

// Access LiteGraph global for initial mode detection
declare const LiteGraph: { vueNodesMode?: boolean } | undefined

export interface AutocompleteTextWidgetInterface {
  inputEl?: HTMLTextAreaElement
  callback?: (v: string) => void
  onSetValue?: (v: string) => void
  metadataWidget?: { value?: unknown }
  name?: string
}

const props = defineProps<{
  widget: AutocompleteTextWidgetInterface
  node: { id: number }
  modelType?: 'loras' | 'prompt'
  placeholder?: string
  showPreview?: boolean
  spellcheck?: boolean
  maxHeight?: number
}>()

// Reactive ref for Vue DOM mode
const isVueDomMode = ref(typeof LiteGraph !== 'undefined' && LiteGraph.vueNodesMode === true)

// Listen for mode change events from main.ts
const onModeChange = (event: Event) => {
  const customEvent = event as CustomEvent<{ isVueDomMode: boolean }>
  isVueDomMode.value = customEvent.detail.isVueDomMode
  // Canvas vs Vue DOM mode use different paddings/geometry.
  updateVScrollbarWidth()
}

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const inputWrapperRef = ref<HTMLElement | null>(null)

// Width of the textarea's own vertical scrollbar gutter. When the content
// overflows and a classic (non-overlay) scrollbar is shown, the scrollbar
// occupies the textarea's rightmost pixels and the absolutely-positioned
// corner clear (x) button would overlap it. We expose this width as a CSS
// var so the button can shift left of the scrollbar; it is 0 when there is
// no scrollbar (content fits, or platform overlay scrollbars that float
// over the content).
const vScrollbarWidth = ref(0)
let scrollbarResizeObserver: ResizeObserver | null = null

const updateVScrollbarWidth = () => {
  const ta = textareaRef.value
  if (!ta) return
  const overflowsY = ta.scrollHeight > ta.clientHeight
  vScrollbarWidth.value = overflowsY ? ta.offsetWidth - ta.clientWidth : 0
}

const observeScrollbarWidth = () => {
  unobserveScrollbarWidth()
  const ta = textareaRef.value
  if (!ta || typeof ResizeObserver === 'undefined') {
    return
  }
  scrollbarResizeObserver = new ResizeObserver(() => {
    updateVScrollbarWidth()
  })
  scrollbarResizeObserver.observe(ta)
}

const unobserveScrollbarWidth = () => {
  if (scrollbarResizeObserver) {
    scrollbarResizeObserver.disconnect()
    scrollbarResizeObserver = null
  }
}

const hasText = ref(false)

// Show clear button when there is text
const showClearButton = computed(() => hasText.value)

// Initialize autocomplete with direct ref access
useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true, node: props.node }
)

// Picks from the field go to the node's LoRA list, which prompt widgets lack.
const showSearchField = computed(() => (props.modelType ?? 'loras') === 'loras')

// A second binding of the same autocomplete class: same dropdown, request and
// added/off cue. `pickIntoNode` routes a pick to the node's list instead of
// writing a tag into the element being typed in.
const searchInputRef = ref<HTMLInputElement | null>(null)
useAutocomplete(searchInputRef, 'loras', {
  node: props.node,
  pickIntoNode: true,
  anchorToElement: true,
})

// Leaving the field drops the query, like a pick does, so the next click starts
// from the whole catalogue. The input event cancels any pending keystroke search
// and, with an empty term, keeps the dropdown from reopening.
const clearSearchField = () => {
  const field = searchInputRef.value
  if (!field) {
    return
  }
  field.value = ''
  field.dispatchEvent(new Event('input', { bubbles: true }))
}

const updateHasTextState = () => {
  hasText.value = textareaRef.value ? textareaRef.value.value.length > 0 : false
}

const onInput = (event: Event) => {
  // Content may grow/shrink past the overflow threshold on each edit.
  updateVScrollbarWidth()

  // A clear via execCommand captures the full-text selection in the browser's
  // undo entry; Ctrl+Z restores the content together with that selection.
  // Collapse the caret so the restored text is not left selected.
  if ((event as InputEvent).inputType === 'historyUndo') {
    const ta = textareaRef.value
    if (ta && ta.selectionStart === 0 && ta.selectionEnd === ta.value.length) {
      ta.setSelectionRange(ta.value.length, ta.value.length)
    }
  }

  // Update hasText state
  updateHasTextState()
  
  // Call widget callback when text changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }
}

// Handle external value changes (e.g., from "send lora to workflow")
const onExternalValueChange = () => {
  // The DOM value was set synchronously by the caller; the new content may
  // have toggled the vertical scrollbar on/off.
  updateVScrollbarWidth()
  updateHasTextState()
}

// Setup widget.onSetValue callback for external value changes
const setupWidgetOnSetValue = () => {
  if (props.widget) {
    props.widget.onSetValue = (value: string) => {
      // The DOM value is already set by setValue, just update our state
      hasText.value = value.length > 0
      // Programmatic sets can toggle the scrollbar; re-measure so the
      // corner clear button stays clear of it.
      updateVScrollbarWidth()
    }
  }
}

/**
 * Clear the textarea contents.
 *
 * Uses a trusted editing command (execCommand: select all + replace with
 * empty string) so the browser records the clear as an undoable edit —
 * Ctrl+Z with focus in the textarea restores the cleared text. Falls back
 * to a plain programmatic clear when execCommand is unavailable (e.g. jsdom
 * test environment), which is not undoable via native Ctrl+Z.
 */
const clearText = () => {
  const ta = textareaRef.value
  if (!ta || ta.value.length === 0) return

  // Select all + replace via a trusted edit command so the browser pushes an
  // undo entry that restores the full previous content.
  ta.focus()
  ta.setSelectionRange(0, ta.value.length)
  let ok = false
  try {
    // Guarded for engines without execCommand (jsdom); some engines also
    // throw instead of returning false for unsupported commands.
    ok = typeof document.execCommand === 'function' && document.execCommand('insertText', false, '')
  } catch {
    ok = false
  }

  if (ok) {
    // execCommand fired a trusted 'input' event → onInput already synced
    // hasText, called the widget callback, and notified the autocomplete.
    hasText.value = false
    return
  }

  // Fallback: execCommand unavailable (jsdom / unsupported browser) — plain
  // programmatic clear. The dispatched input event keeps onInput, the widget
  // callback, and the autocomplete in sync.
  ta.value = ''
  ta.dispatchEvent(new Event('input'))
}

onMounted(() => {
  // A DOM widget swallows the wheel, so the node would stop zooming under the
  // cursor. The shared helper (the LoRA list and tags widgets use it too) keeps
  // the wheel on the canvas: it forwards when the element cannot scroll and
  // leaves it alone when it can, which is what the prompt needs.
  forwardWheelToCanvas(textareaRef.value)
  if (searchInputRef.value) {
    forwardWheelToCanvas(searchInputRef.value)
  }

  // Register textarea reference with widget
  if (textareaRef.value) {
    props.widget.inputEl = textareaRef.value
    ;(textareaRef.value as any)._autocompleteHostWidget = props.widget
    ;(textareaRef.value as any)._autocompleteMetadataWidget = props.widget.metadataWidget
    ;(textareaRef.value as any)._autocompleteTextWidgetName = props.widget.name ?? 'text'

    // Also store on the container element for cloned widgets (subgraph promotion)
    // When widgets are promoted to subgraph nodes, the cloned widget shares the same
    // DOM element but has its own inputEl property. We store the reference on the
    // container so both original and cloned widgets can access it.
    const container = textareaRef.value.closest('[id^="autocomplete-text-widget-"]') as HTMLElement
    if (container && (container as any).__widgetInputEl) {
      (container as any).__widgetInputEl.inputEl = textareaRef.value
    }

    // Apply pending value from setValue if exists (workflow loading before Vue mount)
    const pendingValue = (props.widget as any)._pendingValue
    if (pendingValue !== undefined) {
      textareaRef.value.value = pendingValue
      hasText.value = pendingValue.length > 0
      delete (props.widget as any)._pendingValue
      // Dispatch event to notify autocomplete of value change
      textareaRef.value.dispatchEvent(new CustomEvent('lora-manager:autocomplete-value-changed', {
        detail: { value: pendingValue }
      }))
    }

    // Initialize hasText state (already done if pendingValue was applied, but safe to re-check)
    if (pendingValue === undefined) {
      hasText.value = textareaRef.value.value.length > 0
    }

    // Listen for external value change events from setValue
    textareaRef.value.addEventListener('lora-manager:autocomplete-value-changed', onExternalValueChange as EventListener)
  }

  // Setup callback for input changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }

  // Setup widget.onSetValue callback
  setupWidgetOnSetValue()

  // Keep the corner buttons clear of the textarea's vertical scrollbar.
  updateVScrollbarWidth()
  observeScrollbarWidth()

  // Listen for custom event dispatched by main.ts
  document.addEventListener('lora-manager:vue-mode-change', onModeChange)
})

onUnmounted(() => {
  unobserveScrollbarWidth()

  // Clean up textarea reference
  if (props.widget.inputEl === textareaRef.value) {
    props.widget.inputEl = undefined
  }
  
  // Remove external value change event listener
  if (textareaRef.value) {
    delete (textareaRef.value as any)._autocompleteHostWidget
    delete (textareaRef.value as any)._autocompleteMetadataWidget
    delete (textareaRef.value as any)._autocompleteTextWidgetName
    textareaRef.value.removeEventListener('lora-manager:autocomplete-value-changed', onExternalValueChange as EventListener)
  }
  
  // Clean up onSetValue callback
  if (props.widget) {
    props.widget.onSetValue = undefined
  }

  // Remove event listener
  document.removeEventListener('lora-manager:vue-mode-change', onModeChange)
})
</script>

<style scoped>
.autocomplete-text-widget {
  background: transparent;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.input-wrapper {
  position: relative;
  flex: 1;
  display: flex;
  width: 100%;
  /* The widget slot is shorter than the textarea's min-content height; without
     this the wrapper keeps its full height and pushes the search strip out. */
  min-height: 0;
}

/* Theme tokens (--lm-*) come from the widget container, which ComfyUI's
   renderer switches between the canvas widget palette and the Vue node
   widget palette. Text size matches ComfyUI's own textarea in both modes. */
.text-input {
  flex: 1;
  width: 100%;
  min-height: 0;
  background-color: var(--lm-surface);
  color: var(--lm-fg);
  overflow: hidden;
  overflow-y: auto;
  padding: 2px 2px 24px 2px;  /* Reserve bottom space for clear button */
  border: none;
  border-radius: 0;
  box-sizing: border-box;
  font-size: var(--comfy-textarea-font-size, 10px);
  font-family: monospace;
  /* resize:none set here (0,2,0). Overridden to vertical in app mode
     by the :global(.\[\&_textarea\]\:resize-y) .text-input rule below. */
  resize: none;
}

/* Vue DOM mode: same surface/foreground as the built-in WidgetTextarea,
   only the box metrics differ. */
.text-input.vue-dom-mode {
  padding: 8px 12px 30px 12px;  /* Reserve bottom space for clear button */
  margin: 0 0 4px;
  border-radius: 6px;  /* matches ComfyUI's rounded-md textarea */
  font-family: inherit;
}

.text-input:focus {
  outline: none;
}

/* Clear button styles */
.clear-button {
  position: absolute;
  right: calc(6px + var(--lm-vscrollbar-width, 0px));
  bottom: 6px;  /* Changed from top to bottom */
  width: 18px;
  height: 18px;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 50%;
  background: color-mix(in srgb, var(--lm-fg) 28%, transparent);
  color: var(--lm-fg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;  /* Hidden by default */
  pointer-events: none;  /* Not clickable when hidden */
  transition: opacity 0.2s ease, background-color 0.2s ease;
  z-index: 10;
}

/* Show clear button when hovering over input wrapper */
.input-wrapper:hover .clear-button {
  opacity: 0.7;
  pointer-events: auto;
}

.clear-button:hover {
  opacity: 1;
  background: var(--lm-danger-soft);
  color: var(--lm-danger-text);
}

.clear-button svg {
  width: 12px;
  height: 12px;
}

/* Vue DOM mode adjustments for clear button */
.text-input.vue-dom-mode ~ .clear-button {
  right: calc(8px + var(--lm-vscrollbar-width, 0px));
  bottom: 10px;  /* Changed from top to bottom, adjusted for Vue DOM padding */
  width: 20px;
  height: 20px;
}

.text-input.vue-dom-mode ~ .clear-button svg {
  width: 14px;
  height: 14px;
}

/* Search field: its own place to click and type, so adding a LoRA never
   needs a caret placed inside the prompt. It sits as the widget's first row
   and the layout reserves its height (see applyAutocompleteTextLayoutFix), so
   the prompt keeps its full size instead of being squeezed. */
.lora-search-row {
  flex: 0 0 18px;
  height: 18px;
  margin: 2px 2px 6px 2px;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}

.lora-search-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 18px;
  box-sizing: border-box;
  padding: 0 6px;
  /* Same surface, border and radius as the prompt box and the LoRA list, so
     the three blocks on the node read as one family. */
  border: 1px solid var(--lm-border-soft);
  border-radius: 6px;
  background-color: var(--lm-surface);
  color: var(--lm-fg);
  font-family: inherit;
  font-size: var(--comfy-textarea-font-size, 10px);
  line-height: 16px;
  outline: none;
}

.lora-search-input::placeholder {
  color: color-mix(in srgb, var(--lm-fg) 55%, transparent);
}

.lora-search-input:focus {
  border-color: color-mix(in srgb, var(--lm-fg) 45%, transparent);
}

</style>

<!--
  Non-scoped !important override: scoped .text-input[data-v-xxx] (0,2,0)
  beats the app-mode Tailwind rule (0,1,1), so we use !important here to
  force resize:vertical only when inside the app-mode widget list.
  The data-testid attribute scoping prevents it from leaking into graph
  mode.  This is the only !important in the widget stylesheets.
-->
<style>
[data-testid="app-mode-widget-item"] textarea,
[data-testid="builder-widget-item"] textarea {
  resize: vertical !important;
}
</style>
