<template>
  <div class="lora-randomizer-widget">
    <LoraRandomizerSettingsView
      :count-mode="state.countMode.value"
      :count-fixed="state.countFixed.value"
      :count-min="state.countMin.value"
      :count-max="state.countMax.value"
      :model-strength-min="state.modelStrengthMin.value"
      :model-strength-max="state.modelStrengthMax.value"
      :use-same-clip-strength="state.useSameClipStrength.value"
      :clip-strength-min="state.clipStrengthMin.value"
      :clip-strength-max="state.clipStrengthMax.value"
      :roll-mode="state.rollMode.value"
      :is-rolling="state.isRolling.value"
      :is-clip-strength-disabled="state.isClipStrengthDisabled.value"
      @update:count-mode="state.countMode.value = $event"
      @update:count-fixed="state.countFixed.value = $event"
      @update:count-min="state.countMin.value = $event"
      @update:count-max="state.countMax.value = $event"
      @update:model-strength-min="state.modelStrengthMin.value = $event"
      @update:model-strength-max="state.modelStrengthMax.value = $event"
      @update:use-same-clip-strength="state.useSameClipStrength.value = $event"
      @update:clip-strength-min="state.clipStrengthMin.value = $event"
      @update:clip-strength-max="state.clipStrengthMax.value = $event"
      @update:roll-mode="state.rollMode.value = $event"
      @roll="handleRoll"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import LoraRandomizerSettingsView from './lora-randomizer/LoraRandomizerSettingsView.vue'
import { useLoraRandomizerState } from '../composables/useLoraRandomizerState'
import type { ComponentWidget, RandomizerConfig } from '../composables/types'

// Props
const props = defineProps<{
  widget: ComponentWidget
  node: { id: number }
}>()

// State management
const state = useLoraRandomizerState(props.widget)

// Handle roll button click
const handleRoll = async () => {
  try {
    console.log('[LoraRandomizerWidget] Roll button clicked')

    // Get pool config from connected input (if any)
    // This would need to be passed from the node's pool_config input
    const poolConfig = null // TODO: Get from node input if connected

    // Get locked loras from the loras widget
    // This would need to be retrieved from the loras widget on the node
    const lockedLoras: any[] = [] // TODO: Get from loras widget

    // Call API to get random loras
    const randomLoras = await state.rollLoras(poolConfig, lockedLoras)

    console.log('[LoraRandomizerWidget] Got random LoRAs:', randomLoras)

    // Update the loras widget with the new selection
    // This will be handled by emitting an event or directly updating the loras widget
    // For now, we'll emit a custom event that the parent widget handler can catch
    if (typeof (props.widget as any).onRoll === 'function') {
      (props.widget as any).onRoll(randomLoras)
    }
  } catch (error) {
    console.error('[LoraRandomizerWidget] Error rolling LoRAs:', error)
    alert('Failed to roll LoRAs: ' + (error as Error).message)
  }
}

// Lifecycle
onMounted(async () => {
  // Setup serialization
  props.widget.serializeValue = async () => {
    const config = state.buildConfig()
    console.log('[LoraRandomizerWidget] Serializing config:', config)
    return config
  }

  // Handle external value updates (e.g., loading workflow, paste)
  props.widget.onSetValue = (v) => {
    console.log('[LoraRandomizerWidget] Restoring from config:', v)
    state.restoreFromConfig(v as RandomizerConfig)
  }

  // Restore from saved value
  if (props.widget.value) {
    console.log('[LoraRandomizerWidget] Restoring from saved value:', props.widget.value)
    state.restoreFromConfig(props.widget.value as RandomizerConfig)
  }
})
</script>

<style scoped>
.lora-randomizer-widget {
  padding: 12px;
  background: rgba(40, 44, 52, 0.6);
  border-radius: 4px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}
</style>
