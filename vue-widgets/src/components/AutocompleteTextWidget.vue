<template>
  <div class="autocomplete-text-widget">
    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        :placeholder="placeholder"
        :spellcheck="spellcheck ?? false"
        :class="['text-input', { 'vue-dom-mode': isVueDomMode }]"
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

// Access LiteGraph global for initial mode detection
declare const LiteGraph: { vueNodesMode?: boolean } | undefined

export interface AutocompleteTextWidgetInterface {
  inputEl?: HTMLTextAreaElement
  callback?: (v: string) => void
  onSetValue?: (v: string) => void
}

const props = defineProps<{
  widget: AutocompleteTextWidgetInterface
  node: { id: number }
  modelType?: 'loras' | 'embeddings' | 'custom_words' | 'prompt'
  placeholder?: string
  showPreview?: boolean
  spellcheck?: boolean
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

// Initialize autocomplete with direct ref access
useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true }
)

const updateHasTextState = () => {
  hasText.value = textareaRef.value ? textareaRef.value.value.length > 0 : false
}

const onInput = () => {
  // Update hasText state
  updateHasTextState()
  
  // Call widget callback when text changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }
}

// Handle external value changes (e.g., from "send lora to workflow")
const onExternalValueChange = (event: CustomEvent<{ value: string }>) => {
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

const clearText = () => {
  if (textareaRef.value) {
    textareaRef.value.value = ''
    hasText.value = false
    textareaRef.value.focus()
    
    // Trigger callback with empty value
    if (typeof props.widget.callback === 'function') {
      props.widget.callback('')
    }
    
    // Dispatch input event to ensure autocomplete handles the change
    textareaRef.value.dispatchEvent(new Event('input'))
  }
}

onMounted(() => {
  // Register textarea reference with widget
  if (textareaRef.value) {
    props.widget.inputEl = textareaRef.value
    
    // Also store on the container element for cloned widgets (subgraph promotion)
    // When widgets are promoted to subgraph nodes, the cloned widget shares the same
    // DOM element but has its own inputEl property. We store the reference on the
    // container so both original and cloned widgets can access it.
    const container = textareaRef.value.closest('[id^="autocomplete-text-widget-"]') as HTMLElement
    if (container && (container as any).__widgetInputEl) {
      (container as any).__widgetInputEl.inputEl = textareaRef.value
    }
    
    // Initialize hasText state
    hasText.value = textareaRef.value.value.length > 0
    
    // Listen for external value change events from setValue
    textareaRef.value.addEventListener('lora-manager:autocomplete-value-changed', onExternalValueChange as EventListener)
  }

  // Setup callback for input changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }

  // Setup widget.onSetValue callback
  setupWidgetOnSetValue()

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

/* Canvas mode styles (default) - matches built-in comfy-multiline-input */
.text-input {
  flex: 1;
  width: 100%;
  background-color: var(--comfy-input-bg, #222);
  color: var(--input-text, #ddd);
  overflow: hidden;
  overflow-y: auto;
  padding: 2px;
  resize: none;
  border: none;
  border-radius: 0;
  box-sizing: border-box;
  font-size: var(--comfy-textarea-font-size, 10px);
  font-family: monospace;
}

/* Vue DOM mode styles - matches built-in p-textarea in Vue DOM mode */
.text-input.vue-dom-mode {
  background-color: var(--color-charcoal-400, #313235);
  color: #fff;
  padding: 8px 12px;
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
  right: 4px;
  top: 4px;
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
  opacity: 0.7;
  transition: opacity 0.2s ease, background-color 0.2s ease;
  z-index: 10;
}

.clear-button:hover {
  opacity: 1;
  background: rgba(255, 100, 100, 0.8);
}

.clear-button svg {
  width: 12px;
  height: 12px;
}

/* Vue DOM mode adjustments for clear button */
.text-input.vue-dom-mode ~ .clear-button {
  right: 8px;
  top: 8px;
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
