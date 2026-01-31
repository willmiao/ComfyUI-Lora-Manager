/**
 * Integration tests for batch queue execution scenarios
 *
 * These tests simulate ComfyUI's execution modes to verify correct LoRA cycling behavior.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useLoraCyclerState } from '@/composables/useLoraCyclerState'
import type { CyclerConfig } from '@/composables/types'
import {
  createMockWidget,
  createMockCyclerConfig,
  createMockLoraList,
  createMockPoolConfig
} from '../fixtures/mockConfigs'
import { setupFetchMock, resetFetchMock } from '../setup'
import { BatchQueueSimulator, IndexTracker } from '../utils/BatchQueueSimulator'

/**
 * Creates a test harness that mimics the LoraCyclerWidget's behavior
 */
function createTestHarness(options: {
  totalCount?: number
  initialIndex?: number
  repeatCount?: number
  isPaused?: boolean
} = {}) {
  const {
    totalCount = 5,
    initialIndex = 1,
    repeatCount = 1,
    isPaused = false
  } = options

  const widget = createMockWidget() as any
  const state = useLoraCyclerState(widget)

  // Initialize state
  state.totalCount.value = totalCount
  state.currentIndex.value = initialIndex
  state.repeatCount.value = repeatCount
  state.isPaused.value = isPaused

  // Track if first execution
  const HAS_EXECUTED = Symbol('HAS_EXECUTED')
  widget[HAS_EXECUTED] = false

  // Execution queue for batch synchronization
  interface ExecutionContext {
    isPaused: boolean
    repeatUsed: number
    repeatCount: number
    shouldAdvanceDisplay: boolean
    displayRepeatUsed: number  // Value to show in UI after completion
  }
  const executionQueue: ExecutionContext[] = []

  // beforeQueued hook (mirrors LoraCyclerWidget.vue logic)
  widget.beforeQueued = () => {
    if (state.isPaused.value) {
      executionQueue.push({
        isPaused: true,
        repeatUsed: state.repeatUsed.value,
        repeatCount: state.repeatCount.value,
        shouldAdvanceDisplay: false,
        displayRepeatUsed: state.displayRepeatUsed.value  // Keep current display value when paused
      })
      // CRITICAL: Clear execution_index when paused to force backend to use current_index
      const pausedConfig = state.buildConfig()
      pausedConfig.execution_index = null
      widget.value = pausedConfig
      return
    }

    if (widget[HAS_EXECUTED]) {
      if (state.repeatUsed.value < state.repeatCount.value) {
        state.repeatUsed.value++
      } else {
        state.repeatUsed.value = 1
        state.generateNextIndex()
      }
    } else {
      state.repeatUsed.value = 1
      state.initializeNextIndex()
      widget[HAS_EXECUTED] = true
    }

    const shouldAdvanceDisplay = state.repeatUsed.value >= state.repeatCount.value
    // Calculate the display value to show after this execution completes
    // When advancing to a new LoRA: reset to 0 (fresh start for new LoRA)
    // When repeating same LoRA: show current repeat step
    const displayRepeatUsed = shouldAdvanceDisplay ? 0 : state.repeatUsed.value

    executionQueue.push({
      isPaused: false,
      repeatUsed: state.repeatUsed.value,
      repeatCount: state.repeatCount.value,
      shouldAdvanceDisplay,
      displayRepeatUsed
    })

    widget.value = state.buildConfig()
  }

  // Mock node with onExecuted
  const node = {
    id: 1,
    onExecuted: (output: any) => {
      const context = executionQueue.shift()

      const shouldAdvanceDisplay = context
        ? context.shouldAdvanceDisplay
        : (!state.isPaused.value && state.repeatUsed.value >= state.repeatCount.value)

      // Update displayRepeatUsed (deferred like index updates)
      if (context) {
        state.displayRepeatUsed.value = context.displayRepeatUsed
      }

      if (shouldAdvanceDisplay && output?.next_index !== undefined) {
        const val = Array.isArray(output.next_index) ? output.next_index[0] : output.next_index
        state.currentIndex.value = val
      }
      if (output?.total_count !== undefined) {
        const val = Array.isArray(output.total_count) ? output.total_count[0] : output.total_count
        state.totalCount.value = val
      }
      if (shouldAdvanceDisplay) {
        if (output?.next_lora_name !== undefined) {
          const val = Array.isArray(output.next_lora_name) ? output.next_lora_name[0] : output.next_lora_name
          state.currentLoraName.value = val
        }
        if (output?.next_lora_filename !== undefined) {
          const val = Array.isArray(output.next_lora_filename) ? output.next_lora_filename[0] : output.next_lora_filename
          state.currentLoraFilename.value = val
        }
      }
    }
  }

  // Reset execution state (mimics manual index change)
  const resetExecutionState = () => {
    widget[HAS_EXECUTED] = false
    state.executionIndex.value = null
    state.nextIndex.value = null
    executionQueue.length = 0
  }

  return {
    widget,
    state,
    node,
    executionQueue,
    resetExecutionState,
    getConfig: () => state.buildConfig(),
    HAS_EXECUTED
  }
}

describe('Batch Queue Integration Tests', () => {
  beforeEach(() => {
    resetFetchMock()
  })

  describe('Basic Cycling', () => {
    it('should cycle through N LoRAs in batch of N (batch queue mode)', async () => {
      const harness = createTestHarness({ totalCount: 3 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      // Simulate batch queue of 3 prompts
      await simulator.runBatchQueue(
        3,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // After cycling through all 3, currentIndex should wrap back to 1
      // First execution: index 1, next becomes 2
      // Second execution: index 2, next becomes 3
      // Third execution: index 3, next becomes 1
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should cycle through N LoRAs in batch of N (sequential mode)', async () => {
      const harness = createTestHarness({ totalCount: 3 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      // Simulate sequential execution of 3 prompts
      await simulator.runSequential(
        3,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Same result as batch mode
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should handle partial cycle (batch of 2 in pool of 5)', async () => {
      const harness = createTestHarness({ totalCount: 5, initialIndex: 1 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      await simulator.runBatchQueue(
        2,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // After 2 executions starting from 1: 1 -> 2 -> 3
      expect(harness.state.currentIndex.value).toBe(3)
    })
  })

  describe('Repeat Functionality', () => {
    it('should repeat each LoRA repeatCount times', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 2 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      // With repeatCount=2, need 6 executions to cycle through 3 LoRAs
      await simulator.runBatchQueue(
        6,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Should have cycled back to beginning
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should track repeatUsed correctly during batch', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 3 })

      // First beforeQueued: repeatUsed = 1
      harness.widget.beforeQueued()
      expect(harness.state.repeatUsed.value).toBe(1)

      // Second beforeQueued: repeatUsed = 2
      harness.widget.beforeQueued()
      expect(harness.state.repeatUsed.value).toBe(2)

      // Third beforeQueued: repeatUsed = 3 (will advance on next)
      harness.widget.beforeQueued()
      expect(harness.state.repeatUsed.value).toBe(3)

      // Fourth beforeQueued: repeatUsed resets to 1, index advances
      harness.widget.beforeQueued()
      expect(harness.state.repeatUsed.value).toBe(1)
      expect(harness.state.nextIndex.value).toBe(3) // Advanced from 2 to 3
    })

    it('should not advance display until repeat cycle completes', async () => {
      const harness = createTestHarness({ totalCount: 5, repeatCount: 2 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // First execution: repeatUsed=1 < repeatCount=2, shouldAdvanceDisplay=false
      // Second execution: repeatUsed=2 >= repeatCount=2, shouldAdvanceDisplay=true

      const indexHistory: number[] = []

      // Override onExecuted to track index changes
      const originalOnExecuted = harness.node.onExecuted
      harness.node.onExecuted = (output: any) => {
        originalOnExecuted(output)
        indexHistory.push(harness.state.currentIndex.value)
      }

      await simulator.runBatchQueue(
        4,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Index should only change on 2nd and 4th execution
      // Starting at 1: stay 1, advance to 2, stay 2, advance to 3
      expect(indexHistory).toEqual([1, 2, 2, 3])
    })

    it('should defer displayRepeatUsed updates until workflow completion', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 3 })

      // Initial state
      expect(harness.state.displayRepeatUsed.value).toBe(0)

      // Queue 3 executions in batch mode (all beforeQueued before any onExecuted)
      harness.widget.beforeQueued()  // repeatUsed = 1
      harness.widget.beforeQueued()  // repeatUsed = 2
      harness.widget.beforeQueued()  // repeatUsed = 3

      // displayRepeatUsed should NOT have changed yet (still 0)
      // because no onExecuted has been called
      expect(harness.state.displayRepeatUsed.value).toBe(0)

      // Now simulate workflow completions
      harness.node.onExecuted({ next_index: 1 })
      expect(harness.state.displayRepeatUsed.value).toBe(1)

      harness.node.onExecuted({ next_index: 1 })
      expect(harness.state.displayRepeatUsed.value).toBe(2)

      harness.node.onExecuted({ next_index: 2 })
      // After completing repeat cycle, displayRepeatUsed resets to 0
      expect(harness.state.displayRepeatUsed.value).toBe(0)
    })

    it('should reset displayRepeatUsed to 0 when advancing to new LoRA', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 2 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      const displayHistory: number[] = []

      const originalOnExecuted = harness.node.onExecuted
      harness.node.onExecuted = (output: any) => {
        originalOnExecuted(output)
        displayHistory.push(harness.state.displayRepeatUsed.value)
      }

      // Run 4 executions: 2 repeats of LoRA 1, 2 repeats of LoRA 2
      await simulator.runBatchQueue(
        4,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // displayRepeatUsed should show:
      // 1st exec: 1 (first repeat of LoRA 1)
      // 2nd exec: 0 (complete, reset for next LoRA)
      // 3rd exec: 1 (first repeat of LoRA 2)
      // 4th exec: 0 (complete, reset for next LoRA)
      expect(displayHistory).toEqual([1, 0, 1, 0])
    })

    it('should show current repeat step when not advancing', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 4 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      const displayHistory: number[] = []

      const originalOnExecuted = harness.node.onExecuted
      harness.node.onExecuted = (output: any) => {
        originalOnExecuted(output)
        displayHistory.push(harness.state.displayRepeatUsed.value)
      }

      // Run 4 executions: all 4 repeats of the same LoRA
      await simulator.runBatchQueue(
        4,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // displayRepeatUsed should show:
      // 1st exec: 1 (repeat 1/4, not advancing)
      // 2nd exec: 2 (repeat 2/4, not advancing)
      // 3rd exec: 3 (repeat 3/4, not advancing)
      // 4th exec: 0 (repeat 4/4, complete, reset for next LoRA)
      expect(displayHistory).toEqual([1, 2, 3, 0])
    })
  })

  describe('Pause Functionality', () => {
    it('should maintain index when paused', async () => {
      const harness = createTestHarness({ totalCount: 5, isPaused: true })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      await simulator.runBatchQueue(
        3,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Index should not advance when paused
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should not count paused executions toward repeat limit', async () => {
      const harness = createTestHarness({ totalCount: 5, repeatCount: 2 })

      // Run 2 executions while paused
      harness.state.isPaused.value = true
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()

      // repeatUsed should still be 0 (paused executions don't count)
      expect(harness.state.repeatUsed.value).toBe(0)

      // Unpause and run
      harness.state.isPaused.value = false
      harness.widget.beforeQueued()
      expect(harness.state.repeatUsed.value).toBe(1)
    })

    it('should preserve displayRepeatUsed when paused', async () => {
      const harness = createTestHarness({ totalCount: 5, repeatCount: 3 })

      // Run one execution to set displayRepeatUsed
      harness.widget.beforeQueued()
      harness.node.onExecuted({ next_index: 1 })
      expect(harness.state.displayRepeatUsed.value).toBe(1)

      // Pause
      harness.state.isPaused.value = true

      // Queue and execute while paused
      harness.widget.beforeQueued()
      harness.node.onExecuted({ next_index: 1 })

      // displayRepeatUsed should remain at 1 (paused executions don't change it)
      expect(harness.state.displayRepeatUsed.value).toBe(1)

      // Queue another paused execution
      harness.widget.beforeQueued()
      harness.node.onExecuted({ next_index: 1 })

      // Still should be 1
      expect(harness.state.displayRepeatUsed.value).toBe(1)
    })

    it('should use same LoRA when pause is toggled mid-batch', async () => {
      // This tests the critical bug scenario:
      // 1. User queues multiple prompts (not paused)
      // 2. All beforeQueued calls complete, each advancing execution_index
      // 3. User clicks pause
      // 4. onExecuted starts firing - paused executions should use current_index, not execution_index
      const harness = createTestHarness({ totalCount: 5 })

      // Queue first prompt (not paused) - this sets up execution_index
      harness.widget.beforeQueued()
      const config1 = harness.getConfig()
      expect(config1.execution_index).toBeNull() // First execution uses current_index

      // User clicks pause mid-batch
      harness.state.isPaused.value = true

      // Queue subsequent prompts while paused
      harness.widget.beforeQueued()
      const config2 = harness.getConfig()
      // CRITICAL: execution_index should be null when paused to force backend to use current_index
      expect(config2.execution_index).toBeNull()

      harness.widget.beforeQueued()
      const config3 = harness.getConfig()
      expect(config3.execution_index).toBeNull()

      // Verify execution queue has correct context
      expect(harness.executionQueue.length).toBe(3)
      expect(harness.executionQueue[0].isPaused).toBe(false)
      expect(harness.executionQueue[1].isPaused).toBe(true)
      expect(harness.executionQueue[2].isPaused).toBe(true)
    })

    it('should have null execution_index in widget.value when paused even after non-paused queues', async () => {
      // More detailed test for the execution_index clearing behavior
      // This tests that widget.value (what backend receives) has null execution_index
      const harness = createTestHarness({ totalCount: 5 })

      // Queue 3 prompts while not paused
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()

      // Verify execution_index was set by non-paused queues in widget.value
      expect(harness.widget.value.execution_index).not.toBeNull()

      // User pauses
      harness.state.isPaused.value = true

      // Queue while paused - should clear execution_index in widget.value
      // This is the value that gets sent to the backend
      harness.widget.beforeQueued()
      expect(harness.widget.value.execution_index).toBeNull()

      // State's executionIndex may still have the old value (that's fine)
      // What matters is widget.value which is what the backend uses
    })

it('should have hasQueuedPrompts true when execution queue has items', async () => {
      // This tests the pause button disabled state
      const harness = createTestHarness({ totalCount: 5 })

      // Initially no queued prompts
      expect(harness.executionQueue.length).toBe(0)

      // Queue some prompts
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()

      // Execution queue should have items
      expect(harness.executionQueue.length).toBe(3)
    })

    it('should have empty execution queue after all executions complete', async () => {
      // This tests that pause button becomes enabled after executions complete
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // Run batch queue execution
      await simulator.runBatchQueue(
        3,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // After all executions, queue should be empty
      expect(harness.executionQueue.length).toBe(0)
    })

    it('should resume cycling after unpause', async () => {
      const harness = createTestHarness({ totalCount: 3, initialIndex: 2 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      // Execute once while not paused
      await simulator.runSingle(
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Pause
      harness.state.isPaused.value = true

      // Execute twice while paused
      await simulator.runBatchQueue(
        2,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Unpause and execute
      harness.state.isPaused.value = false

      await simulator.runSingle(
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Should continue from where it left off (index 3 -> 1)
      expect(harness.state.currentIndex.value).toBe(1)
    })
  })

  describe('Manual Index Change', () => {
    it('should reset execution state on manual index change', async () => {
      const harness = createTestHarness({ totalCount: 5 })

      // Execute a few times
      harness.widget.beforeQueued()
      harness.widget.beforeQueued()

      expect(harness.widget[harness.HAS_EXECUTED]).toBe(true)
      expect(harness.executionQueue.length).toBe(2)

      // User manually changes index (mimics handleIndexUpdate)
      harness.resetExecutionState()
      harness.state.setIndex(4)

      expect(harness.widget[harness.HAS_EXECUTED]).toBe(false)
      expect(harness.state.executionIndex.value).toBeNull()
      expect(harness.state.nextIndex.value).toBeNull()
      expect(harness.executionQueue.length).toBe(0)
    })

    it('should start fresh cycle from manual index', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // Execute twice starting from 1
      await simulator.runBatchQueue(
        2,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      expect(harness.state.currentIndex.value).toBe(3)

      // User manually sets index to 1
      harness.resetExecutionState()
      harness.state.setIndex(1)

      // Execute again - should start fresh from 1
      await simulator.runBatchQueue(
        2,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      expect(harness.state.currentIndex.value).toBe(3)
    })
  })

  describe('Execution Queue Mismatch', () => {
    it('should handle interrupted execution (queue > executed)', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // Queue 5 but only execute 2 (simulates cancel)
      await simulator.runInterrupted(
        5, // queued
        2, // executed
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // 3 contexts remain in queue
      expect(harness.executionQueue.length).toBe(3)

      // Index should reflect only the 2 executions that completed
      expect(harness.state.currentIndex.value).toBe(3)
    })

    it('should recover from mismatch on next manual index change', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // Create mismatch
      await simulator.runInterrupted(
        5,
        2,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      expect(harness.executionQueue.length).toBe(3)

      // Manual index change clears queue
      harness.resetExecutionState()
      harness.state.setIndex(1)

      expect(harness.executionQueue.length).toBe(0)

      // Can execute normally again
      await simulator.runSingle(
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      expect(harness.state.currentIndex.value).toBe(2)
    })
  })

  describe('Edge Cases', () => {
    it('should handle single item pool', async () => {
      const harness = createTestHarness({ totalCount: 1 })
      const simulator = new BatchQueueSimulator({ totalCount: 1 })

      await simulator.runBatchQueue(
        3,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // Should always stay at index 1
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should handle empty pool gracefully', async () => {
      const harness = createTestHarness({ totalCount: 0 })

      // beforeQueued should still work without errors
      expect(() => harness.widget.beforeQueued()).not.toThrow()
    })

    it('should handle rapid sequential executions', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      // Run 20 sequential executions
      await simulator.runSequential(
        20,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      // 20 % 5 = 0, so should wrap back to 1
      // But first execution uses index 1, so after 20 executions we're at 21 % 5 = 1
      expect(harness.state.currentIndex.value).toBe(1)
    })

    it('should preserve state consistency across many cycles', async () => {
      const harness = createTestHarness({ totalCount: 3, repeatCount: 2 })
      const simulator = new BatchQueueSimulator({ totalCount: 3 })

      // Run 100 executions in batches
      for (let batch = 0; batch < 10; batch++) {
        await simulator.runBatchQueue(
          10,
          {
            beforeQueued: () => harness.widget.beforeQueued(),
            onExecuted: (output) => harness.node.onExecuted(output)
          },
          () => harness.getConfig()
        )
      }

      // Verify state is still valid
      expect(harness.state.currentIndex.value).toBeGreaterThanOrEqual(1)
      expect(harness.state.currentIndex.value).toBeLessThanOrEqual(3)
      expect(harness.state.repeatUsed.value).toBeGreaterThanOrEqual(1)
      expect(harness.state.repeatUsed.value).toBeLessThanOrEqual(2)
      expect(harness.executionQueue.length).toBe(0)
    })
  })

  describe('Invariant Assertions', () => {
    it('should always have valid index (1 <= currentIndex <= totalCount)', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      const checkInvariant = () => {
        const { currentIndex, totalCount } = harness.state
        if (totalCount.value > 0) {
          expect(currentIndex.value).toBeGreaterThanOrEqual(1)
          expect(currentIndex.value).toBeLessThanOrEqual(totalCount.value)
        }
      }

      // Override onExecuted to check invariant after each execution
      const originalOnExecuted = harness.node.onExecuted
      harness.node.onExecuted = (output: any) => {
        originalOnExecuted(output)
        checkInvariant()
      }

      await simulator.runBatchQueue(
        20,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )
    })

    it('should always have repeatUsed <= repeatCount', async () => {
      const harness = createTestHarness({ totalCount: 5, repeatCount: 3 })

      const checkInvariant = () => {
        expect(harness.state.repeatUsed.value).toBeLessThanOrEqual(harness.state.repeatCount.value)
      }

      // Check after each beforeQueued
      for (let i = 0; i < 20; i++) {
        harness.widget.beforeQueued()
        checkInvariant()
      }
    })

    it('should consume all execution contexts (queue empty after matching executions)', async () => {
      const harness = createTestHarness({ totalCount: 5 })
      const simulator = new BatchQueueSimulator({ totalCount: 5 })

      await simulator.runBatchQueue(
        7,
        {
          beforeQueued: () => harness.widget.beforeQueued(),
          onExecuted: (output) => harness.node.onExecuted(output)
        },
        () => harness.getConfig()
      )

      expect(harness.executionQueue.length).toBe(0)
    })
  })

  describe('Batch vs Sequential Mode Equivalence', () => {
    it('should produce same final state in both modes (basic cycle)', async () => {
      // Create two identical harnesses
      const batchHarness = createTestHarness({ totalCount: 5 })
      const seqHarness = createTestHarness({ totalCount: 5 })

      const batchSimulator = new BatchQueueSimulator({ totalCount: 5 })
      const seqSimulator = new BatchQueueSimulator({ totalCount: 5 })

      // Run same number of executions in different modes
      await batchSimulator.runBatchQueue(
        7,
        {
          beforeQueued: () => batchHarness.widget.beforeQueued(),
          onExecuted: (output) => batchHarness.node.onExecuted(output)
        },
        () => batchHarness.getConfig()
      )

      await seqSimulator.runSequential(
        7,
        {
          beforeQueued: () => seqHarness.widget.beforeQueued(),
          onExecuted: (output) => seqHarness.node.onExecuted(output)
        },
        () => seqHarness.getConfig()
      )

      // Final state should be identical
      expect(batchHarness.state.currentIndex.value).toBe(seqHarness.state.currentIndex.value)
      expect(batchHarness.state.repeatUsed.value).toBe(seqHarness.state.repeatUsed.value)
      expect(batchHarness.state.displayRepeatUsed.value).toBe(seqHarness.state.displayRepeatUsed.value)
    })

    it('should produce same final state in both modes (with repeat)', async () => {
      const batchHarness = createTestHarness({ totalCount: 3, repeatCount: 2 })
      const seqHarness = createTestHarness({ totalCount: 3, repeatCount: 2 })

      const batchSimulator = new BatchQueueSimulator({ totalCount: 3 })
      const seqSimulator = new BatchQueueSimulator({ totalCount: 3 })

      await batchSimulator.runBatchQueue(
        10,
        {
          beforeQueued: () => batchHarness.widget.beforeQueued(),
          onExecuted: (output) => batchHarness.node.onExecuted(output)
        },
        () => batchHarness.getConfig()
      )

      await seqSimulator.runSequential(
        10,
        {
          beforeQueued: () => seqHarness.widget.beforeQueued(),
          onExecuted: (output) => seqHarness.node.onExecuted(output)
        },
        () => seqHarness.getConfig()
      )

      expect(batchHarness.state.currentIndex.value).toBe(seqHarness.state.currentIndex.value)
      expect(batchHarness.state.repeatUsed.value).toBe(seqHarness.state.repeatUsed.value)
      expect(batchHarness.state.displayRepeatUsed.value).toBe(seqHarness.state.displayRepeatUsed.value)
    })
  })
})
