<template>
  <div class="lora-randomizer-widget">
    <LoraRandomizerSettingsView
      :count-mode="state.countMode.value"
      :count-fixed="state.countFixed.value"
      :count-min="state.countMin.value"
      :count-max="state.countMax.value"
      :model-strength-min="state.modelStrengthMin.value"
      :model-strength-max="state.modelStrengthMax.value"
      :use-custom-clip-range="state.useCustomClipRange.value"
      :clip-strength-min="state.clipStrengthMin.value"
      :clip-strength-max="state.clipStrengthMax.value"
      :roll-mode="state.rollMode.value"
      :is-rolling="state.isRolling.value"
      :is-clip-strength-disabled="state.isClipStrengthDisabled.value"
      :last-used="state.lastUsed.value"
      :current-loras="currentLoras"
      :can-reuse-last="canReuseLast"
      :use-recommended-strength="state.useRecommendedStrength.value"
      :recommended-strength-scale-min="state.recommendedStrengthScaleMin.value"
      :recommended-strength-scale-max="state.recommendedStrengthScaleMax.value"
      @update:count-mode="state.countMode.value = $event"
      @update:count-fixed="state.countFixed.value = $event"
      @update:count-min="state.countMin.value = $event"
      @update:count-max="state.countMax.value = $event"
      @update:model-strength-min="state.modelStrengthMin.value = $event"
      @update:model-strength-max="state.modelStrengthMax.value = $event"
      @update:use-custom-clip-range="state.useCustomClipRange.value = $event"
      @update:clip-strength-min="state.clipStrengthMin.value = $event"
      @update:clip-strength-max="state.clipStrengthMax.value = $event"
      @update:roll-mode="state.rollMode.value = $event"
      @update:use-recommended-strength="state.useRecommendedStrength.value = $event"
      @update:recommended-strength-scale-min="state.recommendedStrengthScaleMin.value = $event"
      @update:recommended-strength-scale-max="state.recommendedStrengthScaleMax.value = $event"
      @generate-fixed="handleGenerateFixed"
      @always-randomize="handleAlwaysRandomize"
      @reuse-last="handleReuseLast"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue'
import LoraRandomizerSettingsView from './lora-randomizer/LoraRandomizerSettingsView.vue'
import { useLoraRandomizerState } from '../composables/useLoraRandomizerState'
import type { ComponentWidget, RandomizerConfig, LoraEntry } from '../composables/types'

type RandomizerWidget = ComponentWidget<RandomizerConfig>

// Props
const props = defineProps<{
  widget: RandomizerWidget
  node: { id: number; inputs?: any[]; widgets?: any[]; graph?: any }
}>()

// State management
const state = useLoraRandomizerState(props.widget)

// Symbol to track if the widget has been executed at least once
const HAS_EXECUTED = Symbol('HAS_EXECUTED')

// Track current loras from the loras widget
const currentLoras = ref<LoraEntry[]>([])

// Track if component is mounted to avoid early watch triggers
const isMounted = ref(false)

// Computed property to check if we can reuse last
const canReuseLast = computed(() => {
  const lastUsed = state.lastUsed.value
  if (!lastUsed || lastUsed.length === 0) return false
  return !areLorasEqual(currentLoras.value, lastUsed)
})

// Helper function to compare two lora lists
const areLorasEqual = (a: LoraEntry[], b: LoraEntry[]): boolean => {
  if (a.length !== b.length) return false
  const sortedA = [...a].sort((x, y) => x.name.localeCompare(y.name))
  const sortedB = [...b].sort((x, y) => x.name.localeCompare(y.name))
  return sortedA.every((lora, i) =>
    lora.name === sortedB[i].name &&
    lora.strength === sortedB[i].strength &&
    lora.clipStrength === sortedB[i].clipStrength
  )
}

// Handle "Generate Fixed" button click
const handleGenerateFixed = async () => {
  try {
    // Get pool config from connected pool_config input
    const poolConfig = (props.node as any).getPoolConfig?.() || null

    // Get locked loras from the loras widget
    const lorasWidget = props.node.widgets?.find((w: any) => w.name === "loras")
    const lockedLoras: LoraEntry[] = (lorasWidget?.value || []).filter((lora: LoraEntry) => lora.locked === true)

    // Call API to get random loras
    const randomLoras = await state.rollLoras(poolConfig, lockedLoras)

    // Update the loras widget with the new selection
    if (lorasWidget) {
      lorasWidget.value = randomLoras
      currentLoras.value = randomLoras
    }

    // Set roll mode to fixed
    state.rollMode.value = 'fixed'
  } catch (error) {
    console.error('[LoraRandomizerWidget] Error generating fixed LoRAs:', error)
    alert('Failed to generate LoRAs: ' + (error as Error).message)
  }
}

// Handle "Always Randomize" button click
const handleAlwaysRandomize = async () => {
  try {
    // Get pool config from connected pool_config input
    const poolConfig = (props.node as any).getPoolConfig?.() || null

    // Get locked loras from the loras widget
    const lorasWidget = props.node.widgets?.find((w: any) => w.name === "loras")
    const lockedLoras: LoraEntry[] = (lorasWidget?.value || []).filter((lora: LoraEntry) => lora.locked === true)

    // Call API to get random loras
    const randomLoras = await state.rollLoras(poolConfig, lockedLoras)

    // Update the loras widget with the new selection
    if (lorasWidget) {
      lorasWidget.value = randomLoras
      currentLoras.value = randomLoras
    }

    // Set roll mode to always
    state.rollMode.value = 'always'
  } catch (error) {
    console.error('[LoraRandomizerWidget] Error generating random LoRAs:', error)
    alert('Failed to generate LoRAs: ' + (error as Error).message)
  }
}

// Handle "Reuse Last" button click
const handleReuseLast = () => {
  const lastUsedLoras = state.useLastUsed()
  if (lastUsedLoras) {
    // Update the loras widget with the last used combination
    const lorasWidget = props.node.widgets?.find((w: any) => w.name === 'loras')
    if (lorasWidget) {
      lorasWidget.value = lastUsedLoras
      currentLoras.value = lastUsedLoras
    }

    // Switch to fixed mode
    state.rollMode.value = 'fixed'
  }
}

// Watch for changes to the loras widget to track current loras
watch(() => props.node.widgets?.find((w: any) => w.name === 'loras')?.value, (newVal) => {
  // Only update after component is mounted
  if (isMounted.value) {
    if (newVal && Array.isArray(newVal)) {
      currentLoras.value = newVal
    }
  }
}, { immediate: true, deep: true })

// Lifecycle
onMounted(async () => {
  // IMPORTANT: Save the current loras widget value BEFORE setting isMounted to true
  // This prevents the watch from overwriting an empty value
  const lorasWidget = props.node.widgets?.find((w: any) => w.name === 'loras')
  if (lorasWidget) {
    const currentWidgetValue = lorasWidget.value
    if (currentWidgetValue && Array.isArray(currentWidgetValue) && currentWidgetValue.length > 0) {
      currentLoras.value = currentWidgetValue
    }
  }

  // Mark component as mounted so watch can now respond to changes
  isMounted.value = true

  // Setup callback for external value updates (e.g., workflow load, undo/redo)
  // ComfyUI calls this automatically after setValue() in domWidget.ts
  props.widget.callback = (v: RandomizerConfig) => {
    if (v) {
      state.restoreFromConfig(v)
    }
  }

  // Restore from saved value if workflow was already loaded
  if (props.widget.value) {
    state.restoreFromConfig(props.widget.value)
  }

  // Add beforeQueued hook to handle seed shifting for batch queue synchronization
  // This ensures each execution uses the loras that were displayed before that execution
  ;(props.widget as any).beforeQueued = () => {
    // Only process when roll_mode is 'always' (randomize on each execution)
    if (state.rollMode.value === 'always') {
      if ((props.widget as any)[HAS_EXECUTED]) {
        // After first execution: shift seeds (previous next_seed becomes execution_seed)
        state.generateNewSeed()
      } else {
        // First execution: just initialize next_seed (execution_seed stays null)
        // This means first execution uses loras from widget input
        state.initializeNextSeed()
        ;(props.widget as any)[HAS_EXECUTED] = true
      }

      // Update the widget value so the seeds are included in the serialized config
      props.widget.value = state.buildConfig()
    }
  }

  // Override onExecuted to handle backend UI updates
  const originalOnExecuted = (props.node as any).onExecuted?.bind(props.node)

  ;(props.node as any).onExecuted = function(output: any) {
    console.log("[LoraRandomizerWidget] Node executed with output:", output)

    // Update last_used from backend
    if (output?.last_used !== undefined) {
      state.lastUsed.value = output.last_used
      console.log(`[LoraRandomizerWidget] Updated last_used: ${output.last_used ? output.last_used.length : 0} LoRAs`)
    }

    // Update loras widget if backend provided new loras
    const lorasWidget = props.node.widgets?.find((w: any) => w.name === 'loras')
    if (lorasWidget && output?.loras && Array.isArray(output.loras)) {
      console.log("[LoraRandomizerWidget] Received loras data from backend:", output.loras)
      lorasWidget.value = output.loras
      currentLoras.value = output.loras
    }

    // Call original onExecuted if it exists
    if (originalOnExecuted) {
      return originalOnExecuted(output)
    }
  }
})
</script>

<style scoped>
.lora-randomizer-widget {
  padding: 6px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 6px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
</style>
