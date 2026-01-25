<template>
  <div class="autocomplete-text-widget">
    <textarea
      ref="textareaRef"
      v-model="textValue"
      :placeholder="placeholder"
      :spellcheck="spellcheck ?? false"
      :class="['text-input', { 'vue-dom-mode': isVueDomMode }]"
      @input="onInput"
      @pointerdown.stop
      @pointermove.stop
      @pointerup.stop
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useAutocomplete } from '@/composables/useAutocomplete'

// Access LiteGraph global for initial mode detection
declare const LiteGraph: { vueNodesMode?: boolean } | undefined

export interface AutocompleteTextWidgetInterface {
  serializeValue?: () => Promise<string>
  value?: string
  onSetValue?: (v: string) => void
  callback?: (v: string) => void
}

const props = defineProps<{
  widget: AutocompleteTextWidgetInterface
  node: { id: number }
  modelType?: 'loras' | 'embeddings'
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

onMounted(() => {
  // Listen for custom event dispatched by main.ts
  document.addEventListener('lora-manager:vue-mode-change', onModeChange)
})

onUnmounted(() => {
  document.removeEventListener('lora-manager:vue-mode-change', onModeChange)
})

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const textValue = ref('')

// Initialize autocomplete with direct ref access
const { isInitialized } = useAutocomplete(
  textareaRef,
  props.modelType ?? 'loras',
  { showPreview: props.showPreview ?? true }
)

const onInput = () => {
  // Call widget callback when text changes
  if (typeof props.widget.callback === 'function') {
    props.widget.callback(textValue.value)
  }
}

onMounted(() => {
  // Setup serialization
  props.widget.serializeValue = async () => textValue.value

  // Handle external value updates (e.g., loading workflow, paste)
  props.widget.onSetValue = (v: string) => {
    if (v !== textValue.value) {
      textValue.value = v ?? ''
    }
  }

  // Restore from saved value if exists
  if (props.widget.value !== undefined && props.widget.value !== null) {
    textValue.value = props.widget.value
  }
})

// Watch for external value changes and sync
watch(
  () => props.widget.value,
  (newValue) => {
    if (newValue !== undefined && newValue !== textValue.value) {
      textValue.value = newValue ?? ''
    }
  }
)
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
  padding: 24px 12px 8px;
  margin: 0 0 4px;
  border-radius: 8px;
  font-size: 12px;
  font-family: inherit;
}

.text-input:focus {
  outline: none;
}
</style>
