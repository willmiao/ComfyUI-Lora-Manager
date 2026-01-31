import { ref, watch, computed } from 'vue'
import type { ComponentWidget, CyclerConfig, LoraPoolConfig } from './types'

export interface CyclerLoraItem {
  file_name: string
  model_name: string
}

export function useLoraCyclerState(widget: ComponentWidget<CyclerConfig>) {
  // Flag to prevent infinite loops during config restoration
  // callback → restoreFromConfig → watch → widget.value = config → callback → ...
  let isRestoring = false

  // State refs
  const currentIndex = ref(1)  // 1-based
  const totalCount = ref(0)
  const poolConfigHash = ref('')
  const modelStrength = ref(1.0)
  const clipStrength = ref(1.0)
  const useCustomClipRange = ref(false)
  const sortBy = ref<'filename' | 'model_name'>('filename')
  const currentLoraName = ref('')
  const currentLoraFilename = ref('')
  const isLoading = ref(false)

  // Dual-index mechanism for batch queue synchronization
  // execution_index: index for generating execution_stack (= previous next_index)
  // next_index: index for UI display (= what will be shown after execution)
  const executionIndex = ref<number | null>(null)
  const nextIndex = ref<number | null>(null)

  // Advanced index control features
  const repeatCount = ref(1)        // How many times each LoRA should repeat
  const repeatUsed = ref(0)         // How many times current index has been used (internal tracking)
  const displayRepeatUsed = ref(0)  // For UI display, deferred updates like currentIndex
  const isPaused = ref(false)       // Whether iteration is paused

  // Execution progress tracking (visual feedback)
  const isWorkflowExecuting = ref(false)    // Workflow is currently running
  const executingRepeatStep = ref(0)        // Which repeat step (1-based, 0 = not executing)

  // Build config object from current state
  const buildConfig = (): CyclerConfig => {
    // Skip updating widget.value during restoration to prevent infinite loops
    if (isRestoring) {
      return {
        current_index: currentIndex.value,
        total_count: totalCount.value,
        pool_config_hash: poolConfigHash.value,
        model_strength: modelStrength.value,
        clip_strength: clipStrength.value,
        use_same_clip_strength: !useCustomClipRange.value,
        sort_by: sortBy.value,
        current_lora_name: currentLoraName.value,
        current_lora_filename: currentLoraFilename.value,
        execution_index: executionIndex.value,
        next_index: nextIndex.value,
        repeat_count: repeatCount.value,
        repeat_used: repeatUsed.value,
        is_paused: isPaused.value,
      }
    }
    return {
      current_index: currentIndex.value,
      total_count: totalCount.value,
      pool_config_hash: poolConfigHash.value,
      model_strength: modelStrength.value,
      clip_strength: clipStrength.value,
      use_same_clip_strength: !useCustomClipRange.value,
      sort_by: sortBy.value,
      current_lora_name: currentLoraName.value,
      current_lora_filename: currentLoraFilename.value,
      execution_index: executionIndex.value,
      next_index: nextIndex.value,
      repeat_count: repeatCount.value,
      repeat_used: repeatUsed.value,
      is_paused: isPaused.value,
    }
  }

  // Restore state from config object
  const restoreFromConfig = (config: CyclerConfig) => {
    // Set flag to prevent buildConfig from triggering widget.value updates during restoration
    isRestoring = true

    try {
      currentIndex.value = config.current_index || 1
      totalCount.value = config.total_count || 0
      poolConfigHash.value = config.pool_config_hash || ''
      modelStrength.value = config.model_strength ?? 1.0
      clipStrength.value = config.clip_strength ?? 1.0
      useCustomClipRange.value = !(config.use_same_clip_strength ?? true)
      sortBy.value = config.sort_by || 'filename'
      currentLoraName.value = config.current_lora_name || ''
      currentLoraFilename.value = config.current_lora_filename || ''
      // Advanced index control features
      repeatCount.value = config.repeat_count ?? 1
      repeatUsed.value = config.repeat_used ?? 0
      isPaused.value = config.is_paused ?? false
      // Note: execution_index and next_index are not restored from config
      // as they are transient values used only during batch execution
    } finally {
      isRestoring = false
    }
  }

  // Shift indices for batch queue synchronization
  // Previous next_index becomes current execution_index, and generate a new next_index
  const generateNextIndex = () => {
    executionIndex.value = nextIndex.value  // Previous next becomes current execution
    // Calculate the next index (wrap to 1 if at end)
    const current = executionIndex.value ?? currentIndex.value
    let next = current + 1
    if (totalCount.value > 0 && next > totalCount.value) {
      next = 1
    }
    nextIndex.value = next
  }

  // Initialize next_index for first execution (execution_index stays null)
  const initializeNextIndex = () => {
    if (nextIndex.value === null) {
      // First execution uses current_index, so next is current + 1
      let next = currentIndex.value + 1
      if (totalCount.value > 0 && next > totalCount.value) {
        next = 1
      }
      nextIndex.value = next
    }
  }

  // Generate hash from pool config for change detection
  const hashPoolConfig = (poolConfig: LoraPoolConfig | null): string => {
    if (!poolConfig || !poolConfig.filters) {
      return ''
    }
    try {
      return btoa(JSON.stringify(poolConfig.filters))
    } catch {
      return ''
    }
  }

  // Fetch cycler list from API
  const fetchCyclerList = async (
    poolConfig: LoraPoolConfig | null
  ): Promise<CyclerLoraItem[]> => {
    try {
      isLoading.value = true

      const requestBody: Record<string, unknown> = {
        sort_by: sortBy.value,
      }

      if (poolConfig?.filters) {
        requestBody.pool_config = poolConfig.filters
      }

      const response = await fetch('/api/lm/loras/cycler-list', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || 'Failed to fetch cycler list')
      }

      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to get cycler list')
      }

      return data.loras || []
    } catch (error) {
      console.error('[LoraCyclerState] Error fetching cycler list:', error)
      throw error
    } finally {
      isLoading.value = false
    }
  }

  // Refresh list and update state
  const refreshList = async (poolConfig: LoraPoolConfig | null) => {
    try {
      const newHash = hashPoolConfig(poolConfig)
      const hashChanged = newHash !== poolConfigHash.value

      // Fetch the list
      const loraList = await fetchCyclerList(poolConfig)

      // Update total count
      totalCount.value = loraList.length

      // If pool config changed, reset index to 1
      if (hashChanged) {
        currentIndex.value = 1
        poolConfigHash.value = newHash
      }

      // Clamp index to valid range
      if (currentIndex.value > totalCount.value) {
        currentIndex.value = Math.max(1, totalCount.value)
      }

      // Update current LoRA info
      if (loraList.length > 0 && currentIndex.value > 0) {
        const currentLora = loraList[currentIndex.value - 1]
        if (currentLora) {
          currentLoraName.value = sortBy.value === 'filename' 
            ? currentLora.file_name 
            : (currentLora.model_name || currentLora.file_name)
          currentLoraFilename.value = currentLora.file_name
        }
      } else {
        currentLoraName.value = ''
        currentLoraFilename.value = ''
      }

      return loraList
    } catch (error) {
      console.error('[LoraCyclerState] Error refreshing list:', error)
      throw error
    }
  }

  // Set index manually
  const setIndex = (index: number) => {
    if (index >= 1 && index <= totalCount.value) {
      currentIndex.value = index
    }
  }

  // Reset index to 1 and clear repeat state
  const resetIndex = () => {
    currentIndex.value = 1
    repeatUsed.value = 0
    displayRepeatUsed.value = 0
    // Note: isPaused is intentionally not reset - user may want to stay paused after reset
  }

  // Toggle pause state
  const togglePause = () => {
    isPaused.value = !isPaused.value
  }

  // Computed property to check if clip strength is disabled
  const isClipStrengthDisabled = computed(() => !useCustomClipRange.value)

  // Watch model strength changes to sync with clip strength when not using custom range
  watch(modelStrength, (newValue) => {
    if (!useCustomClipRange.value) {
      clipStrength.value = newValue
    }
  })

  // Watch all state changes and update widget value
  watch([
    currentIndex,
    totalCount,
    poolConfigHash,
    modelStrength,
    clipStrength,
    useCustomClipRange,
    sortBy,
    currentLoraName,
    currentLoraFilename,
    repeatCount,
    repeatUsed,
    isPaused,
  ], () => {
    widget.value = buildConfig()
  }, { deep: true })

  return {
    // State refs
    currentIndex,
    totalCount,
    poolConfigHash,
    modelStrength,
    clipStrength,
    useCustomClipRange,
    sortBy,
    currentLoraName,
    currentLoraFilename,
    isLoading,
    executionIndex,
    nextIndex,
    repeatCount,
    repeatUsed,
    displayRepeatUsed,
    isPaused,
    isWorkflowExecuting,
    executingRepeatStep,

    // Computed
    isClipStrengthDisabled,

    // Methods
    buildConfig,
    restoreFromConfig,
    hashPoolConfig,
    fetchCyclerList,
    refreshList,
    setIndex,
    generateNextIndex,
    initializeNextIndex,
    resetIndex,
    togglePause,
  }
}
