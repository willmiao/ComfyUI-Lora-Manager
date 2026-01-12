import { ref, computed } from 'vue'
import type { ComponentWidget, RandomizerConfig, LoraEntry } from './types'

export function useLoraRandomizerState(widget: ComponentWidget) {
  // State refs
  const countMode = ref<'fixed' | 'range'>('range')
  const countFixed = ref(5)
  const countMin = ref(3)
  const countMax = ref(7)
  const modelStrengthMin = ref(0.0)
  const modelStrengthMax = ref(1.0)
  const useSameClipStrength = ref(true)
  const clipStrengthMin = ref(0.0)
  const clipStrengthMax = ref(1.0)
  const rollMode = ref<'frontend' | 'backend'>('frontend')
  const isRolling = ref(false)

  // Build config object from current state
  const buildConfig = (): RandomizerConfig => ({
    count_mode: countMode.value,
    count_fixed: countFixed.value,
    count_min: countMin.value,
    count_max: countMax.value,
    model_strength_min: modelStrengthMin.value,
    model_strength_max: modelStrengthMax.value,
    use_same_clip_strength: useSameClipStrength.value,
    clip_strength_min: clipStrengthMin.value,
    clip_strength_max: clipStrengthMax.value,
    roll_mode: rollMode.value,
  })

  // Restore state from config object
  const restoreFromConfig = (config: RandomizerConfig) => {
    countMode.value = config.count_mode || 'range'
    countFixed.value = config.count_fixed || 5
    countMin.value = config.count_min || 3
    countMax.value = config.count_max || 7
    modelStrengthMin.value = config.model_strength_min ?? 0.0
    modelStrengthMax.value = config.model_strength_max ?? 1.0
    useSameClipStrength.value = config.use_same_clip_strength ?? true
    clipStrengthMin.value = config.clip_strength_min ?? 0.0
    clipStrengthMax.value = config.clip_strength_max ?? 1.0
    rollMode.value = config.roll_mode || 'frontend'
  }

  // Roll loras - call API to get random selection
  const rollLoras = async (
    poolConfig: any | null,
    lockedLoras: LoraEntry[]
  ): Promise<LoraEntry[]> => {
    try {
      isRolling.value = true

      const config = buildConfig()

      // Build request body
      const requestBody: any = {
        model_strength_min: config.model_strength_min,
        model_strength_max: config.model_strength_max,
        use_same_clip_strength: config.use_same_clip_strength,
        clip_strength_min: config.clip_strength_min,
        clip_strength_max: config.clip_strength_max,
        locked_loras: lockedLoras,
      }

      // Add count parameters
      if (config.count_mode === 'fixed') {
        requestBody.count = config.count_fixed
      } else {
        requestBody.count_min = config.count_min
        requestBody.count_max = config.count_max
      }

      // Add pool config if provided
      if (poolConfig) {
        // Convert pool config to backend format
        requestBody.pool_config = {
          selected_base_models: poolConfig.filters?.baseModels || [],
          include_tags: poolConfig.filters?.tags?.include || [],
          exclude_tags: poolConfig.filters?.tags?.exclude || [],
          include_folders: poolConfig.filters?.folders?.include || [],
          exclude_folders: poolConfig.filters?.folders?.exclude || [],
          no_credit_required: poolConfig.filters?.license?.noCreditRequired || false,
          allow_selling: poolConfig.filters?.license?.allowSelling || false,
        }
      }

      // Call API endpoint
      const response = await fetch('/api/lm/loras/random-sample', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || 'Failed to fetch random LoRAs')
      }

      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to get random LoRAs')
      }

      return data.loras || []
    } catch (error) {
      console.error('[LoraRandomizerState] Error rolling LoRAs:', error)
      throw error
    } finally {
      isRolling.value = false
    }
  }

  // Computed properties
  const isClipStrengthDisabled = computed(() => useSameClipStrength.value)

  return {
    // State refs
    countMode,
    countFixed,
    countMin,
    countMax,
    modelStrengthMin,
    modelStrengthMax,
    useSameClipStrength,
    clipStrengthMin,
    clipStrengthMax,
    rollMode,
    isRolling,

    // Computed
    isClipStrengthDisabled,

    // Methods
    buildConfig,
    restoreFromConfig,
    rollLoras,
  }
}
