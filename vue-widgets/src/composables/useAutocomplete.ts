import { ref, onMounted, onUnmounted, type Ref } from 'vue'

// Dynamic import type for AutoComplete class. The element is the prompt
// textarea for the text widget, or its search field input.
type AutoCompleteClass = new (
  inputElement: HTMLTextAreaElement | HTMLInputElement,
  modelType: 'loras' | 'prompt',
  options?: AutocompleteOptions
) => AutoCompleteInstance

interface AutocompleteOptions {
  maxItems?: number
  minChars?: number
  debounceDelay?: number
  showPreview?: boolean
  // LiteGraph node owning the textarea; the autocomplete reads its LoRA list
  // to mark results that are already added.
  node?: unknown
  // Route a pick to the node's LoRA list instead of inserting a tag into the
  // element the autocomplete is bound to.
  pickIntoNode?: boolean
  // Anchor the dropdown to the input element (left edge, full width) instead
  // of following the caret, so typing does not drag it to the right.
  anchorToElement?: boolean
}

interface AutoCompleteInstance {
  destroy: () => void
  isValid: () => boolean
  refreshCaretHelper: () => void
}

export function useAutocomplete(
  textareaRef: Ref<HTMLTextAreaElement | HTMLInputElement | null>,
  modelType: 'loras' | 'prompt' = 'loras',
  options: AutocompleteOptions = {}
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
