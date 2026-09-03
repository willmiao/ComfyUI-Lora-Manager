<template>
  <div class="autocomplete-text-widget">
    <div class="input-wrapper">
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
        title="Clear text"
        @click="clearText"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
      <button
        v-if="isLorasMode"
        type="button"
        class="active-filters-toggle"
        :class="{ 'is-active': activeFiltersEnabled }"
        :title="activeFiltersToggleTitle"
        @click="toggleActiveFiltersSearch"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useAutocomplete } from '@/composables/useAutocomplete'
// @ts-ignore - ComfyUI external module
import { LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID, SETTING_TOGGLED_EVENT_NAME, getLoraActiveFiltersAutocompletePreference, setLoraManagerSettingValue } from '../../../web/comfyui/settings.js'

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
}

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const hasText = ref(false)

// Show clear button when there is text
const showClearButton = computed(() => hasText.value)

// Active-filters search indicator (loras nodes only). Mirrors the
// loramanager.lora_active_filters_autocomplete setting so users can
// discover and toggle the /activefilters mode without opening the
// dropdown or the settings dialog.
const isLorasMode = (props.modelType ?? 'loras') === 'loras'
const activeFiltersEnabled = ref(false)

const refreshActiveFiltersState = () => {
  if (isLorasMode) {
    activeFiltersEnabled.value = getLoraActiveFiltersAutocompletePreference()
  }
}

const onSettingToggled = (event: Event) => {
  const detail = (event as CustomEvent<{ settingId?: string; value?: unknown }>).detail
  if (detail?.settingId === LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID) {
    activeFiltersEnabled.value = detail.value === true
  }
}

const activeFiltersToggleTitle = computed(() =>
  activeFiltersEnabled.value
    ? 'Active Filters Search is ON: suggestions respect the LoRA Manager page filters. Click to disable, or type /noactivefilters.'
    : 'Active Filters Search is OFF: suggestions search the full library. Click to enable, or type /activefilters.'
)

const toggleActiveFiltersSearch = async () => {
  const newValue = !activeFiltersEnabled.value
  try {
    const success = await setLoraManagerSettingValue(
      LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID,
      newValue
    )
    if (!success) {
      throw new Error('settings API unavailable')
    }
    activeFiltersEnabled.value = newValue
  } catch (error) {
    console.error('[Lora Manager] Failed to toggle active filters search:', error)
  }
}

// Initialize autocomplete with direct ref access
useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true }
)

const updateHasTextState = () => {
  hasText.value = textareaRef.value ? textareaRef.value.value.length > 0 : false
}

const onInput = (event: Event) => {
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
  updateHasTextState()
}

// Setup widget.onSetValue callback for external value changes
const setupWidgetOnSetValue = () => {
  if (props.widget) {
    props.widget.onSetValue = (value: string) => {
      // The DOM value is already set by setValue, just update our state
      hasText.value = value.length > 0
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

  // Active-filters indicator: read initial state and stay in sync with
  // slash-command / context-menu toggles dispatched via settings.js
  refreshActiveFiltersState()
  window.addEventListener(SETTING_TOGGLED_EVENT_NAME, onSettingToggled)

  // Listen for custom event dispatched by main.ts
  document.addEventListener('lora-manager:vue-mode-change', onModeChange)
})

onUnmounted(() => {
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
  window.removeEventListener(SETTING_TOGGLED_EVENT_NAME, onSettingToggled)
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

/* Canvas mode styles (default) - matches built-in comfy-multiline-input */
.text-input {
  flex: 1;
  width: 100%;
  background-color: var(--comfy-input-bg, #222);
  color: var(--input-text, #ddd);
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

/* Vue DOM mode styles - matches built-in p-textarea in Vue DOM mode */
.text-input.vue-dom-mode {
  background-color: var(--color-charcoal-400, #313235);
  color: #fff;
  padding: 8px 12px 30px 12px;  /* Reserve bottom space for clear button */
  margin: 0 0 4px;
  border-radius: 8px;
  font-size: 12px;
  font-family: inherit;
}

.text-input:focus {
  outline: none;
}

/* Clear button styles */
.clear-button {
  position: absolute;
  right: 6px;
  bottom: 6px;  /* Changed from top to bottom */
  width: 18px;
  height: 18px;
  padding: 0;
  margin: 0;
  border: none;
  border-radius: 50%;
  background: rgba(128, 128, 128, 0.5);
  color: #fff;
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
  background: rgba(255, 100, 100, 0.8);
}

.clear-button svg {
  width: 12px;
  height: 12px;
}

/* Active-filters search indicator (loras nodes only) */
.active-filters-toggle {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 16px;
  height: 16px;
  padding: 2px;
  margin: 0;
  border: none;
  border-radius: 4px;
  background: rgba(128, 128, 128, 0.25);
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
  transition: opacity 0.2s ease, background-color 0.2s ease, color 0.2s ease;
  z-index: 10;
}

.active-filters-toggle:hover {
  opacity: 1;
  background: rgba(128, 128, 128, 0.45);
  color: rgba(255, 255, 255, 0.85);
}

.active-filters-toggle.is-active {
  background: rgba(59, 130, 246, 0.35);
  color: #7db8ff;
  opacity: 1;
}

.active-filters-toggle svg {
  width: 11px;
  height: 11px;
}

/* Vue DOM mode adjustments for the indicator */
.text-input.vue-dom-mode ~ .active-filters-toggle {
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
}

.text-input.vue-dom-mode ~ .active-filters-toggle svg {
  width: 13px;
  height: 13px;
}

/* Vue DOM mode adjustments for clear button */
.text-input.vue-dom-mode ~ .clear-button {
  right: 8px;
  bottom: 10px;  /* Changed from top to bottom, adjusted for Vue DOM padding */
  width: 20px;
  height: 20px;
  background: rgba(107, 114, 128, 0.6);
}

.text-input.vue-dom-mode ~ .clear-button:hover {
  background: oklch(62% 0.18 25);
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
