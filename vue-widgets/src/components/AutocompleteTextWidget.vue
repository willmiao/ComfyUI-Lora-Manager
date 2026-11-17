<template>
  <div class="autocomplete-text-widget">
    <div
      ref="inputWrapperRef"
      class="input-wrapper"
      :style="{ '--lm-vscrollbar-width': vScrollbarWidth + 'px' }"
    >
      <textarea
        ref="textareaRef"
        :placeholder="placeholder"
        :spellcheck="spellcheck ?? false"
        :class="['text-input', { 'vue-dom-mode': isVueDomMode, 'lm-wheel-scrollable': isVueDomMode }]"
        :style="maxHeight && isVueDomMode ? { maxHeight: maxHeight + 'px' } : undefined"
        data-capture-wheel="true"
        @input="onInput"
        @wheel="onWheel"
      />
      <button
        v-if="showClearButton"
        type="button"
        class="clear-button"
        :title="clearButtonTitle"
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
import { LORA_PATTERN } from '../../../web/comfyui/utils.js'

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

// A LoRA widget's box is its node's LoRA list in tag form; a prompt widget's is
// free text. Only the former has LoRAs to keep when the box is cleared.
const isLoraTextWidget = computed(() => (props.modelType ?? 'loras') === 'loras')

// The LoRA widget's clear keeps the LoRAs that are switched on, so the tooltip
// says what it does instead of reading as "empty the box".
const clearButtonTitle = computed(() =>
  isLoraTextWidget.value ? 'Clear text, keeping enabled LoRAs' : 'Clear text'
)

// Initialize autocomplete with direct ref access
useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true, node: props.node }
)

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

/**
 * Handle mouse wheel events on the textarea.
 * Forwards the event to the ComfyUI canvas for zooming when the textarea has no scrollbar,
 * or handles pinch-to-zoom gestures.
 * 
 * Logic aligns with ComfyUI's built-in multiline widget:
 * src/renderer/extensions/vueNodes/widgets/composables/useStringWidget.ts
 */
const onWheel = (event: WheelEvent) => {
  const textarea = textareaRef.value
  if (!textarea) return

  // Track if we have a vertical scrollbar
  const canScrollY = textarea.scrollHeight > textarea.clientHeight
  const deltaX = event.deltaX
  const deltaY = event.deltaY
  const isHorizontal = Math.abs(deltaX) > Math.abs(deltaY)
  
  // Access ComfyUI app from global window
  const app = (window as any).app
  if (!app || !app.canvas || typeof app.canvas.processMouseWheel !== 'function') {
    return
  }

  // 1. Handle pinch-to-zoom (ctrlKey is true for pinch-to-zoom on most browsers)
  if (event.ctrlKey) {
    event.preventDefault()
    event.stopPropagation()
    app.canvas.processMouseWheel(event)
    return
  }

  // 2. Horizontal scroll: pass to canvas (textareas usually don't scroll horizontally)
  if (isHorizontal) {
    event.preventDefault()
    event.stopPropagation()
    app.canvas.processMouseWheel(event)
    return
  }

  // 3. Vertical scrolling:
  if (canScrollY) {
    // If the textarea is scrollable, let it handle the wheel event but stop propagation
    // to prevent the canvas from zooming while the user is trying to scroll the text
    event.stopPropagation()
  } else {
    // If the textarea is NOT scrollable, forward the wheel event to the canvas
    // so it can trigger zoom in/out
    event.preventDefault()
    app.canvas.processMouseWheel(event)
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
 * Names of the LoRAs this node currently has enabled.
 *
 * `active` is the LoRA list's own on/off flag; an entry without one is on by
 * default, matching the list widget. Returns null when the node carries no LoRA
 * list (prompt widgets, or a node whose list widget is not attached), which is
 * the case where the box holds nothing but text.
 */
const enabledLoraNames = (): Set<string> | null => {
  const loras = (props.node as { lorasWidget?: { value?: unknown } }).lorasWidget?.value
  if (!Array.isArray(loras)) return null
  const names = new Set<string>()
  for (const lora of loras) {
    const name = typeof lora?.name === 'string' ? lora.name : ''
    if (name && lora?.active !== false) names.add(name)
  }
  return names
}

/**
 * What a clear leaves behind in a LoRA widget's box: the tags of the LoRAs the
 * node has enabled, in the order they appear. Disabled entries and any prompt
 * text around them are dropped.
 *
 * The tag text is kept verbatim rather than reformatted, so a clear never
 * rewrites a strength the user typed; tags are matched by name the way
 * `mergeLoras` matches them, so everything kept survives the merge that the
 * widget callback runs next.
 */
const retainedLoraText = (text: string): string => {
  const enabled = enabledLoraNames()
  if (!enabled || enabled.size === 0) return ''
  const pattern = new RegExp(LORA_PATTERN.source, 'g')
  const kept: string[] = []
  let match = pattern.exec(text)
  while (match) {
    if (enabled.has(match[1])) kept.push(match[0])
    match = pattern.exec(text)
  }
  return kept.join(' ')
}

/**
 * Clear the textarea contents.
 *
 * On a LoRA widget the box is the node's LoRA list in tag form, so clearing it
 * outright takes the LoRAs that are switched on with it — the enabled ones stay
 * and only the disabled entries (and any other text) are dropped. Prompt
 * widgets have no list to keep, so they clear outright.
 *
 * Uses a trusted editing command (execCommand: select all + replace with the
 * retained text) so the browser records the clear as an undoable edit — Ctrl+Z
 * with focus in the textarea restores the cleared content. Falls back to a
 * plain programmatic write when execCommand is unavailable (e.g. jsdom test
 * environment), which is not undoable via native Ctrl+Z.
 */
const clearText = () => {
  const ta = textareaRef.value
  if (!ta || ta.value.length === 0) return

  const nextValue = isLoraTextWidget.value ? retainedLoraText(ta.value) : ''
  ta.focus()
  if (nextValue === ta.value) {
    // Only enabled LoRAs in the box: nothing to clear, so record no edit.
    return
  }

  // Select all + replace via a trusted edit command so the browser pushes an
  // undo entry that restores the full previous content.
  ta.setSelectionRange(0, ta.value.length)
  let ok = false
  try {
    // Guarded for engines without execCommand (jsdom); some engines also
    // throw instead of returning false for unsupported commands.
    ok = typeof document.execCommand === 'function' && document.execCommand('insertText', false, nextValue)
  } catch {
    ok = false
  }

  if (ok) {
    // execCommand fired a trusted 'input' event → onInput already synced
    // hasText, called the widget callback, and notified the autocomplete.
    hasText.value = nextValue.length > 0
    return
  }

  // Fallback: execCommand unavailable (jsdom / unsupported browser) — plain
  // programmatic write. The dispatched input event keeps onInput, the widget
  // callback, and the autocomplete in sync.
  ta.value = nextValue
  ta.dispatchEvent(new Event('input'))
}

onMounted(() => {
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
}

/* Theme tokens (--lm-*) come from the widget container, which ComfyUI's
   renderer switches between the canvas widget palette and the Vue node
   widget palette. Text size matches ComfyUI's own textarea in both modes. */
.text-input {
  flex: 1;
  width: 100%;
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
