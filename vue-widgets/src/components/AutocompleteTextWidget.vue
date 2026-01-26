<template>
  <div class="autocomplete-text-widget">
    <textarea
      ref="textareaRef"
      :placeholder="placeholder"
      :spellcheck="spellcheck ?? false"
      :class="['text-input', { 'vue-dom-mode': isVueDomMode }]"
      @input="onInput"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAutocomplete } from '@/composables/useAutocomplete'

// Access LiteGraph global for initial mode detection
declare const LiteGraph: { vueNodesMode?: boolean } | undefined

export interface AutocompleteTextWidgetInterface {
  inputEl?: HTMLTextAreaElement
  callback?: (v: string) => void
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

// Initialize autocomplete with direct ref access
useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true }
)

const onInput = () => {
  // Call widget callback when text changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }
}

onMounted(() => {
  // Register textarea reference with widget
  if (textareaRef.value) {
    props.widget.inputEl = textareaRef.value
  }

  // Setup callback for input changes
  if (textareaRef.value && typeof props.widget.callback === 'function') {
    props.widget.callback(textareaRef.value.value)
  }

  // Listen for custom event dispatched by main.ts
  document.addEventListener('lora-manager:vue-mode-change', onModeChange)
})

onUnmounted(() => {
  // Clean up textarea reference
  if (props.widget.inputEl === textareaRef.value) {
    props.widget.inputEl = undefined
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
</style>
