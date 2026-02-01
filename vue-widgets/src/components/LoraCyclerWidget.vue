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
      :repeat-count="state.repeatCount.value"
      :repeat-used="state.displayRepeatUsed.value"
      :is-paused="state.isPaused.value"
      :is-pause-disabled="hasQueuedPrompts"
      :is-workflow-executing="state.isWorkflowExecuting.value"
      :executing-repeat-step="state.executingRepeatStep.value"
      @update:current-index="handleIndexUpdate"
      @update:model-strength="state.modelStrength.value = $event"
      @update:clip-strength="state.clipStrength.value = $event"
      @update:use-custom-clip-range="handleUseCustomClipRangeChange"
      @update:repeat-count="handleRepeatCountChange"
      @toggle-pause="handleTogglePause"
      @reset-index="handleResetIndex"
      @open-lora-selector="isModalOpen = true"
    />

    <LoraListModal
      :visible="isModalOpen"
      :lora-list="cachedLoraList"
      :current-index="state.currentIndex.value"
      @close="isModalOpen = false"
      @select="handleModalSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import LoraCyclerSettingsView from './lora-cycler/LoraCyclerSettingsView.vue'
import LoraListModal from './lora-cycler/LoraListModal.vue'
import { useLoraCyclerState } from '../composables/useLoraCyclerState'
import type { ComponentWidget, CyclerConfig, LoraPoolConfig, LoraItem } from '../composables/types'

type CyclerWidget = ComponentWidget<CyclerConfig>

// Props
const props = defineProps<{
  widget: CyclerWidget
  node: { id: number; inputs?: any[]; widgets?: any[]; graph?: any }
  api?: any  // ComfyUI API for execution events
}>()

// State management
const state = useLoraCyclerState(props.widget)

// Symbol to track if the widget has been executed at least once
const HAS_EXECUTED = Symbol('HAS_EXECUTED')

// Execution context queue for batch queue synchronization
// In batch queue mode, all beforeQueued calls happen BEFORE any onExecuted calls,
// so we need to snapshot the state at queue time and replay it during execution
interface ExecutionContext {
  isPaused: boolean
  repeatUsed: number
  repeatCount: number
  shouldAdvanceDisplay: boolean
  displayRepeatUsed: number  // Value to show in UI after completion
}
const executionQueue: ExecutionContext[] = []

// Reactive flag to track if there are queued prompts (for disabling pause button)
const hasQueuedPrompts = ref(false)

// Track pending executions for batch queue support (deferred UI updates)
// Uses FIFO order since executions are processed in the order they were queued
interface PendingExecution {
  repeatUsed: number
  repeatCount: number
  shouldAdvanceDisplay: boolean
  displayRepeatUsed: number  // Value to show in UI after completion
  output?: {
    nextIndex: number
    nextLoraName: string
    nextLoraFilename: string
    currentLoraName: string
    currentLoraFilename: string
  }
}
const pendingExecutions: PendingExecution[] = []

// Track last known pool config hash
const lastPoolConfigHash = ref('')

// Track if component is mounted
const isMounted = ref(false)

// Modal state
const isModalOpen = ref(false)

// Cache for LoRA list (used by modal)
const cachedLoraList = ref<LoraItem[]>([])

// Get pool config from connected node
const getPoolConfig = (): LoraPoolConfig | null => {
  // Check if getPoolConfig method exists on node (added by main.ts)
  if ((props.node as any).getPoolConfig) {
    return (props.node as any).getPoolConfig()
  }
  return null
}

// Update display from LoRA list and index
const updateDisplayFromLoraList = (loraList: LoraItem[], index: number) => {
  if (loraList.length > 0 && index > 0 && index <= loraList.length) {
    const currentLora = loraList[index - 1]
    if (currentLora) {
      state.currentLoraName.value = currentLora.file_name
      state.currentLoraFilename.value = currentLora.file_name
    }
  }
}

// Handle index update from user
const handleIndexUpdate = async (newIndex: number) => {
  // Reset execution state when user manually changes index
  // This ensures the next execution starts from the user-set index
  ;(props.widget as any)[HAS_EXECUTED] = false
  state.executionIndex.value = null
  state.nextIndex.value = null

  // Clear execution queue since user is manually changing state
  executionQueue.length = 0
  hasQueuedPrompts.value = false

  state.setIndex(newIndex)

  // Refresh list to update current LoRA display
  try {
    const poolConfig = getPoolConfig()
    const loraList = await state.fetchCyclerList(poolConfig)
    cachedLoraList.value = loraList
    updateDisplayFromLoraList(loraList, newIndex)
  } catch (error) {
    console.error('[LoraCyclerWidget] Error updating index:', error)
  }
}

// Handle LoRA selection from modal
const handleModalSelect = (index: number) => {
  handleIndexUpdate(index)
}

// Handle use custom clip range toggle
const handleUseCustomClipRangeChange = (newValue: boolean) => {
  state.useCustomClipRange.value = newValue
  // When toggling off, sync clip strength to model strength
  if (!newValue) {
    state.clipStrength.value = state.modelStrength.value
  }
}

// Handle repeat count change
const handleRepeatCountChange = (newValue: number) => {
  state.repeatCount.value = newValue
  // Reset repeatUsed when changing repeat count
  state.repeatUsed.value = 0
  state.displayRepeatUsed.value = 0
}

// Handle pause toggle
const handleTogglePause = () => {
  state.togglePause()
}

// Handle reset index
const handleResetIndex = async () => {
  // Reset execution state
  ;(props.widget as any)[HAS_EXECUTED] = false
  state.executionIndex.value = null
  state.nextIndex.value = null

  // Clear execution queue since user is resetting state
  executionQueue.length = 0
  hasQueuedPrompts.value = false

  // Reset index and repeat state
  state.resetIndex()

  // Refresh list to update current LoRA display
  try {
    const poolConfig = getPoolConfig()
    const loraList = await state.fetchCyclerList(poolConfig)
    cachedLoraList.value = loraList
    updateDisplayFromLoraList(loraList, 1)
  } catch (error) {
    console.error('[LoraCyclerWidget] Error resetting index:', error)
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
      // Update cached list when pool config changes
      const loraList = await state.fetchCyclerList(poolConfig)
      cachedLoraList.value = loraList
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
  // Now with support for repeat count and pause features
  //
  // IMPORTANT: In batch queue mode, ALL beforeQueued calls happen BEFORE any execution.
  // We push an "execution context" snapshot to a queue so that onExecuted can use the
  // correct state values that were captured at queue time (not the live state).
  ;(props.widget as any).beforeQueued = () => {
    if (state.isPaused.value) {
      // When paused: use current index, don't advance, don't count toward repeat limit
      // Push context indicating this execution should NOT advance display
      executionQueue.push({
        isPaused: true,
        repeatUsed: state.repeatUsed.value,
        repeatCount: state.repeatCount.value,
        shouldAdvanceDisplay: false,
        displayRepeatUsed: state.displayRepeatUsed.value  // Keep current display value when paused
      })
      hasQueuedPrompts.value = true
      // CRITICAL: Clear execution_index when paused to force backend to use current_index
      // This ensures paused executions use the same LoRA regardless of any
      // execution_index set by previous non-paused beforeQueued calls
      const pausedConfig = state.buildConfig()
      pausedConfig.execution_index = null
      props.widget.value = pausedConfig
      return
    }

    if ((props.widget as any)[HAS_EXECUTED]) {
      // After first execution: check repeat logic
      if (state.repeatUsed.value < state.repeatCount.value) {
        // Still repeating: increment repeatUsed, use same index
        state.repeatUsed.value++
      } else {
        // Repeat complete: reset repeatUsed to 1, advance to next index
        state.repeatUsed.value = 1
        state.generateNextIndex()
      }
    } else {
      // First execution: initialize
      state.repeatUsed.value = 1
      state.initializeNextIndex()
      ;(props.widget as any)[HAS_EXECUTED] = true
    }

    // Determine if this execution should advance the display
    // (only when repeat cycle is complete for this queued item)
    const shouldAdvanceDisplay = state.repeatUsed.value >= state.repeatCount.value

    // Calculate the display value to show after this execution completes
    // When advancing to a new LoRA: reset to 0 (fresh start for new LoRA)
    // When repeating same LoRA: show current repeat step
    const displayRepeatUsed = shouldAdvanceDisplay ? 0 : state.repeatUsed.value

    // Push execution context snapshot to queue
    executionQueue.push({
      isPaused: false,
      repeatUsed: state.repeatUsed.value,
      repeatCount: state.repeatCount.value,
      shouldAdvanceDisplay,
      displayRepeatUsed
    })
    hasQueuedPrompts.value = true

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
    // Cache the initial LoRA list for modal
    const loraList = await state.fetchCyclerList(poolConfig)
    cachedLoraList.value = loraList
  } catch (error) {
    console.error('[LoraCyclerWidget] Error on initial load:', error)
  }

  // Override onExecuted to handle backend UI updates
  // This defers the UI update until workflow completes (via API events)
  const originalOnExecuted = (props.node as any).onExecuted?.bind(props.node)

  ;(props.node as any).onExecuted = function(output: any) {
    console.log("[LoraCyclerWidget] Node executed with output:", output)

    // Pop execution context from queue (FIFO order)
    const context = executionQueue.shift()
    hasQueuedPrompts.value = executionQueue.length > 0

    // Determine if we should advance the display index
    const shouldAdvanceDisplay = context
      ? context.shouldAdvanceDisplay
      : (!state.isPaused.value && state.repeatUsed.value >= state.repeatCount.value)

    // Extract output values
    const nextIndex = output?.next_index !== undefined
      ? (Array.isArray(output.next_index) ? output.next_index[0] : output.next_index)
      : state.currentIndex.value
    const nextLoraName = output?.next_lora_name !== undefined
      ? (Array.isArray(output.next_lora_name) ? output.next_lora_name[0] : output.next_lora_name)
      : ''
    const nextLoraFilename = output?.next_lora_filename !== undefined
      ? (Array.isArray(output.next_lora_filename) ? output.next_lora_filename[0] : output.next_lora_filename)
      : ''
    const currentLoraName = output?.current_lora_name !== undefined
      ? (Array.isArray(output.current_lora_name) ? output.current_lora_name[0] : output.current_lora_name)
      : ''
    const currentLoraFilename = output?.current_lora_filename !== undefined
      ? (Array.isArray(output.current_lora_filename) ? output.current_lora_filename[0] : output.current_lora_filename)
      : ''

    // Update total count immediately (doesn't need to wait for workflow completion)
    if (output?.total_count !== undefined) {
      const val = Array.isArray(output.total_count) ? output.total_count[0] : output.total_count
      state.totalCount.value = val
    }

    // Store pending update (will be applied on workflow completion)
    if (context) {
      pendingExecutions.push({
        repeatUsed: context.repeatUsed,
        repeatCount: context.repeatCount,
        shouldAdvanceDisplay,
        displayRepeatUsed: context.displayRepeatUsed,
        output: {
          nextIndex,
          nextLoraName,
          nextLoraFilename,
          currentLoraName,
          currentLoraFilename
        }
      })

      // Update visual feedback state (don't update displayRepeatUsed yet - wait for workflow completion)
      state.executingRepeatStep.value = context.repeatUsed
      state.isWorkflowExecuting.value = true
    }

    // Call original onExecuted if it exists
    if (originalOnExecuted) {
      return originalOnExecuted(output)
    }
  }

  // Set up execution tracking via API events
  if (props.api) {
    // Handle workflow completion events using FIFO order
    // Note: The 'executing' event doesn't contain prompt_id (only node ID as string),
    // so we use FIFO order instead of prompt_id matching since executions are processed
    // in the order they were queued
    const handleExecutionComplete = () => {
      // Process the first pending execution (FIFO order)
      if (pendingExecutions.length === 0) {
        return
      }

      const pending = pendingExecutions.shift()!

      // Apply UI update now that workflow is complete
      // Update repeat display (deferred like index updates)
      state.displayRepeatUsed.value = pending.displayRepeatUsed

      if (pending.output) {
        if (pending.shouldAdvanceDisplay) {
          state.currentIndex.value = pending.output.nextIndex
          state.currentLoraName.value = pending.output.nextLoraName
          state.currentLoraFilename.value = pending.output.nextLoraFilename
        } else {
          // When not advancing, show current LoRA info
          state.currentLoraName.value = pending.output.currentLoraName
          state.currentLoraFilename.value = pending.output.currentLoraFilename
        }
      }

      // Reset visual feedback if no more pending
      if (pendingExecutions.length === 0) {
        state.isWorkflowExecuting.value = false
        state.executingRepeatStep.value = 0
      }
    }

    props.api.addEventListener('execution_success', handleExecutionComplete)
    props.api.addEventListener('execution_error', handleExecutionComplete)
    props.api.addEventListener('execution_interrupted', handleExecutionComplete)

    // Store cleanup function for API listeners
    const apiCleanup = () => {
      props.api.removeEventListener('execution_success', handleExecutionComplete)
      props.api.removeEventListener('execution_error', handleExecutionComplete)
      props.api.removeEventListener('execution_interrupted', handleExecutionComplete)
    }

    // Extend existing cleanup
    const existingCleanup = (props.widget as any).onRemoveCleanup
    ;(props.widget as any).onRemoveCleanup = () => {
      existingCleanup?.()
      apiCleanup()
    }
  }

  // Watch for connection changes by polling (since ComfyUI doesn't provide connection events)
  const checkInterval = setInterval(checkPoolConfigChanges, 1000)

  // Cleanup on unmount (handled by Vue's effect scope)
  const existingCleanupForInterval = (props.widget as any).onRemoveCleanup
  ;(props.widget as any).onRemoveCleanup = () => {
    existingCleanupForInterval?.()
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
