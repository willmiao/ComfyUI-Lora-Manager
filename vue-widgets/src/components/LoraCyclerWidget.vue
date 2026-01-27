<template>
  <div class="lora-cycler-widget">
    <LoraCyclerSettingsView
      :current-index="state.currentIndex.value"
      :total-count="state.totalCount.value"
      :current-lora-name="state.currentLoraName.value"
      :current-lora-filename="state.currentLoraFilename.value"
      :model-strength="state.modelStrength.value"
      :clip-strength="state.clipStrength.value"
      :use-custom-clip-range="state.useCustomClipRange.value"
      :is-clip-strength-disabled="state.isClipStrengthDisabled.value"
      :is-loading="state.isLoading.value"
      @update:current-index="handleIndexUpdate"
      @update:model-strength="state.modelStrength.value = $event"
      @update:clip-strength="state.clipStrength.value = $event"
      @update:use-custom-clip-range="handleUseCustomClipRangeChange"
      @refresh="handleRefresh"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import LoraCyclerSettingsView from './lora-cycler/LoraCyclerSettingsView.vue'
import { useLoraCyclerState } from '../composables/useLoraCyclerState'
import type { ComponentWidget, CyclerConfig, LoraPoolConfig } from '../composables/types'

type CyclerWidget = ComponentWidget<CyclerConfig>

// Props
const props = defineProps<{
  widget: CyclerWidget
  node: { id: number; inputs?: any[]; widgets?: any[]; graph?: any }
}>()

// State management
const state = useLoraCyclerState(props.widget)

// Symbol to track if the widget has been executed at least once
const HAS_EXECUTED = Symbol('HAS_EXECUTED')

// Track last known pool config hash
const lastPoolConfigHash = ref('')

// Track if component is mounted
const isMounted = ref(false)

// Get pool config from connected node
const getPoolConfig = (): LoraPoolConfig | null => {
  // Check if getPoolConfig method exists on node (added by main.ts)
  if ((props.node as any).getPoolConfig) {
    return (props.node as any).getPoolConfig()
  }
  return null
}

// Handle index update from user
const handleIndexUpdate = async (newIndex: number) => {
  state.setIndex(newIndex)

  // Refresh list to update current LoRA display
  try {
    const poolConfig = getPoolConfig()
    const loraList = await state.fetchCyclerList(poolConfig)

    if (loraList.length > 0 && newIndex > 0 && newIndex <= loraList.length) {
      const currentLora = loraList[newIndex - 1]
      if (currentLora) {
        state.currentLoraName.value = currentLora.file_name
        state.currentLoraFilename.value = currentLora.file_name
      }
    }
  } catch (error) {
    console.error('[LoraCyclerWidget] Error updating index:', error)
  }
}

// Handle use custom clip range toggle
const handleUseCustomClipRangeChange = (newValue: boolean) => {
  state.useCustomClipRange.value = newValue
  // When toggling off, sync clip strength to model strength
  if (!newValue) {
    state.clipStrength.value = state.modelStrength.value
  }
}

// Handle refresh button click
const handleRefresh = async () => {
  try {
    const poolConfig = getPoolConfig()
    await state.refreshList(poolConfig)
  } catch (error) {
    console.error('[LoraCyclerWidget] Error refreshing:', error)
  }
}

// Check for pool config changes
const checkPoolConfigChanges = async () => {
  if (!isMounted.value) return

  const poolConfig = getPoolConfig()
  const newHash = state.hashPoolConfig(poolConfig)

  if (newHash !== lastPoolConfigHash.value) {
    console.log('[LoraCyclerWidget] Pool config changed, refreshing list')
    lastPoolConfigHash.value = newHash
    try {
      await state.refreshList(poolConfig)
    } catch (error) {
      console.error('[LoraCyclerWidget] Error on pool config change:', error)
    }
  }
}

// Lifecycle
onMounted(async () => {
  // Setup callback for external value updates (e.g., workflow load, undo/redo)
  // ComfyUI calls this automatically after setValue() in domWidget.ts
  props.widget.callback = (v: CyclerConfig) => {
    if (v) {
      state.restoreFromConfig(v)
    }
  }

  // Restore from saved value if workflow was already loaded
  if (props.widget.value) {
    state.restoreFromConfig(props.widget.value)
  }

  // Add beforeQueued hook to handle index shifting for batch queue synchronization
  // This ensures each execution uses a different LoRA in the cycle
  ;(props.widget as any).beforeQueued = () => {
    if ((props.widget as any)[HAS_EXECUTED]) {
      // After first execution: shift indices (previous next_index becomes execution_index)
      state.generateNextIndex()
    } else {
      // First execution: just initialize next_index (execution_index stays null)
      // This means first execution uses current_index from widget
      state.initializeNextIndex()
      ;(props.widget as any)[HAS_EXECUTED] = true
    }

    // Update the widget value so the indices are included in the serialized config
    props.widget.value = state.buildConfig()
  }

  // Mark component as mounted
  isMounted.value = true

  // Initial load
  try {
    const poolConfig = getPoolConfig()
    lastPoolConfigHash.value = state.hashPoolConfig(poolConfig)
    await state.refreshList(poolConfig)
  } catch (error) {
    console.error('[LoraCyclerWidget] Error on initial load:', error)
  }

  // Override onExecuted to handle backend UI updates
  const originalOnExecuted = (props.node as any).onExecuted?.bind(props.node)

  ;(props.node as any).onExecuted = function(output: any) {
    console.log("[LoraCyclerWidget] Node executed with output:", output)

    // Update state from backend response (values are wrapped in arrays)
    if (output?.next_index !== undefined) {
      const val = Array.isArray(output.next_index) ? output.next_index[0] : output.next_index
      state.currentIndex.value = val
    }
    if (output?.total_count !== undefined) {
      const val = Array.isArray(output.total_count) ? output.total_count[0] : output.total_count
      state.totalCount.value = val
    }
    if (output?.current_lora_name !== undefined) {
      const val = Array.isArray(output.current_lora_name) ? output.current_lora_name[0] : output.current_lora_name
      state.currentLoraName.value = val
    }
    if (output?.current_lora_filename !== undefined) {
      const val = Array.isArray(output.current_lora_filename) ? output.current_lora_filename[0] : output.current_lora_filename
      state.currentLoraFilename.value = val
    }
    if (output?.next_lora_name !== undefined) {
      const val = Array.isArray(output.next_lora_name) ? output.next_lora_name[0] : output.next_lora_name
      state.currentLoraName.value = val
    }
    if (output?.next_lora_filename !== undefined) {
      const val = Array.isArray(output.next_lora_filename) ? output.next_lora_filename[0] : output.next_lora_filename
      state.currentLoraFilename.value = val
    }

    // Call original onExecuted if it exists
    if (originalOnExecuted) {
      return originalOnExecuted(output)
    }
  }

  // Watch for connection changes by polling (since ComfyUI doesn't provide connection events)
  const checkInterval = setInterval(checkPoolConfigChanges, 1000)

  // Cleanup on unmount (handled by Vue's effect scope)
  ;(props.widget as any).onRemoveCleanup = () => {
    clearInterval(checkInterval)
  }
})
</script>

<style scoped>
.lora-cycler-widget {
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
