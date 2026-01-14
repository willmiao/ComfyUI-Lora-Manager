import { ref, computed, watch } from 'vue'
import type { ComponentWidget, RandomizerConfig, LoraEntry } from './types'

export function useLoraRandomizerState(widget: ComponentWidget) {
  // State refs
  const countMode = ref<'fixed' | 'range'>('range')
  const countFixed = ref(3)
  const countMin = ref(2)
  const countMax = ref(5)
  const modelStrengthMin = ref(0.0)
  const modelStrengthMax = ref(1.0)
  const useCustomClipRange = ref(false)
  const clipStrengthMin = ref(0.0)
  const clipStrengthMax = ref(1.0)
  const rollMode = ref<'fixed' | 'always'>('fixed')
  const isRolling = ref(false)
  const useRecommendedStrength = ref(false)
  const recommendedStrengthScaleMin = ref(0.5)
  const recommendedStrengthScaleMax = ref(1.0)

  // Track last used combination (for backend roll mode)
  const lastUsed = ref<LoraEntry[] | null>(null)

  // Build config object from current state
  const buildConfig = (): RandomizerConfig => ({
    count_mode: countMode.value,
    count_fixed: countFixed.value,
    count_min: countMin.value,
    count_max: countMax.value,
    model_strength_min: modelStrengthMin.value,
    model_strength_max: modelStrengthMax.value,
    use_same_clip_strength: !useCustomClipRange.value,
    clip_strength_min: clipStrengthMin.value,
    clip_strength_max: clipStrengthMax.value,
    roll_mode: rollMode.value,
    last_used: lastUsed.value,
    use_recommended_strength: useRecommendedStrength.value,
    recommended_strength_scale_min: recommendedStrengthScaleMin.value,
    recommended_strength_scale_max: recommendedStrengthScaleMax.value,
  })

  // Restore state from config object
  const restoreFromConfig = (config: RandomizerConfig) => {
    countMode.value = config.count_mode || 'range'
    countFixed.value = config.count_fixed || 3
    countMin.value = config.count_min || 2
    countMax.value = config.count_max || 5
    modelStrengthMin.value = config.model_strength_min ?? 0.0
    modelStrengthMax.value = config.model_strength_max ?? 1.0
    useCustomClipRange.value = !(config.use_same_clip_strength ?? true)
    clipStrengthMin.value = config.clip_strength_min ?? 0.0
    clipStrengthMax.value = config.clip_strength_max ?? 1.0
    // Migrate old roll_mode values to new ones
    const rawRollMode = (config as any).roll_mode as string
    if (rawRollMode === 'frontend') {
      rollMode.value = 'fixed'
    } else if (rawRollMode === 'backend') {
      rollMode.value = 'always'
    } else if (rawRollMode === 'fixed' || rawRollMode === 'always') {
      rollMode.value = rawRollMode as 'fixed' | 'always'
    } else {
      rollMode.value = 'fixed'
    }
    lastUsed.value = config.last_used || null
    useRecommendedStrength.value = config.use_recommended_strength ?? false
    recommendedStrengthScaleMin.value = config.recommended_strength_scale_min ?? 0.5
    recommendedStrengthScaleMax.value = config.recommended_strength_scale_max ?? 1.0
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
        use_same_clip_strength: !useCustomClipRange.value,
        clip_strength_min: config.clip_strength_min,
        clip_strength_max: config.clip_strength_max,
        locked_loras: lockedLoras,
        use_recommended_strength: config.use_recommended_strength,
        recommended_strength_scale_min: config.recommended_strength_scale_min,
        recommended_strength_scale_max: config.recommended_strength_scale_max,
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
        requestBody.pool_config = poolConfig.filters || {}
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

  // Restore last used and return it
  const useLastUsed = () => {
    if (lastUsed.value && lastUsed.value.length > 0) {
      return lastUsed.value
    }
    return null
  }

  // Computed properties
  const isClipStrengthDisabled = computed(() => !useCustomClipRange.value)
  const isRecommendedStrengthEnabled = computed(() => useRecommendedStrength.value)

  // Watch all state changes and update widget value
  watch([
    countMode,
    countFixed,
    countMin,
    countMax,
    modelStrengthMin,
    modelStrengthMax,
    useCustomClipRange,
    clipStrengthMin,
    clipStrengthMax,
    rollMode,
    useRecommendedStrength,
    recommendedStrengthScaleMin,
    recommendedStrengthScaleMax,
  ], () => {
    const config = buildConfig()
    if (widget.updateConfig) {
      widget.updateConfig(config)
    } else {
      widget.value = config
    }
  }, { deep: true })

  return {
    // State refs
    countMode,
    countFixed,
    countMin,
    countMax,
    modelStrengthMin,
    modelStrengthMax,
    useCustomClipRange,
    clipStrengthMin,
    clipStrengthMax,
    rollMode,
    isRolling,
    lastUsed,
    useRecommendedStrength,
    recommendedStrengthScaleMin,
    recommendedStrengthScaleMax,

    // Computed
    isClipStrengthDisabled,
    isRecommendedStrengthEnabled,

    // Methods
    buildConfig,
    restoreFromConfig,
    rollLoras,
    useLastUsed,
  }
}
