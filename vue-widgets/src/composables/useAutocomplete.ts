import { ref, onMounted, onUnmounted, type Ref } from 'vue'

// Dynamic import type for AutoComplete class
type AutoCompleteClass = new (
  inputElement: HTMLTextAreaElement,
  modelType: 'loras' | 'embeddings' | 'custom_words' | 'prompt',
  options?: AutocompleteOptions
) => AutoCompleteInstance

interface AutocompleteOptions {
  maxItems?: number
  minChars?: number
  debounceDelay?: number
  showPreview?: boolean
}

interface AutoCompleteInstance {
  destroy: () => void
  isValid: () => boolean
  refreshCaretHelper: () => void
}

export interface UseAutocompleteOptions {
  showPreview?: boolean
  maxItems?: number
  minChars?: number
  debounceDelay?: number
}

export function useAutocomplete(
  textareaRef: Ref<HTMLTextAreaElement | null>,
  modelType: 'loras' | 'embeddings' | 'custom_words' | 'prompt' = 'loras',
  options: UseAutocompleteOptions = {}
) {
  const autocompleteInstance = ref<AutoCompleteInstance | null>(null)
  const isInitialized = ref(false)

  const defaultOptions: AutocompleteOptions = {
    maxItems: 20,
    minChars: 1,
    debounceDelay: 200,
    showPreview: true,
    ...options
  }

  const initAutocomplete = async () => {
    if (!textareaRef.value) {
      console.warn('[useAutocomplete] Textarea ref is null, cannot initialize')
      return
    }

    if (autocompleteInstance.value) {
      console.log('[useAutocomplete] Already initialized, skipping')
      return
    }

    try {
      // Dynamically import the AutoComplete class
      const module = await import(/* @vite-ignore */ `${'../autocomplete.js'}`)
      const AutoComplete: AutoCompleteClass = module.AutoComplete

      autocompleteInstance.value = new AutoComplete(
        textareaRef.value,
        modelType,
        defaultOptions
      )
      isInitialized.value = true
      console.log(`[useAutocomplete] Initialized for ${modelType}`)
    } catch (error) {
      console.error('[useAutocomplete] Failed to initialize:', error)
    }
  }

  const destroyAutocomplete = () => {
    if (autocompleteInstance.value) {
      autocompleteInstance.value.destroy()
      autocompleteInstance.value = null
      isInitialized.value = false
      console.log('[useAutocomplete] Destroyed')
    }
  }

  const refreshCaretHelper = () => {
    if (autocompleteInstance.value) {
      autocompleteInstance.value.refreshCaretHelper()
    }
  }

  onMounted(() => {
    // Initialize autocomplete after component is mounted
    // Use nextTick-like delay to ensure DOM is fully ready
    setTimeout(() => {
      initAutocomplete()
    }, 0)
  })

  onUnmounted(() => {
    destroyAutocomplete()
  })

  return {
    autocompleteInstance,
    isInitialized,
    initAutocomplete,
    destroyAutocomplete,
    refreshCaretHelper
  }
}

export type UseAutocompleteReturn = ReturnType<typeof useAutocomplete>
